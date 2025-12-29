import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

# Vision Model API (OpenAI 호환 API용 - 챗봇에서 사용)
API_BASE_URL = os.getenv("API_BASE_URL", "http://localhost:8000/v1")
API_KEY = os.getenv("API_KEY", "token-abc123")
MODEL_NAME = os.getenv("MODEL_NAME", "Qwen/Qwen3-VL-8B-Instruct")

# DeepSeek-OCR vLLM API 설정
DEEPSEEK_API_BASE_URL = os.getenv("DEEPSEEK_API_BASE_URL", "http://localhost:8000/v1")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "token-abc123")
DEEPSEEK_OCR_MODEL = os.getenv("DEEPSEEK_OCR_MODEL", "deepseek-ai/DeepSeek-OCR")

# OCR 엔진 선택: "deepseek" 또는 "openai"
OCR_ENGINE = os.getenv("OCR_ENGINE", "deepseek")

# Server Ports
SERVER_PORT = int(os.getenv("SERVER_PORT", "8000"))
GRADIO_PORT = int(os.getenv("GRADIO_PORT", "7860"))

# LangSmith 설정 (선택사항)
LANGSMITH_API_KEY = os.getenv("LANGSMITH_API_KEY", "")
LANGSMITH_PROJECT = os.getenv("LANGSMITH_PROJECT", "motor-sticker-detection")
LANGSMITH_TRACING = os.getenv("LANGSMITH_TRACING", "false").lower() == "true"

# 디렉토리 설정
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
RESULTS_FILE = DATA_DIR / "results.json"

DATA_DIR.mkdir(exist_ok=True)
UPLOAD_DIR.mkdir(exist_ok=True)

if not RESULTS_FILE.exists():
    import json
    with open(RESULTS_FILE, "w", encoding="utf-8") as f:
        json.dump({
            "total_images": 0,
            "groups": [],
            "results": []
        }, f, ensure_ascii=False, indent=2)
