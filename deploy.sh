#!/bin/sh
set -eu

ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd -P)
ENV_FILE=${ENV_FILE:-"$ROOT/.env"}
COMPOSE_FILE=${COMPOSE_FILE:-"$ROOT/compose.yaml"}
DRY_RUN=0
CONFIG_ONLY=0
FRONTEND_ONLY=0
DEV_MODE=0
DEV_TARGET=

# Never inherit workstation/server proxy variables. Optional download proxies are
# accepted only through the explicit BUILD_*_PROXY settings and are never used
# by runtime containers.
unset HTTP_PROXY HTTPS_PROXY ALL_PROXY FTP_PROXY http_proxy https_proxy all_proxy ftp_proxy

usage() {
    cat <<'EOF'
Usage: ./deploy.sh [--dry-run] [--config-only] [--frontend-only]
       ./deploy.sh --dev frontend

Modes:
  --frontend-only  build/release only frontend; keep all backend services running
  --dev frontend    start backend services in Docker and run frontend with pnpm dev

Environment:
  ENV_FILE       .env path (default: repository/.env)
  COMPOSE_FILE   Compose path (default: repository/compose.yaml)
EOF
}

for arg in "$@"; do
    case "$arg" in
        --help|-h) usage; exit 0 ;;
        --dry-run) DRY_RUN=1 ;;
        --config-only) CONFIG_ONLY=1 ;;
        --frontend-only) FRONTEND_ONLY=1 ;;
        --dev) DEV_MODE=1 ;;
        frontend)
            [ "$DEV_MODE" -eq 1 ] || { printf '%s\n' "unexpected argument: frontend" >&2; usage >&2; exit 2; }
            [ -z "$DEV_TARGET" ] || { printf '%s\n' "duplicate dev target: frontend" >&2; usage >&2; exit 2; }
            DEV_TARGET=frontend
            ;;
        *) printf '%s\n' "unknown option: $arg" >&2; usage >&2; exit 2 ;;
    esac
done

if [ "$DEV_MODE" -eq 1 ]; then
    [ "$DEV_TARGET" = frontend ] || { printf '%s\n' "--dev requires the target: frontend" >&2; usage >&2; exit 2; }
    [ "$FRONTEND_ONLY" -eq 0 ] || { printf '%s\n' "--dev frontend cannot be combined with --frontend-only" >&2; exit 2; }
    [ "$CONFIG_ONLY" -eq 0 ] || { printf '%s\n' "--dev frontend cannot be combined with --config-only" >&2; exit 2; }
fi

fail() {
    printf '%s\n' "deploy: $*" >&2
    exit 1
}

REMOTE_USERSCRIPT_PATH="$ROOT/frontend/static/userscripts/xju-oj-remote-bridge.user.js"
REMOTE_USERSCRIPT_URL_PATH="/static/userscripts/xju-oj-remote-bridge.user.js"

remote_userscript_source_guard() {
    [ -s "$REMOTE_USERSCRIPT_PATH" ] || fail "remote OJ userscript is missing: $REMOTE_USERSCRIPT_PATH"
    grep -Fq '// ==UserScript==' "$REMOTE_USERSCRIPT_PATH" || fail "remote OJ userscript metadata header is missing"
    grep -Fq '@downloadURL  https://oj.icthub.top/static/userscripts/xju-oj-remote-bridge.user.js' \
        "$REMOTE_USERSCRIPT_PATH" || fail "remote OJ userscript download URL is invalid"
    grep -Fq '@updateURL    https://oj.icthub.top/static/userscripts/xju-oj-remote-bridge.user.js' \
        "$REMOTE_USERSCRIPT_PATH" || fail "remote OJ userscript update URL is invalid"
}

remote_userscript_source_guard

command -v docker >/dev/null 2>&1 || fail "docker is required"
command -v python3 >/dev/null 2>&1 || fail "python3 is required"
docker compose version >/dev/null 2>&1 || fail "docker compose is required"

