# syntax=docker/dockerfile:1.7
ARG BASE_IMAGE=python:3.10-slim-bookworm@sha256:7ed92b32353e8d8bd865b5ba811e0315d3999c3b57b1c2df2b504a359d4a1707
ARG UV_VERSION=0.12.5
# uv.lock pins artifact URLs on this index; change both together (see README).
ARG PYPI_INDEX_URL=https://repo.huaweicloud.com/repository/pypi/simple
# Debian packages come from Huawei Cloud; deploy.sh switches to the in-region
# mirror (mirrors.myhuaweicloud.com) when the build host can reach it.
ARG DEBIAN_MIRROR=https://repo.huaweicloud.com

FROM ${BASE_IMAGE} AS backend-deps
ARG DEBIAN_MIRROR
ARG TARGETARCH
ARG TARGETVARIANT
ARG UV_VERSION
ARG PYPI_INDEX_URL
ENV DEBIAN_FRONTEND=noninteractive \
    UV_LINK_MODE=copy \
    UV_COMPILE_BYTECODE=1 \
    UV_INDEX_URL=${PYPI_INDEX_URL} \
    UV_HTTP_TIMEOUT=60 \
    PATH=/root/.local/bin:$PATH
WORKDIR /app

RUN --mount=type=cache,target=/var/cache/apt,id=backend-apt-${TARGETARCH}-${TARGETVARIANT},sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,id=backend-apt-lists-${TARGETARCH}-${TARGETVARIANT},sharing=locked \
    set -eux; \
    rm -f /etc/apt/apt.conf.d/docker-clean; \
    sed -i \
        -e "s|http://deb.debian.org/debian-security|${DEBIAN_MIRROR}/debian-security|g" \
        -e "s|http://deb.debian.org/debian|${DEBIAN_MIRROR}/debian|g" \
        -e "s|https://deb.debian.org/debian-security|${DEBIAN_MIRROR}/debian-security|g" \
        -e "s|https://deb.debian.org/debian|${DEBIAN_MIRROR}/debian|g" \
        /etc/apt/sources.list.d/debian.sources; \
    apt-get -o Acquire::Retries=5 update; \
    apt-get install -y --no-install-recommends \
        build-essential \
        libfreetype6-dev \
        libjpeg62-turbo-dev \
        libpq-dev \
        zlib1g-dev; \
    python -m pip install --no-cache-dir \
        --index-url "${PYPI_INDEX_URL}" \
        --timeout 60 --retries 5 \
        "uv==${UV_VERSION}"

COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv,id=backend-uv-${TARGETARCH}-${TARGETVARIANT}-py310,sharing=locked \
    uv sync --locked --no-dev --no-install-project

FROM backend-deps AS backend-build
COPY . ./
RUN --mount=type=cache,target=/root/.cache/uv,id=backend-uv-${TARGETARCH}-${TARGETVARIANT}-py310,sharing=locked \
    uv sync --locked --no-dev

FROM ${BASE_IMAGE} AS backend-runtime
ARG DEBIAN_MIRROR
ARG TARGETARCH
ARG VCS_REF=unknown
ARG BUILD_VERSION=phase1
ENV DEBIAN_FRONTEND=noninteractive \
    OJ_ENV=production \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/app/.venv/bin:$PATH
WORKDIR /app

RUN --mount=type=cache,target=/var/cache/apt,id=backend-apt-${TARGETARCH},sharing=locked \
    --mount=type=cache,target=/var/lib/apt/lists,id=backend-apt-lists-${TARGETARCH},sharing=locked \
    set -eux; \
    rm -f /etc/apt/apt.conf.d/docker-clean; \
    sed -i \
        -e "s|http://deb.debian.org/debian-security|${DEBIAN_MIRROR}/debian-security|g" \
        -e "s|http://deb.debian.org/debian|${DEBIAN_MIRROR}/debian|g" \
        -e "s|https://deb.debian.org/debian-security|${DEBIAN_MIRROR}/debian-security|g" \
        -e "s|https://deb.debian.org/debian|${DEBIAN_MIRROR}/debian|g" \
        /etc/apt/sources.list.d/debian.sources; \
    apt-get -o Acquire::Retries=5 update; \
    apt-get install -y --no-install-recommends \
        ca-certificates \
        gosu \
        libfreetype6 \
        libjpeg62-turbo \
        libpq5 \
        zlib1g; \
    # XeLaTeX with Chinese support typesets contest statement PDFs (contest/statement_pdf.py).
    apt-get install -y --no-install-recommends \
        fonts-texgyre \
        lmodern \
        texlive-fonts-recommended \
        texlive-lang-chinese \
        texlive-latex-recommended \
        texlive-pictures \
        texlive-plain-generic \
        texlive-xetex; \
    rm -rf /var/lib/apt/lists/*

COPY --from=backend-build /app/.venv /app/.venv
COPY . ./

RUN set -eux; \
    addgroup --system backend; \
    adduser --system --ingroup backend --no-create-home --disabled-login backend; \
    chmod -R u=rwX,go=rX /app; \
    chmod +x /app/deploy/entrypoint.sh; \
    chown -R backend:backend /app

LABEL org.opencontainers.image.source="xju-OJ" \
      org.opencontainers.image.revision="$VCS_REF" \
      org.opencontainers.image.version="$BUILD_VERSION"

EXPOSE 8000
ENTRYPOINT ["/app/deploy/entrypoint.sh"]
CMD ["api"]
