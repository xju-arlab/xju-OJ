"""Prepare private, idempotent runtime configuration outside the checkout."""
import argparse
import json
import os
from pathlib import Path
import secrets
import subprocess


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--runtime", type=Path, required=True)
    parser.add_argument("--project", default="xju-ai")
    parser.add_argument("--oj-url", required=True)
    parser.add_argument("--tag", required=True)
    parser.add_argument("--postgres-image", required=True)
    args = parser.parse_args()
    root = args.runtime.resolve()
    repo = Path(__file__).resolve().parent.parent
    if root == repo or repo in root.parents:
        raise SystemExit("Runtime and credentials must be outside the repository")
    if not args.project.replace("-", "").isalnum():
        raise SystemExit("Invalid project name")
    os.umask(0o077)
    root.mkdir(parents=True, exist_ok=True)
    if (root / "compose.env").exists():
        raise SystemExit("Configuration already exists; edit the private compose.env to upgrade image tags")
    (root / "secrets").mkdir(exist_ok=True)
    (root / "exports").mkdir(exist_ok=True)
    values = {key: secrets.token_hex(32) for key in ("db", "rabbit", "s3", "coda_secret", "oj_worker_token")}
    for key in ("coda_secret", "oj_worker_token"):
        (root / "secrets" / key).write_text(values[key] + "\n")
    # Filled by the trusted bootstrap, never passed to student containers.
    (root / "secrets/coda_token").touch()

    def write(name, data):
        if any("\n" in str(value) for value in data.values()):
            raise ValueError("Newline in configuration")
        (root / name).write_text("".join(f"{key}={value}\n" for key, value in data.items()))

    write("postgres.env", {"POSTGRES_DB": "codabench", "POSTGRES_USER": "codabench", "POSTGRES_PASSWORD": values["db"]})
    write("rabbit.env", {"RABBITMQ_DEFAULT_USER": "codabench", "RABBITMQ_DEFAULT_PASS": values["rabbit"]})
    write("minio.env", {"MINIO_ROOT_USER": "codabench", "MINIO_ROOT_PASSWORD": values["s3"]})
    write("service.env", {
        "DOMAIN_NAME": "codabench", "SITE_DOMAIN": "http://codabench:8000",
        "DATABASE_URL": f"postgres://codabench:{values['db']}@db:5432/codabench",
        "BROKER_URL": f"pyamqp://codabench:{values['rabbit']}@rabbit:5672//",
        "RABBITMQ_DEFAULT_USER": "codabench", "RABBITMQ_DEFAULT_PASS": values["rabbit"],
        "RABBITMQ_HOST": "rabbit", "RABBITMQ_PORT": "5672",
        "REDIS_URL": "redis://redis:6379/0", "SUBMISSIONS_API_URL": "http://codabench:8000/api",
        "STORAGE_TYPE": "minio", "AWS_S3_ENDPOINT_URL": "http://minio:9000",
        "AWS_ACCESS_KEY_ID": "codabench", "AWS_SECRET_ACCESS_KEY": values["s3"],
        "AWS_STORAGE_BUCKET_NAME": "public", "AWS_STORAGE_PRIVATE_BUCKET_NAME": "bundles",
        "AWS_QUERYSTRING_AUTH": "true", "AWS_DEFAULT_ACL": "private", "LOG_LEVEL": "WARNING",
        "OJ_AI_URL": args.oj_url, "AI_WORKER_TOKEN_FILE": "/run/secrets/oj_worker_token",
        "CODABENCH_API_URL": "http://codabench:8000/api/", "CODABENCH_TOKEN_FILE": "/run/secrets/coda_token",
        "CODABENCH_STORAGE_ORIGIN": "http://minio:9000", "COMPETITION_CONTAINER_NETWORK_DISABLED": "true",
    })
    volume = args.project + "-workspace"
    subprocess.run(["docker", "volume", "create", "--driver=local", "--opt=type=tmpfs", "--opt=device=tmpfs",
                    "--opt=o=size=512m,mode=0700", volume], check=True, stdout=subprocess.DEVNULL)
    info = json.loads(subprocess.check_output(["docker", "volume", "inspect", volume]))[0]
    if info["Driver"] != "local" or info.get("Options") != {"type": "tmpfs", "device": "tmpfs", "o": "size=512m,mode=0700"}:
        raise SystemExit("Workspace volume must be the bounded 512 MiB tmpfs; refusing an existing incompatible volume")
    mount = info["Mountpoint"]
    write("compose.env", {"COMPOSE_PROJECT_NAME": args.project, "AI_RUNTIME": str(root),
        "AI_SITE_IMAGE": "xju-ai-codabench:" + args.tag, "AI_COMPUTE_IMAGE": "xju-ai-compute:" + args.tag,
        "AI_NOTEBOOK_IMAGE": "xju-ai-notebook:" + args.tag, "AI_POSTGRES_IMAGE": args.postgres_image,
        "AI_WORKSPACE_VOLUME": volume, "AI_WORKSPACE_PATH": mount})
    print("Private runtime prepared:", root)


if __name__ == "__main__":
    main()
