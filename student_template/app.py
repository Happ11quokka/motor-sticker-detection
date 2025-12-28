"""
Motor Sticker Detection API Server

이미지를 업로드하면 백그라운드에서 3개씩 그룹으로 분석합니다.
업로드 완료 후 /start-analysis로 분석을 시작합니다.
"""
import io
import csv
import threading
from datetime import datetime
from collections import deque

import uvicorn
import gradio as gr
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import config
from models import load_results, clear_results
from worker import image_queue, background_worker, chat_with_data

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


@app.get("/")
def health_check():
    """서버 헬스체크"""
    return {
        "status": "ok",
        "service": "Motor Sticker Detection API",
        "version": "1.0.0"
    }


@app.post("/upload")
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
        image_info = {
            "filename": filename,
            "path": str(file_path),
            "upload_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }

        image_queue.put(image_info)
        image_buffer.append(image_info)

        print(f"[업로드] {filename} | 큐 크기: {image_queue.qsize()}")

        return {
            "success": True,
            "message": "이미지 업로드 완료",
            "filename": filename,
            "queue_size": image_queue.qsize()
        }

    except Exception as e:
        print(f"[업로드 오류] {str(e)}")
        raise HTTPException(status_code=500, detail=f"업로드 중 오류 발생: {str(e)}")


@app.post("/start-analysis")
async def start_analysis():
    """
    업로드된 이미지 분석 시작

    업로드가 모두 완료된 후 이 엔드포인트를 호출하면 분석을 시작합니다.
    """
    queue_size = image_queue.qsize()

    if queue_size == 0:
        return {
            "success": False,
            "message": "분석할 이미지가 없습니다.",
            "queue_size": 0
        }

    if analysis_state["is_analyzing"]:
        return {
            "success": False,
            "message": "이미 분석이 진행 중입니다.",
            "queue_size": queue_size
        }

    # 분석 시작
    analysis_state["is_analyzing"] = True

    def run_analysis():
        try:
            background_worker()
        finally:
            analysis_state["is_analyzing"] = False

    worker_thread = threading.Thread(target=run_analysis, daemon=True)
    worker_thread.start()
    analysis_state["worker_thread"] = worker_thread

    print(f"\n{'='*50}")
    print(f"[분석 시작] 큐에 있는 {queue_size}개 이미지 분석 시작")
    print(f"{'='*50}\n")

    return {
        "success": True,
        "message": f"분석 시작됨 ({queue_size}개 이미지)",
        "queue_size": queue_size
    }


@app.get("/analysis-status")
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

    # 최근 20개 결과
    recent_results = results[-20:][::-1]

    table_data = []
    for r in recent_results:
        table_data.append([
            r["id"],
            r["timestamp"],
            r["filename"],
            "O" if r["has_sticker"] else "X",
            r.get("sticker_number", "-"),
            r.get("sticker_color", "-"),
            r.get("defect_level", "-")
        ])

    # 불량 수준별 통계
    normal = sum(1 for r in results if r.get("defect_level") == "정상")
    minor = sum(1 for r in results if r.get("defect_level") == "경미한 불량")
    severe = sum(1 for r in results if r.get("defect_level") == "심각한 불량")
    total = len(results)

    stats = {
        "정상 (초록색)": normal,
        "경미한 불량 (노란색)": minor,
        "심각한 불량 (빨간색)": severe
    }

    return table_data, stats, total, normal, minor, severe


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
        results_table = gr.Dataframe(
            headers=["ID", "시간", "파일명", "스티커 유무", "번호", "색상", "불량 수준"],
            datatype=["number", "str", "str", "str", "str", "str", "str"],
            row_count=20,
            col_count=(7, "fixed"),
        )

        def update_dashboard():
            """대시보드 데이터 업데이트"""
            table_data, stats, total, normal, minor, severe = get_dashboard_data()
            return table_data, total, normal, minor, severe

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

    return demo


def run_gradio():
    """Gradio 서버 실행"""
    demo = create_gradio_interface()
    demo.launch(
        server_name="0.0.0.0",
        server_port=config.GRADIO_PORT,
        share=False,
        show_error=True
    )


if __name__ == "__main__":
    print("="*70)
    print("Motor Sticker Detection API 서버 시작")
    print("="*70)
    print(f"API Base URL: {config.API_BASE_URL}")
    print(f"Model: {config.MODEL_NAME}")
    print(f"API Key: {config.API_KEY[:20]}..." if len(config.API_KEY) > 20 else "API Key: [설정되지 않음]")
    print(f"FastAPI 포트: {config.SERVER_PORT}")
    print(f"Gradio 포트: {config.GRADIO_PORT}")
    print("="*70)

    # Gradio 대시보드 시작
    gradio_thread = threading.Thread(target=run_gradio, daemon=True)
    gradio_thread.start()

    print(f"\n✓ FastAPI 서버: http://localhost:{config.SERVER_PORT}")
    print(f"✓ Gradio 대시보드: http://localhost:{config.GRADIO_PORT}")
    print(f"✓ 분석 대기 중 (POST /start-analysis 로 시작)\n")

    # FastAPI 서버 실행
    uvicorn.run(app, host="0.0.0.0", port=config.SERVER_PORT)
