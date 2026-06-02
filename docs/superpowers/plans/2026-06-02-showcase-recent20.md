# 최근 20건 쇼케이스 큐레이션 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 데모 대시보드의 "최근 20건" 표를 4종 등급(정상·경미한 불량·심각한 불량·관련없음)이 섞이고, 스티커 `O` 토글로 그룹의 남은 2장을 펼쳐 보이며, 흑백·블러 분석 이미지까지 포함된 큐레이션 쇼케이스로 개편한다.

**Architecture:** 순수 로직(행 구성·HTML 렌더)을 부작용 없는 신규 모듈 `student_template/showcase.py`로 분리해 단위 테스트(pytest)로 검증한다. `app.py`는 이미지 data-URI 함수만 주입해 호출한다. 큐레이션 데이터는 신규 빌더 `teacher_tools/build_showcase.py`가 컬러/흑백/블러/관련없음 이미지를 골라 `results.json`(+seed 번들)에 `showcase: true` 로 결정적으로 생성한다. 실제 업로드/GPT 분석 경로는 불변(데모 전용).

**Tech Stack:** Python 3.10+, Gradio 6 (`gr.HTML`, JS 미사용 → CSS-only 토글), Pillow, pytest 9.

---

## File Structure

| 파일 | 책임 | 변경 |
|---|---|---|
| `student_template/showcase.py` | 행 구성(`build_showcase_rows`) + HTML 렌더(`render_results_html`, 배지/토글). 순수(부작용 없음, config 미임포트). | **신규** |
| `student_template/tests/test_showcase.py` | 위 순수 함수의 단위 테스트 | **신규** |
| `student_template/tests/conftest.py` | `import showcase` 가능하도록 sys.path 설정 | **신규** |
| `student_template/app.py` | `_img_data_uri` 유지. 옛 렌더/배지 함수 제거 → showcase 위임. `get_dashboard_data` 가 dict 행 반환. 호출부 2곳 갱신. | 수정 |
| `teacher_tools/build_showcase.py` | 큐레이션 20행 데이터 + 이미지 사본을 결정적으로 생성 | **신규** |
| `student_template/data/results.json`, `data/uploads/*` | 빌더 산출(로컬) | 재생성 |
| `student_template/data/seed/results.json`, `data/seed/uploads/*` | 빌더 산출(배포 번들) | 재생성 |

**행 dict 스키마** (showcase.py 와 app.py 가 공유하는 인터페이스):
```python
{
  "id": int,            # 표시 ID(1..20)
  "timestamp": str,     # "YYYY-MM-DD HH:MM:SS"
  "filename": str,      # 메인 이미지 파일명(uploads 내)
  "has_sticker": bool,
  "number": str,        # 스티커 번호, 없으면 "-"
  "color": str,         # "초록색"/"노란색"/"-"
  "defect_level": str,  # "정상"/"경미한 불량"/"심각한 불량"/"관련없음"
  "extra_photos": list, # 남은 사진 파일명 0~2개(파일 순서). 관련없음/무스티커는 []
}
```

---

## Task 1: `showcase.py` — `build_showcase_rows` (행 구성, 순수)

**Files:**
- Create: `student_template/showcase.py`
- Create: `student_template/tests/conftest.py`
- Test: `student_template/tests/test_showcase.py`

- [ ] **Step 1: conftest 로 import 경로 확보**

Create `student_template/tests/conftest.py`:
```python
import sys
from pathlib import Path

# student_template 디렉토리를 sys.path 에 추가 → `import showcase` 가능
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
```

- [ ] **Step 2: 실패하는 테스트 작성**

