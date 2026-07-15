# IL-BOT Data Studio — 플랫폼 서버 이미지
# 1단계: 프론트엔드 정적 빌드
FROM node:22-slim AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ .
RUN npm run build

# 2단계: 파이썬 런타임 (ffmpeg은 imageio-ffmpeg 정적 바이너리라 apt 불필요)
FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY src/ src/
RUN pip install --no-cache-dir ".[server]"
COPY --from=ui /ui/dist /app/frontend/dist

ENV ROBOLABEL_DATA=/data \
    ROBOLABEL_UI=/app/frontend/dist
VOLUME /data
EXPOSE 8322
CMD ["uvicorn", "robolabel.server.app:app", "--host", "0.0.0.0", "--port", "8322", "--log-level", "warning"]
