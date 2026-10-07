"""Authenticated admission pause/drain for deployment. Never deletes queued work."""
import argparse
import os
from pathlib import Path
import time

from transport import Client

parser = argparse.ArgumentParser()
parser.add_argument("operation", choices=["pause", "resume", "status"])
parser.add_argument("--wait", type=int, default=0, help="Wait up to N seconds for existing jobs to drain")
args = parser.parse_args()
client = Client(os.environ["OJ_AI_URL"], Path(os.environ["AI_WORKER_TOKEN_FILE"]).read_text().strip(), "Bearer")


def call(operation):
    response = client.call("POST", "worker", {"action": "service", "operation": operation})
    if response.get("error"):
        raise RuntimeError("OJ rejected AI service control")
    return response["data"]


result = call(args.operation)
deadline = time.monotonic() + args.wait
while args.wait and result["active"]:
    if time.monotonic() >= deadline:
        raise SystemExit("AI jobs have not drained. Admission remains paused; inspect before resuming.")
    print("Waiting for", result["active"], "existing AI jobs", flush=True)
    time.sleep(5)
    result = call("status")
print("AI admission paused:", result["paused"], "active jobs:", result["active"])
