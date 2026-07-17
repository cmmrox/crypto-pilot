# CryptoPilot backend — FastAPI + bot + scheduler.
FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# Non-root runtime user (SECURITY_GUIDELINES.md)
RUN groupadd -r app && useradd -r -g app app

WORKDIR /app

# Install dependencies first for layer caching
COPY pyproject.toml ./
RUN pip install --upgrade pip && pip install .

# Application code
COPY alembic.ini ./
COPY app ./app

# Entrypoint: apply migrations, then serve
COPY <<'EOF' /app/entrypoint.sh
#!/bin/sh
set -e
echo "Applying database migrations..."
alembic upgrade head
echo "Starting API..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
EOF
RUN chmod +x /app/entrypoint.sh && chown -R app:app /app

USER app
EXPOSE 8000
CMD ["/app/entrypoint.sh"]