Create `student_template/tests/test_showcase.py`:
```python
import showcase


def _fixture():
    return {
        "showcase": True,
        "results": [
            {"id": 1, "timestamp": "t1", "filename": "g1_main.jpg", "group_id": 1,
             "has_sticker": True, "sticker_number": "112", "sticker_color": "초록색",
             "defect_level": "정상"},
            {"id": 2, "timestamp": "t2", "filename": "junk.jpg", "group_id": 2,
             "has_sticker": False, "sticker_number": None, "sticker_color": None,
             "defect_level": "관련없음"},
        ],
        "groups": [
            {"group_id": 1, "images": [
                {"filename": "g1_a.jpg"}, {"filename": "g1_main.jpg"}, {"filename": "g1_b.jpg"}]},
            {"group_id": 2, "images": [{"filename": "junk.jpg"}]},
        ],
    }


def test_showcase_order_is_preserved_not_reversed():
    rows = showcase.build_showcase_rows(_fixture())
    assert [r["id"] for r in rows] == [1, 2]  # 저장 순서 유지(역순 아님)


def test_sticker_row_has_two_extra_photos_excluding_main():
    rows = showcase.build_showcase_rows(_fixture())
    r = rows[0]
    assert r["extra_photos"] == ["g1_a.jpg", "g1_b.jpg"]  # 메인 제외, 파일 순서
    assert r["number"] == "112"
    assert r["has_sticker"] is True


def test_irrelevant_row_has_no_extra_photos():
    rows = showcase.build_showcase_rows(_fixture())
    r = rows[1]
    assert r["extra_photos"] == []
    assert r["defect_level"] == "관련없음"
    assert r["number"] == "-"


def test_non_showcase_falls_back_to_sticker_filter_reversed():
    data = {
        "results": [
            {"id": 1, "timestamp": "t", "filename": "a.jpg", "group_id": 0,
             "has_sticker": True, "sticker_number": "1", "sticker_color": "초록색", "defect_level": "정상"},
            {"id": 2, "timestamp": "t", "filename": "b.jpg", "group_id": 0,
             "has_sticker": False, "sticker_number": None, "sticker_color": None, "defect_level": "미확인"},
        ],
        "groups": [],
    }
    rows = showcase.build_showcase_rows(data)
    assert [r["id"] for r in rows] == [1]  # 무스티커 제외
```

- [ ] **Step 3: 테스트 실패 확인**

Run: `cd student_template && python -m pytest tests/test_showcase.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'showcase'`

- [ ] **Step 4: 최소 구현**

Create `student_template/showcase.py`:
```python
"""대시보드 결과 표(쇼케이스) 렌더링 — 순수 모듈(부작용 없음).

app.py 가 이미지 data-URI 함수(_img_data_uri)를 주입해 호출한다.
config/gradio 등 무거운 의존성을 임포트하지 않으므로 단위 테스트가 쉽다.
"""


def build_showcase_rows(data: dict) -> list:
    """results.json dict → 표시용 행 dict 리스트.

    data["showcase"]가 참이면 저장된 순서 그대로(큐레이션) 전부 사용.
    아니면 기존 동작(스티커 있는 것만, 최근 20, 역순).
    각 행에 소속 그룹에서 메인을 뺀 '남은 사진' 최대 2장을 붙인다.
    """
    results = data.get("results", [])
    groups_by_id = {g.get("group_id"): g for g in data.get("groups", [])}

    if data.get("showcase"):
        selected = list(results)
    else:
        selected = [r for r in results if r.get("has_sticker")][-20:][::-1]

    rows = []
    for r in selected:
        defect = r.get("defect_level") or "-"
        has_sticker = bool(r.get("has_sticker"))
        # 관련없음/무스티커는 펼칠 그룹 사진이 없음
        if has_sticker and defect != "관련없음":
            group = groups_by_id.get(r.get("group_id"), {})
            extras = [im.get("filename") for im in group.get("images", [])
                      if im.get("filename") and im.get("filename") != r.get("filename")]
            extra_photos = extras[:2]
        else:
            extra_photos = []
        rows.append({
            "id": r.get("id"),
            "timestamp": r.get("timestamp", ""),
            "filename": r.get("filename", ""),
            "has_sticker": has_sticker,
            "number": r.get("sticker_number") or "-",
            "color": r.get("sticker_color") or "-",
            "defect_level": defect,
            "extra_photos": extra_photos,
        })
    return rows
```

- [ ] **Step 5: 테스트 통과 확인**

Run: `cd student_template && python -m pytest tests/test_showcase.py -v`
Expected: 4 passed

- [ ] **Step 6: 커밋**

```bash
git add student_template/showcase.py student_template/tests/conftest.py student_template/tests/test_showcase.py
git commit -m "feat(showcase): build_showcase_rows 순수 행 구성 + 테스트"
```

---

## Task 2: `showcase.py` — `render_results_html` (배지·토글 렌더)

**Files:**
- Modify: `student_template/showcase.py`
- Test: `student_template/tests/test_showcase.py`

- [ ] **Step 1: 실패하는 렌더 테스트 추가**

