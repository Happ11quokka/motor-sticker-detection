# 테스트 가이드

프로젝트를 테스트하기 위한 단계별 가이드입니다.

## 사전 준비

### 1. Vision Model API 설정

교수자가 GPU 서버에서 Vision Model API를 실행해야 합니다.

**vLLM 사용 예시:**
```bash
python -m vllm.entrypoints.openai.api_server \
  --model llava-hf/llava-v1.6-mistral-7b-hf \
  --host 0.0.0.0 \
  --port 8000
```

**API 정보 확인:**
```bash
curl http://localhost:8000/v1/models
```

### 2. 테스트 이미지 준비

`data/motor_checker` 폴더에 테스트 이미지가 있는지 확인:
```bash
ls -la data/motor_checker/
```

## 학생 템플릿 테스트

### Step 1: 환경 설정

```bash
cd student_template

# 가상환경 생성 (프로젝트 루트에 venv가 없는 경우)
python3 -m venv venv
source venv/bin/activate

# 패키지 설치
pip install -r requirements.txt
```

### Step 2: 환경변수 설정

`.env` 파일 생성:
```bash
cp .env.example .env
```

`.env` 파일 편집:
```bash
API_BASE_URL=http://localhost:8000/v1  # Vision Model API 주소
API_KEY=dummy-key                      # API 키
MODEL_NAME=your-model-name             # 모델 이름
SERVER_PORT=8000
GRADIO_PORT=7860
```

### Step 3: 서버 실행

```bash
python app.py
```

**예상 출력:**
```
FastAPI 서버: http://localhost:8000
Gradio 대시보드: http://localhost:7860
INFO:     Uvicorn running on http://0.0.0.0:8000
```

### Step 4: API 테스트

**새 터미널을 열어서 테스트:**

#### 헬스체크
```bash
curl http://localhost:8000/
```

**예상 응답:**
```json
{
  "status": "ok",
  "service": "Motor Sticker Detection API",
  "version": "1.0.0"
}
```

#### 이미지 분석 (단일 이미지)
```bash
curl -X POST http://localhost:8000/analyze \
  -F "file=@../data/motor_checker/image_1.jpg"
```

**예상 응답:**
```json
{
  "success": true,
  "data": {
    "id": 1,
    "timestamp": "2025-12-25 12:00:00",
    "filename": "20251225_120000_image_1.jpg",
    "has_sticker": true,
    "sticker_number": "42",
    "sticker_color": "초록색",
    "defect_level": "정상"
  }
}
```

### Step 5: 대시보드 확인

1. 웹 브라우저에서 `http://localhost:7860` 접속
2. 대시보드에서 다음 확인:
   - 총 처리된 이미지: 1
   - 정상 (초록색): 1 (또는 해당 색상에 맞게)
   - 최근 분석 결과 테이블에 1개 행 표시
3. "새로고침" 버튼 클릭하여 업데이트 확인

### Step 6: 데이터 파일 확인

```bash
cat data/results.json
```

**예상 내용:**
```json
{
  "total_images": 1,
  "results": [
    {
      "id": 1,
      "timestamp": "2025-12-25 12:00:00",
      "filename": "20251225_120000_image_1.jpg",
      "has_sticker": true,
      "sticker_number": "42",
      "sticker_color": "초록색",
      "defect_level": "정상"
    }
  ]
}
```

## 교수자 도구 테스트

### Step 1: 학생 서버 실행

위의 "학생 템플릿 테스트"를 먼저 완료하여 서버를 실행해둡니다.

### Step 2: 교수자 도구 설정

```bash
cd teacher_tools

# 패키지 설치 (프로젝트 루트 venv 사용)
cd ..
source venv/bin/activate
cd teacher_tools
pip install -r requirements.txt
```

### Step 3: 학생 API 목록 확인

`student_apis.json` 확인:
```bash
cat student_apis.json
```

**내용 확인:**
- `api_url`이 실행 중인 학생 서버 주소와 일치하는지
- `active`가 `true`인지

### Step 4: 기본 테스트 (3개 이미지)

```bash
python image_sender.py --limit 3 --output test_results.json
```

**예상 출력:**
```
======================================================================
이미지 전송 시작
======================================================================
이미지 폴더: ../data/motor_checker
이미지 개수: 3개
학생 수: 2명
...

학생: 홍길동 (2021001)
API URL: http://localhost:8000
전송할 이미지: 3개

홍길동 전송 중: 100%|██████████| 3/3 [00:05<00:00,  1.67s/it]

결과: 성공 3 / 실패 0

======================================================================
전송 결과 요약
======================================================================

홍길동 (2021001):
  성공: 3/3 (100.0%)
  실패: 0/3
```

### Step 5: 결과 확인

#### 터미널 출력 확인
위의 요약 정보에서 성공/실패 확인

#### 학생 대시보드 확인
브라우저에서 `http://localhost:7860` 접속하여:
- 총 처리된 이미지가 증가했는지
- 새로운 결과가 테이블에 표시되는지
- 통계가 업데이트되었는지

#### 결과 JSON 파일 확인
```bash
cat test_results.json | head -50
```

### Step 6: 병렬 전송 테스트

```bash
python image_sender.py --parallel --limit 5
```

