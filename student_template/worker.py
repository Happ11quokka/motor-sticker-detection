"""
백그라운드 이미지 분석 워커 (LangSmith 통합)

3개씩 이미지를 그룹으로 묶어 분석하고,
스티커가 있는 이미지를 찾아 불량 수준을 판정합니다.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from queue import Queue

from openai import OpenAI
from langsmith import traceable
from langsmith.wrappers import wrap_openai

import config
from models import (
    file_lock,
    load_results_unsafe,
    encode_image,
    determine_defect_level
)


# LangSmith 환경변수 설정
if config.LANGSMITH_TRACING and config.LANGSMITH_API_KEY:
    os.environ["LANGSMITH_API_KEY"] = config.LANGSMITH_API_KEY
    os.environ["LANGSMITH_PROJECT"] = config.LANGSMITH_PROJECT
    os.environ["LANGSMITH_TRACING"] = "true"
    print(f"[LangSmith] 추적 활성화: {config.LANGSMITH_PROJECT}")


# OpenAI 클라이언트 생성
if config.API_BASE_URL == "https://api.openai.com/v1":
    client = OpenAI(api_key=config.API_KEY)
else:
    # 커스텀 GPU 서버를 사용할 때만 base_url 설정
    client = OpenAI(
        base_url=config.API_BASE_URL,
        api_key=config.API_KEY
    )

# LangSmith 래핑 (추적 활성화시)
if config.LANGSMITH_TRACING and config.LANGSMITH_API_KEY:
    client = wrap_openai(client)
    print("[LangSmith] OpenAI 클라이언트 래핑 완료")


# 전역 큐 (app.py에서 이미지를 추가)
image_queue = Queue()


@traceable(
    name="analyze_sticker",
    run_type="llm",
    metadata={"component": "vision_analysis"}
)
def analyze_sticker(image_path: Path) -> dict:
    """
    Vision Model API를 사용하여 이미지에서 스티커 정보 추출
    (LangSmith 추적 포함)

    Args:
        image_path: 분석할 이미지 경로

    Returns:
        스티커 정보 딕셔너리 {has_sticker, number, color}
    """
    base64_image = encode_image(image_path)

    prompt = """
    이 이미지를 분석해주세요:
    1. 스티커가 있습니까? (예/아니오)
    2. 스티커가 있다면:
       - 스티커에 쓰여진 번호는 무엇입니까? (손글씨로 쓰여진 숫자)
       - 스티커의 색깔은 무엇입니까? (초록색/노란색/빨간색 중 하나)

    다음 JSON 형식으로만 답변해주세요:
    {
        "has_sticker": true/false,
        "number": "숫자" 또는 null,
        "color": "초록색"/"노란색"/"빨간색" 또는 null
    }
    """

    try:
        response = client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": "당신은 이미지 분석 전문가입니다. 스티커 정보를 정확히 추출하여 JSON 형식으로만 응답하세요."
                },
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "text",
                            "text": prompt
                        },
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:image/jpeg;base64,{base64_image}"
                            }
                        }
                    ]
                }
            ],
            max_tokens=150,
            temperature=0.1
        )

        result_text = response.choices[0].message.content.strip()
        print(f"[DEBUG] API 응답: {result_text}")

        if "```json" in result_text:
            result_text = result_text.split("```json")[1].split("```")[0].strip()
        elif "```" in result_text:
            result_text = result_text.split("```")[1].strip()

        result = json.loads(result_text)
        return result

    except Exception as e:
        import traceback
        print(f"분석 오류: {e}")
        print(f"상세 오류:\n{traceback.format_exc()}")
        return {"has_sticker": False, "number": None, "color": None, "error": str(e)}


@traceable(
    name="analyze_image_group",
    run_type="chain",
    metadata={"component": "group_analysis"}
)
def analyze_image_group(images: list) -> dict:
    """
    3개 이미지 그룹을 분석하여 스티커가 있는 이미지 찾기
    (LangSmith 추적 포함)

    Args:
        images: 이미지 정보 리스트 (filename, path, upload_time)

    Returns:
        그룹 분석 결과 딕셔너리
    """
    # 그룹 ID 생성 (락 사용)
    with file_lock:
        data = load_results_unsafe()
        group_id = len(data.get("groups", [])) + 1

    print(f"\n[그룹 {group_id} 분석 시작] 이미지 {len(images)}개")

    results = []
    sticker_found = None

    # 각 이미지 분석 (LangSmith가 자동으로 추적)
    for idx, img_info in enumerate(images):
        print(f"  이미지 {idx+1}/{len(images)}: {img_info['filename']} 분석 중...")

        try:
            sticker_info = analyze_sticker(Path(img_info['path']))

            if sticker_info["has_sticker"]:
                sticker_found = {
                    "filename": img_info['filename'],
                    "number": sticker_info.get("number"),
                    "color": sticker_info.get("color")
                }
                print(f"    ✓ 스티커 발견! (번호: {sticker_info.get('number')}, 색: {sticker_info.get('color')})")

            results.append({
                "filename": img_info['filename'],
                "has_sticker": sticker_info["has_sticker"],
                "sticker_number": sticker_info.get("number"),
                "sticker_color": sticker_info.get("color")
            })

        except Exception as e:
            print(f"    ✗ 분석 오류: {e}")
            results.append({
                "filename": img_info['filename'],
                "has_sticker": False,
                "error": str(e)
            })

    # 그룹 결과 구성
    group_result = {
        "group_id": group_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "images": results,
        "sticker_info": sticker_found,
        "defect_level": determine_defect_level(sticker_found["color"]) if sticker_found else None,
        "status": "정상" if len(results) == 3 and sticker_found else "오류"
    }

    # 결과 저장
    with file_lock:
        try:
            data = load_results_unsafe()
            if "groups" not in data:
                data["groups"] = []
            data["groups"].append(group_result)
            data["total_images"] = data.get("total_images", 0) + len(images)

            # 개별 이미지 결과도 저장 (대시보드 호환성)
            if "results" not in data:
                data["results"] = []

            if sticker_found:
                data["results"].append({
                    "id": len(data["results"]) + 1,
                    "timestamp": group_result["timestamp"],
                    "filename": sticker_found["filename"],
                    "group_id": group_id,
                    "has_sticker": True,
                    "sticker_number": sticker_found["number"],
                    "sticker_color": sticker_found["color"],
                    "defect_level": group_result["defect_level"]
                })

            with open(config.RESULTS_FILE, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)

            print(f"[저장 완료] 그룹 {group_id} 결과 저장됨")
        except Exception as e:
            print(f"[ERROR] 결과 저장 실패: {e}")
            import traceback
            print(traceback.format_exc())

    print(f"[그룹 {group_id} 완료] 불량 수준: {group_result['defect_level']}\n")

    return group_result


def background_worker():
    """
    백그라운드에서 3개씩 이미지를 분석하는 워커

    큐에서 이미지를 가져와서 3개가 모이면 분석을 시작합니다.
    """
    import traceback
    print("[워커 시작] 이미지 분석 백그라운드 워커 실행 중...")

    pending_images = []

    while True:
        try:
            # 큐에서 이미지 가져오기 (1초 타임아웃)
            img_info = image_queue.get(timeout=1)
            pending_images.append(img_info)

            print(f"[워커] 이미지 수신: {img_info['filename']} | 대기 중: {len(pending_images)}/3")

            # 3개가 모이면 분석 시작
            if len(pending_images) >= 3:
                print(f"[워커] 3개 모임! 분석 시작...")
                group = pending_images[:3]
                pending_images = pending_images[3:]

                try:
                    # LangSmith가 자동으로 추적
                    analyze_image_group(group)
                except Exception as analysis_error:
                    print(f"[워커 분석 오류] {analysis_error}")
                    print(traceback.format_exc())

        except Exception as e:
            # 타임아웃은 정상 (큐가 비어있음)
            error_type = str(type(e).__name__)
            if "Empty" not in error_type:
                print(f"[워커 큐 오류] {error_type}: {e}")
                print(traceback.format_exc())
            continue