case "$ENV_FILE" in
    /*) ;;
    *) ENV_FILE="$ROOT/$ENV_FILE" ;;
esac
case "$COMPOSE_FILE" in
    /*) ;;
    *) COMPOSE_FILE="$ROOT/$COMPOSE_FILE" ;;
esac
ENV_FILE=$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$ENV_FILE")
COMPOSE_FILE=$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$COMPOSE_FILE")
EXAMPLE_ENV=$(python3 -c 'import os,sys; print(os.path.realpath(sys.argv[1]))' "$ROOT/.env.example")

[ -f "$ENV_FILE" ] || fail "env file is required: $ENV_FILE (copy .env.example to .env first)"
[ -f "$COMPOSE_FILE" ] || fail "compose file is required: $COMPOSE_FILE"
env_identity=$(stat -c '%d:%i' "$ENV_FILE")
example_identity=$(stat -c '%d:%i' "$EXAMPLE_ENV")
[ "$env_identity" != "$example_identity" ] || fail "do not deploy with .env.example directly; copy it to .env"
if [ "$DRY_RUN" -eq 0 ] && [ "$CONFIG_ONLY" -eq 0 ]; then
    chmod 600 "$ENV_FILE" || fail "cannot protect env file: $ENV_FILE"
fi
unset EXAMPLE_ENV env_identity example_identity

parsed_env=$(python3 - "$ENV_FILE" <<'PY'
import json
import os
import re
import shlex
import sys

path = sys.argv[1]
name_re = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
var_re = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")
allowed = {
    "COMPOSE_PROJECT_NAME", "APP_DOMAIN", "PUBLIC_BASE_URL", "CSRF_TRUSTED_ORIGINS", "DEPLOY_HEARTBEAT_SECONDS",
    "DEV_FRONTEND_HOST", "DEV_FRONTEND_PORT", "DEV_BACKEND_BIND_ADDRESS", "DEV_BACKEND_PORT",
    "HTTP_BIND_ADDRESS", "HTTP_PORT", "DEPLOY_ROOT", "RUNTIME_ROOT", "TRUSTED_PROXY_CIDRS",
    "BACKUP_ROOT", "SECRET_ROOT", "DEPLOY_MODE", "SECRET_PROVISION_MODE",
    "GIT_COMMIT", "BUILD_VERSION", "BUILD_CREATED", "BUILD_TARGETS",
    "BUILD_NETWORK", "BUILD_HTTP_PROXY", "BUILD_HTTPS_PROXY", "BUILD_ALL_PROXY",
    "CACHE_REGISTRY",
    "FRONTEND_IMAGE_REF", "FRONTEND_BASE_IMAGE", "BACKEND_IMAGE_REF", "JUDGE_IMAGE_REF",
    "JUDGE_TOOLCHAIN_IMAGE_REF", "POSTGRES_IMAGE_REF", "REDIS_IMAGE_REF",
    "POSTGRES_DB", "POSTGRES_USER", "INITIAL_ADMIN_USERNAME",
    "POSTGRES_PASSWORD_FILE", "DJANGO_SECRET_KEY_FILE",
    "JUDGE_SERVER_TOKEN_FILE", "INITIAL_ADMIN_PASSWORD_FILE",
    "JUDGER_HTTP_WORKERS", "JUDGER_HTTP_THREADS", "JUDGER_TESTCASE_WORKERS",
    "TEST_CASE_GROUP_GID",
    "AUTHENTIK_OIDC_ENABLED", "AUTHENTIK_LOCAL_LOGIN_ENABLED", "AUTHENTIK_LOCAL_REGISTER_ENABLED", "OJ_FRONTEND_DEV_MODE",
    "AUTHENTIK_OIDC_ISSUER", "AUTHENTIK_OIDC_CLIENT_ID", "AUTHENTIK_OIDC_CLIENT_SECRET_FILE",
    "AUTHENTIK_OIDC_REDIRECT_URI", "AUTHENTIK_OIDC_REGISTER_URL",
    "AUTHENTIK_OIDC_POST_LOGOUT_REDIRECT_URI", "AUTHENTIK_OIDC_SCOPES",
    "AUTHENTIK_OIDC_STATE_TTL_SECONDS", "AUTHENTIK_OIDC_CLOCK_SKEW_SECONDS",
    "AUTHENTIK_OIDC_ALLOWED_ALGORITHMS",
}
forbidden = {
    "POSTGRES_PASSWORD", "DJANGO_SECRET_KEY", "JUDGE_SERVER_TOKEN",
    "INITIAL_ADMIN_PASSWORD",
}
values = dict(os.environ)
file_keys = []

def expand(value):
    return var_re.sub(lambda match: values.get(match.group(1) or match.group(2), ""), value)

with open(path, encoding="utf-8") as handle:
    for line_number, original in enumerate(handle, 1):
        line = original.rstrip("\r\n")
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if stripped.startswith("export "):
            stripped = stripped[7:].lstrip()
        if "=" not in stripped:
            raise SystemExit(f"{path}:{line_number}: expected KEY=value")
        key, raw = stripped.split("=", 1)
        key = key.strip()
        if not name_re.fullmatch(key):
            raise SystemExit(f"{path}:{line_number}: invalid variable name")
        if key in forbidden:
            raise SystemExit(f"{path}:{line_number}: secrets must use *_FILE paths, not {key}")
        if key not in allowed:
            raise SystemExit(f"{path}:{line_number}: unsupported deployment variable: {key}")
        raw = raw.strip()
        if raw.startswith("'"):
            if len(raw) < 2 or not raw.endswith("'"):
                raise SystemExit(f"{path}:{line_number}: unterminated single quote")
            value = raw[1:-1]
        elif raw.startswith('"'):
            try:
                value = expand(json.loads(raw))
            except (json.JSONDecodeError, TypeError) as exc:
                raise SystemExit(f"{path}:{line_number}: invalid double-quoted value: {exc}")
        else:
            raw = re.split(r"\s+#", raw, maxsplit=1)[0].rstrip()
            value = expand(raw)
        if key not in os.environ:
            values[key] = value
        if key not in file_keys:
            file_keys.append(key)

for key in file_keys:
    print(f"export {key}={shlex.quote(values.get(key, ''))}")
PY
) || fail "invalid env file: $ENV_FILE"
eval "$parsed_env"
unset parsed_env

absolute_path() {
    python3 - "$ROOT" "$1" <<'PY'
import os
import sys

root, value = sys.argv[1:]
if not os.path.isabs(value):
    value = os.path.join(root, value)
print(os.path.realpath(value))
PY
}

secret_path() {
    python3 - "$ROOT" "$1" <<'PY'
import os
import sys

root, value = sys.argv[1:]
if not os.path.isabs(value):
    value = os.path.join(root, value)
lexical = os.path.abspath(value)
if os.path.islink(lexical):
    raise SystemExit(f"secret destination must not be a symlink: {lexical}")
parent = os.path.realpath(os.path.dirname(lexical))
print(os.path.join(parent, os.path.basename(lexical)))
PY
}

detected_commit=$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || printf '%s' local)
GIT_COMMIT=${GIT_COMMIT:-$detected_commit}
if [ "$DEV_MODE" -eq 0 ] && [ "$DRY_RUN" -eq 0 ] && [ "$CONFIG_ONLY" -eq 0 ]; then
    [ "$GIT_COMMIT" = "$detected_commit" ] || fail "GIT_COMMIT must identify the checked-out HEAD"
    [ -z "$(git -C "$ROOT" status --porcelain --untracked-files=all)" ] || \
        fail "production deployment requires a committed, clean worktree; commit/pull the intended release first"
fi
git_tag=$(printf '%.12s' "$GIT_COMMIT")
BUILD_VERSION=${BUILD_VERSION:-phase3}
if [ -z "${BUILD_CREATED:-}" ]; then
    BUILD_CREATED=$(git -C "$ROOT" show -s --format=%cI "$GIT_COMMIT" 2>/dev/null || date -u +%Y-%m-%dT%H:%M:%SZ)
fi

COMPOSE_PROJECT_NAME=${COMPOSE_PROJECT_NAME:-xju-oj}
APP_DOMAIN=${APP_DOMAIN:-localhost}
PUBLIC_BASE_URL=${PUBLIC_BASE_URL:-http://127.0.0.1:18080}
CSRF_TRUSTED_ORIGINS=${CSRF_TRUSTED_ORIGINS:-https://oj.icthub.top}
DEV_FRONTEND_HOST=${DEV_FRONTEND_HOST:-127.0.0.1}
DEV_FRONTEND_PORT=${DEV_FRONTEND_PORT:-5173}
DEV_BACKEND_BIND_ADDRESS=${DEV_BACKEND_BIND_ADDRESS:-127.0.0.1}
DEV_BACKEND_PORT=${DEV_BACKEND_PORT:-8000}
HTTP_BIND_ADDRESS=${HTTP_BIND_ADDRESS:-127.0.0.1}
HTTP_PORT=${HTTP_PORT:-18080}
TRUSTED_PROXY_CIDRS=${TRUSTED_PROXY_CIDRS:-}
export TRUSTED_PROXY_CIDRS
python3 - "$TRUSTED_PROXY_CIDRS" <<'PY' || fail "TRUSTED_PROXY_CIDRS must contain numeric proxy addresses/CIDRs"
import ipaddress, sys
for value in sys.argv[1].split():
    network = ipaddress.ip_network(value, strict=False)
    if network.prefixlen == 0:
        raise SystemExit("refusing to trust the entire Internet")
PY
DEPLOY_MODE=${DEPLOY_MODE:-build}
SECRET_PROVISION_MODE=${SECRET_PROVISION_MODE:-prompt}
DEPLOY_HEARTBEAT_SECONDS=${DEPLOY_HEARTBEAT_SECONDS:-60}
case "$DEPLOY_HEARTBEAT_SECONDS" in
    ''|*[!0-9]*) fail "DEPLOY_HEARTBEAT_SECONDS must be an integer between 10 and 3600" ;;
esac
[ "$DEPLOY_HEARTBEAT_SECONDS" -ge 10 ] && [ "$DEPLOY_HEARTBEAT_SECONDS" -le 3600 ] || \
    fail "DEPLOY_HEARTBEAT_SECONDS must be an integer between 10 and 3600"
case "$DEV_FRONTEND_PORT:$DEV_BACKEND_PORT" in
    ''|*[!0-9:]*|*:*:*) fail "DEV_*_PORT values must be numeric" ;;
esac
[ "$DEV_FRONTEND_PORT" -ge 1 ] && [ "$DEV_FRONTEND_PORT" -le 65535 ] || fail "DEV_FRONTEND_PORT must be between 1 and 65535"
[ "$DEV_BACKEND_PORT" -ge 1 ] && [ "$DEV_BACKEND_PORT" -le 65535 ] || fail "DEV_BACKEND_PORT must be between 1 and 65535"
case "$DEV_FRONTEND_HOST" in
    127.0.0.1|localhost) ;;
    *) fail "DEV_FRONTEND_HOST must be localhost or 127.0.0.1" ;;
esac
case "$DEV_BACKEND_BIND_ADDRESS" in
    127.0.0.1|localhost) ;;
    *) fail "DEV_BACKEND_BIND_ADDRESS must be localhost or 127.0.0.1" ;;
esac

DEPLOY_ROOT=$(absolute_path "${DEPLOY_ROOT:-../xju-oj-data}")
RUNTIME_ROOT=$(absolute_path "${RUNTIME_ROOT:-$DEPLOY_ROOT/runtime}")
BACKUP_ROOT=$(absolute_path "${BACKUP_ROOT:-$DEPLOY_ROOT/backups}")
SECRET_ROOT=$(absolute_path "${SECRET_ROOT:-$DEPLOY_ROOT/secrets}")
POSTGRES_PASSWORD_FILE=$(secret_path "${POSTGRES_PASSWORD_FILE:-$SECRET_ROOT/postgres-password}") || fail "invalid POSTGRES_PASSWORD_FILE"
DJANGO_SECRET_KEY_FILE=$(secret_path "${DJANGO_SECRET_KEY_FILE:-$SECRET_ROOT/django-secret}") || fail "invalid DJANGO_SECRET_KEY_FILE"
JUDGE_SERVER_TOKEN_FILE=$(secret_path "${JUDGE_SERVER_TOKEN_FILE:-$SECRET_ROOT/judge-token}") || fail "invalid JUDGE_SERVER_TOKEN_FILE"
INITIAL_ADMIN_PASSWORD_FILE=$(secret_path "${INITIAL_ADMIN_PASSWORD_FILE:-$SECRET_ROOT/admin-password}") || fail "invalid INITIAL_ADMIN_PASSWORD_FILE"

frontend_image_ref_input=${FRONTEND_IMAGE_REF-}
backend_image_ref_input=${BACKEND_IMAGE_REF-}
judge_image_ref_input=${JUDGE_IMAGE_REF-}
judge_toolchain_image_ref_input=${JUDGE_TOOLCHAIN_IMAGE_REF-}
postgres_image_ref_input=${POSTGRES_IMAGE_REF-}
build_targets=${BUILD_TARGETS:-"postgres frontend backend judge-toolchain server"}
if [ "$DEV_MODE" -eq 1 ]; then
    build_targets=${BUILD_TARGETS:-"postgres backend judge-toolchain server"}
    case " $build_targets " in
        *" frontend "*) fail "--dev frontend cannot build the Docker frontend; remove frontend from BUILD_TARGETS" ;;
    esac
fi
if [ "$FRONTEND_ONLY" -eq 1 ]; then
    if [ -n "${BUILD_TARGETS:-}" ] && [ "${BUILD_TARGETS}" != "frontend" ]; then
        fail "--frontend-only requires BUILD_TARGETS=frontend when BUILD_TARGETS is set"
    fi
    build_targets=frontend
fi

case "${FRONTEND_IMAGE_REF:-}" in
    ""|xju-oj-frontend:auto) FRONTEND_IMAGE_REF=xju-oj-frontend:git-$git_tag ;;
esac
case "${BACKEND_IMAGE_REF:-}" in
    ""|xju-oj-backend:auto) BACKEND_IMAGE_REF=xju-oj-backend:git-$git_tag ;;
esac
case "${JUDGE_IMAGE_REF:-}" in
    ""|xju-oj-server:auto) JUDGE_IMAGE_REF=xju-oj-server:git-$git_tag ;;
esac
case "${JUDGE_TOOLCHAIN_IMAGE_REF:-}" in
    ""|xju-oj-judge-toolchain:auto) JUDGE_TOOLCHAIN_IMAGE_REF=xju-oj-judge-toolchain:tc-$git_tag ;;
esac
case "${POSTGRES_IMAGE_REF:-}" in
    ""|xju-oj-postgres:auto) POSTGRES_IMAGE_REF=xju-oj-postgres:git-$git_tag ;;
esac
REDIS_IMAGE_REF=${REDIS_IMAGE_REF:-redis:8.2.8-alpine@sha256:a7859ed111db3c1f5404a973a4747505d559fb5ca32d37e447afc0ef845a2103}
FRONTEND_BASE_IMAGE=${FRONTEND_BASE_IMAGE:-xju-oj-frontend-base:node-24.19.0-bookworm-slim-v1}
CACHE_REGISTRY=${CACHE_REGISTRY:-}
POSTGRES_DB=${POSTGRES_DB:-onlinejudge}
POSTGRES_USER=${POSTGRES_USER:-onlinejudge}
INITIAL_ADMIN_USERNAME=${INITIAL_ADMIN_USERNAME:-admin}

AUTHENTIK_OIDC_ENABLED=${AUTHENTIK_OIDC_ENABLED:-false}
AUTHENTIK_LOCAL_LOGIN_ENABLED=${AUTHENTIK_LOCAL_LOGIN_ENABLED:-true}
AUTHENTIK_LOCAL_REGISTER_ENABLED=${AUTHENTIK_LOCAL_REGISTER_ENABLED:-true}
OJ_FRONTEND_DEV_MODE=${OJ_FRONTEND_DEV_MODE:-false}
case "$OJ_FRONTEND_DEV_MODE" in
    true|false) ;;
    *) fail "OJ_FRONTEND_DEV_MODE must be true or false" ;;
esac
if [ "$DEV_MODE" -eq 0 ] && [ "$OJ_FRONTEND_DEV_MODE" = true ]; then
    fail "OJ_FRONTEND_DEV_MODE=true is allowed only with --dev frontend"
fi
if [ "$DEV_MODE" -eq 1 ] && [ "$OJ_FRONTEND_DEV_MODE" = true ]; then
    AUTHENTIK_OIDC_ENABLED=false
    AUTHENTIK_LOCAL_LOGIN_ENABLED=true
    AUTHENTIK_LOCAL_REGISTER_ENABLED=true
fi
AUTHENTIK_OIDC_ISSUER=${AUTHENTIK_OIDC_ISSUER:-https://auth.icthub.top/application/o/xju-oj/}
AUTHENTIK_OIDC_CLIENT_ID=${AUTHENTIK_OIDC_CLIENT_ID:-}
AUTHENTIK_OIDC_REDIRECT_URI=${AUTHENTIK_OIDC_REDIRECT_URI:-$PUBLIC_BASE_URL/api/auth/oidc/callback/}
AUTHENTIK_OIDC_REGISTER_URL=${AUTHENTIK_OIDC_REGISTER_URL:-https://auth.icthub.top/if/flow/icthub-xju-oj-registration/}
AUTHENTIK_OIDC_POST_LOGOUT_REDIRECT_URI=${AUTHENTIK_OIDC_POST_LOGOUT_REDIRECT_URI:-$PUBLIC_BASE_URL}
AUTHENTIK_OIDC_SCOPES=${AUTHENTIK_OIDC_SCOPES:-openid profile email groups}
AUTHENTIK_OIDC_STATE_TTL_SECONDS=${AUTHENTIK_OIDC_STATE_TTL_SECONDS:-300}
AUTHENTIK_OIDC_CLOCK_SKEW_SECONDS=${AUTHENTIK_OIDC_CLOCK_SKEW_SECONDS:-60}
AUTHENTIK_OIDC_ALLOWED_ALGORITHMS=${AUTHENTIK_OIDC_ALLOWED_ALGORITHMS:-RS256}
if [ "$AUTHENTIK_OIDC_ENABLED" = true ]; then
    AUTHENTIK_OIDC_CLIENT_SECRET_FILE=$(secret_path "${AUTHENTIK_OIDC_CLIENT_SECRET_FILE:-$SECRET_ROOT/authentik-oidc-client-secret}") || fail "invalid AUTHENTIK_OIDC_CLIENT_SECRET_FILE"
else
    AUTHENTIK_OIDC_CLIENT_SECRET_FILE=/dev/null
fi

case "$AUTHENTIK_OIDC_ENABLED:$AUTHENTIK_LOCAL_LOGIN_ENABLED:$AUTHENTIK_LOCAL_REGISTER_ENABLED" in
    true:true:true|true:true:false|true:false:true|true:false:false|false:true:true|false:true:false|false:false:true|false:false:false) ;;
    *) fail "AUTHENTIK_*_ENABLED values must be true or false" ;;
esac
if [ "$AUTHENTIK_OIDC_ENABLED" = true ] && {
    [ "$AUTHENTIK_LOCAL_LOGIN_ENABLED" = true ] || [ "$AUTHENTIK_LOCAL_REGISTER_ENABLED" = true ];
}; then
    fail "OIDC rollout requires AUTHENTIK_LOCAL_LOGIN_ENABLED=false and AUTHENTIK_LOCAL_REGISTER_ENABLED=false"
fi

export COMPOSE_PROJECT_NAME APP_DOMAIN PUBLIC_BASE_URL CSRF_TRUSTED_ORIGINS
export DEV_FRONTEND_HOST DEV_FRONTEND_PORT DEV_BACKEND_BIND_ADDRESS DEV_BACKEND_PORT
export HTTP_BIND_ADDRESS HTTP_PORT
export DEPLOY_ROOT RUNTIME_ROOT BACKUP_ROOT SECRET_ROOT DEPLOY_MODE SECRET_PROVISION_MODE
export FRONTEND_IMAGE_REF FRONTEND_BASE_IMAGE BACKEND_IMAGE_REF JUDGE_IMAGE_REF JUDGE_TOOLCHAIN_IMAGE_REF
export POSTGRES_IMAGE_REF REDIS_IMAGE_REF GIT_COMMIT BUILD_VERSION BUILD_CREATED
export CACHE_REGISTRY
export POSTGRES_DB POSTGRES_USER POSTGRES_PASSWORD_FILE DJANGO_SECRET_KEY_FILE
export JUDGE_SERVER_TOKEN_FILE INITIAL_ADMIN_USERNAME INITIAL_ADMIN_PASSWORD_FILE
export AUTHENTIK_OIDC_ENABLED AUTHENTIK_LOCAL_LOGIN_ENABLED AUTHENTIK_LOCAL_REGISTER_ENABLED
export OJ_FRONTEND_DEV_MODE
export AUTHENTIK_OIDC_ISSUER AUTHENTIK_OIDC_CLIENT_ID AUTHENTIK_OIDC_CLIENT_SECRET_FILE
export AUTHENTIK_OIDC_REDIRECT_URI AUTHENTIK_OIDC_REGISTER_URL AUTHENTIK_OIDC_POST_LOGOUT_REDIRECT_URI
export AUTHENTIK_OIDC_SCOPES AUTHENTIK_OIDC_STATE_TTL_SECONDS AUTHENTIK_OIDC_CLOCK_SKEW_SECONDS
export AUTHENTIK_OIDC_ALLOWED_ALGORITHMS

required() {
    name=$1
    eval "value=\${$name:-}"
    [ -n "$value" ] || fail "$name is required"
}

for name in COMPOSE_PROJECT_NAME APP_DOMAIN PUBLIC_BASE_URL HTTP_BIND_ADDRESS HTTP_PORT \
    RUNTIME_ROOT BACKUP_ROOT FRONTEND_IMAGE_REF FRONTEND_BASE_IMAGE BACKEND_IMAGE_REF JUDGE_IMAGE_REF \
    JUDGE_TOOLCHAIN_IMAGE_REF POSTGRES_IMAGE_REF REDIS_IMAGE_REF POSTGRES_DB POSTGRES_USER \
    POSTGRES_PASSWORD_FILE DJANGO_SECRET_KEY_FILE JUDGE_SERVER_TOKEN_FILE \
    INITIAL_ADMIN_PASSWORD_FILE; do
    required "$name"
done

if [ "$AUTHENTIK_OIDC_ENABLED" = true ]; then
    [ -n "$AUTHENTIK_OIDC_CLIENT_ID" ] || fail "AUTHENTIK_OIDC_CLIENT_ID is required when OIDC is enabled"
    python3 - "$AUTHENTIK_OIDC_ISSUER" "$AUTHENTIK_OIDC_REDIRECT_URI" \
        "$AUTHENTIK_OIDC_REGISTER_URL" "$AUTHENTIK_OIDC_POST_LOGOUT_REDIRECT_URI" \
        "$AUTHENTIK_OIDC_SCOPES" <<'PY' || fail "invalid Authentik OIDC configuration"
import sys
from urllib.parse import urlparse

issuer, redirect_uri, register_url, logout_uri, scopes = sys.argv[1:]
expected_register_url = "https://auth.icthub.top/if/flow/icthub-xju-oj-registration/"
issuer_parts = urlparse(issuer)
redirect_parts = urlparse(redirect_uri)
register_parts = urlparse(register_url)
logout_parts = urlparse(logout_uri)
if issuer_parts.scheme != "https" or not issuer_parts.netloc or issuer_parts.query or issuer_parts.fragment:
    raise SystemExit(1)
if redirect_parts.scheme != "https" or not redirect_parts.netloc or redirect_parts.query or redirect_parts.fragment:
    raise SystemExit(1)
if redirect_parts.path != "/api/auth/oidc/callback/":
    raise SystemExit(1)
for parts in (register_parts, logout_parts):
    if parts.scheme != "https" or not parts.netloc or parts.query or parts.fragment:
        raise SystemExit(1)
if register_url != expected_register_url:
    raise SystemExit(1)
if "openid" not in scopes.split():
    raise SystemExit(1)
PY
fi

python3 - "$CSRF_TRUSTED_ORIGINS" <<'PY' || fail "invalid CSRF_TRUSTED_ORIGINS"
import sys
from urllib.parse import urlsplit

origins = [item.strip().rstrip("/") for item in sys.argv[1].split(",") if item.strip()]
if not origins:
    raise SystemExit(1)
for origin in origins:
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.netloc or parsed.path or parsed.query or parsed.fragment:
        raise SystemExit(1)
PY

for path_name in DEPLOY_ROOT RUNTIME_ROOT BACKUP_ROOT SECRET_ROOT; do
    eval "path_value=\${$path_name}"
    case "$path_value" in
        /*) ;;
        *) fail "$path_name must be absolute" ;;
    esac
    [ "$path_value" != "/" ] || fail "$path_name cannot be /"
    case "$path_value" in
        "$ROOT"|"$ROOT"/*) fail "$path_name must be outside the checkout" ;;
    esac
done

for secret_path in "$POSTGRES_PASSWORD_FILE" "$DJANGO_SECRET_KEY_FILE" \
    "$JUDGE_SERVER_TOKEN_FILE" "$INITIAL_ADMIN_PASSWORD_FILE"; do
    case "$secret_path" in
        /*) ;;
        *) fail "secret file paths must be absolute" ;;
    esac
    case "$secret_path" in
        "$ROOT"|"$ROOT"/*) fail "secret files must be outside the checkout" ;;
    esac
done
if [ "$AUTHENTIK_OIDC_ENABLED" = true ]; then
    case "$AUTHENTIK_OIDC_CLIENT_SECRET_FILE" in
        /*) ;;
        *) fail "AUTHENTIK_OIDC_CLIENT_SECRET_FILE must be absolute" ;;
    esac
    case "$AUTHENTIK_OIDC_CLIENT_SECRET_FILE" in
        "$ROOT"|"$ROOT"/*) fail "OIDC client secret must be outside the checkout" ;;
    esac
    python3 - "$POSTGRES_PASSWORD_FILE" "$DJANGO_SECRET_KEY_FILE" \
        "$JUDGE_SERVER_TOKEN_FILE" "$INITIAL_ADMIN_PASSWORD_FILE" \
        "$AUTHENTIK_OIDC_CLIENT_SECRET_FILE" <<'PY' || fail "secret file destinations must be distinct"
import sys

paths = sys.argv[1:]
if len(paths) != len(set(paths)):
    raise SystemExit(1)
PY
else
    python3 - "$POSTGRES_PASSWORD_FILE" "$DJANGO_SECRET_KEY_FILE" \
        "$JUDGE_SERVER_TOKEN_FILE" "$INITIAL_ADMIN_PASSWORD_FILE" <<'PY' || fail "secret file destinations must be distinct"
import sys

paths = sys.argv[1:]
if len(paths) != len(set(paths)):
    raise SystemExit(1)
PY
fi

case "$SECRET_PROVISION_MODE" in
    prompt|external) ;;
    *) fail "SECRET_PROVISION_MODE must be prompt or external" ;;
esac

check_secret_file() {
    secret_file=$1
    secret_label=$2
    minimum_length=$3
    [ ! -L "$secret_file" ] || fail "secret file must not be a symlink: $secret_file"
    [ -f "$secret_file" ] || fail "secret file is missing: $secret_file"
    [ -r "$secret_file" ] || fail "secret file is unreadable: $secret_file"
    [ -s "$secret_file" ] || fail "secret file is empty: $secret_file"
    secret_mode=$(stat -c '%a' "$secret_file")
    case "$secret_mode" in
        400|440|600|640) ;;
        *) fail "secret file must be owner-readable and not writable by others: $secret_file" ;;
    esac
    secret_length=$(python3 - "$secret_file" <<'PY'
from pathlib import Path
import sys

data = Path(sys.argv[1]).read_bytes()
value = data.rstrip(b"\r\n")
if not value or b"\x00" in value or b"\n" in value or b"\r" in value:
    raise SystemExit(1)
print(len(value))
PY
    ) || fail "$secret_label must be a non-empty single-line value"
    [ "$secret_length" -ge "$minimum_length" ] || fail "$secret_label is shorter than $minimum_length characters"
}

check_secret_set() {
    check_secret_file "$POSTGRES_PASSWORD_FILE" "PostgreSQL password" 16
    check_secret_file "$DJANGO_SECRET_KEY_FILE" "Django secret key" 32
    check_secret_file "$JUDGE_SERVER_TOKEN_FILE" "JudgeServer token" 32
    check_secret_file "$INITIAL_ADMIN_PASSWORD_FILE" "Initial administrator password" 12
    set -- "$POSTGRES_PASSWORD_FILE" "$DJANGO_SECRET_KEY_FILE" "$JUDGE_SERVER_TOKEN_FILE" "$INITIAL_ADMIN_PASSWORD_FILE"
    if [ "$AUTHENTIK_OIDC_ENABLED" = true ]; then
        check_secret_file "$AUTHENTIK_OIDC_CLIENT_SECRET_FILE" "Authentik OIDC client secret" 16
        set -- "$@" "$AUTHENTIK_OIDC_CLIENT_SECRET_FILE"
    fi
    python3 - "$@" <<'PY' || fail "secret files must not be hard-linked aliases"
import os
import sys

identities = [(os.stat(path).st_dev, os.stat(path).st_ino) for path in sys.argv[1:]]
if len(identities) != len(set(identities)):
    raise SystemExit(1)
PY
}

prompt_secret_value() {
    prompt_label=$1
    prompt_minimum=$2
    prompt_confirm=${3:-0}
    [ -r /dev/tty ] && [ -w /dev/tty ] || fail "missing $prompt_label secret; rerun interactively or provision its *_FILE path"
    python3 - "$prompt_label" "$prompt_minimum" "$prompt_confirm" <<'PY'
import getpass
import sys

label = sys.argv[1]
minimum = int(sys.argv[2])
confirm = sys.argv[3] == "1"
while True:
    try:
        value = getpass.getpass(f"{label} (minimum {minimum} characters): ")
    except (EOFError, KeyboardInterrupt):
        raise SystemExit(f"could not read {label}")
    if len(value) < minimum:
        print(f"{label} is too short", file=sys.stderr)
        continue
    if confirm:
        try:
            repeated = getpass.getpass(f"Confirm {label}: ")
        except (EOFError, KeyboardInterrupt):
            raise SystemExit(f"could not confirm {label}")
        if value != repeated:
            print(f"{label} confirmation does not match", file=sys.stderr)
            continue
    sys.stdout.write(value)
    break
PY
}

write_secret_once() {
    secret_destination=$1
    if ! python3 -c '
import os
import sys

path = sys.argv[1]
data = sys.stdin.buffer.read()
parent, name = os.path.split(path)
dir_flags = (
    os.O_RDONLY
    | getattr(os, "O_DIRECTORY", 0)
    | getattr(os, "O_CLOEXEC", 0)
    | getattr(os, "O_NOFOLLOW", 0)
)
dir_fd = os.open(parent, dir_flags)
try:
    file_flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    fd = os.open(name, file_flags, 0o600, dir_fd=dir_fd)
    try:
        remaining = memoryview(data)
        while remaining:
            written = os.write(fd, remaining)
            remaining = remaining[written:]
        os.fsync(fd)
    except BaseException:
        os.close(fd)
        os.unlink(name, dir_fd=dir_fd)
        raise
    else:
        os.close(fd)
finally:
    os.close(dir_fd)
' "$secret_destination"; then
        fail "could not create protected secret file: $secret_destination"
    fi
}

provision_secret_file() {
    secret_destination=$1
    secret_label=$2
    secret_minimum=$3
    secret_confirm=${4:-0}
    [ ! -e "$secret_destination" ] || return 0
    [ "$SECRET_PROVISION_MODE" = prompt ] || fail "secret file is missing: $secret_destination"
    ensure_dir "$(dirname "$secret_destination")" 0700
    secret_value=$(prompt_secret_value "$secret_label" "$secret_minimum" "$secret_confirm") || fail "could not read $secret_label"
    printf '%s\n' "$secret_value" | write_secret_once "$secret_destination"
    unset secret_value
    chmod 600 "$secret_destination" || fail "cannot protect secret file: $secret_destination"
    printf '%s\n' "$secret_label stored in protected file: $secret_destination"
}

compose() {
    if [ "$DEV_MODE" -eq 1 ]; then
        docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" -f "$ROOT/compose.dev.yaml" "$@"
    else
        docker compose --env-file "$ENV_FILE" -f "$COMPOSE_FILE" "$@"
    fi
}

release_dir="$RUNTIME_ROOT/deployments"
release_file="$release_dir/current.json"
if [ "$DRY_RUN" -eq 0 ] && [ "$CONFIG_ONLY" -eq 0 ]; then
    command -v flock >/dev/null 2>&1 || fail "flock is required"
    mkdir -p "$release_dir"
    exec 9>"$release_dir/.deploy.lock"
    flock -n 9 || fail "another deployment is already using this runtime root"
fi

frontend_only_source_guard() {
    [ -f "$release_file" ] || fail "--frontend-only requires a previous successful release: $release_file"
    previous_commit=$(release_source_commit 2>/dev/null || true)
    [ -n "$previous_commit" ] || fail "--frontend-only requires source commit metadata in $release_file"
    python3 - "$ROOT" "$previous_commit" "${GIT_COMMIT:-}" <<'PY' || fail "--frontend-only is allowed only when changes are confined to frontend/"
import subprocess
import sys

root, previous, current = sys.argv[1:]
if not current:
    raise SystemExit("missing current source commit")

def git(*args):
    return subprocess.check_output(["git", "-C", root, *args], text=True)

try:
    committed = [path for path in git("diff", "--name-only", previous, current, "--").splitlines() if path]
except subprocess.CalledProcessError as exc:
    raise SystemExit(f"cannot compare release commits: {previous}..{current}") from exc

status = git("status", "--porcelain=v1", "-z", "--untracked-files=all")
working = []
records = iter(status.split("\0"))
for record in records:
    if not record:
        continue
    path = record[3:] if len(record) >= 3 else record
    working.append(path)
    if "R" in record[:2] or "C" in record[:2]:
        working.append(next(records))

changed = committed + working
outside = sorted({path for path in changed if not (path == "frontend" or path.startswith("frontend/"))})
if outside:
    print("changed paths outside frontend/: " + ", ".join(outside), file=sys.stderr)
    raise SystemExit(1)

PY
}

release_source_commit() {
    [ -f "$release_file" ] || return 1
    python3 - "$release_file" "${1:-}" <<'PY'
import json
import subprocess
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    release = json.load(handle)
target = sys.argv[2].replace("-", "_")
if target:
    metadata = release.get("images", {}).get(target, {})
    value = metadata.get("source_commit", "")
    if not value and metadata.get("reference"):
        try:
            image = json.loads(subprocess.check_output(["docker", "image", "inspect", metadata["reference"]],
                                                      stderr=subprocess.DEVNULL))[0]
            value = (image["Config"].get("Labels") or {}).get("org.opencontainers.image.revision", "")
        except (subprocess.CalledProcessError, KeyError, ValueError):
            value = ""
else:
    value = release.get("source_commit", "")
if value:
    print(value)
else:
    raise SystemExit(1)
PY
}

release_image_ref() {
    target=$1
    [ -f "$release_file" ] || return 1
    case "$target" in
        postgres|redis|frontend|backend|server) release_key=$target ;;
        judge-toolchain) release_key=judge_toolchain ;;
        *) return 1 ;;
    esac
    python3 - "$release_file" "$release_key" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    value = json.load(handle).get("images", {}).get(sys.argv[2], {}).get("reference", "")
if value:
    print(value)
else:
    raise SystemExit(1)
PY
}

target_paths() {
    case "$1" in
        frontend) printf '%s\n' frontend/ docker-bake.hcl ;;
        backend) printf '%s\n' backend/ docker-bake.hcl ;;
        postgres) printf '%s\n' deploy/images/postgres/ docker-bake.hcl .dockerignore ;;
        judge-toolchain) printf '%s\n' server/Dockerfile docker-bake.hcl .dockerignore ;;
        server) printf '%s\n' server/ docker-bake.hcl .dockerignore ;;
        *) return 1 ;;
    esac
}

target_is_requested() {
    requested_target=$1
    for requested_item in $build_targets; do
        [ "$requested_item" = "$requested_target" ] && return 0
    done
    return 1
}

target_skip_requested() {
    skipped_target=$1
    case " $build_skip_targets " in
        *" $skipped_target "*) return 0 ;;
        *) return 1 ;;
    esac
}

target_ref_for() {
    case "$1" in
        frontend) printf '%s\n' "$FRONTEND_IMAGE_REF" ;;
        backend) printf '%s\n' "$BACKEND_IMAGE_REF" ;;
        server) printf '%s\n' "$JUDGE_IMAGE_REF" ;;
        judge-toolchain) printf '%s\n' "$JUDGE_TOOLCHAIN_IMAGE_REF" ;;
        postgres) printf '%s\n' "$POSTGRES_IMAGE_REF" ;;
        redis) printf '%s\n' "$REDIS_IMAGE_REF" ;;
        *) return 1 ;;
    esac
}

target_ref_is_auto() {
    case "$1:$2" in
        frontend:|frontend:xju-oj-frontend:auto|backend:|backend:xju-oj-backend:auto|server:|server:xju-oj-server:auto|judge-toolchain:|judge-toolchain:xju-oj-judge-toolchain:auto|postgres:|postgres:xju-oj-postgres:auto) return 0 ;;
        *) return 1 ;;
    esac
}

target_unchanged_since_release() {
    previous_commit=$(release_source_commit "$1" 2>/dev/null || true)
    [ -n "$previous_commit" ] || return 1
    git -C "$ROOT" cat-file -e "$previous_commit^{commit}" >/dev/null 2>&1 || return 1
    target_path_list=$(target_paths "$1") || return 1
    for target_path in $target_path_list; do
        git -C "$ROOT" diff --quiet "$previous_commit" -- "$target_path" || return 1
        target_status=$(git -C "$ROOT" status --porcelain --untracked-files=all -- "$target_path")
        [ -z "$target_status" ] || return 1
    done
    return 0
}

set_target_ref_from_release() {
    target=$1
    previous_ref=$(release_image_ref "$target" 2>/dev/null || true)
    [ -n "$previous_ref" ] || return 1
    docker image inspect "$previous_ref" >/dev/null 2>&1 || return 1
    case "$target" in
        frontend) FRONTEND_IMAGE_REF=$previous_ref ;;
        backend) BACKEND_IMAGE_REF=$previous_ref ;;
        server) JUDGE_IMAGE_REF=$previous_ref ;;
        judge-toolchain) JUDGE_TOOLCHAIN_IMAGE_REF=$previous_ref ;;
        postgres) POSTGRES_IMAGE_REF=$previous_ref ;;
        redis) REDIS_IMAGE_REF=$previous_ref ;;
        *) return 1 ;;
    esac
}

# Reuse the last successful image for targets that were not requested or whose
# build inputs did not change. This keeps a frontend-only change from rebuilding
# backend, judge and database images, while still allowing explicit image refs
# to override the optimization.
build_skip_targets=
for reuse_target in postgres frontend backend judge-toolchain server; do
    case "$reuse_target" in
        frontend) reuse_input=$frontend_image_ref_input ;;
        backend) reuse_input=$backend_image_ref_input ;;
        server) reuse_input=$judge_image_ref_input ;;
        judge-toolchain) reuse_input=$judge_toolchain_image_ref_input ;;
        postgres) reuse_input=$postgres_image_ref_input ;;
    esac
    target_ref_is_auto "$reuse_target" "$reuse_input" || continue
    if ! target_is_requested "$reuse_target"; then
        if set_target_ref_from_release "$reuse_target"; then
            printf '%s\n' "[reuse] $reuse_target: not requested; using previous release image"
        fi
        continue
    fi
    if target_unchanged_since_release "$reuse_target" && set_target_ref_from_release "$reuse_target"; then
        build_skip_targets="$build_skip_targets $reuse_target"
        printf '%s\n' "[reuse] $reuse_target: inputs unchanged; using previous release image"
    fi
done

validate_pull_references() {
    for immutable_ref in "$FRONTEND_IMAGE_REF" "$BACKEND_IMAGE_REF" "$JUDGE_IMAGE_REF" \
        "$JUDGE_TOOLCHAIN_IMAGE_REF" "$POSTGRES_IMAGE_REF" "$REDIS_IMAGE_REF"; do
        case "$immutable_ref" in
            *@sha256:*) ;;
            *) fail "pull mode requires immutable image@sha256 references: $immutable_ref" ;;
        esac
    done
}

compose config --quiet || fail "compose config validation failed"

config_json=$(mktemp)
cleanup_config() { rm -f "$config_json"; }
trap cleanup_config 0
compose config --format json > "$config_json"
python3 - "$config_json" "$DEV_MODE" <<'PY'
import json
import sys

with open(sys.argv[1], encoding="utf-8") as handle:
    config = json.load(handle)

published = []
for name, service in config.get("services", {}).items():
    if service.get("ports"):
        published.append(name)
expected = ["backend-api", "frontend"] if sys.argv[2] == "1" else ["frontend"]
if published != expected:
    raise SystemExit("unexpected host-published services: " + ",".join(published))
PY
rm -f "$config_json"
trap - 0

if [ "$FRONTEND_ONLY" -eq 1 ] && [ "$CONFIG_ONLY" -eq 0 ]; then
    frontend_only_source_guard
    for retained_target in postgres redis backend judge-toolchain server; do
        if set_target_ref_from_release "$retained_target"; then
            printf '%s\n' "[frontend-only] retaining $retained_target from previous release"
        else
            fail "--frontend-only requires the previous $retained_target image to be available locally"
        fi
    done
fi

if [ "$CONFIG_ONLY" -eq 1 ]; then
    printf '%s\n' "deploy config-only passed"
    exit 0
fi

command -v curl >/dev/null 2>&1 || fail "curl is required"
docker info >/dev/null 2>&1 || fail "docker daemon is unavailable"

if [ "$FRONTEND_ONLY" -eq 0 ]; then
    python3 "$ROOT/deploy/ops/check-judge-host.py" || fail "judge host is incompatible"
fi

if [ "$DRY_RUN" -eq 1 ]; then
    case "$DEPLOY_MODE" in
        build) docker buildx version >/dev/null 2>&1 || fail "docker buildx is required for build mode" ;;
        pull) validate_pull_references ;;
        *) fail "DEPLOY_MODE must be build or pull" ;;
    esac
    if [ "$SECRET_PROVISION_MODE" = external ]; then
        check_secret_set
    fi
    printf '%s\n' "deploy dry-run passed"
    exit 0
fi

case "$HTTP_BIND_ADDRESS" in
    0.0.0.0|::) http_host=127.0.0.1 ;;
    *) http_host=$HTTP_BIND_ADDRESS ;;
esac
case "$http_host" in
    *:*) http_url="http://[${http_host}]:${HTTP_PORT}" ;;
    *) http_url="http://${http_host}:${HTTP_PORT}" ;;
esac

umask 077
ensure_dir() {
    ensure_path=$1
    ensure_mode=$2
    if [ -e "$ensure_path" ]; then
        [ -d "$ensure_path" ] || fail "runtime path is not a directory: $ensure_path"
        return 0
    fi
    mkdir -p "$ensure_path"
    chmod "$ensure_mode" "$ensure_path" || fail "cannot set permissions on new runtime path: $ensure_path"
}

ensure_dir "$DEPLOY_ROOT" 0750
ensure_dir "$RUNTIME_ROOT" 0750
ensure_dir "$SECRET_ROOT" 0700
ensure_dir "$RUNTIME_ROOT/backend" 0750
ensure_dir "$RUNTIME_ROOT/backend/public" 0750
ensure_dir "$RUNTIME_ROOT/backend/test_case" 0750
# PostgreSQL re-execs its entrypoint as the image's postgres user; the parent mount must be traversable.
ensure_dir "$RUNTIME_ROOT/postgres" 0755
ensure_dir "$RUNTIME_ROOT/redis" 0750
ensure_dir "$RUNTIME_ROOT/judge-server" 0750
ensure_dir "$RUNTIME_ROOT/judge-server/run" 0750
ensure_dir "$RUNTIME_ROOT/judge-server/log" 0750
ensure_dir "$RUNTIME_ROOT/deployments" 0750
ensure_dir "$RUNTIME_ROOT/deployments/history" 0750
ensure_dir "$BACKUP_ROOT" 0700

if [ "$FRONTEND_ONLY" -eq 0 ]; then
    provision_secret_file "$POSTGRES_PASSWORD_FILE" "PostgreSQL password" 16
    provision_secret_file "$DJANGO_SECRET_KEY_FILE" "Django secret key" 32
    provision_secret_file "$JUDGE_SERVER_TOKEN_FILE" "JudgeServer token" 32
    provision_secret_file "$INITIAL_ADMIN_PASSWORD_FILE" "Initial administrator password" 12 1
    if [ "$AUTHENTIK_OIDC_ENABLED" = true ]; then
        provision_secret_file "$AUTHENTIK_OIDC_CLIENT_SECRET_FILE" "Authentik OIDC client secret" 16
    fi
    check_secret_set
fi

attempt_dir="$RUNTIME_ROOT/deployments/history/attempt-$(date -u +%Y%m%dT%H%M%SZ)-$$"
ensure_dir "$attempt_dir" 0700

if [ -t 1 ]; then
    color_reset=$(printf '\033[0m')
    color_cyan=$(printf '\033[36m')
    color_green=$(printf '\033[32m')
    color_yellow=$(printf '\033[33m')
    color_red=$(printf '\033[31m')
else
    color_reset=
    color_cyan=
    color_green=
    color_yellow=
    color_red=
fi
log_info() { printf '%s%s%s\n' "$color_cyan" "$*" "$color_reset"; }
log_success() { printf '%s%s%s\n' "$color_green" "$*" "$color_reset"; }
log_warn() { printf '%s%s%s\n' "$color_yellow" "$*" "$color_reset" >&2; }
log_error() { printf '%s%s%s\n' "$color_red" "$*" "$color_reset" >&2; }

compact_build_output() {
    while IFS= read -r stream_line; do
        case "$stream_line" in
            *" CACHED"*|*" DONE"*|*" ERROR"*|*"ERROR"*|*"error"*|*"failed"*|*"naming to "*|*"writing image "*|*"transferring context"*|*"load metadata"*|*"resolve image config"*|*"] RUN "*|*"] COPY "*|*"exporting"*)
                printf '%s%s%s\n' "$color_cyan" "$stream_line" "$color_reset"
                ;;
        esac
    done
}

# Keep a complete copy of every command's output in the attempt directory.
# Interactive BuildKit output is summarized in the terminal to avoid a line
# flood; non-build commands remain live. Status sidecars keep this POSIX-sh
# compatible (unlike PIPESTATUS) and preserve exit codes through tee/filter.
stream_command() {
    stream_log=$1
    shift
    stream_status="$stream_log.status"
    stream_tee_status="$stream_log.tee-status"
    rm -f "$stream_status"
    rm -f "$stream_tee_status"
    log_info "[deploy] logging command output to $stream_log"
    stream_parent_pid=$$
    (
        stream_waited=0
        while [ ! -s "$stream_status" ]; do
            sleep "$DEPLOY_HEARTBEAT_SECONDS"
            kill -0 "$stream_parent_pid" 2>/dev/null || exit 0
            stream_waited=$((stream_waited + DEPLOY_HEARTBEAT_SECONDS))
            [ -s "$stream_status" ] && break
            log_warn "[deploy] still running (${stream_waited}s): $stream_log"
        done
    ) &
    stream_watchdog_pid=$!
    stream_compact=0
    case "$stream_log" in
        */build-*.log) [ -t 1 ] && stream_compact=1 ;;
    esac
    stream_run_command() {
        set +e
        "$@"
        stream_rc=$?
        printf '%s\n' "$stream_rc" > "$stream_status"
        exit "$stream_rc"
    }
    stream_capture_output() {
        set +e
        tee "$stream_log"
        stream_tee_rc=$?
        printf '%s\n' "$stream_tee_rc" > "$stream_tee_status"
        exit "$stream_tee_rc"
    }
    if [ "$stream_compact" -eq 1 ]; then
        stream_run_command "$@" 2>&1 | stream_capture_output | compact_build_output
    else
        stream_run_command "$@" 2>&1 | stream_capture_output
    fi
    stream_pipeline_rc=$?
    kill "$stream_watchdog_pid" 2>/dev/null || true
    wait "$stream_watchdog_pid" 2>/dev/null || true
    if [ ! -s "$stream_tee_status" ]; then
        rm -f "$stream_status"
        return 125
    fi
    stream_tee_rc=$(cat "$stream_tee_status")
    rm -f "$stream_tee_status"
    if [ "$stream_tee_rc" -ne 0 ]; then
        rm -f "$stream_status"
        return "$stream_tee_rc"
    fi
    [ "$stream_pipeline_rc" -eq 0 ] || { rm -f "$stream_status"; return 125; }
    if [ ! -s "$stream_status" ]; then
        return 125
    fi
    stream_rc=$(cat "$stream_status")
    rm -f "$stream_status"
    case "$stream_rc" in
        ''|*[!0-9]*) return 125 ;;
    esac
    return "$stream_rc"
}

