# Motor Sticker Detection API - 학생용 템플릿

이미지에서 스티커를 검출하고 불량 여부를 판단하는 API 서버입니다.

## 프로젝트 개요

**핵심 기능:**
- 이미지 업로드 즉시 응답 (비동기 처리)
- 백그라운드에서 3개씩 그룹으로 자동 분석
- Vision Model API를 통한 스티커 정보 추출
- 실시간 Gradio 대시보드

**동작 방식:**
```
[이미지 업로드] → [큐에 추가] → [즉시 응답]
                        ↓
              [백그라운드 워커]
                        ↓
                  [3개씩 그룹화]
                        ↓
              [Vision API 호출]
                        ↓
              [결과 저장 및 대시보드 업데이트]
```

## 프로젝트 구조

```
student_template/
├── app.py                  # FastAPI 서버 + Gradio 대시보드
├── worker.py               # 백그라운드 이미지 분석 워커
├── models.py               # 데이터 모델 및 유틸리티 함수
├── config.py               # 설정 관리
├── requirements.txt        # 필요한 패키지 목록
├── .env.example            # 환경변수 예시
├── .env                    # 실제 환경변수 (직접 생성)
├── data/
│   ├── uploads/            # 업로드된 이미지 저장
│   └── results.json        # 분석 결과 저장
└── README.md               # 이 문서
```

### 파일 설명

**app.py** - 메인 서버
- FastAPI 엔드포인트 (`/`, `/upload`)
- Gradio 대시보드 UI
- 서버 실행 로직

**worker.py** - 백그라운드 워커
- `analyze_sticker()`: Vision API로 이미지 분석
- `analyze_image_group()`: 3개 이미지 그룹 분석
- `background_worker()`: 백그라운드 워커 메인 루프

**models.py** - 데이터 및 유틸리티
- `AnalysisResult`: 분석 결과 데이터 모델
- `load_results()` / `save_result()`: JSON 파일 읽기/쓰기
- `resize_image()` / `encode_image()`: 이미지 처리
- `determine_defect_level()`: 불량 수준 판정

**config.py** - 설정 관리
- 환경변수 로드
- 디렉토리 초기화

## 설치 및 실행 방법

### 1단계: 가상환경 생성 및 활성화

```bash
cd student_template

# 가상환경 생성
python3 -m venv venv

# 활성화
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows
```

### 2단계: 패키지 설치

```bash
pip install -r requirements.txt
```

### 3단계: 환경변수 설정

`.env.example` 파일을 복사하여 `.env` 파일을 생성:

```bash
cp .env.example .env
```

`.env` 파일을 편집:

```bash
# Vision Model API 설정 (교수자가 제공)
API_BASE_URL=http://your-vision-api-url/v1
API_KEY=your-api-key-here
MODEL_NAME=gpt-4o

# 서버 포트 설정
SERVER_PORT=8000
GRADIO_PORT=7860
```

**중요**: 교수자가 제공한 Vision Model API 정보를 반드시 입력해야 합니다!

### 4단계: 서버 실행

```bash
python app.py
```

**정상 실행 시 출력:**
```
======================================================================
Motor Sticker Detection API 서버 시작
======================================================================
API Base URL: http://your-vision-api-url/v1
Model: gpt-4o
API Key: your-api-key...
FastAPI 포트: 8000
Gradio 포트: 7860
======================================================================
[워커 시작] 이미지 분석 백그라운드 워커 실행 중...

✓ FastAPI 서버: http://localhost:8000
✓ Gradio 대시보드: http://localhost:7860
✓ 백그라운드 워커: 실행 중 (3개씩 그룹 분석)

INFO:     Uvicorn running on http://0.0.0.0:8000
```

## 사용 방법

### 대시보드 확인

웹 브라우저에서 접속:
```
http://localhost:7860
```

**대시보드 기능:**
- 총 처리된 이미지 수
- 불량 수준별 통계 (정상/경미/심각)
- 최근 20개 분석 결과 테이블
- 새로고침 버튼

### API 테스트

#### 헬스체크

```bash
curl http://localhost:8000/
```

**응답:**
```json
{
  "status": "ok",
  "service": "Motor Sticker Detection API",
  "version": "1.0.0"
}
```

#### 이미지 업로드

```bash
curl -X POST http://localhost:8000/upload \
  -F "file=@/path/to/image.jpg"
```

**응답:**
```json
{
  "success": true,
  "message": "이미지 업로드 완료",
  "filename": "20251225_120000_123456_image.jpg",
  "queue_size": 1
}
```

**중요**: 업로드는 즉시 완료되고, 분석은 백그라운드에서 진행됩니다!

## API 엔드포인트

### GET /

서버 헬스체크

**응답:**
- `status`: 서버 상태
- `service`: 서비스 이름
- `version`: 버전

### POST /upload

이미지 업로드 (비동기 처리)

**요청:**
- `file`: 이미지 파일 (form-data)

**응답:**
- `success`: 성공 여부
- `message`: 메시지
- `filename`: 저장된 파일명
- `queue_size`: 현재 큐 크기

**처리 흐름:**
1. 이미지 파일 저장
2. 큐에 추가
3. 즉시 응답 반환
4. 백그라운드에서 3개가 모이면 자동 분석

## 백그라운드 워커 동작 방식

### 1. 이미지 수신

