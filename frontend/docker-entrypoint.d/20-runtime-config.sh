#!/bin/sh
set -eu

json_escape() {
    # Encode bytes instead of interpolating shell values into JavaScript.
    # JSON accepts escaped controls, and UTF-8 bytes remain unchanged.
    printf '%s' "$1" | od -An -v -tu1 | LC_ALL=C awk '
        { for (i = 1; i <= NF; i++) {
            n = $i + 0
            if (n == 34) printf "\\\""
            else if (n == 92) printf "\\\\"
            else if (n < 32) printf "\\u%04x", n
            else printf "%c", n
        }}'
}

json_bool() {
    case "$1" in
        true|false) printf '%s' "$1" ;;
        *) printf '%s\n' "Invalid runtime boolean" >&2; exit 1 ;;
    esac
}

app_domain=$(json_escape "${APP_DOMAIN:-_}")
public_base_url=$(json_escape "${PUBLIC_BASE_URL:-}")
version=$(json_escape "${GIT_COMMIT:-unknown}")
authentik_enabled=$(json_bool "${AUTHENTIK_OIDC_ENABLED:-false}")
authentik_register_url=$(json_escape "${AUTHENTIK_OIDC_REGISTER_URL:-https://auth.icthub.top/if/flow/icthub-public-registration/}")
local_login_enabled=$(json_bool "${AUTHENTIK_LOCAL_LOGIN_ENABLED:-true}")
local_register_enabled=$(json_bool "${AUTHENTIK_LOCAL_REGISTER_ENABLED:-true}")

cat > /usr/share/nginx/html/runtime-config.js <<EOF
window.__XJU_RUNTIME_CONFIG__ = {
  "APP_DOMAIN": "${app_domain}",
  "PUBLIC_BASE_URL": "${public_base_url}",
  "VERSION": "${version}",
  "OJ_FRONTEND_DEV_MODE": false,
  "AUTHENTIK_OIDC_ENABLED": ${authentik_enabled},
  "AUTHENTIK_OIDC_REGISTER_URL": "${authentik_register_url}",
  "AUTHENTIK_LOCAL_LOGIN_ENABLED": ${local_login_enabled},
  "AUTHENTIK_LOCAL_REGISTER_ENABLED": ${local_register_enabled}
};
EOF