Append to `student_template/tests/test_showcase.py`:
```python
def _stub_uri(filename, max_size, quality=80):
    return ""  # 이미지 없음 → 구조만 검증


def test_render_sticker_row_has_toggle_and_expand_row():
    rows = [{
        "id": 7, "timestamp": "t", "filename": "m.jpg", "has_sticker": True,
        "number": "112", "color": "초록색", "defect_level": "정상",
        "extra_photos": ["x1.jpg", "x2.jpg"],
    }]
    html = showcase.render_results_html(rows, _stub_uri)
    assert 'href="#exp7"' in html        # 토글 앵커
    assert 'id="exp7"' in html           # 펼침 행
    assert 'colspan="7"' in html         # 전체 폭
    assert "x1.jpg" in html and "x2.jpg" in html
    assert "b-normal" in html            # 정상 배지


def test_render_irrelevant_row_has_no_toggle_and_badge():
    rows = [{
        "id": 9, "timestamp": "t", "filename": "junk.jpg", "has_sticker": False,
        "number": "-", "color": "-", "defect_level": "관련없음", "extra_photos": [],
    }]
    html = showcase.render_results_html(rows, _stub_uri)
    assert 'href="#exp9"' not in html    # 토글 없음
    assert 'id="exp9"' not in html       # 펼침 행 없음
    assert "b-irrelevant" in html        # 관련없음 배지
    assert "관련없음" in html


def test_render_empty_shows_placeholder():
    html = showcase.render_results_html([], _stub_uri)
    assert "분석 결과가 없습니다" in html
```

- [ ] **Step 2: 테스트 실패 확인**

Run: `cd student_template && python -m pytest tests/test_showcase.py -v`
Expected: FAIL — `AttributeError: module 'showcase' has no attribute 'render_results_html'`

- [ ] **Step 3: 렌더러 구현 (showcase.py 에 추가)**

Append to `student_template/showcase.py`:
```python
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
.b-irrelevant{background:#e5e7eb;color:#4b5563}
.cdot{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:5px;vertical-align:middle;border:1px solid rgba(0,0,0,.15)}
.stoggle{display:inline-block;min-width:34px;padding:2px 8px;border-radius:7px;background:#eef2ff;color:#3730a3;font-weight:700;text-decoration:none;border:1px solid #c7d2fe}
.stoggle:hover{background:#e0e7ff}
.exp-row{display:none}
.exp-row:target{display:table-row}
.exp-row td{background:#f8fafc;text-align:left}
.exp-wrap{display:flex;align-items:center;gap:14px;flex-wrap:wrap;padding:4px 2px}
.exp-label{font-size:12px;font-weight:600;color:#475569;margin-right:4px}
.exp-item{display:flex;align-items:center;gap:6px}
.exp-thumb{width:64px;height:64px;object-fit:cover;border-radius:6px;border:1px solid #cbd5e1}
.exp-name{font-family:ui-monospace,monospace;font-size:10px;color:#64748b}
.exp-close{margin-left:auto;font-size:12px;color:#64748b;text-decoration:none;border:1px solid #cbd5e1;border-radius:6px;padding:2px 8px}
</style>
"""

_BADGE_CLASS = {"정상": "b-normal", "경미한 불량": "b-minor",
                "심각한 불량": "b-severe", "관련없음": "b-irrelevant"}
_COLOR_HEX = {"초록색": "#22c55e", "노란색": "#eab308", "빨간색": "#ef4444"}


def _badge(level: str) -> str:
    cls = _BADGE_CLASS.get(level, "")
    return f'<span class="badge {cls}">{level}</span>' if cls else (level or "-")


def _color_cell(color: str) -> str:
    hx = _COLOR_HEX.get(color)
    dot = f'<span class="cdot" style="background:{hx}"></span>' if hx else ""
    return f'{dot}{color or "-"}'


def render_results_html(rows, img_uri) -> str:
    """행 dict 리스트 → 썸네일·라이트박스·스티커 토글(남은 2장) 포함 HTML 표.

    img_uri(filename, max_size, quality) -> data URI 문자열(없으면 "").
    """
    if not rows:
        return _RESULTS_CSS + (
            '<p style="color:#6b7280;padding:12px">아직 분석 결과가 없습니다. '
            '이미지를 업로드하고 분석을 시작하세요.</p>'
        )

    body, boxes = [], []
    for row in rows:
        rid = row["id"]
        filename = row["filename"]
        number = row["number"]
        color = row["color"]
        defect = row["defect_level"]
        extras = row.get("extra_photos") or []

        thumb = img_uri(filename, 40, 70)
        big = img_uri(filename, 1000, 82)
        if thumb:
            thumb_html = f'<a href="#lb{rid}"><img class="res-thumb" src="{thumb}" title="클릭하여 확대"></a>'
            boxes.append(
                f'<div id="lb{rid}" class="lb"><a class="lb-bg" href="#_"></a>'
                f'<a class="lb-x" href="#_">&times;</a><img src="{big}">'
                f'<div class="lb-cap">{filename} · 번호 {number} · {color} · {defect}</div></div>'
            )
        else:
            thumb_html = '<span class="res-noimg">없음</span>'

        # 스티커 칸: 정상/경미/심각 = 토글, 관련없음/무스티커 = X
        if extras:
            sticker_cell = f'<a class="stoggle" href="#exp{rid}" title="남은 사진 2장 보기">O ▾</a>'
        elif row.get("has_sticker"):
            sticker_cell = "O"
        else:
            sticker_cell = "X"

        body.append(
            f'<tr><td>{rid}</td><td>{row["timestamp"]}</td>'
            f'<td class="fname">{thumb_html}{filename}</td>'
            f'<td>{sticker_cell}</td><td>{number}</td><td>{_color_cell(color)}</td>'
            f'<td>{_badge(defect)}</td></tr>'
        )

        if extras:
            items = []
            for ex in extras:
                ex_uri = img_uri(ex, 120, 75)
                img_tag = (f'<img class="exp-thumb" src="{ex_uri}">' if ex_uri
                           else '<span class="res-noimg">없음</span>')
                items.append(f'<span class="exp-item">{img_tag}<span class="exp-name">{ex}</span></span>')
            body.append(
                f'<tr id="exp{rid}" class="exp-row"><td colspan="7"><div class="exp-wrap">'
                f'<span class="exp-label">남은 사진 {len(extras)}장 (파일 순서)</span>'
                f'{"".join(items)}<a class="exp-close" href="#_">✕ 닫기</a>'
                f'</div></td></tr>'
            )

    return (
        _RESULTS_CSS
        + '<div class="res-wrap"><table class="res-tbl">'
        + '<thead><tr><th>ID</th><th>시간</th><th>미리보기 · 파일명</th>'
        + '<th>스티커</th><th>번호</th><th>색상</th><th>불량 수준</th></tr></thead>'
        + '<tbody>' + ''.join(body) + '</tbody></table></div>'
        + ''.join(boxes)
    )
```

