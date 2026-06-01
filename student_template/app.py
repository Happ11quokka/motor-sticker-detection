"""
Motor Sticker Detection API Server

이미지를 업로드하면 백그라운드에서 3개씩 그룹으로 분석합니다.
업로드 완료 후 /start-analysis로 분석을 시작합니다.
"""
import io
import csv
import shutil
import base64
import threading
from pathlib import Path
from datetime import datetime
from collections import deque

import uvicorn
import gradio as gr
from PIL import Image
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import config
from models import load_results, clear_results
from worker import image_queue, background_worker, chat_with_data, reanalyze_image

# 분석 상태 관리
analysis_state = {
    "is_analyzing": False,
    "worker_thread": None
}


# FastAPI 앱 생성
app = FastAPI(title="Motor Sticker Detection API")

# CORS 설정 (로컬 테스트용)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 최근 업로드된 이미지 버퍼 (디버깅용)
image_buffer = deque(maxlen=1000)


@app.get("/healthz")
def health_check():
    """서버 헬스체크 (Railway healthcheck)"""
    return {
        "status": "ok",
        "service": "Motor Sticker Detection API",
        "version": "1.0.0"
    }


# 큐 추가 / 워커 시작 헬퍼 (FastAPI 엔드포인트와 Gradio 버튼이 공유)
def _enqueue(filename: str, file_path) -> None:
    """이미지 메타데이터를 분석 큐에 추가."""
    image_info = {
        "filename": filename,
        "path": str(file_path),
        "upload_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }
    image_queue.put(image_info)
    image_buffer.append(image_info)
    print(f"[큐 추가] {filename} | 큐 크기: {image_queue.qsize()}")


def _queue_image(src, original_name: str) -> str:
    """기존 파일(src)을 UPLOAD_DIR로 복사한 뒤 큐에 추가. 저장 파일명 반환."""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
    filename = f"{timestamp}_{original_name}"
    dest = config.UPLOAD_DIR / filename
    shutil.copy(src, dest)
    _enqueue(filename, dest)
    return filename


def ensure_worker_started():
    """백그라운드 분석 워커를 (한 번만) 시작한다. 멱등."""
    if analysis_state["is_analyzing"]:
        return

    analysis_state["is_analyzing"] = True

    def run_analysis():
        try:
            background_worker()
        finally:
            analysis_state["is_analyzing"] = False

    worker_thread = threading.Thread(target=run_analysis, daemon=True)
    worker_thread.start()
    analysis_state["worker_thread"] = worker_thread
    print("[워커] 백그라운드 분석 워커 시작됨")


@app.on_event("startup")
def _on_startup():
    """앱 시작 시 워커 자동 기동 (로컬/컨테이너 공통)."""
    ensure_worker_started()


@app.post("/api/upload")
async def upload_image(file: UploadFile = File(...)):
    """
    이미지를 받아서 저장하고 즉시 응답 (분석은 백그라운드에서)

    Args:
        file: 업로드된 이미지 파일

    Returns:
        업로드 성공 메시지 및 큐 상태
    """
    if not file.content_type or not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="이미지 파일만 업로드 가능합니다.")

    if file.size and file.size > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="파일 크기는 10MB 이하여야 합니다.")

    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{timestamp}_{file.filename}"
        file_path = config.UPLOAD_DIR / filename

        # 파일 저장
        with open(file_path, "wb") as f:
            content = await file.read()
            f.write(content)

        # 큐에 추가 (백그라운드 워커가 처리)
        _enqueue(filename, file_path)

        return {
            "success": True,
            "message": "이미지 업로드 완료",
            "filename": filename,
            "queue_size": image_queue.qsize()
        }

    except Exception as e:
        print(f"[업로드 오류] {str(e)}")
        raise HTTPException(status_code=500, detail=f"업로드 중 오류 발생: {str(e)}")


@app.post("/api/start-analysis")
async def start_analysis():
    """
    업로드된 이미지 분석 시작

    워커는 상시 실행되며 큐를 계속 소비한다. 이 엔드포인트는 워커가 떠 있는지
    확인하고(없으면 시작) 현재 큐 상태를 반환한다.
    """
    queue_size = image_queue.qsize()

    if queue_size == 0:
        return {
            "success": False,
            "message": "분석할 이미지가 없습니다.",
            "queue_size": 0
        }

    already = analysis_state["is_analyzing"]
    ensure_worker_started()

    print(f"\n{'='*50}")
    print(f"[분석] 큐에 있는 {queue_size}개 이미지 처리 중")
    print(f"{'='*50}\n")

    return {
        "success": True,
        "message": ("워커 실행 중 — 큐에 추가됨" if already else f"분석 시작됨 ({queue_size}개 이미지)"),
        "queue_size": queue_size
    }


