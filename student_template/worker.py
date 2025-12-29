"""
백그라운드 이미지 분석 워커 (DeepSeek-OCR vLLM API 통합)

3개씩 이미지를 그룹으로 묶어 분석하고,
스티커가 있는 이미지를 찾아 불량 수준을 판정합니다.

DeepSeek-OCR은 원격 vLLM 서버에서 실행되며,
로컬에서는 API 호출만 수행합니다.
"""
import base64
import json
import os
import re
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
    determine_defect_level
)


# LangSmith 환경변수 설정
if config.LANGSMITH_TRACING and config.LANGSMITH_API_KEY:
    os.environ["LANGSMITH_API_KEY"] = config.LANGSMITH_API_KEY
    os.environ["LANGSMITH_PROJECT"] = config.LANGSMITH_PROJECT
    os.environ["LANGSMITH_TRACING"] = "true"
    print(f"[LangSmith] 추적 활성화: {config.LANGSMITH_PROJECT}")


# DeepSeek-OCR vLLM API 클라이언트
deepseek_client = OpenAI(
    base_url=config.DEEPSEEK_API_BASE_URL,
    api_key=config.DEEPSEEK_API_KEY
)

# OpenAI 클라이언트 생성 (챗봇용)
if config.API_BASE_URL == "https://api.openai.com/v1":
    openai_client = OpenAI(api_key=config.API_KEY)
else:
    openai_client = OpenAI(
        base_url=config.API_BASE_URL,
        api_key=config.API_KEY
    )

# LangSmith 래핑 (추적 활성화시)
if config.LANGSMITH_TRACING and config.LANGSMITH_API_KEY:
    openai_client = wrap_openai(openai_client)
    print("[LangSmith] OpenAI 클라이언트 래핑 완료")


# 전역 큐 (app.py에서 이미지를 추가)
image_queue = Queue()


def parse_sticker_info(ocr_result: str) -> dict:
    """
    DeepSeek-OCR 결과에서 스티커 정보 추출 (JSON 형식 지원)

    Args:
        ocr_result: OCR 결과 텍스트 (JSON 또는 일반 텍스트)

    Returns:
        스티커 정보 딕셔너리 {has_sticker, number, color, is_irrelevant}
    """
    result = {
        "has_sticker": False,
        "number": None,
        "color": None,
        "is_irrelevant": False  # 관련없는 이미지 플래그
    }

    # JSON 파싱 시도
    try:
        # ```json ... ``` 블록 추출
        if "```json" in ocr_result:
            json_text = ocr_result.split("```json")[1].split("```")[0].strip()
        elif "```" in ocr_result:
            json_text = ocr_result.split("```")[1].split("```")[0].strip()
        else:
            json_text = ocr_result.strip()

        parsed = json.loads(json_text)

        # status 확인
        status = parsed.get("status", "")
        if "관련없는" in status:
            result["is_irrelevant"] = True
            return result
        elif "스티커_없음" in status or "없음" in status:
            return result

        # sticker_info 파싱
        sticker_info = parsed.get("sticker_info", {})
        if sticker_info.get("detected", False):
            result["has_sticker"] = True

            # 색상 매핑
            color = sticker_info.get("color", "")
            color_mapping = {
                "초록": "초록색",
                "녹색": "초록색",
                "green": "초록색",
                "노랑": "노란색",
                "황색": "노란색",
                "yellow": "노란색",
                "빨강": "빨간색",
                "적색": "빨간색",
                "red": "빨간색",
                "판단불가": "판단불가"
            }
            result["color"] = color_mapping.get(color.lower() if color else "", color)

            # 숫자 추출
            number = sticker_info.get("number", "")
            if number and number != "인식불가":
                # 숫자만 추출
                num_match = re.search(r'(\d{3})', str(number))
                if num_match:
                    result["number"] = num_match.group(1)

        return result

    except (json.JSONDecodeError, IndexError, KeyError):
        # JSON 파싱 실패 시 기존 텍스트 파싱 방식 사용
        pass

    ocr_lower = ocr_result.lower()

    # 관련없는 이미지 체크
    irrelevant_keywords = ["관련없는_이미지", "관련없는 이미지", "관련 없는 이미지", "irrelevant", "not relevant"]
    for keyword in irrelevant_keywords:
        if keyword in ocr_lower:
            result["is_irrelevant"] = True
            return result

    # 스티커 없음 체크
    if "스티커_없음" in ocr_result or "스티커 없음" in ocr_lower:
        return result

    # 색상 감지
    color_mapping = {
        "초록색": "초록색",
        "초록": "초록색",
        "녹색": "초록색",
        "green": "초록색",
        "노란색": "노란색",
        "노랑": "노란색",
        "황색": "노란색",
        "yellow": "노란색",
        "빨간색": "빨간색",
        "빨강": "빨간색",
        "적색": "빨간색",
        "red": "빨간색",
        "판단불가": "판단불가",
        "판단 불가": "판단불가"
    }

    for keyword, color in color_mapping.items():
        if keyword in ocr_lower:
            result["color"] = color
            if color != "판단불가":
                result["has_sticker"] = True
            break

    # 숫자 추출 - 3자리 숫자 찾기
    numbers = re.findall(r'\b(\d{3})\b', ocr_result)
    if numbers:
        result["number"] = numbers[0]
        result["has_sticker"] = True

    # "정상_처리"가 있으면 스티커 있음
    if "정상_처리" in ocr_result:
        result["has_sticker"] = True

    return result