- [ ] **Step 4: 테스트 통과 확인**

Run: `cd student_template && python -m pytest tests/test_showcase.py -v`
Expected: 7 passed

- [ ] **Step 5: 커밋**

```bash
git add student_template/showcase.py student_template/tests/test_showcase.py
git commit -m "feat(showcase): 관련없음 배지 + 스티커 토글(남은 2장) 렌더러 + 테스트"
```

---

## Task 3: `app.py` 배선 — showcase 위임

**Files:**
- Modify: `student_template/app.py` (함수 `get_dashboard_data` ~189-232, `_RESULTS_CSS`/`_badge`/`_color_cell`/`render_results_html` ~254-332, 호출부 434·439)

- [ ] **Step 1: import 추가**

`app.py` 상단 import 블록(예: `import config` 다음 줄)에 추가:
```python
import showcase
```

- [ ] **Step 2: 옛 렌더/배지/CSS 정의 삭제**

`app.py`에서 다음 정의를 **삭제**한다(showcase.py 로 이전됨): `_RESULTS_CSS = """..."""`(약 254-274), `def _badge(...)`(277-279), `def _color_cell(...)`(282-285), `def render_results_html(rows)`(288-332). `def _img_data_uri(...)`(235-251)는 **유지**.

- [ ] **Step 3: `get_dashboard_data` 를 dict 행 기반으로 교체**

`def get_dashboard_data():` 본문(189-232)을 아래로 교체:
```python
def get_dashboard_data():
    """대시보드 표시 데이터: (행 dict 리스트, stats, total, normal, minor, severe)."""
    data = load_results()
    rows = showcase.build_showcase_rows(data)
    if not rows:
        return [], {}, 0, 0, 0, 0

    normal = sum(1 for r in rows if r["defect_level"] == "정상")
    minor = sum(1 for r in rows if r["defect_level"] == "경미한 불량")
    severe = sum(1 for r in rows if r["defect_level"] == "심각한 불량")
    total = len(rows)
    stats = {"정상 (초록색)": normal, "경미한 불량 (노란색)": minor, "심각한 불량 (빨간색)": severe}
    return rows, stats, total, normal, minor, severe
```

