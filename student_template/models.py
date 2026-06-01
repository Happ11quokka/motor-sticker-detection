"""
데이터 모델 및 유틸리티 함수
"""
import base64
import json
import threading
from datetime import datetime
from pathlib import Path
from typing import Optional
from io import BytesIO

from pydantic import BaseModel
from PIL import Image

import config


file_lock = threading.Lock()


class AnalysisResult(BaseModel):
    """분석 결과 데이터 모델"""
    id: int
    timestamp: str
    filename: str
    has_sticker: bool
    sticker_number: Optional[str] = None
    sticker_color: Optional[str] = None
    defect_level: Optional[str] = None


def load_results_unsafe():
    """락 없이 파일 읽기 (내부 사용)"""
    try:
        with open(config.RESULTS_FILE, "r", encoding="utf-8") as f:
            content = f.read().strip()
            # 빈 파일 체크
            if not content:
                print("[WARNING] results.json이 비어있습니다. 초기화합니다.")
                return {"total_images": 0, "groups": [], "results": []}

            data = json.loads(content)
            # 구 형식 호환성 체크
            if "groups" not in data:
                data["groups"] = []
            if "results" not in data:
                data["results"] = []
            if "total_images" not in data:
                data["total_images"] = 0
            return data
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON 파싱 오류: {e}")
        print("[WARNING] results.json을 초기화합니다.")
        # 손상된 파일 백업
        import shutil
        backup_file = config.RESULTS_FILE.parent / f"results_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        try:
            shutil.copy(config.RESULTS_FILE, backup_file)
            print(f"[INFO] 손상된 파일 백업: {backup_file}")
        except:
            pass
        # 초기화된 데이터 반환
        return {"total_images": 0, "groups": [], "results": []}
    except Exception as e:
        print(f"[ERROR] 파일 읽기 오류: {e}")
        return {"total_images": 0, "groups": [], "results": []}


def load_results():
    """락을 사용하여 안전하게 파일 읽기"""
    with file_lock:
        return load_results_unsafe()


def save_result(result: dict):
    """결과를 JSON 파일에 저장 (deprecated - 그룹 분석으로 대체)"""
    with file_lock:
        data = load_results_unsafe()
        data["total_images"] += 1
        result["id"] = data["total_images"]
        result["timestamp"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        data["results"].append(result)

        try:
            with open(config.RESULTS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[ERROR] JSON 저장 실패: {e}")
            raise

    return result


def resize_image(image_path: Path, max_size: int = 1024) -> bytes:
    """
    이미지를 리사이즈하고 JPEG로 압축

    Args:
        image_path: 이미지 파일 경로
        max_size: 최대 크기 (픽셀)

    Returns:
        압축된 이미지 바이트
    """
    img = Image.open(image_path)

    # RGBA 이미지를 RGB로 변환 (JPEG는 RGBA 지원 안함)
    if img.mode in ('RGBA', 'LA', 'P'):
        background = Image.new('RGB', img.size, (255, 255, 255))
        if img.mode == 'P':
            img = img.convert('RGBA')
        background.paste(img, mask=img.split()[-1] if img.mode in ('RGBA', 'LA') else None)
        img = background
    elif img.mode != 'RGB':
        img = img.convert('RGB')

    # 비율을 유지하면서 리사이즈
    img.thumbnail((max_size, max_size), Image.Resampling.LANCZOS)

    # JPEG로 압축
    buffer = BytesIO()
    img.save(buffer, format='JPEG', quality=85, optimize=True)
    return buffer.getvalue()


def encode_image(image_path: Path) -> str:
    """
    이미지를 리사이즈하고 base64로 인코딩

    Args:
        image_path: 이미지 파일 경로

    Returns:
        base64 인코딩된 문자열
    """
    image_bytes = resize_image(image_path)
    return base64.b64encode(image_bytes).decode('utf-8')


def determine_defect_level(color: Optional[str]) -> str:
    """
    스티커 색상에 따른 불량 수준 판정

    Args:
        color: 스티커 색상 (초록색/노란색/빨간색)

    Returns:
        불량 수준 (정상/경미한 불량/심각한 불량/미확인)
    """
    if color == "초록색":
        return "정상"
    elif color == "노란색":
        return "경미한 불량"
    elif color == "빨간색":
        return "심각한 불량"
    else:
        return "미확인"


def clear_results():
    """모든 분석 결과 삭제"""
    with file_lock:
        empty_data = {"total_images": 0, "groups": [], "results": []}
        try:
            with open(config.RESULTS_FILE, "w", encoding="utf-8") as f:
                json.dump(empty_data, f, ensure_ascii=False, indent=2)
            print("[INFO] 분석 결과가 모두 삭제되었습니다.")
            return True
        except Exception as e:
            print(f"[ERROR] 결과 삭제 실패: {e}")
            return False
