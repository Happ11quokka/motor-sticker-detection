# Teacher Tools - 교수자용 이미지 전송 도구

학생들이 구축한 API 서버로 자동으로 이미지를 전송하고 테스트하는 도구입니다.

## 파일 구조

```
teacher_tools/
├── image_sender.py         # 이미지 자동 전송 스크립트
├── config.py               # 설정
├── student_apis.json       # 학생 API 주소 목록
├── requirements.txt        # 필요한 패키지
└── README.md               # 이 문서
```

## 설치 방법

### 1단계: 가상환경 활성화

프로젝트 루트의 가상환경을 사용합니다:

```bash
# 프로젝트 루트로 이동
cd /path/to/project

# 가상환경 활성화
source venv/bin/activate  # macOS/Linux
# 또는
venv\Scripts\activate     # Windows
```

### 2단계: 패키지 설치

```bash
cd teacher_tools
pip install -r requirements.txt
```

## 학생 API 목록 관리

### student_apis.json 편집

학생들이 제출한 API 주소를 `student_apis.json` 파일에 추가합니다:

```json
{
  "students": [
    {
      "id": 1,
      "name": "홍길동",
      "student_id": "2021001",
      "api_url": "http://localhost:8000",
      "active": true
    },
    {
      "id": 2,
      "name": "김철수",
      "student_id": "2021002",
      "api_url": "https://abc123.ngrok.io",
      "active": true
    },
    {
      "id": 3,
      "name": "이영희",
      "student_id": "2021003",
      "api_url": "http://192.168.1.100:8000",
      "active": false
    }
  ]
}
```

