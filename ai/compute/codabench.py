"""Headless adapter for codalab/codabench e40d067ea3b61b9d7fa0146b7c075ed3d677862c."""
import io
import json
import math
import re
import time
import urllib.parse
import zipfile

from transport import RemoteError

# A package's scoring program may end its stdout with this one line for the student.
FEEDBACK = "XJU_FEEDBACK "


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

    def feedback(self, submission):
        """Return the scoring program's marked feedback line, or "" (best effort, never a verdict).

        The rest of the scoring log can contain hidden answers and is never read.
        """
        try:
            details = self.client.call("GET", "submissions/" + str(submission) + "/get_details/")
            logs = details.get("logs") if isinstance(details, dict) else None
            urls = [item.get("data_file") for item in logs or [] if isinstance(item, dict) and item.get("name") == "scoring_stdout"]
            if len(urls) != 1 or not isinstance(urls[0], str):
                return ""
            text = self.client.get_object(urls[0], self.storage_origin).decode("utf-8", "replace")
            lines = [line for line in text.splitlines() if line.startswith(FEEDBACK)]
            message = json.loads(lines[-1][len(FEEDBACK):]).get("message") if lines else ""
            return " ".join(message.split())[:400] if isinstance(message, str) else ""
        except Exception:  # Feedback must never turn a trusted score into a system error.
            return ""

    def run(self, job, heartbeat):
        remote_id = self.submit(job, heartbeat)
        deadline = time.monotonic() + 1200
        scores_deadline = None
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
                rows, scored = result.get("scores", []), remote_id
                if not rows and len(result.get("children", [])) == 1:
                    scored = result["children"][0]
                    child = self.client.call("GET", "submissions/" + str(scored) + "/")
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
                required = {job["judge"][key] for key in ("public_column", "private_column", "accuracy_column")
                            if job["judge"].get(key)}
                if required - scores.keys():
                    # This upstream revision marks Finished in Run.start(), then
                    # uploads score columns separately in run_wrapper(). A poll
                    # can therefore observe no scores or only some columns.
                    if scores_deadline is None:
                        scores_deadline = min(deadline, time.monotonic() + 30)
                    if time.monotonic() >= scores_deadline:
                        raise RemoteError("Required score column is missing")
                    time.sleep(3)
                    continue
                output = {"status": "SCORED", "remote_id": remote_id}
                for setting, field in (("public_column", "public_score"), ("private_column", "private_score"),
                                       ("accuracy_column", "accuracy")):
                    column = job["judge"].get(setting)
                    if column:
                        if column not in scores:
                            raise RemoteError("Required score column is missing")
                        output[field] = scores[column]
                message = self.feedback(scored)
                if message:
                    output["feedback"] = message
                return output
            time.sleep(3)
        return {"status": "SYSTEM_ERROR", "remote_id": remote_id}
