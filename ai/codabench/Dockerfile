# syntax=docker/dockerfile:1
FROM python:3.13.11-slim-bookworm@sha256:20080e807bfc404f8450b185cf0fc95d553462673598549613735f70a5b4d5d0 AS base
RUN pip install --no-cache-dir uv==0.12.5
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 UV_LINK_MODE=copy

FROM base AS site
WORKDIR /app
COPY --from=codabench /pyproject.toml /uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY --from=codabench /LICENSE.TXT /usr/share/licenses/codabench/LICENSE.TXT
COPY --from=codabench /src ./src
COPY ai/codabench/site_settings.py /app/src/settings/xju.py
COPY ai/practice /opt/xju/practice
COPY ai/codabench/bootstrap.py /opt/xju/bootstrap.py
ENV PATH=/app/.venv/bin:$PATH DJANGO_SETTINGS_MODULE=settings.xju
WORKDIR /app/src
CMD ["gunicorn", "--bind=0.0.0.0:8000", "--workers=1", "--threads=4", "--timeout=60", "wsgi:application"]

FROM base AS compute
WORKDIR /app
COPY --from=codabench /compute_worker/pyproject.toml /compute_worker/uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project
COPY --from=codabench /LICENSE.TXT /usr/share/licenses/codabench/LICENSE.TXT
COPY --from=codabench /compute_worker/*.py ./
COPY --from=codabench /src/settings/logs_loguru.py ./logs_loguru.py
COPY ai/codabench/secure_worker.py ./
COPY ai/compute /opt/bridge
ENV PATH=/app/.venv/bin:$PATH
CMD ["celery", "-A", "secure_worker", "worker", "--loglevel=WARNING", "--queues=compute-worker", "--concurrency=1"]
