# Motor Sticker Detection System

이미지에서 스티커를 검출하고 불량 여부를 판단하는 시스템 - 학생 실습 프로젝트

## 해야할 일

  - 1. 문제 정의
    - 작업자는 불량 검사를 하고 이미지를 서버로 전송만 함.
    - 어떤 서비스가 되어야 작업자 (+관리자) 는 만족할 것인가?
    
  - 2. 구현
    - 제한된 지능 (GPU 리소스 제한, API 비용 제한) 에서 오류 없이 정확한 자동 분석 시스템 만들기
    - 유저가 원하는 정보를 조합해서 보기 좋게 만들기
    - 유저는 절대 이상적으로 행동하지 않음
    
  - 3. 피칭
    - 만든 과정과 결과물을 효과적으로 어필하기


## 프로젝트 개요

학생들이 FastAPI와 Gradio를 사용하여 이미지 분석 API 서버를 구축하고, 교수자가 제공하는 이미지를 분석하여 실시간 대시보드를 업데이트하는 실습 프로젝트입니다.

### 시스템 아키텍처

```
[교수자 도구]              [학생 API 서버]           [Vision Model GPU]
image_sender.py ---------> FastAPI Server ---------> OpenAI Compatible API
                                  |
                                  v
                          Gradio Dashboard
                                  |
                                  v
                          JSON Data Storage
```

## 프로젝트 구조

```
project/
├── README.md                          # 전체 프로젝트 문서 (이 파일)
├── plans.md                           # 구현 계획서
├── requirements.txt                   # 공통 의존성
├── .gitignore                         # Git 무시 파일
│
├── student_template/                  # ★ 학생용 템플릿
│   ├── app.py                         # FastAPI + Gradio 서버
│   ├── config.py                      # 설정 관리
│   ├── requirements.txt               # 의존성
│   ├── .env.example                   # 환경변수 예시
│   ├── README.md                      # 학생용 가이드
│   ├── data/
│   │   ├── uploads/                   # 업로드된 이미지
│   │   └── results.json               # 분석 결과
│   └── static/                        # 정적 파일
│
├── teacher_tools/                     # ★ 교수자용 도구
│   ├── image_sender.py                # 자동 이미지 전송
│   ├── config.py                      # 설정
│   ├── student_apis.json              # 학생 API 목록
│   ├── requirements.txt               # 의존성
│   └── README.md                      # 교수자용 가이드
│
└── venv/                              # 가상환경
```

## 빠른 시작 가이드

### 교수자용

1. **환경 설정**
   ```bash
   cd project
   python3 -m venv venv
   source venv/bin/activate  # Windows: venv\Scripts\activate
   ```

2. **학생 API 목록 작성**
   ```bash
   cd teacher_tools
   # student_apis.json 파일 편집
   ```

3. **이미지 전송**
   ```bash
   pip install -r requirements.txt
   python image_sender.py
   ```

자세한 내용: [teacher_tools/README.md](teacher_tools/README.md)

### 학생용

1. **템플릿 복사**
   ```bash
   cp -r student_template my_project
   cd my_project
   ```

2. **가상환경 및 패키지 설치**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

3. **환경변수 설정**
   ```bash
   cp .env.example .env
   # .env 파일 편집 (API 정보 입력)
   ```

4. **서버 실행**
   ```bash
   python app.py
   ```

자세한 내용: [student_template/README.md](student_template/README.md)

## 주요 기능

### 학생 구현 사항

- [x] FastAPI 기반 REST API 서버
- [x] 이미지 업로드 엔드포인트 (`POST /analyze`)
- [x] Vision Model API 연동
- [x] 스티커 정보 추출 (번호, 색상)
- [x] 불량 수준 판정 (정상/경미/심각)
- [x] JSON 파일 데이터 저장
- [x] Gradio 실시간 대시보드
  - 총 처리된 이미지 수
  - 불량 수준별 통계
  - 최근 분석 결과 테이블
  - 새로고침 기능

### 교수자 도구 기능

- [x] 여러 학생 API로 자동 이미지 전송
- [x] 순차/병렬 전송 모드
- [x] 전송 결과 요약 및 통계
- [x] JSON 형식 결과 저장
- [x] 진행률 표시
- [x] 재시도 및 에러 처리
- [x] 다양한 옵션 (간격, 타임아웃, 반복 등)

