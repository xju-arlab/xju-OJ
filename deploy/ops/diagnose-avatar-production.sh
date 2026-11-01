#!/usr/bin/env bash

set -Eeuo pipefail

REPO_ROOT="${REPO_ROOT:-/home/winbeau/xju-OJ}"
USERNAME="${1:-winbeau}"
PUBLIC_ORIGIN="${PUBLIC_ORIGIN:-https://oj.icthub.top}"
COMPOSE_FILE="${COMPOSE_FILE:-compose.yaml}"

if [[ ! "$USERNAME" =~ ^[A-Za-z0-9_.@+-]+$ ]]; then
  echo "Invalid username: $USERNAME" >&2
  exit 2
fi

if [[ ! -d "$REPO_ROOT" ]]; then
  echo "Repository not found: $REPO_ROOT" >&2
  exit 2
fi

cd "$REPO_ROOT"

compose=(docker compose -f "$COMPOSE_FILE")
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

section() {
  printf '\n\n========== %s ==========\n' "$1"
}

request_file() {
  local label="$1"
  local url="$2"
  local output="$3"

  echo "[$label] $url"
  if curl -ksS \
    --connect-timeout 10 \
    --max-time 30 \
    -o "$output" \
    -w 'http_code=%{http_code}\ncontent_type=%{content_type}\nsize_download=%{size_download}\neffective_url=%{url_effective}\n' \
    "$url"; then
    if [[ -s "$output" ]]; then
      file "$output" || true
      sha256sum "$output" || true
    fi
  else
    echo "curl_failed=yes"
  fi
}

section "HOST AND REPOSITORY"
hostname
pwd
echo "git_head=$(git rev-parse HEAD)"
echo "git_short_head=$(git rev-parse --short HEAD)"
git status --short || true

section "CONTAINERS"
"${compose[@]}" ps
echo
docker inspect xju-oj-frontend-1 \
  --format 'frontend_image={{.Config.Image}} image_id={{.Image}}' || true
docker inspect xju-oj-backend-api-1 \
  --format 'backend_image={{.Config.Image}} image_id={{.Image}}' || true

section "IMAGE LABELS"
docker inspect xju-oj-frontend-1 \
  --format '{{range $key, $value := .Config.Labels}}{{$key}}={{$value}}{{println}}{{end}}' \
  | grep -E 'revision|version|source' || true
docker inspect xju-oj-backend-api-1 \
  --format '{{range $key, $value := .Config.Labels}}{{$key}}={{$value}}{{println}}{{end}}' \
  | grep -E 'revision|version|source' || true

section "DATABASE AVATAR"
profile_output="$(
  "${compose[@]}" exec -T backend-api python manage.py shell -c "
from account.models import User
from django.conf import settings
import hashlib
import mimetypes
import os
import stat

username = '${USERNAME}'
user = User.objects.filter(username=username).first()

if user is None:
    print('AVATAR_DIAG|USER_NOT_FOUND')
else:
    avatar = user.userprofile.avatar or ''
    filename = os.path.basename(avatar)
    path = os.path.join(settings.AVATAR_UPLOAD_DIR, filename)
    exists = os.path.isfile(path)
    size = os.path.getsize(path) if exists else -1
    mode = stat.S_IMODE(os.stat(path).st_mode) if exists else 0
    digest = ''
    if exists:
        with open(path, 'rb') as source:
            digest = hashlib.sha256(source.read()).hexdigest()

    print(
        'AVATAR_DIAG|OK'
        + '|username=' + username
        + '|avatar=' + avatar
        + '|upload_dir=' + settings.AVATAR_UPLOAD_DIR
        + '|path=' + path
        + '|exists=' + str(exists)
        + '|size=' + str(size)
        + '|mode=' + format(mode, '04o')
        + '|public_readable=' + str(bool(mode & stat.S_IROTH))
        + '|mime=' + str(mimetypes.guess_type(path)[0])
        + '|sha256=' + digest
    )
"
)"

printf '%s\n' "$profile_output"
profile_line="$(printf '%s\n' "$profile_output" | grep '^AVATAR_DIAG|' | tail -1 || true)"

if [[ "$profile_line" == "AVATAR_DIAG|USER_NOT_FOUND" || -z "$profile_line" ]]; then
  echo "Cannot continue: user was not found or profile query failed." >&2
  exit 3
fi

field_value() {
  local name="$1"
  printf '%s\n' "$profile_line" \
    | tr '|' '\n' \
    | sed -n "s/^${name}=//p" \
    | head -1
}

avatar_uri="$(field_value avatar)"
avatar_path="$(field_value path)"
avatar_exists="$(field_value exists)"
avatar_mode="$(field_value mode)"
avatar_public_readable="$(field_value public_readable)"
backend_sha="$(field_value sha256)"

echo
echo "resolved_avatar_uri=$avatar_uri"
echo "resolved_avatar_path=$avatar_path"
echo "resolved_avatar_exists=$avatar_exists"
echo "resolved_avatar_mode=$avatar_mode"
echo "resolved_avatar_public_readable=$avatar_public_readable"
echo "backend_avatar_sha256=$backend_sha"

section "RECENT AVATAR FILES"
"${compose[@]}" exec -T backend-api sh -lc '
  echo "directory:"
  ls -ld /data/public /data/public/avatar 2>&1 || true
  echo
  echo "latest files:"
  find /data/public/avatar -maxdepth 1 -type f \
    -printf "%TY-%Tm-%Td %TH:%TM:%TS  %u:%g  %m  %s bytes  %f\n" 2>/dev/null \
    | sort -r \
    | head -30
'

