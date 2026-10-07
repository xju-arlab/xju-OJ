#!/bin/sh
# Locked upstream source; runtime/private files are never build contexts.
set -eu
ai_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ai_sha=$(git -C "$ai_root" rev-parse HEAD)
ai_tag=${1:-git-$(printf '%s' "$ai_sha" | cut -c1-12)}
case "$ai_tag" in *[!a-zA-Z0-9_.-]*|'') echo 'Invalid image tag' >&2; exit 1;; esac
if [ "$ai_tag" != dev ] && [ -n "$(git -C "$ai_root" status --porcelain)" ]; then
  echo 'Release builds require a clean committed checkout' >&2
  exit 1
fi
ai_upstream_sha=e40d067ea3b61b9d7fa0146b7c075ed3d677862c
ai_upstream=${AI_UPSTREAM_CACHE:-${XDG_CACHE_HOME:-$HOME/.cache}/xju-ai/codabench-$ai_upstream_sha}
if [ ! -d "$ai_upstream/.git" ]; then
  mkdir -p "$(dirname -- "$ai_upstream")"
  git clone --filter=blob:none --no-checkout https://github.com/codalab/codabench.git "$ai_upstream"
  git -C "$ai_upstream" checkout --detach "$ai_upstream_sha"
fi
[ "$(git -C "$ai_upstream" rev-parse HEAD)" = "$ai_upstream_sha" ] || { echo 'Unexpected Codabench revision' >&2; exit 1; }
[ -z "$(git -C "$ai_upstream" status --porcelain)" ] || { echo 'Codabench checkout has local changes' >&2; exit 1; }
build_image() {
  docker buildx build --load --network "${BUILD_NETWORK:-default}" \
    --build-arg "HTTP_PROXY=${HTTP_PROXY:-}" --build-arg "HTTPS_PROXY=${HTTPS_PROXY:-}" \
    --label "org.opencontainers.image.revision=$ai_sha" \
    --label "org.xju.codabench.revision=$ai_upstream_sha" "$@"
}
build_image -f "$ai_root/ai/notebook/Dockerfile" -t "xju-ai-notebook:$ai_tag" "$ai_root/ai/notebook"
build_image --build-context "codabench=$ai_upstream" --target site -f "$ai_root/ai/codabench/Dockerfile" -t "xju-ai-codabench:$ai_tag" "$ai_root"
build_image --build-context "codabench=$ai_upstream" --target compute -f "$ai_root/ai/codabench/Dockerfile" -t "xju-ai-compute:$ai_tag" "$ai_root"
