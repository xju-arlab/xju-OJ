"""An outbound-only compute agent. Run on a dedicated Docker host, outside OJ."""
import argparse
import atexit
import logging
import os
import signal
import time
from pathlib import Path

from codabench import Codabench
from notebook import NotebookExecutor
from transport import Client, RemoteError

log = logging.getLogger("ai-worker")


def secret(variable):
    value = Path(os.environ[variable]).read_text().strip()
    if len(value) < 32:
        raise ValueError("Missing or short service credential")
    return value


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true")
    parser.add_argument("--preflight", action="store_true")
    args = parser.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    kinds = os.environ.get("AI_WORKER_KINDS", "notebook,evaluation").split(",")
    if not kinds or set(kinds) - {"notebook", "evaluation"}:
        raise ValueError("Invalid worker capabilities")
    notebook = None
    worker = os.environ.get("AI_WORKER_NAME", "ai-worker-1")
    if "notebook" in kinds:
        notebook = NotebookExecutor(os.environ["AI_NOTEBOOK_IMAGE"], owner=worker,
                                    max_kernels=os.environ.get("AI_NOTEBOOK_MAX_KERNELS", "3"),
                                    memory_mb=os.environ.get("AI_NOTEBOOK_MEMORY_MB", "1024"),
                                    idle_seconds=os.environ.get("AI_NOTEBOOK_IDLE_SECONDS", "600"))
        notebook.preflight()
    oj = Client(os.environ["OJ_AI_URL"], secret("AI_WORKER_TOKEN_FILE"), "Bearer")
    evaluator = None
    if "evaluation" in kinds:
        evaluator = Codabench(Client(os.environ["CODABENCH_API_URL"], secret("CODABENCH_TOKEN_FILE"), "Token"),
                             os.environ["CODABENCH_STORAGE_ORIGIN"])
        evaluator.client.call("GET", "submissions/?limit=1")
    if args.preflight:
        log.info("Container engine, notebook image and configured evaluation service are available")
        return
    if notebook:
        notebook.recover()
        atexit.register(notebook.close)

        def stop(_signal, _frame):
            raise SystemExit(0)

        signal.signal(signal.SIGTERM, stop)

    def call(action, **data):
        result = oj.call("POST", "worker", {"worker": worker, "kinds": kinds, "action": action, **data})
        if result.get("error"):
            # The public API's error text is bounded and does not contain source or credentials.
            raise RemoteError(str(result.get("data", "Worker request failed"))[:256])
        return result["data"]

    while True:
        try:
            if notebook:
                notebook.reap_idle()
            job = call("claim")
            if job:
                log.info("Claimed %s %s", job["kind"], job["id"])

                def heartbeat(**data):
                    return call("heartbeat", id=job["id"], lease=job["lease"], **data)

                try:
                    result = (notebook if job["kind"] == "notebook" else evaluator).run(job, heartbeat)
                except Exception as exc:
                    # Never log raw request errors, signed storage URLs or user code.
                    log.error("Job %s failed: %s", job["id"], type(exc).__name__)
                    result = {"status": "SYSTEM_ERROR"}
                for attempt in range(3):
                    try:
                        call("finish", id=job["id"], lease=job["lease"], **result)
                        break
                    except RemoteError:
                        if attempt == 2:
                            raise
                        time.sleep(2)
                log.info("Finished %s: %s", job["id"], result["status"])
        except (RemoteError, OSError) as exc:
            log.error("Compute service request failed: %s", type(exc).__name__)
        if args.once:
            return
        time.sleep(2)


if __name__ == "__main__":
    main()
