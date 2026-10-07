#!/bin/sh
# Deploy the AI adjunct after the OJ database migration has completed.
set -eu
ai_root=$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)
ai_runtime=${1:?Usage: sh ai/deploy.sh /absolute/private/runtime}
[ -f "$ai_runtime/compose.env" ] || { echo 'Run ai/prepare.py first' >&2; exit 1; }
ai_runtime=$(CDPATH= cd -- "$ai_runtime" && pwd)
[ -z "$(git -C "$ai_root" status --porcelain)" ] || { echo 'Commit changes before deploying' >&2; exit 1; }
exec 9>"$ai_runtime/deploy.lock"
flock -n 9 || { echo 'Another AI deployment is active' >&2; exit 1; }
umask 077
compose() { docker compose --env-file "$ai_runtime/compose.env" -f "$ai_root/ai/compose.yaml" "$@"; }
compose config --quiet
# Check image provenance before changing running services.
AI_RUNTIME_CHECK="$ai_runtime" AI_REPO_CHECK="$ai_root" python3 - <<'PY'
import json, os, pathlib, subprocess
root = pathlib.Path(os.environ['AI_RUNTIME_CHECK'])
values = dict(line.split('=', 1) for line in (root/'compose.env').read_text().splitlines() if '=' in line)
sha = subprocess.check_output(['git','-C',os.environ['AI_REPO_CHECK'],'rev-parse','HEAD'], text=True).strip()
for key in ('AI_SITE_IMAGE','AI_COMPUTE_IMAGE','AI_NOTEBOOK_IMAGE'):
    info = json.loads(subprocess.check_output(['docker','image','inspect',values[key]]))[0]
    if info['Config'].get('Labels',{}).get('org.opencontainers.image.revision') != sha:
        raise SystemExit('Build or load AI images for this exact Git revision first')
PY
compose run --rm --no-deps evaluation-agent python /opt/bridge/control.py pause --wait 1800
if [ -n "$(compose ps -q codabench)" ]; then
  # Admission is paused and existing leases have drained before service replacement.
  compose exec -T codabench python -m django shell -c 'from competitions.models import Submission; assert not Submission.objects.exclude(status__in=["Finished","Failed","Cancelled"]).exists(), "Drain active Codabench submissions before deploying"'
  ai_backup="$ai_runtime/backups/$(date -u +%Y%m%dT%H%M%SZ)"
  mkdir -p "$ai_backup"
  compose exec -T db pg_dump -U codabench -d codabench -Fc > "$ai_backup/codabench.dump"
  [ -s "$ai_backup/codabench.dump" ]
  ai_objects=$(docker inspect --format '{{range .Mounts}}{{if eq .Destination "/data"}}{{.Name}}{{end}}{{end}}' "$(compose ps -q minio)")
  [ -n "$ai_objects" ]
  compose run --rm --no-deps -v "$ai_objects:/objects:ro" -v "$ai_backup:/backup" codabench \
    python -c 'import shutil; shutil.make_archive("/backup/objects", "gztar", "/objects")'
  # Bootstrap exports are root-owned 0600. Copy inside the trusted service image;
  # do not relax their permissions or print credential values to the terminal.
  compose run --rm --no-deps -v "$ai_runtime:/private-runtime:ro" -v "$ai_backup:/backup" codabench \
    python -c 'import os,shutil; os.umask(0o077); names=("compose.env","service.env","postgres.env","rabbit.env","minio.env"); [shutil.copy2("/private-runtime/"+n,"/backup/"+n) for n in names]; [shutil.copytree("/private-runtime/"+n,"/backup/"+n) for n in ("secrets","exports")]'
fi
compose up -d --wait --wait-timeout 120 db redis rabbit minio
compose run --rm --no-deps codabench python -m django migrate --noinput
compose run --rm --no-deps codabench python -m django shell -c 'exec(open("/opt/xju/bootstrap.py").read())'
# bootstrap writes with a root-owned private umask; copy without exposing its value.
compose run --rm --no-deps -v "$ai_runtime/secrets:/private-secrets" codabench python -c 'from pathlib import Path; p=Path("/private-secrets/coda_token"); p.write_text(Path("/exports/coda-token").read_text()); p.chmod(0o600)'
compose up -d
compose exec -T notebook-agent python /opt/bridge/worker.py --preflight
compose exec -T evaluation-agent python /opt/bridge/worker.py --preflight
compose run --rm --no-deps evaluation-agent python /opt/bridge/control.py resume
echo 'AI services started. Import exports/oj-practice.json in OJ, then verify a real submission before opening access.'
