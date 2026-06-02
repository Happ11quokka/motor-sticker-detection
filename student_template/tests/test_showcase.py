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
