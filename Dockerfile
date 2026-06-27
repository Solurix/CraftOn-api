# CRAFT-ON API container — runs on Cloud Run (asia-northeast1).
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# System deps kept minimal; psycopg[binary] ships its own libpq.
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Install dependencies first for better layer caching.
COPY pyproject.toml README.md ./
RUN pip install --upgrade pip && pip install .

# App source + migrations.
COPY app ./app
COPY migrations ./migrations
COPY alembic.ini ./

# Cloud Run provides $PORT (default 8080).
ENV PORT=8080
EXPOSE 8080

# Run migrations then start the server. Cloud Run health-checks /readyz.
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