on_exit() {
    rc=$?
    if [ "$rc" -ne 0 ]; then
        compose ps > "$attempt_dir/compose-ps.txt" 2>&1 || true
        compose logs --no-color --tail=200 > "$attempt_dir/compose-logs.txt" 2>&1 || true
        printf '%s\n' "deploy failed; diagnostic files retained under $attempt_dir" >&2
    fi
    exit "$rc"
}
trap on_exit 0

run_step() {
    name=$1
    pattern=$2
    shift 2
    log="$attempt_dir/$name.log"
    log_info "[step] $name: START (log: $log)"
    if stream_command "$log" "$@"; then
        log_success "$name: PASS"
        if [ -n "$pattern" ]; then
            grep -nE "$pattern" "$log" | tail -20 || true
        fi
        return 0
    fi
    log_error "$name: FAIL (key lines; full log: $log)"
    grep -nE 'ERROR|error|failed|unhealthy|timeout|permission|Traceback|OperationalError|CommandError' "$log" | tail -80 >&2 || true
    fail "$name failed"
}

if [ "$CONFIG_ONLY" -eq 0 ]; then
    case "$DEPLOY_MODE" in
        build)
            docker buildx version >/dev/null 2>&1 || fail "docker buildx is required for build mode"
            build_network=${BUILD_NETWORK:-default}
            build_http_proxy=${BUILD_HTTP_PROXY:-}
            build_https_proxy=${BUILD_HTTPS_PROXY:-}
            build_all_proxy=${BUILD_ALL_PROXY:-}
            case "$build_network" in
                default|host|none) ;;
                *) fail "BUILD_NETWORK must be default, host, or none" ;;
            esac
            for build_proxy in "$build_http_proxy" "$build_https_proxy" "$build_all_proxy"; do
                [ -n "$build_proxy" ] || continue
                if ! python3 - "$build_proxy" "$build_network" >/dev/null 2>&1 <<'PY'
