"""
테스트 데이터셋(52장)을 미리 분석하여 배포에 번들할 시드를 생성한다.

앱과 동일한 "3장 그룹" 파이프라인(worker.analyze_image_group)으로 분석하므로
대시보드/통계/챗봇이 라이브 분석과 완전히 동일한 결과를 보여준다.

산출물:
  student_template/data/results.json        ← 라이브(로컬 확인용)
  student_template/data/uploads/*.jpg        ← 라이브 썸네일용(리사이즈)
  student_template/data/seed/results.json    ← 배포 번들(커밋/도커 포함)
  student_template/data/seed/uploads/*.jpg   ← 배포 번들(리사이즈)

실행:
  python teacher_tools/preseed.py
"""
import sys
import shutil
from pathlib import Path
from datetime import datetime

# student_template 모듈 임포트 경로 확보
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "student_template"))

import config  # noqa: E402
from models import clear_results  # noqa: E402
from worker import analyze_image_group  # noqa: E402
from PIL import Image  # noqa: E402

TEST_DIR = ROOT / "data" / "motor_checker_2" / "test_img"
SEED_DIR = config.DATA_DIR / "seed"
SEED_UPLOADS = SEED_DIR / "uploads"

GROUP_SIZE = 3
DISPLAY_MAX = 1000   # 라이트박스 확대 뷰가 1000px이므로 그에 맞춤
DISPLAY_Q = 82


def _save_display_copy(src: Path, dest: Path) -> None:
    """표시용 리사이즈 사본 저장(원본 144MB → 수 MB로 축소)."""
    with Image.open(src) as im:
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        im.thumbnail((DISPLAY_MAX, DISPLAY_MAX), Image.Resampling.LANCZOS)
        im.save(dest, format="JPEG", quality=DISPLAY_Q, optimize=True)


def main() -> None:
    images = []
    for ext in ("*.jpg", "*.jpeg", "*.png", "*.JPG", "*.JPEG", "*.PNG"):
        images.extend(TEST_DIR.glob(ext))
    images = sorted(set(images))

    if not images:
        print(f"[오류] 테스트 이미지가 없습니다: {TEST_DIR}")
        sys.exit(1)

    print(f"[시작] 테스트 이미지 {len(images)}장 미리 분석")

    # 깨끗한 상태에서 시작
    clear_results()
    for d in (config.UPLOAD_DIR, SEED_UPLOADS):
        d.mkdir(parents=True, exist_ok=True)
        for f in d.glob("*.jpg"):
            f.unlink()

    # 타임스탬프 파일명 + 표시용 사본 준비
    infos = []
    for src in images:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
        filename = f"{ts}_{src.name}"
        # 표시용 리사이즈 사본을 라이브/시드 양쪽 uploads에 저장
        _save_display_copy(src, config.UPLOAD_DIR / filename)
        shutil.copy(config.UPLOAD_DIR / filename, SEED_UPLOADS / filename)
        # 분석은 원본 풀해상도로(encode_image가 1024로 재축소 → 최상 정확도)
        infos.append({
            "filename": filename,
            "path": str(src),
            "upload_time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })

    # 3장씩 그룹 분석(앱 워커와 동일 로직)
    total_groups = (len(infos) + GROUP_SIZE - 1) // GROUP_SIZE
    for gi in range(0, len(infos), GROUP_SIZE):
        group = infos[gi:gi + GROUP_SIZE]
        print(f"\n===== 그룹 {gi // GROUP_SIZE + 1}/{total_groups} ({len(group)}장) =====")
        analyze_image_group(group)

    # 라이브 결과 → 시드로 복사(배포 번들)
    shutil.copy(config.RESULTS_FILE, SEED_DIR / "results.json")

    # 요약
    import json
    with open(config.RESULTS_FILE, encoding="utf-8") as f:
        data = json.load(f)
    results = data.get("results", [])
    with_sticker = [r for r in results if r.get("has_sticker")]
    print("\n" + "=" * 50)
    print(f"[완료] 그룹 {len(data.get('groups', []))}개 / 결과 행 {len(results)}개")
    print(f"  스티커 발견: {len(with_sticker)}개")
    for level in ("정상", "경미한 불량", "심각한 불량", "미확인"):
        n = sum(1 for r in results if r.get("defect_level") == level)
        print(f"  - {level}: {n}개")
    print(f"[시드 저장] {SEED_DIR}")
    print("=" * 50)


if __name__ == "__main__":
    main()
