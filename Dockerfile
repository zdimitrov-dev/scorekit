FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

# Default: run the ingestion job. Override args at `docker compose run` time.
ENTRYPOINT ["python", "-m", "scorekit.jobs.ingest"]