### Step 7: 부하 테스트

```bash
python image_sender.py --repeat 3 --interval 0.5 --limit 3
```

## 통합 테스트 시나리오

### 시나리오 1: 기본 워크플로우

1. 학생 서버 실행
2. 교수자가 이미지 3개 전송
3. 학생 대시보드에서 결과 확인
4. JSON 파일에 데이터 저장 확인

### 시나리오 2: 여러 학생 동시 테스트

1. 학생 템플릿을 3개 복사 (다른 포트 사용)
   ```bash
   cp -r student_template student1
   cp -r student_template student2
   cp -r student_template student3
   ```

2. 각 학생 폴더에서 `.env` 파일 편집 (다른 포트 사용)
   ```
   student1: SERVER_PORT=8000, GRADIO_PORT=7860
   student2: SERVER_PORT=8001, GRADIO_PORT=7861
   student3: SERVER_PORT=8002, GRADIO_PORT=7862
   ```

3. 각 서버를 별도 터미널에서 실행

4. `teacher_tools/student_apis.json` 업데이트
   ```json
   {
     "students": [
       {"id": 1, "name": "학생1", "student_id": "001", "api_url": "http://localhost:8000", "active": true},
       {"id": 2, "name": "학생2", "student_id": "002", "api_url": "http://localhost:8001", "active": true},
       {"id": 3, "name": "학생3", "student_id": "003", "api_url": "http://localhost:8002", "active": true}
     ]
   }
   ```

5. 병렬 전송 테스트
   ```bash
   cd teacher_tools
   python image_sender.py --parallel
   ```

### 시나리오 3: 에러 처리 테스트

#### 서버 다운 시나리오
1. 학생 서버 1개를 중지
2. 이미지 전송
3. 에러 메시지 확인
4. 다른 학생 서버는 정상 작동하는지 확인

#### 타임아웃 시나리오
1. 매우 짧은 타임아웃 설정
   ```bash
   python image_sender.py --timeout 1
   ```
2. 타임아웃 에러 처리 확인

#### 잘못된 파일 형식
1. 텍스트 파일을 업로드
   ```bash
   curl -X POST http://localhost:8000/analyze \
     -F "file=@README.md"
   ```
2. 400 에러 응답 확인

## 체크리스트

### 학생 템플릿

- [ ] 가상환경 생성 및 패키지 설치 성공
- [ ] `.env` 파일 정상 설정
- [ ] 서버 정상 실행
- [ ] 헬스체크 엔드포인트 응답 OK
- [ ] 이미지 업로드 성공
- [ ] Vision Model API 호출 성공
- [ ] JSON 응답 형식 올바름
- [ ] 데이터가 results.json에 저장됨
- [ ] Gradio 대시보드 접속 가능
- [ ] 대시보드에 통계 표시
- [ ] 대시보드에 결과 테이블 표시
- [ ] 새로고침 버튼 작동

### 교수자 도구

- [ ] 패키지 설치 성공
- [ ] student_apis.json 정상 로드
- [ ] 이미지 폴더에서 파일 로드
- [ ] 단일 이미지 전송 성공
- [ ] 여러 이미지 전송 성공
- [ ] 진행률 표시 정상 작동
- [ ] 전송 결과 요약 출력
- [ ] 결과 JSON 파일 저장
- [ ] 병렬 전송 모드 작동
- [ ] 에러 처리 및 재시도 작동

## 알려진 이슈

### 이슈 1: Gradio 자동 새로고침

**문제:** 대시보드가 자동으로 업데이트되지 않음

**해결:** "새로고침" 버튼 클릭

**개선 방안:** Gradio의 실시간 업데이트 기능 추가
```python
demo.load(fn=update_dashboard, inputs=[], outputs=[...], every=5)
```

### 이슈 2: 동시성 문제

**문제:** 여러 요청이 동시에 들어올 때 JSON 파일 충돌 가능

**현재 해결:** `threading.Lock` 사용

**개선 방안:** 데이터베이스 사용 (SQLite, PostgreSQL)

### 이슈 3: 포트 충돌

**문제:** 포트가 이미 사용 중

**해결:** `.env`에서 다른 포트 번호 사용

## 성능 벤치마크

### 예상 성능 지표

- **이미지 업로드**: ~100ms
- **Vision Model API 호출**: ~2-10s (모델에 따라 다름)
- **JSON 저장**: ~10ms
- **전체 처리 시간**: ~2-10s per image

### 부하 테스트

```bash
# 100개 이미지, 0.1초 간격
python image_sender.py --limit 100 --interval 0.1
```

## 디버깅 팁

### FastAPI 디버그 모드

`app.py` 마지막 줄 수정:
```python
uvicorn.run(app, host="0.0.0.0", port=config.SERVER_PORT, reload=True, log_level="debug")
```

### 상세 로그 출력

교수자 도구에서:
```python
# image_sender.py에 추가
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Vision Model API 응답 확인

```python
# app.py의 analyze_sticker 함수에서
print(f"API Response: {response.choices[0].message.content}")
```

## 다음 단계

테스트 완료 후:
1. 버그 수정
2. 코드 리팩토링
3. 문서 업데이트
4. 학생들에게 배포