from urllib.parse import urlparse
import socket
import sys

proxy, network = sys.argv[1:]
parsed = urlparse(proxy)
if parsed.scheme not in {"http", "https", "socks5", "socks5h"}:
    raise SystemExit(1)
if not parsed.hostname or not parsed.port:
    raise SystemExit(1)
if parsed.hostname in {"127.0.0.1", "localhost", "::1"} and network != "host":
    raise SystemExit(1)
socket.create_connection((parsed.hostname, parsed.port), timeout=1).close()
PY
                then
                    fail "configured build proxy is not reachable from BuildKit; leave BUILD_*_PROXY empty or use a reachable endpoint"
                fi
            done
            git_sha=${GIT_COMMIT:-local}
            build_version=${BUILD_VERSION:-phase2}
            build_allow=
            [ "$build_network" = host ] && build_allow=--allow=network.host

            frontend_build_needed=0
            if target_is_requested frontend && ! target_skip_requested frontend; then
                frontend_build_needed=1
            fi
            if [ "$frontend_build_needed" -eq 1 ] && ! docker image inspect "$FRONTEND_BASE_IMAGE" >/dev/null 2>&1; then
                base_log="$attempt_dir/build-frontend-base.log"
                log_info "[build] frontend-base: START (image: $FRONTEND_BASE_IMAGE; log: $base_log)"
                if ! stream_command "$base_log" env \
                    BUILD_NETWORK="$build_network" GIT_SHA="$git_sha" BUILD_VERSION="$build_version" \
                    BUILD_CREATED="${BUILD_CREATED:-unknown}" \
                    docker buildx bake $build_allow --progress=plain --file "$ROOT/docker-bake.hcl" \
                    --set '*.platform=linux/amd64' \
                    --set frontend-base.tags="$FRONTEND_BASE_IMAGE" \
                    --load frontend-base
                then
                    log_error "build chunk frontend-base failed; key lines (full log: $base_log):"
                    grep -nE 'ERROR|error|failed|ECONNREFUSED|CANCELED|cancelled' "$base_log" | tail -80 >&2 || true
                    fail "image build failed in chunk frontend-base"
                fi
                log_success "build chunk frontend-base passed"
            elif [ "$frontend_build_needed" -eq 1 ]; then
                log_success "[reuse] frontend-base: local image $FRONTEND_BASE_IMAGE"
            fi
            for build_target in $build_targets; do
                if target_skip_requested "$build_target"; then
                    target_ref=$(target_ref_for "$build_target")
                    log_success "[build] $build_target: SKIP (inputs unchanged; reusing $target_ref)"
                    continue
                fi
                case "$build_target" in
                    postgres)
                        target_ref=$POSTGRES_IMAGE_REF
                        target_http_proxy=$build_http_proxy
                        target_https_proxy=$build_https_proxy
                        target_all_proxy=$build_all_proxy
                        ;;
                    frontend)
                        target_ref=$FRONTEND_IMAGE_REF
                        target_http_proxy=$build_http_proxy
                        target_https_proxy=$build_https_proxy
                        target_all_proxy=$build_all_proxy
                        ;;
                    backend)
                        target_ref=$BACKEND_IMAGE_REF
                        target_http_proxy=
                        target_https_proxy=
                        target_all_proxy=
                        ;;
                    server)
                        target_ref=$JUDGE_IMAGE_REF
                        target_http_proxy=
                        target_https_proxy=
                        target_all_proxy=
                        ;;
                    judge-toolchain)
                        target_ref=${JUDGE_TOOLCHAIN_IMAGE_REF:-xju-oj-judge-toolchain:tc-$git_sha}
                        target_http_proxy=
                        target_https_proxy=
                        target_all_proxy=
                        ;;
                    *)
                        fail "BUILD_TARGETS contains unsupported target: $build_target"
                        ;;
                esac
                build_log="$attempt_dir/build-$build_target.log"
                log_info "[build] $build_target: START (image: $target_ref; log: $build_log)"
                if ! stream_command "$build_log" env \
                    BUILD_NETWORK="$build_network" GIT_SHA="$git_sha" BUILD_VERSION="$build_version" \
                    BUILD_CREATED="${BUILD_CREATED:-unknown}" \
                    docker buildx bake $build_allow --progress=plain --file "$ROOT/docker-bake.hcl" \
                    --set '*.platform=linux/amd64' \
                    --set "$build_target.args.HTTP_PROXY=$target_http_proxy" \
                    --set "$build_target.args.HTTPS_PROXY=$target_https_proxy" \
                    --set "$build_target.args.ALL_PROXY=$target_all_proxy" \
                    --set "$build_target.args.FRONTEND_BASE_IMAGE=$FRONTEND_BASE_IMAGE" \
                    --set "$build_target.tags=$target_ref" \
                    --load "$build_target"
                then
                    log_error "build chunk $build_target failed; key lines (full log: $build_log):"
                    grep -nE 'ERROR|error|failed|ECONNREFUSED|CANCELED|cancelled' "$build_log" | tail -80 >&2 || true
                    fail "image build failed in chunk $build_target"
                fi
                log_success "build chunk $build_target passed:"
                grep -E 'naming to |writing image ' "$build_log" | tail -10 || true
                if grep -qE 'WARN|warning' "$build_log"; then
                    log_warn "non-fatal warnings in $build_target (tail; full log: $build_log):"
                    grep -nE 'WARN|warning' "$build_log" | tail -20
                fi
            done
            ;;
        pull)
            validate_pull_references
            compose pull --policy missing postgres redis frontend backend-api backend-worker judge-server
            ;;
        *)
            fail "DEPLOY_MODE must be build or pull"
            ;;
    esac