@app.get("/api/analysis-status")
async def get_analysis_status():
    """분석 진행 상태 확인"""
    return {
        "is_analyzing": analysis_state["is_analyzing"],
        "queue_size": image_queue.qsize()
    }


def get_dashboard_data():
    """
    대시보드에 표시할 데이터 가져오기

    Returns:
        테이블 데이터, 통계, 개수
    """
    data = load_results()
    results = data.get("results", [])

    if not results:
        return [], {}, 0, 0, 0, 0

    # 스티커가 있는 결과만 필터링 (대시보드에는 스티커 확인된 것만 표시)
    sticker_results = [r for r in results if r.get("has_sticker")]

    # 최근 20개 결과 (스티커 있는 것만)
    recent_results = sticker_results[-20:][::-1]

    table_data = []
    for r in recent_results:
        table_data.append([
            r["id"],
            r["timestamp"],
            r["filename"],
            "O",  # 스티커 있는 것만 표시하므로 항상 O
            r.get("sticker_number", "-"),
            r.get("sticker_color", "-"),
            r.get("defect_level", "-")
        ])

    # 불량 수준별 통계 (스티커 있는 것만)
    normal = sum(1 for r in sticker_results if r.get("defect_level") == "정상")
    minor = sum(1 for r in sticker_results if r.get("defect_level") == "경미한 불량")
    severe = sum(1 for r in sticker_results if r.get("defect_level") == "심각한 불량")
    total = len(sticker_results)  # 스티커 있는 것만 카운트

    stats = {
        "정상 (초록색)": normal,
        "경미한 불량 (노란색)": minor,
        "심각한 불량 (빨간색)": severe
    }

    return table_data, stats, total, normal, minor, severe


def _img_data_uri(filename: str, max_size: int, quality: int = 80) -> str:
    """업로드 이미지를 지정 크기로 줄여 base64 data URI로 반환 (없거나 실패 시 빈 문자열)."""
    try:
        path = config.UPLOAD_DIR / filename
        if not path.exists():
            return ""
        with Image.open(path) as im:
            if im.mode not in ("RGB", "L"):
                im = im.convert("RGB")
            im.thumbnail((max_size, max_size))
            buf = io.BytesIO()
            im.save(buf, format="JPEG", quality=quality)
        b64 = base64.b64encode(buf.getvalue()).decode("ascii")
        return f"data:image/jpeg;base64,{b64}"
    except Exception as e:
        print(f"[썸네일 오류] {filename}: {e}")
        return ""


_RESULTS_CSS = """
<style>
.res-wrap{overflow-x:auto}
.res-tbl{border-collapse:collapse;width:100%;font-size:13px}
.res-tbl th,.res-tbl td{border:1px solid #e5e7eb;padding:6px 8px;text-align:center;vertical-align:middle}
.res-tbl th{background:#f9fafb;font-weight:600}
.res-tbl td.fname{text-align:left;font-family:ui-monospace,monospace;font-size:11px;color:#374151}
.res-thumb{width:36px;height:36px;object-fit:cover;border-radius:5px;border:1px solid #d1d5db;cursor:zoom-in;vertical-align:middle;margin-right:8px;transition:transform .12s}
.res-thumb:hover{transform:scale(1.15)}
.res-noimg{display:inline-block;width:36px;height:36px;border-radius:5px;background:#f3f4f6;color:#9ca3af;font-size:9px;line-height:36px;text-align:center;margin-right:8px;vertical-align:middle}
.lb{position:fixed;inset:0;background:rgba(0,0,0,.85);display:none;align-items:center;justify-content:center;z-index:9999}
.lb:target{display:flex}
.lb img{max-width:92vw;max-height:90vh;border-radius:8px;box-shadow:0 8px 40px rgba(0,0,0,.6)}
.lb .lb-bg{position:absolute;inset:0}
.lb .lb-x{position:absolute;top:14px;right:24px;color:#fff;font-size:36px;text-decoration:none;line-height:1}
.lb .lb-cap{position:absolute;bottom:16px;left:0;right:0;text-align:center;color:#e5e7eb;font-size:13px}
.badge{display:inline-block;padding:2px 9px;border-radius:11px;font-size:11px;font-weight:600;white-space:nowrap}
.b-normal{background:#dcfce7;color:#166534}.b-minor{background:#fef9c3;color:#854d0e}.b-severe{background:#fee2e2;color:#991b1b}
.cdot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;vertical-align:middle;border:1px solid rgba(0,0,0,.15)}
</style>
"""


