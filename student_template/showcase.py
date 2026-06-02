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
            for j, ex in enumerate(extras):
                ex_thumb = img_uri(ex, 96, 75)
                ex_big = img_uri(ex, 1000, 82)
                if ex_thumb:
                    lbe = f"lbe{rid}_{j}"
                    img_tag = (f'<a href="#{lbe}"><img class="exp-thumb" src="{ex_thumb}" '
                               f'title="클릭하여 확대"></a>')
                    boxes.append(
                        f'<div id="{lbe}" class="lb"><a class="lb-bg" href="#_"></a>'
                        f'<a class="lb-x" href="#_">&times;</a><img src="{ex_big}">'
                        f'<div class="lb-cap">{ex}</div></div>'
                    )
                else:
                    img_tag = '<span class="res-noimg">없음</span>'
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