fi

frontend_userscript_image_smoke() {
    docker run --rm --entrypoint sh "$FRONTEND_IMAGE_REF" -c '
        script=/usr/share/nginx/html/static/userscripts/xju-oj-remote-bridge.user.js
        test -s "$script" &&
        grep -Fq "// ==UserScript==" "$script" &&
        grep -Fq "@version" "$script"
    '
}

if [ "$DEV_MODE" -eq 0 ]; then
    frontend_userscript_image_smoke || fail "frontend image does not contain the remote OJ userscript"
fi

frontend_backend_ready() {
    compose ps --status running --services | grep -qx 'backend-api'
    curl --noproxy '*' --fail --silent --show-error --retry 5 --retry-all-errors --retry-delay 1 \
        "$http_url/api/website/" >/dev/null
}

http_response_smoke() (
    smoke_url=$1
    smoke_expected_status=$2
    smoke_expected_content=$3
    shift 3
    smoke_body=$(mktemp "$attempt_dir/http-smoke.XXXXXX") || exit 1
    trap 'rm -f "$smoke_body"' 0
    trap 'exit 1' HUP INT TERM
    # Check curl's exit status before inspecting content. Piping a large script
    # into grep -q closes the download early and triggers spurious curl retries;
    # it can also hide a truncated response containing the expected header.
    smoke_status=$(curl --noproxy '*' --fail --silent --show-error \
        --connect-timeout 10 --max-time 30 --retry-max-time 90 \
        --retry 15 --retry-all-errors --retry-delay 1 \
        --output "$smoke_body" --write-out '%{http_code}' "$@" "$smoke_url") || exit 1
    if [ "$smoke_status" != "$smoke_expected_status" ]; then
        printf 'HTTP smoke failed: %s returned %s, expected %s\n' \
            "$smoke_url" "$smoke_status" "$smoke_expected_status" >&2
        exit 1
    fi
    if [ -n "$smoke_expected_content" ] && ! grep -Fq -- "$smoke_expected_content" "$smoke_body"; then
        printf 'HTTP smoke failed: required content missing from %s\n' "$smoke_url" >&2
        exit 1
    fi
    if [ "$smoke_expected_content" = '"error"' ]; then
        python3 - "$smoke_body" <<'PY' || exit 1
import json, sys
with open(sys.argv[1], encoding="utf-8") as response:
    body = json.load(response)
if not isinstance(body, dict) or "error" not in body or body["error"] is not None:
    raise SystemExit("HTTP smoke failed: API returned an error envelope")
PY
    fi
)