**필드 설명:**
- `id`: 학생 고유 번호
- `name`: 학생 이름
- `student_id`: 학번
- `api_url`: API 서버 주소 (http:// 또는 https://)
- `active`: 활성화 여부 (false면 전송하지 않음)

## 사용 방법

### 기본 사용법

모든 활성화된 학생에게 이미지를 순차적으로 전송:

```bash
python image_sender.py
```

### 옵션

#### 이미지 폴더 지정

```bash
python image_sender.py --image-folder /path/to/images
```

기본값: `../data/motor_checker`

#### 학생 파일 지정

```bash
python image_sender.py --student-file my_students.json
```

기본값: `student_apis.json`

#### 전송 간격 설정

이미지 전송 사이의 대기 시간 (초):

```bash
python image_sender.py --interval 2.0
```

기본값: 1.0초

#### 타임아웃 설정

API 요청 타임아웃 (초):

```bash
python image_sender.py --timeout 60
```

기본값: 30초

#### 병렬 전송

여러 학생에게 동시에 전송:

```bash
python image_sender.py --parallel
```

기본값: 순차 전송

#### 반복 전송

같은 이미지를 여러 번 전송:

```bash
python image_sender.py --repeat 3
```

기본값: 1회

#### 이미지 개수 제한

전송할 이미지 개수 제한:

```bash
python image_sender.py --limit 10
```

기본값: 전체 이미지

#### 결과 저장

결과를 JSON 파일로 저장:

```bash
python image_sender.py --output results.json
```

기본값: `send_results.json`

### 사용 예시

#### 예시 1: 기본 테스트

```bash
python image_sender.py --limit 5
```

처음 5개 이미지만 전송하여 빠르게 테스트

#### 예시 2: 병렬 전송

```bash
python image_sender.py --parallel --interval 0.5
```

모든 학생에게 동시에 전송, 이미지 간 0.5초 간격

#### 예시 3: 부하 테스트

```bash
python image_sender.py --repeat 10 --interval 0.1
```

같은 이미지를 10번 반복 전송, 간격 0.1초 (성능 테스트)

#### 예시 4: 특정 이미지 폴더

```bash
python image_sender.py \
  --image-folder /path/to/test_images \
  --timeout 60 \
  --output test_results.json
```

특정 폴더의 이미지 사용, 타임아웃 60초, 결과 저장

## 출력 형식

### 실행 중 출력

```
======================================================================
이미지 전송 시작
======================================================================
이미지 폴더: ../data/motor_checker
이미지 개수: 9개
학생 수: 2명
전송 간격: 1.0초
타임아웃: 30초
반복 횟수: 1회
병렬 모드: 아니오
======================================================================

학생: 홍길동 (2021001)
API URL: http://localhost:8000
전송할 이미지: 9개

홍길동 전송 중: 100%|██████████| 9/9 [00:12<00:00,  1.38s/it]

결과: 성공 9 / 실패 0
```

### 최종 요약

```
======================================================================
전송 결과 요약
======================================================================

홍길동 (2021001):
  성공: 9/9 (100.0%)
  실패: 0/9

김철수 (2021002):
  성공: 8/9 (88.9%)
  실패: 1/9
  실패한 이미지:
    - image_3.jpg: Timeout after 30 seconds

======================================================================
```

### 결과 JSON 파일

`send_results.json` 파일에 상세한 결과가 저장됩니다:

```json
[
  {
    "student": {
      "id": 1,
      "name": "홍길동",
      "student_id": "2021001",
      "api_url": "http://localhost:8000"
    },
    "total": 9,
    "success": 9,
    "failed": 0,
    "details": [
      {
        "image": "image_1.jpg",
        "status": "✓",
        "result": {
          "success": true,
          "status_code": 200,
          "data": {
            "id": 1,
            "timestamp": "2025-12-25 12:00:00",
            "has_sticker": true,
            "sticker_number": "42",
            "sticker_color": "초록색",
            "defect_level": "정상"
          }
        }
      }
    ]
  }
]
```

## 트러블슈팅

### 문제: Connection failed

**원인:** 학생 서버가 실행되지 않았거나 주소가 잘못됨

**해결:**
1. 학생에게 서버 실행 확인 요청
2. `student_apis.json`의 URL이 정확한지 확인
3. 네트워크 연결 확인

### 문제: Timeout

**원인:** Vision Model API가 느리거나 응답 없음

**해결:**
- `--timeout` 값을 증가 (예: 60초)
- 학생에게 Vision Model API 설정 확인 요청

### 문제: 이미지를 찾을 수 없음

**원인:** 이미지 폴더 경로가 잘못됨

**해결:**
```bash
python image_sender.py --image-folder /correct/path/to/images
```

## 채점 가이드

### 기본 채점 기준

1. **서버 실행** (20점)
   - API 서버가 정상적으로 실행되는가?
   - 헬스체크 엔드포인트가 응답하는가?

2. **이미지 분석** (40점)
   - 이미지를 받아서 정상적으로 분석하는가?
   - Vision Model API 연동이 잘 되어있는가?
   - 응답 형식이 올바른가?

3. **데이터 저장** (20점)
   - 분석 결과가 JSON 파일에 저장되는가?
   - 데이터 구조가 올바른가?

4. **대시보드** (20점)
   - Gradio 대시보드가 실행되는가?
   - 실시간으로 결과가 업데이트되는가?
   - 통계가 정확하게 표시되는가?

### 자동 채점 스크립트 (예시)

```bash
# 1. 헬스체크
curl http://localhost:8000/

# 2. 이미지 3개 전송
python image_sender.py --limit 3 --output grade_results.json

# 3. 결과 확인
cat grade_results.json
```

## 고급 사용법

### 특정 학생만 테스트

`student_apis.json`에서 해당 학생만 `active: true`로 설정

### 실시간 모니터링

다른 터미널에서 학생 대시보드 접속:
```
http://student-api-url:7860
```

### 스크립트 작성

```bash
#!/bin/bash
# 여러 테스트를 순차적으로 실행

echo "=== 기본 테스트 (3개 이미지) ==="
python image_sender.py --limit 3 --output test1.json

echo "=== 부하 테스트 (반복 5회) ==="
python image_sender.py --repeat 5 --output test2.json

echo "=== 병렬 테스트 ==="
python image_sender.py --parallel --output test3.json

echo "모든 테스트 완료"
```

## 참고사항

- 학생 서버는 반드시 먼저 실행되어 있어야 합니다
- ngrok 같은 터널링 서비스는 무료 플랜에서 요청 제한이 있을 수 있습니다
- 대량의 이미지를 전송할 때는 `--interval`을 적절히 조절하세요
- Vision Model API에 비용이 발생할 수 있으니 주의하세요
