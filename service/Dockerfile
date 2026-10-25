FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8080

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends libegl1 libgles2 libportaudio2 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./requirements.txt
RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r requirements.txt

# Match the locally verified MediaPipe setup without allowing it to replace the
# project's pinned OpenCV 5 package with an OpenCV 4 wheel.
RUN python -m pip install --no-cache-dir --no-deps mediapipe==1.1.0 \
    && python -m pip install --no-cache-dir absl-py certifi flatbuffers sounddevice matplotlib protobuf

COPY app ./app
COPY models ./models

EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