- [ ] **Step 4: 렌더 호출부 2곳 갱신 (`_img_data_uri` 주입)**

라인 434 `results_table = gr.HTML(value=render_results_html([]))` →
```python
        results_table = gr.HTML(value=showcase.render_results_html([], _img_data_uri))
```
라인 439 `return render_results_html(table_data), total, normal, minor, severe` →
```python
            return showcase.render_results_html(table_data, _img_data_uri), total, normal, minor, severe
```

- [ ] **Step 5: 스모크 테스트 — import 및 데이터 함수 동작**

Run:
```bash
cd student_template && python -c "import app; rows,*_ = app.get_dashboard_data(); print('rows', len(rows)); print(app.showcase.render_results_html(rows, app._img_data_uri)[:60])"
```
Expected: 오류 없이 `rows N` 출력 + HTML 시작 문자열 출력. (현재 시드 기준 N>0)

- [ ] **Step 6: 전체 테스트 재확인 + 커밋**

```bash
cd student_template && python -m pytest tests/ -v   # 7 passed
git add student_template/app.py
git commit -m "refactor(app): 결과 렌더를 showcase 모듈로 위임 + dict 행"
```

---

## Task 4: `build_showcase.py` — 큐레이션 20행 데이터 생성

**Files:**
- Create: `teacher_tools/build_showcase.py`

- [ ] **Step 1: 빌더 스크립트 작성**

Create `teacher_tools/build_showcase.py`:
```python
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
    ("severe",     "gray",  "20240817_000444.jpg", "251", "-",     ["20240817_000433.jpg", "20240817_000459.jpg"]),
    ("normal",     "blur",  "20240817_000227.jpg", "104", "초록색", ["20240817_000216.jpg", "20240817_000238.jpg"]),
    ("irrelevant", "irr",   "c92257_99.jpg", "-", "-", []),
    ("normal",     "color", "20240817_000148.jpg", "103", "초록색", ["20240817_000138.jpg", "20240817_000204.jpg"]),
    ("minor",      "gray",  "20240817_000512.jpg", "252", "-",     ["20240817_000501.jpg", "20240817_000546.jpg"]),
    ("normal",     "color", "20240817_000249.jpg", "105", "초록색", ["20240817_000241.jpg", "20240817_000314.jpg"]),
    ("irrelevant", "irr",   "dmbt6_34031327_D00_SPI00.jpg", "-", "-", []),
    ("severe",     "blur",  "20240817_000650.jpg", "253", "-",     ["20240817_000642.jpg", "20240817_000707.jpg"]),
    ("normal",     "gray",  "20240817_000625.jpg", "601", "초록색", ["20240817_000552.jpg", "20240817_000639.jpg"]),
    ("minor",      "blur",  "20240817_000717.jpg", "254", "-",     ["20240817_000710.jpg", "20240817_000731.jpg"]),
    ("normal",     "color", "20240817_000408.jpg", "106", "초록색", ["20240817_000355.jpg", "20240817_000431.jpg"]),
    ("irrelevant", "irr",   "SMNM20111906_main3.jpg", "-", "-", []),
    ("normal",     "blur",  "20240817_000116.jpg", "256", "초록색", ["20240817_000108.jpg", "20240817_000136.jpg"]),
    ("severe",     "gray",  "20240817_000148.jpg", "255", "-",     ["20240817_000138.jpg", "20240817_000204.jpg"]),
    ("normal",     "gray",  "20240817_000249.jpg", "257", "초록색", ["20240817_000241.jpg", "20240817_000314.jpg"]),
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
    for i, (cat, variant, main_base, number, color, neighbors) in enumerate(SHOW, start=1):
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
```

- [ ] **Step 2: 빌더 실행**

Run: `cd /Users/imdonghyeon/motor-sticker-detection && python teacher_tools/build_showcase.py`
Expected: `[완료] 쇼케이스 20행 생성: {'정상': 9, '관련없음': 5, '경미한 불량': 3, '심각한 불량': 3}` 및 `포함 확인 000743: True`

- [ ] **Step 3: 산출물 구조 검증**