def _badge(level: str) -> str:
    cls = {"정상": "b-normal", "경미한 불량": "b-minor", "심각한 불량": "b-severe"}.get(level, "")
    return f'<span class="badge {cls}">{level}</span>' if cls else (level or "-")


def _color_cell(color: str) -> str:
    hx = {"초록색": "#22c55e", "노란색": "#eab308", "빨간색": "#ef4444"}.get(color)
    dot = f'<span class="cdot" style="background:{hx}"></span>' if hx else ""
    return f'{dot}{color or "-"}'


def render_results_html(rows) -> str:
    """결과 행 리스트 → 썸네일 미리보기 + 클릭 확대(라이트박스) 포함 HTML 테이블."""
    if not rows:
        return _RESULTS_CSS + (
            '<p style="color:#6b7280;padding:12px">아직 분석 결과가 없습니다. '
            '이미지를 업로드하고 분석을 시작하세요.</p>'
        )

    body, boxes = [], []
    for row in rows:
        rid, ts, filename = row[0], row[1], row[2]
        number = row[4] if row[4] not in (None, "") else "-"
        color, defect = row[5], row[6]
        thumb = _img_data_uri(filename, 40, 70)
        big = _img_data_uri(filename, 1000, 82)
        lb_id = f"lb{rid}"
        if thumb:
            thumb_html = (
                f'<a href="#{lb_id}"><img class="res-thumb" src="{thumb}" title="클릭하여 확대"></a>'
            )
            boxes.append(
                f'<div id="{lb_id}" class="lb">'
                f'<a class="lb-bg" href="#_"></a>'
                f'<a class="lb-x" href="#_">&times;</a>'
                f'<img src="{big}">'
                f'<div class="lb-cap">{filename} · 번호 {number} · {color or "-"} · {defect or "-"}</div>'
                f'</div>'
            )
        else:
            thumb_html = '<span class="res-noimg">없음</span>'
        body.append(
            f'<tr><td>{rid}</td><td>{ts}</td>'
            f'<td class="fname">{thumb_html}{filename}</td>'
            f'<td>O</td><td>{number}</td><td>{_color_cell(color)}</td>'
            f'<td>{_badge(defect)}</td></tr>'
        )

    return (
        _RESULTS_CSS
        + '<div class="res-wrap"><table class="res-tbl">'
        + '<thead><tr><th>ID</th><th>시간</th><th>미리보기 · 파일명</th>'
        + '<th>스티커</th><th>번호</th><th>색상</th><th>불량 수준</th></tr></thead>'
        + '<tbody>' + ''.join(body) + '</tbody></table></div>'
        + ''.join(boxes)
    )


def export_results_to_csv():
    """
    전체 분석 결과를 CSV 파일로 내보내기

    Returns:
        CSV 파일 경로 (Gradio File 컴포넌트용)
    """
    data = load_results()
    results = data.get("results", [])

    if not results:
        return None

    # CSV 파일 생성
    output = io.StringIO()
    writer = csv.writer(output)

    # 헤더 작성
    writer.writerow(["ID", "시간", "파일명", "그룹ID", "스티커유무", "번호", "색상", "불량수준"])

    # 데이터 작성
    for r in results:
        writer.writerow([
            r.get("id", ""),
            r.get("timestamp", ""),
            r.get("filename", ""),
            r.get("group_id", ""),
            "O" if r.get("has_sticker") else "X",
            r.get("sticker_number", ""),
            r.get("sticker_color", ""),
            r.get("defect_level", "")
        ])

    # 파일로 저장
    csv_filename = f"analysis_results_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    csv_path = config.DATA_DIR / csv_filename

    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        f.write(output.getvalue())

    print(f"[CSV 내보내기] {csv_path}")
    return str(csv_path)


def chatbot_response(message, history):
    """
    챗봇 응답 생성 (vLLM/Qwen 사용)

    Args:
        message: 사용자 메시지
        history: 대화 기록

    Returns:
        AI 응답
    """
    if not message.strip():
        return "질문을 입력해주세요."

    try:
        response = chat_with_data(message)
        return response
    except Exception as e:
        return f"오류가 발생했습니다: {str(e)}"