def encode_image_base64(image_path: Path) -> str:
    """이미지를 base64로 인코딩"""
    with open(image_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


@traceable(
    name="analyze_sticker_deepseek",
    run_type="llm",
    metadata={
        "component": "vision_analysis",
        "model": "DeepSeek-OCR",
        "provider": "vllm"
    }
)
def analyze_sticker_deepseek(image_path: Path, max_retries: int = 3) -> dict:
    """
    DeepSeek-OCR vLLM API를 사용하여 이미지에서 스티커 정보 추출

    원격 vLLM 서버에서 DeepSeek-OCR 모델이 실행되며,
    OpenAI 호환 API를 통해 호출합니다.

    Args:
        image_path: 분석할 이미지 경로
        max_retries: 최대 재시도 횟수

    Returns:
        스티커 정보 딕셔너리 {has_sticker, number, color}
    """
    # 이미지를 base64로 인코딩
    base64_image = encode_image_base64(image_path)

    # 디버깅 모드 확인
    debug_mode = os.getenv("DEBUG_PROMPT", "false").lower() == "true"

    if debug_mode:
        # 디버깅용 프롬프트 - 모델이 이미지를 어떻게 보는지 확인
        prompt = """당신은 시각 정보 분석 전문가입니다. 주어진 이미지를 있는 그대로 자세히 묘사해야 합니다.

다음 순서대로 답변해 주세요:
1. **이미지 전체 설명**: 이 이미지는 무엇을 찍은 사진입니까? (예: 금속 기계 부품, 책상 위, 어두운 배경 등)
2. **색상 탐지**: 이미지 안에 '초록색', '노란색', '빨간색'으로 된 물체가 있습니까? 있다면 위치와 모양을 설명하세요.
3. **텍스트 탐지**: 이미지 안에 글자나 숫자가 보입니까? 인쇄된 글자와 손으로 쓴 글씨를 구분해서 보이는 대로 다 적어보세요.
4. **스티커 확인**: 부품 위에 붙어 있는 '동그란 스티커'가 보입니까?

제약 조건:
- JSON 형식이 아니라, 줄글로 자세히 설명하세요.
- 판단이 어려우면 "잘 안 보임"이라고 솔직하게 말하세요.
"""
    else:
        # 실제 분석용 프롬프트
        prompt = """당신은 자동차 모터 부품의 품질 관리를 담당하는 **AI 비전 검사관**입니다.
제공된 이미지에서 **품질 검사 확인용 원형 스티커**를 찾아 그 정보를 추출하는 것이 당신의 목표입니다.

## 1. 단계별 분석 절차 (이 순서대로 생각하고 판단하세요)
1. **이미지 적합성 판단**:
   - 이미지가 모터 부품이 아닌 경우(사람, 풍경, 동물 등) 즉시 중단합니다.
   - 이미지가 실제 사물이 아닌 모니터 화면을 찍은 것(무아레 패턴, 베젤 보임)인지 확인합니다.
2. **스티커 탐지**:
   - 부품 표면에 부착된 **'동그란 원형'** 스티커를 찾으세요. (사각형 바코드나 경고 라벨은 무시)
   - 스티커는 보통 초록, 노랑, 빨강 중 하나의 색상입니다.
3. **텍스트 인식 (OCR)**:
   - 스티커 내부에 **손글씨(매직/펜)**로 적힌 3자리 숫자를 찾으세요.
   - 글자가 기울어지거나 흐릿할 수 있습니다. 주변의 인쇄된 텍스트(부품 번호 등)와 혼동하지 마세요.
4. **색상 판별**:
   - 스티커 배경색을 확인하세요. 흑백 이미지라면 '판단불가'로 처리하세요.

## 2. 제약 조건
- 숫자가 3자리가 아니거나 명확하지 않으면 가장 유력한 숫자를 적되, 확신이 없으면 "인식불가"라고 하세요.
- 원형 스티커가 없으면 결과는 무조건 "없음"입니다.

## 3. 답변 출력 형식 (JSON)
분석이 끝나면 오직 아래의 JSON 형식으로만 답변을 출력하세요. 다른 설명은 포함하지 마세요.

```json
{
  "status": "정상_처리" OR "관련없는_이미지" OR "스티커_없음",
  "sticker_info": {
    "detected": true/false,
    "color": "초록" OR "노랑" OR "빨강" OR "판단불가",
    "number": "숫자(문자열)" OR "인식불가"
  },
  "reasoning": "판단 이유를 한 문장으로 요약 (예: 원형 스티커가 발견되었고 102가 적혀있음)"
}
```
"""

    last_error = None

    for attempt in range(max_retries):
        try:
            # vLLM OpenAI 호환 API 호출
            response = deepseek_client.chat.completions.create(
                model=config.DEEPSEEK_OCR_MODEL,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/jpeg;base64,{base64_image}"
                                }
                            },
                            {
                                "type": "text",
                                "text": prompt
                            }
                        ]
                    }
                ],
                max_tokens=500,
                temperature=0.0
            )

            result = response.choices[0].message.content.strip()
            print(f"[DEBUG] DeepSeek-OCR 결과: {result}")

            # 결과 파싱
            sticker_info = parse_sticker_info(str(result))

            # JSON 형식 응답 시도 (모델이 JSON으로 답변한 경우)
            try:
                if "```json" in result:
                    json_text = result.split("```json")[1].split("```")[0].strip()
                    parsed = json.loads(json_text)
                    if "has_sticker" in parsed:
                        return parsed
            except:
                pass

            return sticker_info

        except Exception as e:
            last_error = e

            if attempt < max_retries - 1:
                wait_time = (attempt + 1) * 2
                print(f"[재시도 {attempt + 1}/{max_retries}] 오류 발생, {wait_time}초 후 재시도...")
                print(f"  오류: {e}")
                time.sleep(wait_time)
                continue
            break

    import traceback
    print(f"분석 오류: {last_error}")
    print(f"상세 오류:\n{traceback.format_exc()}")
    return {"has_sticker": False, "number": None, "color": None, "error": str(last_error)}