frontend_http_smoke() {
    http_response_smoke "$http_url/" 200 '' || return 1
    http_response_smoke "$http_url/admin" 301 '' --head || return 1
    http_response_smoke "$http_url/admin/" 200 '' || return 1
    http_response_smoke "$http_url/api/website/" 200 '"error"' || return 1
    http_response_smoke "$http_url/runtime-config.js" 200 '__XJU_RUNTIME_CONFIG__' || return 1
    http_response_smoke "$http_url$REMOTE_USERSCRIPT_URL_PATH" 200 '// ==UserScript=='
}

if [ "$FRONTEND_ONLY" -eq 1 ]; then
    log_info '[frontend-only] backend-api must already be running; no backend service will be restarted'
    run_step frontend-backend-ready '.*' frontend_backend_ready
    run_step frontend-ready 'Healthy|healthy' compose up -d --no-deps --force-recreate --wait frontend
    run_step frontend-http-smoke '.*' frontend_http_smoke
else
    run_step infra-ready 'Healthy|healthy' compose up -d --wait postgres redis

    if [ "$CONFIG_ONLY" -eq 0 ]; then
        run_step backend-bootstrap 'completed|passed' compose --profile init run --rm --no-deps backend-bootstrap
        backup_before_migrate() {
            database_backup="$BACKUP_ROOT/pre-migrate-$(date -u +%Y%m%dT%H%M%SZ)-$$.dump"
            compose exec -T postgres pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc > "$database_backup.partial" || return 1
            [ -s "$database_backup.partial" ] || return 1
            mv "$database_backup.partial" "$database_backup"
            printf '%s\n' "Database backup passed: $database_backup"
        }
        run_step database-backup 'passed' backup_before_migrate
        run_step backend-migrate 'Applying |No migrations to apply|Operations to perform|Running migrations:' compose --profile init run --rm --no-deps backend-migrate

        token_log="$attempt_dir/backend-configure-token.log"
        if compose --profile init run --rm --no-deps backend-configure-token >"$token_log" 2>&1; then
            printf '%s\n' 'backend-configure-token: PASS'
            grep -nE 'configured|already' "$token_log" | tail -10 || true
        else
            token_check_log="$attempt_dir/backend-configure-token-check.log"
            if ! compose run --rm --no-deps backend-api manage shell -c \
                'from options.models import SysOptions; raise SystemExit(0 if SysOptions.objects.filter(key="judge_server_token").exists() else 1)' >"$token_check_log" 2>&1; then
                printf '%s\n' "backend-configure-token: FAIL (key lines; full log: $token_log)" >&2
                grep -nE 'ERROR|error|failed|Traceback|CommandError' "$token_log" | tail -80 >&2 || true
                fail "JudgeServer token initialization failed"
            fi
            printf '%s\n' 'backend-configure-token: PASS (already configured; no overwrite)'
        fi

        run_step judge-token-volume 'PASS|already|error|failed' compose --profile init run --rm --no-deps judge-token-init
        run_step backend-create-admin 'administrator|created|ignored' compose --profile init run --rm --no-deps backend-create-admin
    fi

    if [ "$DEV_MODE" -eq 1 ]; then
        run_step services-ready 'Healthy|healthy' compose up -d --wait postgres redis backend-api backend-worker judge-server
        dev_backend_http_smoke() {
            curl --noproxy '*' --fail --silent --show-error --retry 15 --retry-all-errors --retry-delay 1 \
                "http://${DEV_BACKEND_BIND_ADDRESS}:${DEV_BACKEND_PORT}/api/website/" >/dev/null
        }
        run_step dev-backend-http-smoke '.*' dev_backend_http_smoke
    else
        run_step services-ready 'Healthy|healthy' compose up -d --remove-orphans --wait
        http_smoke() {
            frontend_http_smoke
        }
        run_step http-smoke 'PASS' http_smoke
    fi

    run_step runtime-worker-smoke 'passed|PASS' compose exec -T backend-api python deploy/worker_smoke.py
    run_step runtime-judge-smoke 'passed|PASS' compose exec -T judge-server python -c '
