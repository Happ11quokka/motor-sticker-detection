# Motor Sticker Detection System

이미지에서 모터 스티커를 자동으로 검출하고 불량 여부를 판단하는 AI 기반 품질 검사 시스템

## Background

### 기존 문제점
- OpenAI API 모델 사용 시 비용 및 정확도 문제

### 해결 방안
| 항목 | 내용 |
|------|------|
| **GPU 환경** | Runpod (최대 40GB VRAM) |
| **선택 모델** | Qwen/Qwen3-VL-8B-Instruct |
| **선택 이유** | 40GB 용량 내에서 실행 가능한 Vision-Language 모델 |
| **서빙 방식** | vLLM (OpenAI Compatible API) |

---

## Architecture

```
┌─────────────────┐      ┌──────────────────┐      ┌─────────────────────┐
│  Teacher Tools  │      │  Student Server  │      │   Vision Model API  │
│  image_sender   │─────▶│  FastAPI + Gradio│─────▶│  (vLLM/Qwen)        │
└─────────────────┘      └────────┬─────────┘      └─────────────────────┘
                                  │
                                  ▼
                         ┌────────────────┐
                         │  Dashboard UI  │
                         │   (Gradio)     │
                         └────────┬───────┘
                                  │
                                  ▼
                         ┌────────────────┐
                         │  JSON Storage  │
                         │  + CSV Export  │
                         └────────────────┘
```

### Project Structure

```
Motor_Sticker_Detection_System/
├── student_template/          # 메인 API 서버
│   ├── app.py                 # FastAPI + Gradio 대시보드
│   ├── worker.py              # Vision Model 호출 + 분석 로직
│   ├── models.py              # 데이터 모델 + 유틸리티
│   ├── config.py              # 환경 설정
│   └── data/
│       ├── uploads/           # 업로드된 이미지 저장
│       └── results.json       # 분석 결과 저장
│
├── teacher_tools/             # 교수자 도구
│   ├── image_sender.py        # 이미지 자동 전송
│   └── student_apis.json      # 학생 API 목록
│
└── data/                      # 테스트 데이터셋
    ├── motor_checker/         # 원본 컬러 이미지 (6개)
    └── motor_checker_2/
        ├── grayscale/         # 흑백 이미지 (36개)
        └── blurred/           # 가우시안 블러 이미지 (36개)
```

---

## Test Scenarios

### 1. 컬러 이미지 처리
- **데이터셋**: `data/motor_checker/` (원본 이미지)
- **처리 방식**: Vision Model이 직접 색상 판별
- **판별 기준**: 초록색/노란색/빨간색 스티커 직접 인식

### 2. 흑백 이미지 처리
- **데이터셋**: `data/motor_checker_2/grayscale/` (36개)
- **생성 알고리즘**: PIL의 `Image.convert('L')` 사용
- **목적**: 흑백 이미지 대응

```python
from PIL import Image
img = Image.open("original.jpg")
grayscale_img = img.convert('L')  # Luminance 모드로 변환
grayscale_img.save("grayscale.jpg")
```

### 3. 흐린 이미지 처리 (가우시안 블러)
- **데이터셋**: `data/motor_checker_2/blurred/` (36개)
- **생성 알고리즘**: OpenCV GaussianBlur 필터
- **목적**: 초점이 맞지 않은 사진 시뮬레이션

```python
import cv2
img = cv2.imread("original.jpg")
blurred = cv2.GaussianBlur(img, (15, 15), 0)
cv2.imwrite("blurred.jpg", blurred)
```

---

## System Workflow

