FROM python:3.11-slim

WORKDIR /app

# 의존성 먼저 설치 (레이어 캐시)
COPY student_template/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 앱 소스 + 번들 샘플 이미지 복사
COPY student_template/ ./student_template/

WORKDIR /app/student_template

# config가 $PORT(Railway 주입)를 읽어 바인딩하고, startup 이벤트가 워커를 기동
CMD ["python", "app.py"]
