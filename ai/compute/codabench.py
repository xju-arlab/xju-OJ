"""Headless adapter for codalab/codabench e40d067ea3b61b9d7fa0146b7c075ed3d677862c."""
import io
import math
import re
import time
import urllib.parse
import zipfile

from transport import RemoteError


def submission_bundle(job):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        if job["category"] == "challenge":
            archive.writestr("predictions.csv", job["payload"]["predictions"])
        else:
            cells = job["payload"]["cells"]
            archive.writestr("solution.py", "\n\n".join(cells))
            for name, content in job["payload"].get("files", {}).items():
                if re.fullmatch(r"[A-Za-z0-9_-]{1,64}\.csv", name):
                    archive.writestr("data/" + name, content)
    return stream.getvalue()


class Codabench:
    def __init__(self, client, storage_origin):
        self.client = client
        self.storage_origin = storage_origin

    def find_submission(self, job):
        query = urllib.parse.urlencode({"phase": job["judge"]["phase_id"], "search": job["id"]})
        result = self.client.call("GET", "submissions/?" + query)
        items = result.get("results", []) if isinstance(result, dict) else result
        matches = [item for item in items if not item.get("parent") and job["id"] in item.get("filename", "")
                   and item.get("phase") == job["judge"]["phase_id"]]
        if len(matches) > 1:
            raise RemoteError("Ambiguous Codabench submission")
        return matches[0]["id"] if matches else None

    def submit(self, job, heartbeat):
        remote_id = job.get("remote_id") or self.find_submission(job)
        if remote_id:
            heartbeat(remote_id=remote_id)
            return remote_id
        if job.get("dispatch_started"):
            # A timed-out POST might have been committed. Do not blindly submit again.
            raise RemoteError("Previous Codabench dispatch is indeterminate")
        content = submission_bundle(job)
        name = "oj-" + job["id"] + "-" + job["lease"][:8]
        dataset = self.client.call("POST", "datasets/", {"name": name, "type": "submission", "is_public": False,
                                                        "request_sassy_file_name": name + ".zip", "file_size": len(content)})
        self.client.put_zip(dataset["sassy_url"], content, self.storage_origin)
        self.client.call("PUT", "datasets/completed/" + dataset["key"] + "/", {})
        heartbeat(dispatch_started=True)
        data = {"phase": job["judge"]["phase_id"], "data": dataset["key"]}
        if job["judge"].get("task_id"):
            data["tasks"] = [job["judge"]["task_id"]]
        try:
            created = self.client.call("POST", "submissions/", data)
            remote_id = created["id"]
        except (RemoteError, KeyError):
            remote_id = self.find_submission(job)
            if not remote_id:
                raise RemoteError("Codabench submission could not be reconciled") from None
        heartbeat(remote_id=remote_id)
        return remote_id

    def run(self, job, heartbeat):
        remote_id = self.submit(job, heartbeat)
        deadline = time.monotonic() + 1200
        while time.monotonic() < deadline:
            heartbeat(remote_id=remote_id)
            result = self.client.call("GET", "submissions/" + str(remote_id) + "/")
            if result.get("phase") != job["judge"]["phase_id"]:
                raise RemoteError("Codabench phase mismatch")
            status = result.get("status")
            if status in ("Failed", "Cancelled"):
                verdict = "CANCELLED"
                if status == "Failed":
                    details = str(result.get("status_details", ""))
                    if len(result.get("children", [])) == 1:
                        child = self.client.call("GET", "submissions/" + str(result["children"][0]) + "/")
                        details += " " + str(child.get("status_details", ""))
                    verdict = "RUNTIME_ERROR"
                    # Only authenticated worker status metadata is inspected. Student
                    # stdout and stderr are never used to choose an official verdict.
                    if "execution time limit exceeded" in details.lower():
                        verdict = "TIME_LIMIT"
                    elif "XJU_MEMORY_LIMIT" in details:
                        verdict = "MEMORY_LIMIT"
                return {"status": verdict, "remote_id": remote_id}
            if status == "Finished":
                rows = result.get("scores", [])
                if not rows and len(result.get("children", [])) == 1:
                    child = self.client.call("GET", "submissions/" + str(result["children"][0]) + "/")
                    rows = child.get("scores", [])
                scores = {}
                for row in rows:
                    key = row["column_key"]
                    if key in scores:
                        raise RemoteError("Ambiguous score column")
                    score = float(row["score"])
                    if not math.isfinite(score):
                        raise RemoteError("Nonfinite score")
                    scores[key] = score
                output = {"status": "SCORED", "remote_id": remote_id}
                for setting, field in (("public_column", "public_score"), ("private_column", "private_score"),
                                       ("accuracy_column", "accuracy")):
                    column = job["judge"].get(setting)
                    if column:
                        if column not in scores:
                            raise RemoteError("Required score column is missing")
                        output[field] = scores[column]
                return output
            time.sleep(3)
        return {"status": "SYSTEM_ERROR", "remote_id": remote_id}
