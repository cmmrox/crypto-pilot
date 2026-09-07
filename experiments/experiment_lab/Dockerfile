FROM python:3.11-slim AS builder
COPY packages/strategy_runtime /runtime
COPY experiments/experiment_lab /lab
RUN pip install --upgrade pip==26.2 && pip wheel --no-deps --wheel-dir /wheels /runtime /lab

FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
RUN groupadd --gid 1100 lab && useradd --uid 1100 --gid 1100 --create-home lab
WORKDIR /app
COPY experiments/experiment_lab/requirements.lock ./
RUN pip install --upgrade pip==26.2 && pip install --require-hashes --no-deps -r requirements.lock
COPY --from=builder /wheels /wheels
RUN pip install --no-deps /wheels/*.whl && mkdir /data && chown lab:lab /data
USER lab
CMD ["uvicorn", "experiment_lab.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8010", "--workers", "1"]
