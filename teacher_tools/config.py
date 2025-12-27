import os
from pathlib import Path

DEFAULT_IMAGE_FOLDER = Path(__file__).parent.parent / "data" / "motor_checker"
DEFAULT_STUDENT_FILE = Path(__file__).parent / "student_apis.json"

DEFAULT_INTERVAL = 0.5  # 업로드만 하므로 빠르게
DEFAULT_TIMEOUT = 10    # 업로드는 빨라야 하므로 타임아웃 짧게
MAX_RETRIES = 3
