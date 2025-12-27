"""
Motor Sticker Detection API Server

이미지를 업로드하면 백그라운드에서 3개씩 그룹으로 분석합니다.
"""
import threading
from datetime import datetime
from collections import deque

import uvicorn
import gradio as gr
from fastapi import FastAPI, File, UploadFile, HTTPException
from fastapi.middleware.cors import CORSMiddleware

import config
from models import load_results
from worker import image_queue, background_worker


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

        print(f"[업로드] 큐에 추가하기 전 - 큐 크기: {image_queue.qsize()}")
        image_queue.put(image_info)
        print(f"[업로드] 큐에 추가한 후 - 큐 크기: {image_queue.qsize()}")
        image_buffer.append(image_info)

        print(f"[업로드 완료] {filename} | 큐 크기: {image_queue.qsize()}")

        return {
            "success": True,
            "message": "이미지 업로드 완료",
            "filename": filename,
            "queue_size": image_queue.qsize()
        }

    except Exception as e:
        print(f"[업로드 오류] {str(e)}")
        raise HTTPException(status_code=500, detail=f"업로드 중 오류 발생: {str(e)}")


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

        # 새로고침 버튼 클릭 시
        refresh_btn.click(
            fn=update_dashboard,
            inputs=[],
            outputs=[results_table, total_count, normal_count, minor_count, severe_count]
        )

        # 페이지 로드 시 자동 업데이트
        demo.load(
            fn=update_dashboard,
            inputs=[],
            outputs=[results_table, total_count, normal_count, minor_count, severe_count]
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

    # 백그라운드 워커 시작 (3개씩 그룹 분석)
    worker_thread = threading.Thread(target=background_worker, daemon=True)
    worker_thread.start()

    # Gradio 대시보드 시작
    gradio_thread = threading.Thread(target=run_gradio, daemon=True)
    gradio_thread.start()

    print(f"\n✓ FastAPI 서버: http://localhost:{config.SERVER_PORT}")
    print(f"✓ Gradio 대시보드: http://localhost:{config.GRADIO_PORT}")
    print(f"✓ 백그라운드 워커: 실행 중 (3개씩 그룹 분석)\n")

    # FastAPI 서버 실행
    uvicorn.run(app, host="0.0.0.0", port=config.SERVER_PORT)
