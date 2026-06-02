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
