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