section "AVATAR FILE PERMISSIONS"
"${compose[@]}" exec -T backend-api sh -lc "
  id
  if [ -n '$avatar_path' ]; then
    namei -l '$avatar_path' 2>&1 || true
    stat '$avatar_path' 2>&1 || true
    file '$avatar_path' 2>&1 || true
  fi
"

section "CONTAINER MOUNTS"
echo "--- backend-api ---"
docker inspect xju-oj-backend-api-1 \
  --format '{{range .Mounts}}{{println .Type ":" .Source "->" .Destination "rw=" .RW}}{{end}}' || true
echo
echo "--- frontend ---"
docker inspect xju-oj-frontend-1 \
  --format '{{range .Mounts}}{{println .Type ":" .Source "->" .Destination "rw=" .RW}}{{end}}' || true

section "FRONTEND NGINX PUBLIC ROUTE"
docker exec xju-oj-frontend-1 nginx -T 2>&1 \
  | grep -nE -A8 -B4 'location[[:space:]].*(/public|/api)|proxy_pass' \
  | head -160 || true

section "FRONTEND BUILD MARKERS"
docker exec xju-oj-frontend-1 sh -lc '
  echo "index metadata:"
  stat /usr/share/nginx/html/index.html 2>&1 || true
  echo
  echo "profile.avatar markers:"
  grep -R -l "profile.avatar" /usr/share/nginx/html/static/js 2>/dev/null | head -10 || true
  echo
  echo "XJU-OJ markers:"
  grep -R -l "XJU-OJ" /usr/share/nginx/html/static/js 2>/dev/null | head -10 || true
'

local_sha=""
public_sha=""

section "AVATAR HTTP RESPONSE"
if [[ -z "$avatar_uri" ]]; then
  echo "Avatar URI is empty; skipping HTTP checks."
else
  request_file \
    "frontend-container-loopback" \
    "http://127.0.0.1:18080${avatar_uri}" \
    "$tmp_dir/avatar-local"

  echo
  request_file \
    "public-origin" \
    "${PUBLIC_ORIGIN}${avatar_uri}" \
    "$tmp_dir/avatar-public"

  echo
  echo "--- response headers: local ---"
  curl -ksSI --connect-timeout 10 --max-time 30 \
    "http://127.0.0.1:18080${avatar_uri}" || true

  echo
  echo "--- response headers: public ---"
  curl -ksSI --connect-timeout 10 --max-time 30 \
    "${PUBLIC_ORIGIN}${avatar_uri}" || true

  if [[ -s "$tmp_dir/avatar-local" ]]; then
    local_sha="$(sha256sum "$tmp_dir/avatar-local" | awk '{print $1}')"
  fi
  if [[ -s "$tmp_dir/avatar-public" ]]; then
    public_sha="$(sha256sum "$tmp_dir/avatar-public" | awk '{print $1}')"
  fi

  section "CHECKSUM COMPARISON"
  echo "backend_sha256=$backend_sha"
  echo "local_http_sha256=$local_sha"
  echo "public_http_sha256=$public_sha"

  if [[ -n "$backend_sha" && "$backend_sha" == "$local_sha" ]]; then
    echo "backend_vs_local=MATCH"
  else
    echo "backend_vs_local=MISMATCH"
  fi

  if [[ -n "$backend_sha" && "$backend_sha" == "$public_sha" ]]; then
    echo "backend_vs_public=MATCH"
  else
    echo "backend_vs_public=MISMATCH"
  fi
fi

section "PUBLIC PROFILE API"
curl -ksS \
  --connect-timeout 10 \
  --max-time 30 \
  "${PUBLIC_ORIGIN}/api/profile?username=${USERNAME}" \
  | head -c 4000 || true
echo

section "RECENT BACKEND LOGS"
"${compose[@]}" logs --since=2h backend-api 2>&1 \
  | grep -Ei 'upload_avatar|avatar|POST /api/upload|invalid file|picture is too large|unsupported file|permission denied|error|traceback' \
  | tail -160 || true

section "RECENT FRONTEND LOGS"
"${compose[@]}" logs --since=2h frontend 2>&1 \
  | grep -Ei 'public/avatar|404|403|error' \
  | tail -120 || true

section "AUTOMATIC SUMMARY"
if [[ "$avatar_exists" != "True" ]]; then
  echo "FAIL: database points to an avatar file that does not exist."
  echo "Likely cause: the avatar directory is not persistent or the write failed."
elif [[ "$avatar_public_readable" != "True" ]]; then
  echo "FAIL: avatar mode $avatar_mode is not readable by the frontend Nginx worker."
  echo "Fix existing files with chmod 0644 and make the upload API set mode 0644 after writing."
elif [[ -n "$backend_sha" && -n "$local_sha" && "$backend_sha" != "$local_sha" ]]; then
  echo "FAIL: frontend loopback returns content different from the backend file."
  echo "Likely cause: the frontend /public route or mounted public directory is incorrect."
elif [[ -n "$backend_sha" && -n "$public_sha" && "$backend_sha" != "$public_sha" ]]; then
  echo "FAIL: public origin returns content different from the backend file."
  echo "Likely cause: Caddy cache or public reverse-proxy routing is incorrect."
elif [[ -n "$backend_sha" && "$backend_sha" == "$local_sha" && "$backend_sha" == "$public_sha" ]]; then
  echo "PASS: database, backend file, local frontend route and public URL are consistent."
  echo "If the browser still shows initials, inspect the authenticated profile response and frontend rendering."
else
  echo "INCONCLUSIVE: inspect the non-200 responses in the sections above."
fi

echo
echo "Diagnostic completed. No database, avatar file or container changes were made."
