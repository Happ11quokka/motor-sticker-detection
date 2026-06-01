import os
from pathlib import Path
from dotenv import load_dotenv

# .env 파일 경로를 명시적으로 지정
env_path = Path(__file__).parent / ".env"
load_dotenv(env_path)

# Vision Model API
API_BASE_URL = os.getenv("API_BASE_URL", "https://api.openai.com/v1")
API_KEY = os.getenv("API_KEY", "")
MODEL_NAME = os.getenv("MODEL_NAME", "gpt-4o")

# Server Ports
# Railway 등 PaaS는 PORT를 주입한다. PORT > SERVER_PORT > 8000 순으로 사용.
SERVER_PORT = int(os.getenv("PORT", os.getenv("SERVER_PORT", "8000")))
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

# 데모용 번들 테스트 이미지 ("테스트 데이터 분석" 버튼 소스)
SAMPLE_DIR = DATA_DIR / "sample_test_img"
SAMPLE_LIMIT = int(os.getenv("SAMPLE_LIMIT", "12"))

# 미리 분석된 시드(배포 번들). 첫 기동 시 결과/이미지를 즉시 주입한다.
# (teacher_tools/preseed.py 로 생성)
SEED_DIR = DATA_DIR / "seed"

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


def seed_if_empty():
    """결과가 비어 있고 시드가 있으면, 미리 분석한 결과/이미지를 주입한다.

    배포 컨테이너는 results.json/uploads 가 비어 있는 상태로 기동하므로,
    링크에 접속하면 곧바로 대시보드 결과와 챗봇 데이터가 보이도록 한다.
    사용자가 이미 분석을 돌린 경우(결과 존재)에는 덮어쓰지 않는다.
    """
    import json
    import shutil

    seed_results = SEED_DIR / "results.json"
    seed_uploads = SEED_DIR / "uploads"
    if not seed_results.exists():
        return

    try:
        with open(RESULTS_FILE, encoding="utf-8") as f:
            current = json.load(f)
        if current.get("results"):
            return  # 이미 결과가 있으면 보존
    except Exception:
        pass  # 손상/비정상 → 시드로 복구

    try:
        shutil.copy(seed_results, RESULTS_FILE)
        copied = 0
        if seed_uploads.exists():
            for img in seed_uploads.iterdir():
                dest = UPLOAD_DIR / img.name
                if not dest.exists():
                    shutil.copy(img, dest)
                    copied += 1
        print(f"[SEED] 미리 분석된 결과 주입 완료 (이미지 {copied}장)")
    except Exception as e:
        print(f"[SEED] 주입 실패: {e}")


seed_if_empty()
