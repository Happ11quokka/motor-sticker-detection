"""
백그라운드 이미지 분석 워커 (LangSmith 통합)

3개씩 이미지를 그룹으로 묶어 분석하고,
스티커가 있는 이미지를 찾아 불량 수준을 판정합니다.
"""
import json
import os
import time
from datetime import datetime
from pathlib import Path
from queue import Queue

from openai import OpenAI
from langsmith import traceable
from langsmith.wrappers import wrap_openai

import config
from models import (
    file_lock,
    load_results,
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
    metadata={
        "component": "vision_analysis",
        "model": config.MODEL_NAME,
        "provider": "runpod" if "runpod" in config.API_BASE_URL else "openai"
    }
)
def analyze_sticker(image_path: Path, max_retries: int = 3) -> dict:
    """
    Vision Model API를 사용하여 이미지에서 스티커 정보 추출
    (LangSmith 추적 포함, 재시도 로직 포함)

    Args:
        image_path: 분석할 이미지 경로
        max_retries: 최대 재시도 횟수 (502 오류 등 일시적 오류 대응)

    Returns:
        스티커 정보 딕셔너리 {has_sticker, number, color}
    """
    base64_image = encode_image(image_path)

    prompt = """
    이 이미지에서 **모터 부품에 부착된** 품질 검사용 원형 스티커를 찾아주세요.

    [1단계: 이미지 유효성 검사 - 가장 먼저 확인!]
    이 이미지가 모터/기계 부품의 **스티커가 부착된 외부 커버** 사진인지 먼저 확인하세요.

    다음과 같은 이미지는 has_sticker: false로 판정하세요:
    - 스티커 시트/스티커 판매 이미지 (여러 스티커가 시트에 나열된 경우)
    - 안내판, 게시판, 포스터, 인쇄물
    - 사무용품, 문구류 이미지
    - 모터/기계 부품이 아닌 일반 물체
    - 손가락으로 스티커를 들고 있는 상품 사진
    - 모터 내부 사진 (케이블, 배선, 기어, 코일 등만 보이는 경우)
    - 카메라/모니터 화면을 찍은 사진 (화면 테두리, UI, 날짜/시간 표시가 보이는 경우)
    - 스티커가 보이지 않는 모터 부품 사진

    오직 **금속 모터 부품 외부 커버에 직접 부착된 원형 스티커**만 인식하세요!
    스티커는 보통 DANGER 경고 라벨 옆에 있습니다.

    [2단계: 모터 부품인 경우, 스티커 특징 확인]
    - 원형의 색깔 스티커 (초록색, 노란색, 또는 빨간색)
    - 스티커 위에 손글씨로 쓰여진 2~3자리 숫자 (예: 96, 102, 505 등)
    - 숫자 아래에 밑줄이 그어져 있을 수 있음 (밑줄은 숫자가 아님)
    - DANGER 경고 라벨은 스티커가 아닙니다! 원형 색깔 스티커만 찾으세요.
    - 모터 부품에는 보통 DANGER 경고 스티커가 함께 있습니다.

    [중요! 숫자 인식 방법]
    1. 이미지나 스티커가 거꾸로(180도 회전) 되어 있을 수 있습니다!
    2. 숫자를 읽을 때 반드시 올바른 방향으로 읽어주세요:
       - 숫자가 뒤집어져 있으면 정방향으로 돌려서 읽으세요
       - 예: 뒤집어진 "96"은 → "96"으로 읽어야 합니다
       - 예: 뒤집어진 "505"는 → "505"로 읽어야 합니다
    3. 밑줄이 있다면, 밑줄이 아래에 오도록 방향을 정하세요
    4. 손글씨 숫자는 보통 2~3자리입니다
    5. 숫자 '1'은 세로 막대 형태로, 밑줄과 구분해주세요

    [색상 판별 방법 - 반드시 초록색/노란색/빨간색 중 하나로 답변!]
    색상은 반드시 "초록색", "노란색", "빨간색" 중 하나만 선택하세요.
    "흰색", "회색", "white", "gray" 등은 절대 사용하지 마세요!

    1. 컬러 이미지인 경우: 스티커의 실제 색상을 직접 확인
       - 초록색, 노란색, 빨간색 중 하나

    2. 흑백/grayscale 이미지인 경우 (색상 정보가 없음):
       스티커의 밝기(brightness)로 원래 색상을 추론하세요:
       - 가장 밝은 회색/흰색에 가까운 스티커 → "초록색" (초록색이 흑백에서 가장 밝게 보임)
       - 중간 밝기의 회색 스티커 → "노란색"
       - 어두운 회색 스티커 → "빨간색" (빨간색이 흑백에서 가장 어둡게 보임)

    3. 스티커가 보이지 않는 경우에만 null로 설정하세요
       (스티커가 보이면 반드시 초록색/노란색/빨간색 중 하나를 선택!)

    다음 JSON 형식으로만 답변해주세요:
    {
        "has_sticker": true/false,
        "number": "숫자" 또는 null,
        "color": "초록색"/"노란색"/"빨간색" 또는 null
    }
    """

    last_error = None

    for attempt in range(max_retries):
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

            # Qwen 모델의 <think> 태그 제거 (thinking 모드 응답 처리)
            if "<think>" in result_text and "</think>" in result_text:
                result_text = result_text.split("</think>")[-1].strip()

            if "```json" in result_text:
                result_text = result_text.split(
                    "```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].strip()

            result = json.loads(result_text)
            return result

        except Exception as e:
            last_error = e
            error_str = str(e).lower()

            # 502 Bad Gateway 또는 서버 오류인 경우 재시도
            if "502" in error_str or "bad gateway" in error_str or "500" in error_str or "503" in error_str:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2  # 2초, 4초, 6초...
                    print(
                        f"[재시도 {attempt + 1}/{max_retries}] 서버 오류 발생, {wait_time}초 후 재시도...")
                    time.sleep(wait_time)
                    continue

            # 다른 오류는 바로 종료
            break

    import traceback
    print(f"분석 오류: {last_error}")
    print(f"상세 오류:\n{traceback.format_exc()}")
    return {"has_sticker": False, "number": None, "color": None, "error": str(last_error)}


@traceable(
    name="analyze_sticker_with_thinking",
    run_type="llm",
    metadata={
        "component": "vision_analysis_reanalyze",
        "model": config.MODEL_NAME,
        "provider": "runpod" if "runpod" in config.API_BASE_URL else "openai",
        "mode": "thinking"
    }
)
def analyze_sticker_with_thinking(image_path: Path, max_retries: int = 3) -> dict:
    """
    Vision Model API를 사용하여 이미지에서 스티커 정보 추출 (재분석용)
    thinking 모드 활성화 및 temperature=0.7로 더 창의적인 분석 수행

    Args:
        image_path: 분석할 이미지 경로
        max_retries: 최대 재시도 횟수

    Returns:
        스티커 정보 딕셔너리 {has_sticker, number, color}
    """
    base64_image = encode_image(image_path)

    prompt = """
    이 이미지에서 **모터 부품에 부착된** 품질 검사용 원형 스티커를 찾아주세요.

    [1단계: 이미지 유효성 검사 - 가장 먼저 확인!]
    이 이미지가 모터/기계 부품의 **스티커가 부착된 외부 커버** 사진인지 먼저 확인하세요.

    다음과 같은 이미지는 has_sticker: false로 판정하세요:
    - 스티커 시트/스티커 판매 이미지 (여러 스티커가 시트에 나열된 경우)
    - 안내판, 게시판, 포스터, 인쇄물
    - 사무용품, 문구류 이미지
    - 모터/기계 부품이 아닌 일반 물체
    - 손가락으로 스티커를 들고 있는 상품 사진
    - 모터 내부 사진 (케이블, 배선, 기어, 코일 등만 보이는 경우)
    - 카메라/모니터 화면을 찍은 사진 (화면 테두리, UI, 날짜/시간 표시가 보이는 경우)
    - 스티커가 보이지 않는 모터 부품 사진

    오직 **금속 모터 부품 외부 커버에 직접 부착된 원형 스티커**만 인식하세요!
    스티커는 보통 DANGER 경고 라벨 옆에 있습니다.

    [2단계: 모터 부품인 경우, 스티커 특징 확인]
    - 원형의 색깔 스티커 (초록색, 노란색, 또는 빨간색)
    - 스티커 위에 손글씨로 쓰여진 2~3자리 숫자 (예: 96, 102, 505 등)
    - 숫자 아래에 밑줄이 그어져 있을 수 있음 (밑줄은 숫자가 아님)
    - DANGER 경고 라벨은 스티커가 아닙니다! 원형 색깔 스티커만 찾으세요.
    - 모터 부품에는 보통 DANGER 경고 스티커가 함께 있습니다.

    [중요! 숫자 인식 방법]
    1. 이미지나 스티커가 거꾸로(180도 회전) 되어 있을 수 있습니다!
    2. 숫자를 읽을 때 반드시 올바른 방향으로 읽어주세요:
       - 숫자가 뒤집어져 있으면 정방향으로 돌려서 읽으세요
       - 예: 뒤집어진 "96"은 → "96"으로 읽어야 합니다
       - 예: 뒤집어진 "505"는 → "505"로 읽어야 합니다
    3. 밑줄이 있다면, 밑줄이 아래에 오도록 방향을 정하세요
    4. 손글씨 숫자는 보통 2~3자리입니다
    5. 숫자 '1'은 세로 막대 형태로, 밑줄과 구분해주세요

    [색상 판별 방법 - 반드시 초록색/노란색/빨간색 중 하나로 답변!]
    색상은 반드시 "초록색", "노란색", "빨간색" 중 하나만 선택하세요.
    "흰색", "회색", "white", "gray" 등은 절대 사용하지 마세요!

    1. 컬러 이미지인 경우: 스티커의 실제 색상을 직접 확인
       - 초록색, 노란색, 빨간색 중 하나

    2. 흑백/grayscale 이미지인 경우 (색상 정보가 없음):
       스티커의 밝기(brightness)로 원래 색상을 추론하세요:
       - 가장 밝은 회색/흰색에 가까운 스티커 → "초록색" (초록색이 흑백에서 가장 밝게 보임)
       - 중간 밝기의 회색 스티커 → "노란색"
       - 어두운 회색 스티커 → "빨간색" (빨간색이 흑백에서 가장 어둡게 보임)

    3. 스티커가 보이지 않는 경우에만 null로 설정하세요
       (스티커가 보이면 반드시 초록색/노란색/빨간색 중 하나를 선택!)

    다음 JSON 형식으로만 답변해주세요:
    {
        "has_sticker": true/false,
        "number": "숫자" 또는 null,
        "color": "초록색"/"노란색"/"빨간색" 또는 null
    }
    """

    last_error = None

    for attempt in range(max_retries):
        try:
            # thinking 모드와 temperature=0.7로 재분석
            response = client.chat.completions.create(
                model=config.MODEL_NAME,
                messages=[
                    {
                        "role": "system",
                        "content": "당신은 이미지 분석 전문가입니다. 스티커 정보를 정확히 추출하여 JSON 형식으로만 응답하세요. 깊이 생각하고 신중하게 분석하세요."
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
                max_tokens=8000,  # thinking 출력을 위해 증가
                temperature=0.7,  # 더 창의적인 분석
                extra_body=(
                    {"chat_template_kwargs": {"enable_thinking": True}}
                    if config.API_BASE_URL != "https://api.openai.com/v1"
                    else None  # OpenAI는 chat_template_kwargs를 거부하므로 vLLM/Qwen 서버일 때만 전송
                )
            )

            result_text = response.choices[0].message.content.strip()
            print(f"[DEBUG 재분석] API 응답 (thinking 모드): {result_text[:500]}...")

            # Qwen 모델의 <think> 태그 제거 (thinking 모드 응답 처리)
            if "<think>" in result_text and "</think>" in result_text:
                # thinking 내용 로그 출력 (디버깅용)
                think_content = result_text.split("<think>")[1].split("</think>")[0]
                print(f"[DEBUG 재분석] Thinking 내용: {think_content[:300]}...")
                result_text = result_text.split("</think>")[-1].strip()

            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].strip()

            result = json.loads(result_text)
            return result

        except Exception as e:
            last_error = e
            error_str = str(e).lower()

            # 502 Bad Gateway 또는 서버 오류인 경우 재시도
            if "502" in error_str or "bad gateway" in error_str or "500" in error_str or "503" in error_str:
                if attempt < max_retries - 1:
                    wait_time = (attempt + 1) * 2
                    print(f"[재시도 {attempt + 1}/{max_retries}] 서버 오류 발생, {wait_time}초 후 재시도...")
                    time.sleep(wait_time)
                    continue

            # 다른 오류는 바로 종료
            break

    import traceback
    print(f"재분석 오류: {last_error}")
    print(f"상세 오류:\n{traceback.format_exc()}")
    return {"has_sticker": False, "number": None, "color": None, "error": str(last_error)}


@traceable(
    name="analyze_image_group",
    run_type="chain",
    metadata={
        "component": "group_analysis",
        "model": config.MODEL_NAME,
        "provider": "runpod" if "runpod" in config.API_BASE_URL else "openai"
    }
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
                print(
                    f"    ✓ 스티커 발견! (번호: {sticker_info.get('number')}, 색: {sticker_info.get('color')})")

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
            else:
                # 스티커가 없는 이미지도 "미확인"으로 저장
                for img_result in results:
                    data["results"].append({
                        "id": len(data["results"]) + 1,
                        "timestamp": group_result["timestamp"],
                        "filename": img_result["filename"],
                        "group_id": group_id,
                        "has_sticker": False,
                        "sticker_number": None,
                        "sticker_color": None,
                        "defect_level": "미확인"
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
    백그라운드에서 이미지를 분석하는 워커

    큐에서 이미지를 가져와서 3개가 모이면 분석을 시작합니다.
    3개 미만이라도 일정 시간(3초) 동안 새 이미지가 없으면 분석을 진행합니다.
    """
    import traceback
    print("[워커 시작] 이미지 분석 백그라운드 워커 실행 중...")

    pending_images = []
    idle_count = 0  # 타임아웃 횟수 카운터
    IDLE_THRESHOLD = 3  # 3초 동안 새 이미지가 없으면 남은 이미지 처리

    while True:
        try:
            # 큐에서 이미지 가져오기 (1초 타임아웃)
            img_info = image_queue.get(timeout=1)
            pending_images.append(img_info)
            idle_count = 0  # 이미지 수신 시 카운터 리셋

            print(
                f"[워커] 이미지 수신: {img_info['filename']} | 대기 중: {len(pending_images)}개")

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
            else:
                # 큐가 비어있고, 대기 중인 이미지가 있으면 카운터 증가
                if pending_images:
                    idle_count += 1
                    if idle_count >= IDLE_THRESHOLD:
                        # 3초 동안 새 이미지가 없으면 남은 이미지 분석
                        print(f"[워커] {len(pending_images)}개 이미지 대기 중, 타임아웃으로 분석 시작...")
                        group = pending_images
                        pending_images = []
                        idle_count = 0

                        try:
                            analyze_image_group(group)
                        except Exception as analysis_error:
                            print(f"[워커 분석 오류] {analysis_error}")
                            print(traceback.format_exc())
            continue


def reanalyze_image(result_id: int) -> dict:
    """
    특정 이미지를 재분석하고 결과 업데이트

    Args:
        result_id: 재분석할 결과의 ID

    Returns:
        재분석 결과 딕셔너리
    """
    import json

    with file_lock:
        data = load_results_unsafe()
        results = data.get("results", [])

        # ID로 결과 찾기
        target_result = None
        target_idx = None
        for idx, r in enumerate(results):
            if r.get("id") == result_id:
                target_result = r
                target_idx = idx
                break

        if not target_result:
            return {"success": False, "message": f"ID {result_id}를 찾을 수 없습니다."}

        filename = target_result.get("filename")

        # 파일 경로 찾기
        file_path = config.UPLOAD_DIR / filename
        if not file_path.exists():
            return {"success": False, "message": f"파일을 찾을 수 없습니다: {filename}"}

    # 재분석 수행 (락 밖에서) - thinking 모드와 temperature=0.7로 더 신중하게 분석
    print(f"[재분석] ID {result_id}: {filename} 재분석 시작 (thinking 모드)...")
    new_analysis = analyze_sticker_with_thinking(file_path)

    # 결과 업데이트
    with file_lock:
        data = load_results_unsafe()
        results = data.get("results", [])

        for idx, r in enumerate(results):
            if r.get("id") == result_id:
                old_number = r.get("sticker_number")
                old_color = r.get("sticker_color")

                r["has_sticker"] = new_analysis.get("has_sticker", False)
                r["sticker_number"] = new_analysis.get("number")
                r["sticker_color"] = new_analysis.get("color")
                r["defect_level"] = determine_defect_level(new_analysis.get("color"))
                r["reanalyzed"] = True

                with open(config.RESULTS_FILE, "w", encoding="utf-8") as f:
                    json.dump(data, f, ensure_ascii=False, indent=2)

                return {
                    "success": True,
                    "id": result_id,
                    "filename": filename,
                    "old": {"number": old_number, "color": old_color},
                    "new": {
                        "number": new_analysis.get("number"),
                        "color": new_analysis.get("color"),
                        "defect_level": determine_defect_level(new_analysis.get("color"))
                    }
                }

        return {"success": False, "message": "업데이트 중 오류가 발생했습니다."}


def parse_reanalyze_request(user_message: str) -> list:
    """
    사용자 메시지에서 재분석 요청 ID 추출

    Args:
        user_message: 사용자 메시지

    Returns:
        재분석할 ID 리스트
    """
    import re

    # 재분석 관련 키워드 확인
    reanalyze_keywords = ["재분석", "다시 분석", "다시분석", "재검사", "다시 검사", "reanalyze", "retry"]

    is_reanalyze = any(kw in user_message.lower() for kw in reanalyze_keywords)

    if not is_reanalyze:
        return []

    # ID 추출
    ids = []

    # "ID 1, 2, 3" 또는 "1번, 2번" 또는 "1, 2, 3" 패턴
    id_patterns = [
        r'ID\s*(\d+)',
        r'(\d+)\s*번',
        r'#(\d+)',
    ]

    for pattern in id_patterns:
        matches = re.findall(pattern, user_message, re.IGNORECASE)
        ids.extend([int(m) for m in matches])

    # "미확인" 또는 "unknown" 키워드로 미확인 항목 모두 재분석
    # 스티커가 있는데 인식 실패한 경우만 대상
    if "미확인" in user_message or "unknown" in user_message.lower() or "인식 안" in user_message:
        data = load_results()
        results = data.get("results", [])
        unknown_ids = [r.get("id") for r in results if r.get("has_sticker") and (r.get("defect_level") == "미확인" or r.get("sticker_number") is None)]
        ids.extend(unknown_ids)

    # "불량" 키워드로 불량 항목 모두 재분석
    if "불량" in user_message and ("전부" in user_message or "모두" in user_message or "다" in user_message):
        data = load_results()
        results = data.get("results", [])
        defect_ids = [r.get("id") for r in results if r.get("defect_level") in ["경미한 불량", "심각한 불량"]]
        ids.extend(defect_ids)

    # "전부" 또는 "모두" 재분석
    if ("전부" in user_message or "모두" in user_message or "전체" in user_message) and not ids:
        data = load_results()
        results = data.get("results", [])
        ids = [r.get("id") for r in results]

    return list(set(ids))  # 중복 제거


@traceable(
    name="chat_with_data",
    run_type="llm",
    metadata={
        "component": "chatbot",
        "model": config.MODEL_NAME
    }
)
def chat_with_data(user_message: str) -> str:
    """
    분석 데이터를 기반으로 사용자 질문에 답변하는 챗봇
    재분석 요청도 처리 가능
    (vLLM/Qwen 모델 사용)

    Args:
        user_message: 사용자 질문

    Returns:
        AI 응답 문자열
    """
    # 재분석 요청 확인
    reanalyze_ids = parse_reanalyze_request(user_message)

    if reanalyze_ids:
        # 재분석 수행
        results_text = []
        results_text.append(f"🔄 **{len(reanalyze_ids)}개 항목 재분석 시작**\n")

        for rid in reanalyze_ids:
            result = reanalyze_image(rid)
            if result.get("success"):
                old = result.get("old", {})
                new = result.get("new", {})
                results_text.append(
                    f"✅ **ID {rid}** ({result.get('filename')})\n"
                    f"   - 이전: 번호={old.get('number', '-')}, 색상={old.get('color', '-')}\n"
                    f"   - 변경: 번호={new.get('number', '-')}, 색상={new.get('color', '-')}, 불량수준={new.get('defect_level', '-')}\n"
                )
            else:
                results_text.append(f"❌ **ID {rid}**: {result.get('message')}\n")

        results_text.append("\n📊 재분석이 완료되었습니다. 대시보드를 새로고침하여 결과를 확인하세요.")
        return "\n".join(results_text)

    # 현재 분석 데이터 로드
    data = load_results()
    results = data.get("results", [])
    total_images = data.get("total_images", 0)

    # 통계 계산
    total_results = len(results)
    # 스티커가 있는 결과만 필터링
    sticker_results = [r for r in results if r.get("has_sticker")]
    # 스티커 없는 이미지 (미확인 포함)
    no_sticker_results = [r for r in results if not r.get("has_sticker")]
    no_sticker_count = len(no_sticker_results)

    normal_count = sum(1 for r in sticker_results if r.get("defect_level") == "정상")
    minor_count = sum(1 for r in sticker_results if r.get("defect_level") == "경미한 불량")
    severe_count = sum(1 for r in sticker_results if r.get("defect_level") == "심각한 불량")
    # 스티커가 있는데 인식 실패한 경우
    sticker_unknown_count = sum(1 for r in sticker_results if r.get("defect_level") == "미확인" or r.get("sticker_number") is None)
    # 전체 미확인: 스티커 없는 이미지 + 스티커 있는데 인식 실패
    unknown_count = no_sticker_count + sticker_unknown_count

    # 불량률 계산
    defect_count = minor_count + severe_count
    defect_rate = (defect_count / total_results * 100) if total_results > 0 else 0

    # 최근 결과 샘플 (최대 10개)
    recent_samples = results[-10:] if results else []
    samples_text = ""
    for r in recent_samples:
        sticker_status = "스티커있음" if r.get("has_sticker") else "스티커없음"
        samples_text += f"  - ID {r.get('id')}: {r.get('filename')}, {sticker_status}, 번호: {r.get('sticker_number', '-')}, 색상: {r.get('sticker_color', '-')}, 불량수준: {r.get('defect_level', '-')}\n"

    # 비율 계산 (스티커가 있는 것 기준)
    sticker_total = len(sticker_results) if sticker_results else 0
    normal_pct = (normal_count / sticker_total * 100) if sticker_total > 0 else 0
    minor_pct = (minor_count / sticker_total * 100) if sticker_total > 0 else 0
    severe_pct = (severe_count / sticker_total * 100) if sticker_total > 0 else 0

    # 데이터 컨텍스트 생성
    data_context = f"""
## 모터 스티커 검사 분석 데이터 요약

### 전체 통계
- 총 분석된 이미지 수: {total_results}건
- 스티커 발견: {sticker_total}건
- 미확인 (스티커 없음 또는 인식 실패): {unknown_count}건
  - 스티커 없음: {no_sticker_count}건
  - 스티커 있으나 인식 실패: {sticker_unknown_count}건

### 스티커 분석 결과 (스티커 있는 이미지 기준)
- 정상 (초록색): {normal_count}건 ({normal_pct:.1f}%)
- 경미한 불량 (노란색): {minor_count}건 ({minor_pct:.1f}%)
- 심각한 불량 (빨간색): {severe_count}건 ({severe_pct:.1f}%)

### 불량률 (스티커 있는 것 기준)
- 전체 불량품 수: {defect_count}건
- 불량률: {(defect_count / sticker_total * 100) if sticker_total > 0 else 0:.1f}%

### 최근 분석 결과 (최대 10개)
{samples_text if samples_text else "  (분석 결과 없음)"}

### 사용 가능한 재분석 명령어
- "ID 1, 2, 3 재분석해줘" - 특정 ID 재분석
- "미확인 항목 재분석해줘" - 인식 실패한 항목 재분석
- "불량 전부 재분석해줘" - 불량 판정 항목 재분석
- "전체 재분석해줘" - 모든 항목 재분석
"""

    system_prompt = """당신은 모터 부품 품질 검사 시스템의 AI 어시스턴트입니다.
사용자가 분석 결과에 대해 질문하면, 제공된 데이터를 바탕으로 명확하고 간결하게 답변해주세요.

역할:
- 불량품 현황과 통계를 요약해드립니다
- 품질 트렌드를 분석해드립니다
- 개선이 필요한 부분을 파악해드립니다
- 재분석 방법을 안내해드립니다

답변 시 주의사항:
- 숫자와 비율은 정확하게 계산해서 제공하세요
- 한국어로 친절하게 답변하세요
- 데이터가 없으면 솔직하게 말씀해주세요
- 미확인이나 인식 실패 항목이 있다면 재분석을 권장해주세요
"""

    try:
        response = client.chat.completions.create(
            model=config.MODEL_NAME,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt
                },
                {
                    "role": "user",
                    "content": f"다음은 현재 분석 데이터입니다:\n{data_context}\n\n사용자 질문: {user_message}"
                }
            ],
            max_tokens=1000,
            temperature=0.7
        )

        result_text = response.choices[0].message.content.strip()

        # Qwen 모델의 <think> 태그 제거
        if "<think>" in result_text and "</think>" in result_text:
            result_text = result_text.split("</think>")[-1].strip()

        return result_text

    except Exception as e:
        print(f"[챗봇 오류] {e}")
        # API 오류 시 로컬에서 직접 통계 응답 생성
        fallback_response = f"""📊 **분석 결과 요약** (AI 응답 오류로 직접 통계 제공)

**전체 통계**
- 총 분석된 이미지: {total_results}건
- 스티커 발견: {sticker_total}건
- 미확인: {unknown_count}건 (스티커없음: {no_sticker_count}, 인식실패: {sticker_unknown_count})

**스티커 분석 결과**
- 정상 (초록색): {normal_count}건 ({normal_pct:.1f}%)
- 경미한 불량 (노란색): {minor_count}건 ({minor_pct:.1f}%)
- 심각한 불량 (빨간색): {severe_count}건 ({severe_pct:.1f}%)

**불량률**: {(defect_count / sticker_total * 100) if sticker_total > 0 else 0:.1f}%

---
⚠️ AI 응답 생성 중 오류가 발생했습니다: {str(e)}
재분석이 필요하면 "ID X 재분석해줘" 또는 "전체 재분석해줘"라고 입력하세요.
"""
        return fallback_response