def create_gradio_interface():
    """Gradio 대시보드 UI 생성"""
    with gr.Blocks(title="Motor Sticker Detection Dashboard") as demo:
        gr.Markdown("# Motor Sticker Detection Dashboard")
        gr.Markdown("실시간 이미지 분석 결과를 확인할 수 있습니다.")

        # 상단 분석 시작 컨트롤
        gr.Markdown("## ▶️ 분석 시작")
        with gr.Row():
            sample_btn = gr.Button(
                f"📊 테스트 데이터 분석 ({config.SAMPLE_LIMIT}장)",
                variant="primary", scale=2
            )
            upload_files = gr.File(
                label="또는 이미지 업로드", file_count="multiple",
                file_types=["image"], scale=3
            )
            upload_btn = gr.Button("업로드 이미지 분석", variant="secondary", scale=1)
        run_status = gr.Markdown("")

        with gr.Row():
            total_count = gr.Number(label="총 처리된 이미지", value=0, interactive=False)
            normal_count = gr.Number(label="정상 (초록색)", value=0, interactive=False)
            minor_count = gr.Number(label="경미한 불량 (노란색)", value=0, interactive=False)
            severe_count = gr.Number(label="심각한 불량 (빨간색)", value=0, interactive=False)

        with gr.Row():
            refresh_btn = gr.Button("새로고침", variant="primary")
            clear_btn = gr.Button("결과 전체 삭제", variant="stop")
            csv_btn = gr.Button("📥 전체 결과 CSV 다운로드", variant="secondary")

        csv_file = gr.File(label="다운로드 파일", visible=False)

        gr.Markdown("## 최근 분석 결과 (최대 20개)")
        results_table = gr.HTML(value=render_results_html([]))

        def update_dashboard():
            """대시보드 데이터 업데이트"""
            table_data, stats, total, normal, minor, severe = get_dashboard_data()
            return render_results_html(table_data), total, normal, minor, severe

        def clear_and_update():
            """결과 삭제 후 대시보드 업데이트"""
            clear_results()
            return update_dashboard()

        # 새로고침 버튼 클릭 시
        refresh_btn.click(
            fn=update_dashboard,
            inputs=[],
            outputs=[results_table, total_count, normal_count, minor_count, severe_count]
        )

        # 결과 삭제 버튼 클릭 시
        clear_btn.click(
            fn=clear_and_update,
            inputs=[],
            outputs=[results_table, total_count, normal_count, minor_count, severe_count]
        )

        # CSV 다운로드 버튼 클릭 시
        def download_csv():
            """CSV 파일 생성 후 반환"""
            path = export_results_to_csv()
            if path:
                return gr.update(value=path, visible=True)
            return gr.update(value=None, visible=False)

        csv_btn.click(
            fn=download_csv,
            inputs=[],
            outputs=[csv_file]
        )

        # 페이지 로드 시 자동 업데이트
        demo.load(
            fn=update_dashboard,
            inputs=[],
            outputs=[results_table, total_count, normal_count, minor_count, severe_count]
        )

        # 상단 버튼 핸들러
        def start_sample_analysis():
            """번들된 샘플 테스트 이미지를 큐에 넣고 분석 시작."""
            exts = ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG")
            images = []
            for ext in exts:
                images.extend(sorted(config.SAMPLE_DIR.glob(ext)))
            images = images[:config.SAMPLE_LIMIT]
            if not images:
                return ("⚠️ 샘플 이미지가 없습니다. "
                        "`student_template/data/sample_test_img/`를 확인하세요.")
            for src in images:
                _queue_image(src, src.name)
            ensure_worker_started()
            return (f"✅ 테스트 데이터 {len(images)}장 분석 시작됨 "
                    "(3장씩 그룹 분석). 아래 결과가 3초마다 자동 갱신됩니다.")

        def start_upload_analysis(files):
            """업로드된 이미지를 큐에 넣고 분석 시작."""
            if not files:
                return "⚠️ 업로드된 이미지가 없습니다."
            count = 0
            for f in files:
                src = Path(getattr(f, "name", f))
                try:
                    _queue_image(src, src.name)
                    count += 1
                except Exception as e:
                    print(f"[업로드 큐 오류] {e}")
            ensure_worker_started()
            return (f"✅ 업로드 이미지 {count}장 분석 시작됨. "
                    "아래 결과가 3초마다 자동 갱신됩니다.")

        sample_btn.click(fn=start_sample_analysis, inputs=[], outputs=[run_status])
        upload_btn.click(fn=start_upload_analysis, inputs=[upload_files], outputs=[run_status])

        # 분석 진행 중 대시보드 자동 갱신 (3초 주기)
        dashboard_timer = gr.Timer(value=3)
        dashboard_timer.tick(
            fn=update_dashboard,
            inputs=[],
            outputs=[results_table, total_count, normal_count, minor_count, severe_count]
        )

        # 챗봇 섹션
        gr.Markdown("---")
        gr.Markdown("## 🤖 AI 분석 어시스턴트")
        gr.Markdown("분석 결과에 대해 질문하세요. (예: '불량품 비율은?', '결과를 요약해줘', '가장 많은 불량 유형은?')")

        chatbot = gr.Chatbot(
            label="대화",
            height=300
        )
        msg_input = gr.Textbox(
            label="질문 입력",
            placeholder="분석 결과에 대해 질문하세요...",
            lines=1
        )
        with gr.Row():
            send_btn = gr.Button("전송", variant="primary")
            clear_chat_btn = gr.Button("대화 초기화")

        def respond(message, chat_history):
            """챗봇 응답 처리"""
            if not message.strip():
                return "", chat_history

            # AI 응답 생성
            bot_response = chatbot_response(message, chat_history)

            # messages 형식으로 추가
            chat_history = chat_history + [
                {"role": "user", "content": message},
                {"role": "assistant", "content": bot_response}
            ]

            return "", chat_history

        def clear_chat():
            """대화 초기화"""
            return []

        # 챗봇 이벤트 연결
        msg_input.submit(
            fn=respond,
            inputs=[msg_input, chatbot],
            outputs=[msg_input, chatbot]
        )
        send_btn.click(
            fn=respond,
            inputs=[msg_input, chatbot],
            outputs=[msg_input, chatbot]
        )
        clear_chat_btn.click(
            fn=clear_chat,
            inputs=[],
            outputs=[chatbot]
        )

        # 미확인 항목 검토 섹션
        gr.Markdown("---")
        gr.Markdown("## 🔍 미확인 항목 검토")
        gr.Markdown("스티커가 없거나 인식에 실패한 항목을 검토하고 재분석할 수 있습니다.")

        with gr.Row():
            review_refresh_btn = gr.Button("🔄 미확인 항목 불러오기", variant="primary")

        # 미확인 항목 갤러리 (최대 6개씩 표시)
        review_status = gr.Markdown("미확인 항목을 불러오려면 위 버튼을 클릭하세요.")

        with gr.Row():
            with gr.Column(scale=1):
                review_img1 = gr.Image(label="이미지 1", visible=False, height=200)
                review_info1 = gr.Markdown("", visible=False)
                review_btn1 = gr.Button("재분석", visible=False, size="sm")
                review_id1 = gr.State(value=None)

            with gr.Column(scale=1):
                review_img2 = gr.Image(label="이미지 2", visible=False, height=200)
                review_info2 = gr.Markdown("", visible=False)
                review_btn2 = gr.Button("재분석", visible=False, size="sm")
                review_id2 = gr.State(value=None)

            with gr.Column(scale=1):
                review_img3 = gr.Image(label="이미지 3", visible=False, height=200)
                review_info3 = gr.Markdown("", visible=False)
                review_btn3 = gr.Button("재분석", visible=False, size="sm")
                review_id3 = gr.State(value=None)

        with gr.Row():
            with gr.Column(scale=1):
                review_img4 = gr.Image(label="이미지 4", visible=False, height=200)
                review_info4 = gr.Markdown("", visible=False)
                review_btn4 = gr.Button("재분석", visible=False, size="sm")
                review_id4 = gr.State(value=None)

            with gr.Column(scale=1):
                review_img5 = gr.Image(label="이미지 5", visible=False, height=200)
                review_info5 = gr.Markdown("", visible=False)
                review_btn5 = gr.Button("재분석", visible=False, size="sm")
                review_id5 = gr.State(value=None)

            with gr.Column(scale=1):
                review_img6 = gr.Image(label="이미지 6", visible=False, height=200)
                review_info6 = gr.Markdown("", visible=False)
                review_btn6 = gr.Button("재분석", visible=False, size="sm")
                review_id6 = gr.State(value=None)

        def get_unknown_items():
            """미확인 항목 가져오기"""
            data = load_results()
            results = data.get("results", [])

            # 미확인 항목 필터링 (스티커 없음 또는 색상 null)
            unknown_items = [
                r for r in results
                if not r.get("has_sticker") or r.get("sticker_color") is None or r.get("defect_level") == "미확인"
            ]

            return unknown_items[-6:]  # 최근 6개만

        def load_review_items():
            """미확인 항목 UI 업데이트"""
            items = get_unknown_items()

            # 기본값 설정
            outputs = []
            status_text = f"**미확인 항목: {len(items)}개**" if items else "✅ 미확인 항목이 없습니다."

            for i in range(6):
                if i < len(items):
                    item = items[i]
                    filename = item.get("filename", "")
                    file_path = config.UPLOAD_DIR / filename

                    # 이미지 경로
                    img_path = str(file_path) if file_path.exists() else None

                    # 정보 텍스트
                    info_text = f"""**ID: {item.get('id')}**
- 파일: {filename[:30]}...
- 번호: {item.get('sticker_number', '-')}
- 색상: {item.get('sticker_color', '-')}
- 상태: {item.get('defect_level', '미확인')}"""

                    outputs.extend([
                        gr.update(value=img_path, visible=True),  # 이미지
                        gr.update(value=info_text, visible=True),  # 정보
                        gr.update(visible=True),  # 버튼
                        item.get('id')  # ID
                    ])
                else:
                    outputs.extend([
                        gr.update(value=None, visible=False),
                        gr.update(value="", visible=False),
                        gr.update(visible=False),
                        None
                    ])

            return [status_text] + outputs

        def do_reanalyze(item_id):
            """단일 항목 재분석"""
            if item_id is None:
                return "ID가 없습니다."

            result = reanalyze_image(item_id)

            if result.get("success"):
                new_info = result.get("new", {})
                return f"""✅ **재분석 완료 (ID: {item_id})**
- 번호: {new_info.get('number', '-')}
- 색상: {new_info.get('color', '-')}
- 불량수준: {new_info.get('defect_level', '-')}

🔄 새로고침하여 결과를 확인하세요."""
            else:
                return f"❌ 재분석 실패: {result.get('message', '알 수 없는 오류')}"

        # 미확인 항목 불러오기 버튼
        review_refresh_btn.click(
            fn=load_review_items,
            inputs=[],
            outputs=[
                review_status,
                review_img1, review_info1, review_btn1, review_id1,
                review_img2, review_info2, review_btn2, review_id2,
                review_img3, review_info3, review_btn3, review_id3,
                review_img4, review_info4, review_btn4, review_id4,
                review_img5, review_info5, review_btn5, review_id5,
                review_img6, review_info6, review_btn6, review_id6,
            ]
        )

        # 각 재분석 버튼 연결
        review_btn1.click(fn=do_reanalyze, inputs=[review_id1], outputs=[review_status])
        review_btn2.click(fn=do_reanalyze, inputs=[review_id2], outputs=[review_status])
        review_btn3.click(fn=do_reanalyze, inputs=[review_id3], outputs=[review_status])
        review_btn4.click(fn=do_reanalyze, inputs=[review_id4], outputs=[review_status])
        review_btn5.click(fn=do_reanalyze, inputs=[review_id5], outputs=[review_status])
        review_btn6.click(fn=do_reanalyze, inputs=[review_id6], outputs=[review_status])

    return demo


# Gradio 대시보드를 FastAPI 루트(/)에 마운트 → 단일 포트로 서빙
demo = create_gradio_interface()
demo.queue()
app = gr.mount_gradio_app(app, demo, path="/")


if __name__ == "__main__":
    print("=" * 70)
    print("Motor Sticker Detection 서버 시작 (단일 포트)")
    print("=" * 70)
    print(f"API Base URL: {config.API_BASE_URL}")
    print(f"Model: {config.MODEL_NAME}")
    print("API Key: " + (f"{config.API_KEY[:8]}..." if len(config.API_KEY) > 8 else "[설정되지 않음]"))
    print(f"Port: {config.SERVER_PORT}")
    print(f"대시보드 http://localhost:{config.SERVER_PORT}/  |  API /api/*  |  헬스 /healthz")
    print("=" * 70)

    uvicorn.run(app, host="0.0.0.0", port=config.SERVER_PORT)
