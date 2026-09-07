# CryptoPilot backend — FastAPI + bot + scheduler.
FROM python:3.11-slim AS runtime-builder
COPY packages/strategy_runtime /runtime
RUN pip install --upgrade pip==26.2 && pip wheel --no-deps --wheel-dir /wheels /runtime

FROM python:3.11-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# gosu lets the entrypoint fix volume ownership as root then drop to the app user.
RUN apt-get update && apt-get install -y --no-install-recommends gosu \
    && rm -rf /var/lib/apt/lists/*

# Non-root runtime user (SECURITY_GUIDELINES.md)
RUN groupadd -r app && useradd -r -g app app

WORKDIR /app

# Install the hash-locked production graph first for reproducible, auditable
# images. requirements.lock is generated from uv.lock and excludes dev tools.
COPY backend/requirements.lock ./
RUN pip install --upgrade pip==26.2 && pip install --require-hashes --no-deps -r requirements.lock
COPY --from=runtime-builder /wheels /wheels
RUN pip install --no-deps /wheels/*.whl

# Application code
COPY backend/alembic.ini ./
COPY backend/app ./app

# Entrypoint: fix CODEX_HOME volume ownership (as root), then run as app.
COPY <<'EOF' /app/entrypoint.sh
#!/bin/sh
set -e
# Ensure the mounted CODEX_HOME volume is writable by the app user.
CODEX_DIR="${CP_CODEX_HOME:-/data/codex}"
mkdir -p "$CODEX_DIR"
chown -R app:app "$CODEX_DIR" 2>/dev/null || true
echo "Applying database migrations..."
gosu app alembic upgrade head
echo "Starting API..."
exec gosu app uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 1
EOF
RUN chmod +x /app/entrypoint.sh && chown -R app:app /app

# Entrypoint starts as root to chown the volume, then drops to app via gosu.
EXPOSE 8000
CMD ["/app/entrypoint.sh"]
