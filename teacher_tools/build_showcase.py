"""데모용 '최근 20건' 쇼케이스 시드를 결정적으로 생성한다.

정상·경미한 불량·심각한 불량·관련없음 4종을 섞고, 흑백/블러 이미지를 포함하며,
각 스티커 행은 3장 그룹(메인+남은 2장)을 갖는다. GPT 호출 없음(라벨은 큐레이션 고정).

산출물: results.json(+seed/results.json), uploads/*(+seed/uploads/*).
실행:  python teacher_tools/build_showcase.py
"""
import sys
import json
import shutil
from pathlib import Path
from datetime import datetime

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "student_template"))
import config  # noqa: E402
from PIL import Image  # noqa: E402

COLOR_DIR = ROOT / "data" / "motor_checker_2"
GRAY_DIR = COLOR_DIR / "grayscale"
BLUR_DIR = COLOR_DIR / "blurred"
IRR_DIR = COLOR_DIR / "test_img"
SEED_DIR = config.DATA_DIR / "seed"
SEED_UPLOADS = SEED_DIR / "uploads"
DISPLAY_MAX, DISPLAY_Q = 1000, 82


def _src_dir(variant: str) -> Path:
    return {"color": COLOR_DIR, "gray": GRAY_DIR, "blur": BLUR_DIR, "irr": IRR_DIR}[variant]

# 큐레이션 20행: (category, variant, main_base, number, color, [neighbor_base, neighbor_base])
# category: normal/minor/severe/irrelevant   variant: color/gray/blur/irr
SHOW = [
    ("normal",     "color", "20240817_000743.jpg", "112", "초록색", ["20240817_000736.jpg", "20240817_000731.jpg"]),
    ("irrelevant", "irr",   "thumb_d_568043175A035B75FE0CBB82F6E4E084.jpg", "-", "-", []),
    ("minor",      "color", "20240817_000336.jpg", "169", "노란색", ["20240817_000322.jpg", "20240817_000350.jpg"]),
    ("normal",     "color", "20240817_000116.jpg", "102", "초록색", ["20240817_000108.jpg", "20240817_000136.jpg"]),
    ("normal",     "gray",  "20240817_000444.jpg", "107", "초록색", ["20240817_000433.jpg", "20240817_000459.jpg"]),
    ("normal",     "blur",  "20240817_000227.jpg", "104", "초록색", ["20240817_000216.jpg", "20240817_000238.jpg"]),
    ("irrelevant", "irr",   "c92257_99.jpg", "-", "-", []),
    ("normal",     "color", "20240817_000148.jpg", "103", "초록색", ["20240817_000138.jpg", "20240817_000204.jpg"]),
    ("normal",     "gray",  "20240817_000512.jpg", "108", "초록색", ["20240817_000501.jpg", "20240817_000546.jpg"]),
    ("normal",     "color", "20240817_000249.jpg", "105", "초록색", ["20240817_000241.jpg", "20240817_000314.jpg"]),
    ("irrelevant", "irr",   "dmbt6_34031327_D00_SPI00.jpg", "-", "-", []),
    ("normal",     "blur",  "20240817_000650.jpg", "110", "초록색", ["20240817_000642.jpg", "20240817_000707.jpg"]),
    ("normal",     "gray",  "20240817_000625.jpg", "601", "초록색", ["20240817_000552.jpg", "20240817_000639.jpg"]),
    ("normal",     "blur",  "20240817_000717.jpg", "111", "초록색", ["20240817_000710.jpg", "20240817_000731.jpg"]),
    ("normal",     "color", "20240817_000408.jpg", "106", "초록색", ["20240817_000355.jpg", "20240817_000431.jpg"]),
    ("irrelevant", "irr",   "SMNM20111906_main3.jpg", "-", "-", []),
    ("normal",     "blur",  "20240817_000116.jpg", "102", "초록색", ["20240817_000108.jpg", "20240817_000136.jpg"]),
    ("normal",     "gray",  "20240817_000148.jpg", "103", "초록색", ["20240817_000138.jpg", "20240817_000204.jpg"]),
    ("normal",     "gray",  "20240817_000249.jpg", "105", "초록색", ["20240817_000241.jpg", "20240817_000314.jpg"]),
    ("irrelevant", "irr",   "abd64b20-e26d-4c08-aa7c-761b48dba2e5.jpg", "-", "-", []),
]
DEFECT = {"normal": "정상", "minor": "경미한 불량", "severe": "심각한 불량", "irrelevant": "관련없음"}


def _save_copy(src: Path, dest: Path) -> None:
    with Image.open(src) as im:
        if im.mode not in ("RGB", "L"):
            im = im.convert("RGB")
        im.thumbnail((DISPLAY_MAX, DISPLAY_MAX), Image.Resampling.LANCZOS)
        im.save(dest, format="JPEG", quality=DISPLAY_Q, optimize=True)


def _stamp(i: int, base: str) -> str:
    # 인덱스로 충돌 없는 고유 파일명
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"{ts}_{i:03d}_{Path(base).stem}.jpg"


def _copy_in(i: int, variant: str, base: str) -> str:
    src = _src_dir(variant) / base
    if not src.exists():
        raise FileNotFoundError(f"소스 이미지 없음: {src}")
    fn = _stamp(i, base)
    _save_copy(src, config.UPLOAD_DIR / fn)
    shutil.copy(config.UPLOAD_DIR / fn, SEED_UPLOADS / fn)
    return fn


def main() -> None:
    for d in (config.UPLOAD_DIR, SEED_UPLOADS):
        d.mkdir(parents=True, exist_ok=True)
        for f in list(d.glob("*.jpg")) + list(d.glob("*.png")):
            f.unlink()

    groups, results = [], []
    ts0 = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for idx, (cat, variant, main_base, number, color, neighbors) in enumerate(SHOW):
        i = idx + 1
        has_sticker = cat != "irrelevant"
        main_fn = _copy_in(i, variant, main_base)
        images = [{"filename": main_fn, "has_sticker": has_sticker,
                   "sticker_number": number if has_sticker else None,
                   "sticker_color": color if color != "-" else None}]
        for nb in neighbors:
            nb_fn = _copy_in(i, variant, nb)
            images.append({"filename": nb_fn, "has_sticker": False,
                           "sticker_number": None, "sticker_color": None})
        groups.append({
            "group_id": i, "timestamp": ts0, "images": images,
            "sticker_info": ({"filename": main_fn, "number": number, "color": color}
                             if has_sticker else None),
            "defect_level": DEFECT[cat] if has_sticker else None,
            "status": "정상" if has_sticker else "관련없음",
        })
        results.append({
            "id": i, "timestamp": ts0, "filename": main_fn, "group_id": i,
            "has_sticker": has_sticker,
            "sticker_number": number if has_sticker else None,
            "sticker_color": color if color != "-" else None,
            "defect_level": DEFECT[cat],
        })

    out = {"total_images": len(results), "showcase": True,
           "groups": groups, "results": results}
    SEED_DIR.mkdir(parents=True, exist_ok=True)
    for path in (config.RESULTS_FILE, SEED_DIR / "results.json"):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(out, f, ensure_ascii=False, indent=2)

    from collections import Counter
    c = Counter(r["defect_level"] for r in results)
    print(f"[완료] 쇼케이스 {len(results)}행 생성:", dict(c))
    print(f"  포함 확인 000743: {any('000743' in r['filename'] for r in results)}")
    print(f"[저장] {config.RESULTS_FILE}\n        {SEED_DIR/'results.json'}")


if __name__ == "__main__":
    main()