```
[1] 이미지 업로드 (POST /upload)
     │
     │  • 파일 검증: 이미지 형식, 10MB 이하
     │  • 타임스탬프 파일명: {YYYYMMDD_HHMMSS_ffffff}_{원본파일명}
     │  • 저장 위치: student_template/data/uploads/
     ▼
[2] 분석 시작 (POST /start-analysis)
     │
     │  • 백그라운드 워커 스레드 생성
     │  • 3개씩 배치 처리
     ▼
[3] Vision Model 분석
     │
     │  [이미지 전처리]
     │  • RGBA → RGB 변환
     │  • 1024x1024 이하로 리사이징
     │  • JPEG 품질 85로 압축
     │  • Base64 인코딩
     │
     │  [API 호출]
     │  • OpenAI Compatible API 사용
     │  • max_tokens=150, temperature=0.1
     │  • 최대 3회 재시도 (502/500/503 오류)
     ▼
[4] 응답 파싱 및 불량 판정
     │
     │  • 초록색 → "정상"
     │  • 노란색 → "경미한 불량"
     │  • 빨간색 → "심각한 불량"
     ▼
[5] 결과 저장 → results.json
```

---

## Key Features

### Image Analysis
- **Sticker Detection** - 모터 이미지에서 스티커 유무 자동 검출
- **Information Extraction** - 스티커 번호 및 색상 정보 추출
- **Defect Classification** - 불량 수준 3단계 분류 (정상/경미한 불량/심각한 불량)
- **Batch Processing** - 3개 이미지씩 그룹으로 효율적 처리

### Dashboard
- **Real-time Statistics** - 총 처리 이미지, 불량 수준별 통계
- **Result Table** - 최근 분석 결과 20개 표시
- **CSV Export** - 전체 분석 결과 CSV 파일 다운로드
- **AI Assistant** - 분석 결과에 대한 자연어 질의응답

### Teacher Tools
- **Automated Transmission** - 여러 학생 API로 자동 이미지 전송
- **Parallel/Sequential Mode** - 순차 또는 병렬 전송 지원
- **Progress Tracking** - 진행률 표시 및 재시도 처리

---

## Prompt Design

### 스티커 분석 프롬프트

```
모터 부품 이미지에서 품질 검사용 원형 스티커를 찾아주세요.

[스티커 특징]
- 원형의 색깔 스티커 (초록색, 노란색, 또는 빨간색)
- 스티커 위에 손글씨로 쓰여진 3자리 숫자 (예: 102, 169, 213 등)
- 숫자 아래에 밑줄이 그어져 있을 수 있음 (밑줄은 숫자가 아님)

[색상 판별 방법]
1. 컬러 이미지인 경우: 스티커의 실제 색상을 직접 확인
   - 초록색, 노란색, 빨간색 중 하나

2. 이미지가 흑백인 경우, DANGER 경고 스티커를 기준으로 색상을 판별:
   - DANGER 스티커에는 빨간색 영역(어두운 회색)과 노란색 번개 마크(중간 밝기)가 있습니다
   - 원형 스티커가 DANGER의 빨간색 영역과 비슷한 밝기 → 빨간색
   - 원형 스티커가 DANGER의 노란색 번개와 비슷한 밝기 → 노란색
   - 원형 스티커가 둘 다보다 밝음 (가장 연한 회색) → 초록색

[숫자 인식 주의사항]
- 손글씨 숫자는 보통 3자리입니다
- 숫자 '1'은 세로 막대 형태로, 밑줄과 구분해주세요
- 밑줄은 숫자의 일부가 아닙니다

다음 JSON 형식으로만 답변해주세요:
{
    "has_sticker": true/false,
    "number": "숫자" 또는 null,
    "color": "초록색"/"노란색"/"빨간색" 또는 null
}
```

### 챗봇 시스템 프롬프트

```
당신은 모터 부품 품질 검사 시스템의 AI 어시스턴트입니다.
사용자가 분석 결과에 대해 질문하면, 제공된 데이터를 바탕으로 명확하고 간결하게 답변해주세요.

역할:
- 불량품 현황과 통계를 요약해드립니다
- 품질 트렌드를 분석해드립니다
- 개선이 필요한 부분을 파악해드립니다
```

---

## Test Results