# 기존 OpenAI 기반 분석 함수 (폴백용)
@traceable(
    name="analyze_sticker_openai",
    run_type="llm",
    metadata={
        "component": "vision_analysis",
        "model": config.MODEL_NAME,
        "provider": "openai"
    }
)
def analyze_sticker_openai(image_path: Path, max_retries: int = 3) -> dict:
    """OpenAI Vision API를 사용한 스티커 분석 (폴백용)"""
    from models import encode_image
    base64_image = encode_image(image_path)

    prompt = """
    모터 부품 이미지에서 품질 검사용 원형 스티커를 찾아주세요.

    [스티커 특징]
    - 원형의 색깔 스티커 (초록색, 노란색, 또는 빨간색)
    - 스티커 위에 손글씨로 쓰여진 3자리 숫자 (예: 102, 169, 213 등)

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
            response = openai_client.chat.completions.create(
                model=config.MODEL_NAME,
                messages=[
                    {
                        "role": "system",
                        "content": "당신은 이미지 분석 전문가입니다. 스티커 정보를 정확히 추출하여 JSON 형식으로만 응답하세요."
                    },
                    {
                        "role": "user",
                        "content": [
                            {"type": "text", "text": prompt},
                            {
                                "type": "image_url",
                                "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}
                            }
                        ]
                    }
                ],
                max_tokens=150,
                temperature=0.1
            )

            result_text = response.choices[0].message.content.strip()

            if "<think>" in result_text and "</think>" in result_text:
                result_text = result_text.split("</think>")[-1].strip()

            if "```json" in result_text:
                result_text = result_text.split("```json")[1].split("```")[0].strip()
            elif "```" in result_text:
                result_text = result_text.split("```")[1].strip()

            result = json.loads(result_text)
            return result

        except Exception as e:
            last_error = e
            if attempt < max_retries - 1:
                time.sleep((attempt + 1) * 2)
                continue
            break

    return {"has_sticker": False, "number": None, "color": None, "error": str(last_error)}


def analyze_sticker(image_path: Path, max_retries: int = 3) -> dict:
    """
    설정에 따라 적절한 OCR 엔진으로 스티커 분석

    Args:
        image_path: 분석할 이미지 경로
        max_retries: 최대 재시도 횟수

    Returns:
        스티커 정보 딕셔너리
    """
    if config.OCR_ENGINE == "deepseek":
        return analyze_sticker_deepseek(image_path, max_retries)
    else:
        return analyze_sticker_openai(image_path, max_retries)


@traceable(
    name="analyze_image_group",
    run_type="chain",
    metadata={
        "component": "group_analysis",
        "ocr_engine": config.OCR_ENGINE
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

    print(f"\n[그룹 {group_id} 분석 시작] 이미지 {len(images)}개 (엔진: {config.OCR_ENGINE})")

    results = []
    valid_results = []  # 관련있는 이미지만 저장
    sticker_found = None
    skipped_count = 0  # 스킵된 이미지 수

    # 각 이미지 분석
    for idx, img_info in enumerate(images):
        print(f"  이미지 {idx+1}/{len(images)}: {img_info['filename']} 분석 중...")

        try:
            sticker_info = analyze_sticker(Path(img_info['path']))

            # 관련없는 이미지는 스킵
            if sticker_info.get("is_irrelevant", False):
                print(f"    ⊘ 관련없는 이미지 - 그룹에서 제외")
                skipped_count += 1
                continue

            if sticker_info["has_sticker"]:
                # 그룹당 스티커는 1개만 존재 - 이미 찾았으면 무시
                if sticker_found is None:
                    sticker_found = {
                        "filename": img_info['filename'],
                        "number": sticker_info.get("number"),
                        "color": sticker_info.get("color")
                    }
                    print(
                        f"    ✓ 스티커 발견! (번호: {sticker_info.get('number')}, 색: {sticker_info.get('color')})")
                else:
                    # 이미 스티커를 찾았으므로 이 이미지는 스티커 없음으로 처리
                    print(f"    ⚠ 스티커 중복 감지 - 첫 번째 스티커만 사용 (이 이미지는 무시)")
                    sticker_info["has_sticker"] = False
                    sticker_info["number"] = None
                    sticker_info["color"] = None
            else:
                print(f"    ✗ 스티커 없음")

            result_item = {
                "filename": img_info['filename'],
                "has_sticker": sticker_info["has_sticker"],
                "sticker_number": sticker_info.get("number"),
                "sticker_color": sticker_info.get("color")
            }
            results.append(result_item)
            valid_results.append(result_item)

        except Exception as e:
            print(f"    ✗ 분석 오류: {e}")
            results.append({
                "filename": img_info['filename'],
                "has_sticker": False,
                "error": str(e)
            })

    # 스킵된 이미지 로그
    if skipped_count > 0:
        print(f"  [정보] {skipped_count}개 이미지가 관련없는 이미지로 제외됨")

    # 유효한 이미지가 없으면 그룹 생성 안함
    if len(valid_results) == 0:
        print(f"[그룹 {group_id} 스킵] 유효한 이미지가 없음")
        return None

    # 불량 수준 결정 (판단불가인 경우 "미확인"으로)
    defect_level = None
    if sticker_found:
        if sticker_found.get("color") == "판단불가":
            defect_level = "미확인"
        else:
            defect_level = determine_defect_level(sticker_found["color"])

    # 그룹 결과 구성
    group_result = {
        "group_id": group_id,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "images": valid_results,  # 유효한 이미지만 저장
        "skipped_images": skipped_count,
        "sticker_info": sticker_found,
        "defect_level": defect_level,
        "status": "정상" if sticker_found else "스티커 미발견"
    }

    # 결과 저장
    with file_lock:
        try:
            data = load_results_unsafe()
            if "groups" not in data:
                data["groups"] = []
            data["groups"].append(group_result)
            data["total_images"] = data.get("total_images", 0) + len(valid_results)  # 유효한 이미지만 카운트

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
    print(f"[워커 시작] 이미지 분석 백그라운드 워커 실행 중... (OCR 엔진: {config.OCR_ENGINE})")

    pending_images = []

    while True:
        try:
            # 큐에서 이미지 가져오기 (1초 타임아웃)
            img_info = image_queue.get(timeout=1)
            pending_images.append(img_info)

            print(
                f"[워커] 이미지 수신: {img_info['filename']} | 대기 중: {len(pending_images)}/3")

            # 3개가 모이면 분석 시작
            if len(pending_images) >= 3:
                print(f"[워커] 3개 모임! 분석 시작...")
                group = pending_images[:3]
                pending_images = pending_images[3:]

                try:
                    analyze_image_group(group)
                except Exception as analysis_error:
                    print(f"[워커 분석 오류] {analysis_error}")
                    print(traceback.format_exc())

        except Exception as e:
            error_type = str(type(e).__name__)
            if "Empty" not in error_type:
                print(f"[워커 큐 오류] {error_type}: {e}")
                print(traceback.format_exc())
            continue


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
    (OpenAI 호환 API 사용)

    Args:
        user_message: 사용자 질문

    Returns:
        AI 응답 문자열
    """
    # 현재 분석 데이터 로드
    data = load_results()
    results = data.get("results", [])
    total_images = data.get("total_images", 0)

    # 통계 계산
    total_results = len(results)
    normal_count = sum(1 for r in results if r.get("defect_level") == "정상")
    minor_count = sum(1 for r in results if r.get("defect_level") == "경미한 불량")
    severe_count = sum(1 for r in results if r.get("defect_level") == "심각한 불량")
    unknown_count = sum(1 for r in results if r.get("defect_level") == "미확인")

    # 불량률 계산
    defect_count = minor_count + severe_count
    defect_rate = (defect_count / total_results * 100) if total_results > 0 else 0

    # 최근 결과 샘플 (최대 10개)
    recent_samples = results[-10:] if results else []
    samples_text = ""
    for r in recent_samples:
        samples_text += f"  - ID {r.get('id')}: {r.get('filename')}, 색상: {r.get('sticker_color', '-')}, 불량수준: {r.get('defect_level', '-')}\n"

    # 비율 계산
    normal_pct = (normal_count / total_results * 100) if total_results > 0 else 0
    minor_pct = (minor_count / total_results * 100) if total_results > 0 else 0
    severe_pct = (severe_count / total_results * 100) if total_results > 0 else 0

    # 데이터 컨텍스트 생성
    data_context = f"""
## 모터 스티커 검사 분석 데이터 요약

### 전체 통계
- 총 처리된 이미지 수: {total_images}장
- 스티커 분석 결과 수: {total_results}건
- 정상 (초록색): {normal_count}건 ({normal_pct:.1f}%)
- 경미한 불량 (노란색): {minor_count}건 ({minor_pct:.1f}%)
- 심각한 불량 (빨간색): {severe_count}건 ({severe_pct:.1f}%)
- 미확인: {unknown_count}건

### 불량률
- 전체 불량품 수: {defect_count}건
- 불량률: {defect_rate:.1f}%

### 최근 분석 결과 (최대 10개)
{samples_text if samples_text else "  (분석 결과 없음)"}
"""

    system_prompt = """당신은 모터 부품 품질 검사 시스템의 AI 어시스턴트입니다.
사용자가 분석 결과에 대해 질문하면, 제공된 데이터를 바탕으로 명확하고 간결하게 답변해주세요.

역할:
- 불량품 현황과 통계를 요약해드립니다
- 품질 트렌드를 분석해드립니다
- 개선이 필요한 부분을 파악해드립니다

답변 시 주의사항:
- 숫자와 비율은 정확하게 계산해서 제공하세요
- 한국어로 친절하게 답변하세요
- 데이터가 없으면 솔직하게 말씀해주세요
"""

    try:
        response = openai_client.chat.completions.create(
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
        return f"죄송합니다. 응답 생성 중 오류가 발생했습니다: {str(e)}"