import hashlib, os, requests
with open(os.environ["TOKEN_FILE"], encoding="utf-8") as handle:
    token = handle.read().strip()
response = requests.post("http://127.0.0.1:8080/ping", headers={"X-Judge-Server-Token": hashlib.sha256(token.encode()).hexdigest()}, timeout=5)
response.raise_for_status()
assert response.json().get("err") is None
print("Judge /ping passed")
'

    heartbeat_ok=0
    heartbeat_attempt=1
    while [ "$heartbeat_attempt" -le 20 ]; do
        if compose exec -T backend-api python manage.py shell -c \
            'from datetime import timedelta; from django.utils import timezone; from conf.models import JudgeServer; raise SystemExit(0 if JudgeServer.objects.filter(is_disabled=False, last_heartbeat__gte=timezone.now()-timedelta(seconds=6)).exists() else 1)' >/dev/null 2>&1; then
            heartbeat_ok=1
            break
        fi
        sleep 1
        heartbeat_attempt=$((heartbeat_attempt + 1))
    done
    [ "$heartbeat_ok" -eq 1 ] || fail "JudgeServer heartbeat was not observed"
fi

if [ "$DEV_MODE" -eq 1 ]; then
    command -v pnpm >/dev/null 2>&1 || fail "pnpm is required for --dev frontend"
    [ -f "$ROOT/frontend/package.json" ] || fail "frontend/package.json is missing"
    if [ ! -x "$ROOT/frontend/node_modules/.bin/vite" ]; then
        log_info "[dev] frontend dependencies missing; running pnpm install --frozen-lockfile"
        (cd "$ROOT/frontend" && pnpm install --frozen-lockfile)
    fi
    dev_backend_url="http://${DEV_BACKEND_BIND_ADDRESS}:${DEV_BACKEND_PORT}"
    log_success "[dev] backend services are ready; starting Vite at http://${DEV_FRONTEND_HOST}:${DEV_FRONTEND_PORT}"
    log_info "[dev] Vite /api and /public proxy target: $dev_backend_url"
    log_info "[dev] Ctrl-C stops Vite only; Docker backend services remain running"
    cd "$ROOT/frontend"
    # Keep the host Vite runtime flags aligned with the backend Compose env.
    # Only non-secret OIDC presentation settings are passed to the frontend;
    # client IDs and secrets remain server-side.
    exec env TARGET="$dev_backend_url" PORT="$DEV_FRONTEND_PORT" VITE_DEV_HOST="$DEV_FRONTEND_HOST" \
        GIT_COMMIT="$GIT_COMMIT" APP_DOMAIN="$APP_DOMAIN" PUBLIC_BASE_URL="$PUBLIC_BASE_URL" \
        OJ_DEV_PUBLIC_DIR="$RUNTIME_ROOT/backend/public" \
        OJ_FRONTEND_DEV_MODE="$OJ_FRONTEND_DEV_MODE" \
        AUTHENTIK_OIDC_ENABLED="$AUTHENTIK_OIDC_ENABLED" \
        AUTHENTIK_OIDC_REGISTER_URL="$AUTHENTIK_OIDC_REGISTER_URL" \
        AUTHENTIK_LOCAL_LOGIN_ENABLED="$AUTHENTIK_LOCAL_LOGIN_ENABLED" \
        AUTHENTIK_LOCAL_REGISTER_ENABLED="$AUTHENTIK_LOCAL_REGISTER_ENABLED" pnpm dev
