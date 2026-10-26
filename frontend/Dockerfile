# No syntax= directive on purpose: the daemon's built-in Dockerfile frontend
# finds the host-only FRONTEND_BASE_IMAGE locally, while the external
# docker/dockerfile image asks the registry for it first and stalls the build.
ARG NODE_IMAGE=node:24.19.0-bookworm-slim@sha256:3638d9a6fe4030bd716be989438248074489337ba3275657f93595428be4fc03
ARG NGINX_IMAGE=nginx:1.30.4-alpine@sha256:97d490c12ba55b4946b01546d1c3ed324e8d41ab1c9fcb2a616aa470620e5b46
ARG PNPM_VERSION=11.22.0
ARG FRONTEND_BASE_IMAGE=xju-oj-frontend-base:node-24.19.0-bookworm-slim-v1

FROM ${NODE_IMAGE} AS frontend-base
ARG PNPM_VERSION
RUN set -eux; \
    sed -i \
        -e 's|http://deb.debian.org/debian-security|http://mirrors.aliyun.com/debian-security|g' \
        -e 's|http://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g' \
        -e 's|https://deb.debian.org/debian-security|http://mirrors.aliyun.com/debian-security|g' \
        -e 's|https://deb.debian.org/debian|http://mirrors.aliyun.com/debian|g' \
        /etc/apt/sources.list.d/debian.sources; \
    apt-get -o Acquire::Retries=5 update; \
    apt-get install -y --no-install-recommends ca-certificates git; \
    rm -rf /var/lib/apt/lists/*; \
    corepack enable; \
    corepack install --global "pnpm@${PNPM_VERSION}"; \
    pnpm --version | grep -Fx "${PNPM_VERSION}"

FROM ${FRONTEND_BASE_IMAGE} AS frontend-deps
ARG TARGETOS TARGETARCH
WORKDIR /src
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
RUN --mount=type=cache,id=pnpm-${TARGETOS:-linux}-${TARGETARCH:-amd64},target=/pnpm/store,sharing=locked \
    pnpm config set store-dir /pnpm/store && pnpm fetch --frozen-lockfile

FROM frontend-deps AS frontend-build
ARG TARGETOS TARGETARCH
ARG GIT_COMMIT=unknown
ENV GIT_COMMIT=${GIT_COMMIT}
COPY . ./
RUN --mount=type=cache,id=pnpm-${TARGETOS:-linux}-${TARGETARCH:-amd64},target=/pnpm/store,sharing=locked \
    pnpm config set store-dir /pnpm/store && \
    pnpm install --offline --frozen-lockfile && \
    pnpm run build

FROM ${NGINX_IMAGE} AS frontend-runtime
ARG VCS_REF=unknown
ARG BUILD_VERSION=phase1
LABEL org.opencontainers.image.source="xju-OJ" \
      org.opencontainers.image.revision="$VCS_REF" \
      org.opencontainers.image.version="$BUILD_VERSION"
COPY nginx/nginx.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.d/ /docker-entrypoint.d/
COPY --from=frontend-build /src/dist/ /usr/share/nginx/html/
COPY --from=frontend-build /src/static/userscripts/ /usr/share/nginx/html/static/userscripts/
RUN test -s /usr/share/nginx/html/static/userscripts/xju-oj-remote-bridge.user.js && \
    grep -Fq '// ==UserScript==' /usr/share/nginx/html/static/userscripts/xju-oj-remote-bridge.user.js
EXPOSE 80