Run:
```bash
cd /Users/imdonghyeon/motor-sticker-detection && python -c "
import json; d=json.load(open('student_template/data/seed/results.json'))
assert d.get('showcase') is True
assert len(d['results'])==20, len(d['results'])
levels={r['defect_level'] for r in d['results']}
assert levels=={'정상','경미한 불량','심각한 불량','관련없음'}, levels
assert any('000743' in r['filename'] for r in d['results'])
# 스티커 그룹은 3장, 관련없음은 1장
for g in d['groups']:
    n=len(g['images']); assert (n==3) or (g['status']=='관련없음' and n==1), (g['group_id'],n)
print('OK', len(d['results']), 'rows', sorted(levels))
"
```
Expected: `OK 20 rows ['경미한 불량', '관련없음', '심각한 불량', '정상']`

- [ ] **Step 4: 커밋 (스크립트 + 재생성된 시드/업로드)**

```bash
cd /Users/imdonghyeon/motor-sticker-detection
git add teacher_tools/build_showcase.py student_template/data/seed/results.json student_template/data/seed/uploads
git add -f student_template/data/seed/uploads   # uploads 가 gitignore 면 강제(시드 번들은 커밋 대상)
git commit -m "feat(showcase): 큐레이션 20행 빌더 + 재생성된 시드 번들"
```
> 주의: `git status` 로 `student_template/data/results.json`·`data/uploads/`(로컬용)가 .gitignore 대상인지 확인. 기존 시드 커밋 관례를 따른다(로컬 산출물은 커밋 제외 가능).

---

## Task 5: 시각 검증 (Gradio 토글·배지 육안 확인)

**Files:** 없음(검증 전용). 문제 발견 시 해당 Task 로 돌아가 수정.

- [ ] **Step 1: 앱 기동**

Run (백그라운드): `cd student_template && python app.py`
- GPT 키 없어도 대시보드는 시드 데이터로 렌더됨(분석 버튼만 비활성 의미). Gradio: `http://localhost:7860`.

- [ ] **Step 2: 대시보드 확인 (gstack-browse 스킬 사용)**

`gstack-browse` 스킬로 `http://localhost:7860` 열고 스크린샷:
- 표에 정상/경미한 불량/심각한 불량/관련없음 배지가 섞여 보임.
- 1번 행 = `..._000743.jpg`(번호 112, 초록, 정상).
- 정상/경미/심각 행 스티커 칸에 `O ▾` 토글, 관련없음 행은 `X`.

- [ ] **Step 3: 토글 동작 확인**

`O ▾` 클릭 → 바로 아래 펼침 행에 남은 사진 2장(파일 순서) + `✕ 닫기` 표시. `✕ 닫기` 클릭 시 접힘. (CSS `:target` — 한 번에 한 행 펼침)
- 만약 펼침 행이 안 나오면(살균 의심): showcase.py 의 토글을 `<details><summary>` 방식으로 교체 후 Task 2 테스트 재실행.

- [ ] **Step 4: 회귀 확인**

메인 썸네일 클릭 → 기존 라이트박스 확대 정상. "새로고침" 클릭 → 표 유지. 앱 종료.

- [ ] **Step 5: (수정 발생 시) 커밋**

```bash
git add -A && git commit -m "fix(showcase): 시각 검증 반영"
```

---

## Self-Review (작성자 점검 완료)

- **Spec coverage:** 4종 등급(Task4 데이터+Task2 배지) · 토글 남은 2장(Task1 extras+Task2 렌더+Task5 검증) · 임의 배치(Task4 SHOW 순서, build_showcase_rows 역순 안 함) · 흑백/블러 포함 무배지(Task4 variant, 별도 배지 없음) · 000743 포함(Task4 1행 + Step3 assert) — 모두 매핑됨.
- **No placeholders:** 모든 스텝에 실제 코드/명령/기대출력 포함. 큐레이션 20행은 SHOW 리터럴로 전량 명시.
- **Type consistency:** 행 dict 키(id/timestamp/filename/has_sticker/number/color/defect_level/extra_photos)가 Task1·2·3 전반 일치. `render_results_html(rows, img_uri)` 시그니처가 Task2 정의·Task3 호출 일치. `build_showcase_rows(data)` 일치.
- **가정:** 심각한 불량 = 흑백/블러에 라벨만(색 "-"); 관련없음 토글 없음; 통계 카드 3종 유지(관련없음 카드 없음).