fi

release_dir="$RUNTIME_ROOT/deployments"
if [ -f "$release_dir/current.json" ]; then
    cp "$release_dir/current.json" "$release_dir/previous.json"
fi
image_id() {
    docker image inspect --format '{{.Id}}' "$1"
}
image_revision() {
    docker image inspect --format '{{index .Config.Labels "org.opencontainers.image.revision"}}' "$1"
}
compose_hash=$(sha256sum "$COMPOSE_FILE" | awk '{print $1}')
cat > "$attempt_dir/release.json" <<EOF
{
  "source_commit": "${GIT_COMMIT:-unknown}",
  "compose_sha256": "$compose_hash",
  "deployed_at": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
  "build_bases": {
    "frontend": "$FRONTEND_BASE_IMAGE"
  },
  "images": {
    "postgres": {"reference": "$POSTGRES_IMAGE_REF", "image_id": "$(image_id "$POSTGRES_IMAGE_REF")", "source_commit": "$(image_revision "$POSTGRES_IMAGE_REF")"},
    "redis": {"reference": "$REDIS_IMAGE_REF", "image_id": "$(image_id "$REDIS_IMAGE_REF")"},
    "frontend": {"reference": "$FRONTEND_IMAGE_REF", "image_id": "$(image_id "$FRONTEND_IMAGE_REF")", "source_commit": "$(image_revision "$FRONTEND_IMAGE_REF")"},
    "backend": {"reference": "$BACKEND_IMAGE_REF", "image_id": "$(image_id "$BACKEND_IMAGE_REF")", "source_commit": "$(image_revision "$BACKEND_IMAGE_REF")"},
    "judge_toolchain": {"reference": "$JUDGE_TOOLCHAIN_IMAGE_REF", "runtime_loaded": false, "source_commit": "$(image_revision "$JUDGE_TOOLCHAIN_IMAGE_REF" 2>/dev/null || true)"},
    "server": {"reference": "$JUDGE_IMAGE_REF", "image_id": "$(image_id "$JUDGE_IMAGE_REF")", "source_commit": "$(image_revision "$JUDGE_IMAGE_REF")"}
  }
}
EOF
python3 -m json.tool "$attempt_dir/release.json" >/dev/null || fail "invalid release metadata"
mv "$attempt_dir/release.json" "$release_dir/current.json"
cp "$release_dir/current.json" "$attempt_dir/release-success.json"

trap - 0
printf '%s\n' "deploy succeeded; release metadata written to $release_dir/current.json"
