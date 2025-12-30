import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 경로를 명시적으로 지정
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

# Vision Model API
API_BASE_URL = os.getenv("API_BASE_URL", "https://api.openai.com/v1")
API_KEY = os.getenv("API_KEY", "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")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o")

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