```
[업로드 완료] image1.jpg | 큐 크기: 1
[워커] 이미지 수신: image1.jpg | 대기 중: 1/3

[업로드 완료] image2.jpg | 큐 크기: 2
[워커] 이미지 수신: image2.jpg | 대기 중: 2/3

[업로드 완료] image3.jpg | 큐 크기: 3
[워커] 이미지 수신: image3.jpg | 대기 중: 3/3
```

### 2. 그룹 분석 시작

```
[워커] 3개 모임! 분석 시작...

[그룹 1 분석 시작] 이미지 3개
  이미지 1/3: image1.jpg 분석 중...
  이미지 2/3: image2.jpg 분석 중...
    ✓ 스티커 발견! (번호: 42, 색: 초록색)
  이미지 3/3: image3.jpg 분석 중...
[그룹 1 완료] 불량 수준: 정상
```

### 3. 결과 저장

`data/results.json` 파일에 저장:

```json
{
  "total_images": 3,
  "groups": [
    {
      "group_id": 1,
      "timestamp": "2025-12-25 12:00:00",
      "images": [
        {"filename": "image1.jpg", "has_sticker": false, ...},
        {"filename": "image2.jpg", "has_sticker": true, "sticker_number": "42", "sticker_color": "초록색"},
        {"filename": "image3.jpg", "has_sticker": false, ...}
      ],
      "sticker_info": {
        "filename": "image2.jpg",
        "number": "42",
        "color": "초록색"
      },
      "defect_level": "정상",
      "status": "정상"
    }
  ],
  "results": [
    {
      "id": 1,
      "timestamp": "2025-12-25 12:00:00",
      "filename": "image2.jpg",
      "group_id": 1,
      "has_sticker": true,
      "sticker_number": "42",
      "sticker_color": "초록색",
      "defect_level": "정상"
    }
  ]
}
```

## 불량 수준 판정 기준

| 스티커 색상 | 불량 수준 |
|------------|----------|
| 초록색     | 정상      |
| 노란색     | 경미한 불량 |
| 빨간색     | 심각한 불량 |

## 제출 방법

### 1. 로컬 서버 실행

위의 4단계를 완료하여 서버를 실행합니다.

### 2. 외부 접속 설정 (선택사항)

**ngrok 사용:**
```bash
# 다른 터미널에서
ngrok http 8000
```

ngrok이 제공하는 URL (예: `https://abc123.ngrok.io`)을 기록합니다.

### 3. API 주소 제출

교수자에게 다음 정보를 제출:
- 학생 이름/학번
- API 주소 (예: `http://localhost:8000` 또는 `https://abc123.ngrok.io`)

## 트러블슈팅

### 문제: 포트가 이미 사용 중

**증상:** `Address already in use` 오류

**해결방법:**
```bash
# .env 파일에서 포트 변경
SERVER_PORT=8001
GRADIO_PORT=7861
```

### 문제: Vision Model API 연결 실패

**증상:** `Connection refused` 또는 `Unauthorized` 오류

**해결방법:**
1. `.env` 파일의 `API_BASE_URL`과 `API_KEY` 확인
2. 교수자가 제공한 정보와 일치하는지 확인
3. 네트워크 연결 확인

### 문제: 워커가 분석하지 않음

**증상:** 업로드는 되는데 분석이 안됨

**해결방법:**
1. 서버 로그에서 "[워커 시작]" 메시지 확인
2. 3개 이미지가 모두 업로드되었는지 확인
3. 서버 재시작

### 문제: 대시보드가 업데이트 안됨

**해결방법:** "새로고침" 버튼 클릭

## 코드 구조 설명

### 왜 3개 파일로 분리했나요?

**가독성과 유지보수를 위해:**

1. **app.py**: 서버와 API 엔드포인트
   - FastAPI 라우트
   - Gradio 대시보드
   - 메인 실행 코드

2. **worker.py**: 이미지 분석 로직
   - Vision API 호출
   - 그룹 분석
   - 백그라운드 워커

3. **models.py**: 데이터와 유틸리티
   - 데이터 모델
   - 파일 읽기/쓰기
   - 이미지 처리

**장점:**
- 각 파일의 역할이 명확함
- 코드 찾기 쉬움
- 테스트 및 디버깅 용이
- 협업 시 충돌 최소화

### 비동기 처리를 왜 사용했나요?

**Vision API 호출은 시간이 오래 걸립니다:**
- 이미지 1개 분석: 약 2-10초
- 3개 분석: 약 6-30초

**동기 방식의 문제:**
- 교수자가 이미지를 보낼 때 30초씩 기다려야 함
- 타임아웃 발생
- 느린 사용자 경험

**비동기 방식의 장점:**
- 업로드는 즉시 완료 (0.1초)
- 분석은 백그라운드에서 진행
- 여러 이미지 빠르게 업로드 가능
- 타임아웃 없음

## 추가 개선 아이디어

- [ ] 자동 새로고침 기능 (Gradio `every` 파라미터)
- [ ] 이미지 썸네일 표시
- [ ] 그룹별 상세 정보 페이지
- [ ] 차트/그래프 추가
- [ ] 데이터베이스 연동 (SQLite)
- [ ] CSV 내보내기 기능
- [ ] 에러 알림 기능
- [ ] WebSocket 실시간 업데이트

## 참고 자료

- [FastAPI 공식 문서](https://fastapi.tiangolo.com/)
- [Gradio 공식 문서](https://gradio.app/docs/)
- [OpenAI API 문서](https://platform.openai.com/docs/)
- [Python Queue 문서](https://docs.python.org/3/library/queue.html)

## 문의

프로젝트 관련 문의는 교수자에게 연락하세요.