### 1. 모델 전환 테스트 (OpenAI GPT-4o → Qwen)

| 항목 | 결과 |
|------|------|
| **기존 GPT-4o 인식** | 213 → 273으로 잘못 인식 |
| **Qwen 인식** | 273으로 정확히 인식 |
| **원인 분석** | 원본 파일 확인 결과, 273이 정답 (GPT-4o가 오류) |

**결론**: Qwen 모델이 기존 GPT-4o보다 숫자 인식 정확도가 높음

### 2. 프롬프트 최적화 테스트

| 항목 | 수정 전 | 수정 후 |
|------|---------|---------|
| **169 인식** | 69 (오류) | 169 (정확) |
| **원인** | 숫자 '1'을 밑줄로 오인 | 3자리 숫자 힌트 + 밑줄 구분 명시 |

### 3. 흑백 이미지 테스트

- **초기 접근 (실패)**: RGB 값 차이로 색상 판별 시도 → 밝기만으로 색상 구분 불가
- **개선된 접근**: DANGER 스티커 기준 상대적 밝기 비교
- **결과**: 정확도 대폭 향상 (미해결 케이스 2건)

### 4. 가우시안 블러 테스트

| 항목 | 결과 |
|------|------|
| **전체 정확도** | 대부분 성공 |
| **실패 케이스** | 1건 (심하게 흐린 이미지) |
| **실패 원인** | 블러가 과도하여 숫자 판독 불가 |
| **해결 가능성** | 해결 불가 (물리적 한계) |

**결론**: 적당한 수준의 블러는 모델이 처리 가능하나, 과도한 블러는 한계

---

## Dashboard Comparison

| 항목 | 기존 | 개선 후 |
|------|------|---------|
| **통계 카드** | 없음 | 4개 (총 이미지/정상/경미/심각) |
| **결과 테이블** | 최근 20개 | 최근 20개 + 실시간 업데이트 |
| **새로고침** | 없음 | 버튼 제공 |
| **데이터 삭제** | 없음 | 전체 삭제 기능 |
| **CSV 내보내기** | 없음 | 전체 결과 다운로드 |
| **AI 챗봇** | 없음 | 분석 데이터 기반 질의응답 |

---

## Tech Stack

| 계층 | 기술 |
|------|------|
| **Web Framework** | FastAPI |
| **UI** | Gradio |
| **Vision AI** | Qwen/vLLM (OpenAI Compatible API) |
| **이미지 처리** | Pillow, OpenCV |
| **모니터링** | LangSmith |
| **HTTP Client** | requests, tqdm |
| **Environment** | python-dotenv |

---

## Installation

### 1. vLLM 서버 설정 (GPU 환경)

```bash
# vLLM 및 의존성 설치
pip install vllm hf_transfer

# Qwen Vision 모델 서빙 시작
vllm serve Qwen/Qwen3-VL-8B-Instruct --max-model-len 65536
```

### 2. 학생 서버 설치

```bash
cd student_template
pip install fastapi uvicorn gradio openai langsmith pillow python-dotenv
```

### 3. 환경 변수 설정 (.env)

```
API_BASE_URL=http://localhost:8000/v1    # vLLM 서버 주소
API_KEY=your-api-key
MODEL_NAME=Qwen/Qwen3-VL-8B-Instruct
LANGSMITH_API_KEY=your-langsmith-key     # 선택사항
LANGSMITH_PROJECT=motor-sticker-detection
```

### 4. 서버 실행

```bash
cd student_template
python app.py
```

- API 서버: `http://localhost:8001`
- Dashboard: `http://localhost:7860`

---

## License

이 프로젝트는 교육 목적으로 사용됩니다.

---

## References

- [FastAPI Documentation](https://fastapi.tiangolo.com/)
- [Gradio Documentation](https://gradio.app/docs/)
- [vLLM Documentation](https://docs.vllm.ai/)
- [Qwen Model](https://huggingface.co/Qwen)
