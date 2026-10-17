# One container: the web app and the API together (recommended for Northflank).
# Build from the repository root:  docker build -t isift .
FROM node:22-alpine AS web
WORKDIR /app
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install
COPY frontend/ .
# "true" turns on the built-in sign-in / sign-up screens; the API is on the same address.
ENV VITE_DEMO_MODE=true VITE_API_BASE=/api/v1
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOSTED=true APP_ENV=production AUTH_MODE=local ALLOW_LOCAL_AUTH=true \
    RUN_WORKER=true WEB_DIR=/app/web AUDIO_STORAGE_DIR=/data/audio PORT=8000
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ .
COPY --from=web /app/dist /app/web
RUN mkdir -p /data/audio && useradd -m app && chown -R app /data /app
USER app
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s CMD python -c "import urllib.request,os; urllib.request.urlopen('http://127.0.0.1:%s/api/v1/health' % os.environ.get('PORT','8000'))"
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000} --proxy-headers --forwarded-allow-ips='*'"]
