"""Outbound-only, leased package provisioning; uploaded programs are never executed here."""
import argparse
import logging
import os
import sys
import threading
import time
from pathlib import Path
from urllib.parse import urlencode

sys.path.insert(0, "/app/src")
import django
django.setup()

from django.db import close_old_connections
from django.contrib.auth import get_user_model
from packages import register, SERVICE_USER
from transport import Client, RemoteError

log = logging.getLogger("ai-package-agent")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s", force=True)
    token = Path(os.environ["AI_WORKER_TOKEN_FILE"]).read_text().strip()
    if len(token) < 32:
        raise ValueError("Missing worker credential")
    get_user_model().objects.get(username=SERVICE_USER)
    worker = os.environ.get("AI_WORKER_NAME", "package-1")
    client = Client(os.environ["OJ_AI_URL"], token, "Bearer")

    def call(action, **values):
        result = client.call("POST", "package-worker", {"worker": worker, "action": action, **values})
        if result.get("error"):
            raise RemoteError("Package service request rejected")
        return result["data"]

    if args.preflight:
        # Status proves connectivity and the bearer credential without claiming work.
        result = client.call("POST", "worker", {"action": "service", "operation": "status"})
        if result.get("error") or "imports" not in result.get("data", {}):
            raise RemoteError("Deploy the OJ package API first")
        log.info("Package API and private evaluation database are available")
        return

    while True:
        try:
            close_old_connections()
            job = call("claim")
            if job:
                values = {"id": job["id"], "lease": job["lease"]}
                stop = threading.Event()
                lost = threading.Event()

                def heartbeat():
                    while not stop.wait(20):
                        try:
                            call("heartbeat", **values)
                        except RemoteError:
                            lost.set()
                            return

                thread = threading.Thread(target=heartbeat, daemon=True)
                thread.start()
                try:
                    raw = client.get_zip("package-worker?" + urlencode({"worker": worker, **values}))
                    result = {"status": "SUCCEEDED", "results": register(job["id"], job["sha256"], raw)}
                except Exception as exc:
                    log.error("Package %s registration failed: %s", job["id"], type(exc).__name__)
                    result = {"status": "FAILED"}
                finally:
                    stop.set()
                    thread.join(timeout=16)
                if not lost.is_set():
                    for attempt in range(3):
                        try:
                            call("finish", **values, **result)
                            break
                        except RemoteError:
                            if attempt == 2:
                                raise
                            time.sleep(2)
                    log.info("Package %s: %s", job["id"], result["status"])
        except (RemoteError, OSError) as exc:
            log.error("Package service unavailable: %s", type(exc).__name__)
        if args.once:
            return
        time.sleep(3)


if __name__ == "__main__":
    main()
