#!/bin/sh
set -eu

# Empty by default: directly published frontend ports never trust client headers.
# Allow only explicit numeric proxy addresses/CIDRs, validated by deploy.sh too.
umask 022
output=/etc/nginx/conf.d/trusted-proxies.conf
temporary="$output.tmp"
trap 'rm -f "$temporary"' 0
{
    printf '%s\n' 'real_ip_header X-Forwarded-For;' 'real_ip_recursive on;'
    for cidr in ${TRUSTED_PROXY_CIDRS:-}; do
        case "$cidr" in
            *[!0-9a-fA-F:./]*|'') printf '%s\n' 'Invalid trusted proxy address' >&2; exit 1 ;;
        esac
        printf 'set_real_ip_from %s;\n' "$cidr"
    done
    printf '%s\n' 'geo $realip_remote_addr $oj_trusted_proxy {' '    default 0;'
    for cidr in ${TRUSTED_PROXY_CIDRS:-}; do printf '    %s 1;\n' "$cidr"; done
    printf '%s\n' '}' 'map "$oj_trusted_proxy:$http_x_forwarded_proto" $oj_forwarded_proto {' \
        '    default $scheme;' '    "1:https" https;' '    "1:http" http;' '}'
} > "$temporary"
mv "$temporary" "$output"
