# syntax=docker/dockerfile:1
FROM python:3.12-slim-bookworm@sha256:34386ef0cb081344d7ec1c103ba398e6e9f64e9ab3a1509accc92a4e24a07258
WORKDIR /opt/xju
RUN pip install --no-cache-dir uv==0.12.5
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project && .venv/bin/python -m ipykernel install --prefix=/usr/local
ENV PATH=/opt/xju/.venv/bin:$PATH PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY notebook_runner.py ./
USER 65532:65532
WORKDIR /work
CMD ["python", "-I", "/opt/xju/notebook_runner.py"]
