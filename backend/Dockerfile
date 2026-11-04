FROM python:3.12-slim AS base
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
RUN apt-get update && apt-get install -y --no-install-recommends \
        tesseract-ocr tesseract-ocr-fra tesseract-ocr-eng poppler-utils curl \
    && rm -rf /var/lib/apt/lists/*
RUN useradd --create-home --uid 10001 documind
WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt boto3 azure-storage-blob
COPY --chown=documind:documind . .
USER documind
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s CMD curl -fsS http://localhost:8000/api/v1/health/live || exit 1
# The API container runs migrations then serves; workers use the same image with another command.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port 8000 --proxy-headers --workers ${WEB_CONCURRENCY:-2}"]