## 기술 스택

### 학생용
- **FastAPI**: 고성능 비동기 웹 프레임워크
- **Gradio**: 빠른 대시보드 UI 생성
- **OpenAI SDK**: Vision Model API 클라이언트
- **Uvicorn**: ASGI 서버
- **Pydantic**: 데이터 검증

### 교수자용
- **requests**: HTTP 클라이언트
- **tqdm**: 진행률 표시
- **concurrent.futures**: 병렬 처리

## 설치 및 설정

### 필수 요구사항

- Python 3.8 이상
- pip

### 가상환경 설정

```bash
# 프로젝트 루트에서
python3 -m venv venv

# 활성화
source venv/bin/activate  # macOS/Linux
venv\Scripts\activate     # Windows
```

### Vision Model API 설정

GPU 서버에서 OpenAI compatible API를 호스팅해야 합니다.

**추천 프레임워크:**
- vLLM

## 테스트 가이드

### 로컬 테스트 (단일 학생)

1. **학생 서버 실행**
   ```bash
   cd student_template
   python app.py
   ```

2. **헬스체크**
   ```bash
   curl http://localhost:8000/
   ```

3. **이미지 전송**
   ```bash
   curl -X POST http://localhost:8000/analyze \
     -F "file=@test_image.jpg"
   ```

4. **대시보드 확인**
   - 브라우저에서 `http://localhost:7860` 접속
   - 새로고침 버튼 클릭

### 전체 테스트 (여러 학생)

1. **학생 API 목록 작성**
   ```bash
   cd teacher_tools
   # student_apis.json 편집
   ```

2. **기본 테스트 (3개 이미지)**
   ```bash
   python image_sender.py --limit 3
   ```

3. **전체 이미지 전송**
   ```bash
   python image_sender.py
   ```

4. **병렬 전송 테스트**
   ```bash
   python image_sender.py --parallel
   ```

## 채점 기준

### 기본 기능 (70점)

1. **서버 실행** (15점)
   - FastAPI 서버가 정상 실행
   - 헬스체크 엔드포인트 응답

2. **이미지 분석** (30점)
   - POST /analyze 엔드포인트 구현
   - Vision Model API 연동
   - 스티커 정보 추출
   - 불량 수준 판정
   - 올바른 JSON 응답

3. **데이터 저장** (15점)
   - JSON 파일에 결과 저장
   - 올바른 데이터 구조
   - 동시성 처리

4. **대시보드** (10점)
   - Gradio 대시보드 실행
   - 통계 표시
   - 결과 테이블 표시
   - 새로고침 기능

### 추가 기능 (30점)

- 에러 처리 (10점)
- 코드 품질 및 주석 (10점)
- 문서화 (5점)
- UI/UX 개선 (5점)

## 트러블슈팅

### 학생 측 문제

**문제: Vision Model API 연결 실패**
- `.env` 파일 확인
- API 주소와 키 검증
- 네트워크 연결 확인

**문제: 포트 충돌**
- `.env`에서 포트 변경
- 기존 프로세스 종료

**문제: 패키지 설치 오류**
- Python 버전 확인 (3.8+)
- pip 업그레이드
- 가상환경 재생성

### 교수자 측 문제

**문제: 학생 서버 연결 실패**
- 학생 서버 실행 상태 확인
- API URL 정확성 확인
- 방화벽/네트워크 설정

**문제: 타임아웃**
- `--timeout` 값 증가
- Vision Model API 상태 확인

## 확장 아이디어

### 학생 프로젝트

- [ ] 데이터베이스 연동 (SQLite/PostgreSQL)
- [ ] 사용자 인증 및 권한 관리
- [ ] 이미지 썸네일 표시
- [ ] 실시간 차트/그래프
- [ ] WebSocket 실시간 업데이트
- [ ] 필터링 및 검색 기능
- [ ] CSV/Excel 내보내기
- [ ] Docker 컨테이너화


## 라이선스

이 프로젝트는 교육 목적으로 사용됩니다.

## 참고 자료

- [FastAPI 공식 문서](https://fastapi.tiangolo.com/)
- [Gradio 공식 문서](https://gradio.app/docs/)
- [OpenAI API 문서](https://platform.openai.com/docs/)
- [vLLM 문서](https://docs.vllm.ai/)