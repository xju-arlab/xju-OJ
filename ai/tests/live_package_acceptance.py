"""Opt-in real import/grading/export test using synthetic, hidden problems.

Requires private administrator/student sessions. Creates and retains its own
password contest and problems, then hides the contest. Never edits existing tasks.
"""
import argparse
from datetime import datetime, timedelta, timezone
import json
from pathlib import Path
import sys
import time
import urllib.parse
import urllib.request
import uuid

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from ai_studio.package_format import FORMAT, export_problem, make_zip, parse_package
from live_acceptance import API


def fixture(category, nonce):
    evaluation = {"public_column": "score", "pass_score": 100, "run_seconds": 30}
    if category == "model":
        evaluation["accuracy_column"] = "accuracy"
    if category == "challenge":
        evaluation["private_column"] = "private_score"
    metadata = {"format": FORMAT, "version": 1, "title": "Import acceptance " + category + " " + nonce,
                "type": category, "statement": {"objective": "Synthetic package verification", "signature": "solve(x)",
                "inputSpec": "one value", "outputSpec": "one value"}, "evaluation": evaluation}
    ingestion = '''import json, runpy
from pathlib import Path
source = runpy.run_path('/app/ingested_program/solution.py')
x = json.loads(Path('/app/input_data/case.json').read_text())['x']
Path('/app/output/answer.json').write_text(json.dumps({'answer': float(source['solve'](x))}, allow_nan=False))
'''
    scoring = '''import csv, json, math
from pathlib import Path
ref = json.loads(Path('/app/input/ref/answer.json').read_text())
if ref['type'] == 'challenge':
    with Path('/app/input/res/predictions.csv').open() as stream:
        reader = csv.DictReader(stream)
        assert reader.fieldnames == ['id', 'value']
        rows = list(reader)
    assert len(rows) == 1 and rows[0]['id'] == '0'
    answer = float(rows[0]['value'])
else:
    answer = float(json.loads(Path('/app/input/res/answer.json').read_text())['answer'])
assert math.isfinite(answer)
score = 100 if abs(answer - ref['expected']) < 1e-6 else 0
Path('/app/output/scores.json').write_text(json.dumps({'score': score, 'private_score': score, 'accuracy': score / 100}))
'''
    assets = {"scoring_program": {"program.py": scoring.encode()},
              "reference_data": {"answer.json": json.dumps({"type": category, "expected": 7}).encode()}}
    if category != "challenge":
        assets.update(ingestion_program={"program.py": ingestion.encode()}, input_data={"case.json": b'{"x": 7}'})
    return export_problem(metadata, ["# Synthetic starter"], {"sample.csv": "id,x\n0,7\n"}, assets)


def upload(api, raw):
    boundary = "package-" + uuid.uuid4().hex
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="file"; filename="acceptance.zip"\r\n'
            'Content-Type: application/zip\r\n\r\n').encode() + raw + f'\r\n--{boundary}--\r\n'.encode()
    request = urllib.request.Request(api.base + "admin/ai/packages", data=body, method="POST",
                                     headers={**api.headers, "Content-Type": "multipart/form-data; boundary=" + boundary})
    result = json.load(api.opener.open(request, timeout=30))
    assert not result.get("error"), result.get("data")
    return result["data"]


def wait_import(api, batch):
    for _ in range(100):
        result = api.call("admin/ai/packages", data={"id": batch["id"]})
        if result["status"] not in ("PENDING", "RUNNING"):
            assert result["status"] == "SUCCEEDED", result["status"] + ": " + result["message"]
            return result
        time.sleep(2)
    raise TimeoutError("Package import did not finish")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base", required=True)
    parser.add_argument("--sessions", type=Path, required=True)
    parser.add_argument("--report", type=Path, required=True)
    args = parser.parse_args()
    sessions = json.loads(args.sessions.read_text())
    admin, student = [API(args.base, item["session"]) for item in sessions[:2]]
    report = {"checks": [], "imports": [], "jobs": []}

    def check(value):
        report["checks"].append(value)
        args.report.write_text(json.dumps(report, indent=2))
        print(value, flush=True)

    nonce = uuid.uuid4().hex[:10]
    raw = make_zip({str(i) + ".zip": fixture(category, nonce) for i, category in enumerate(("logic", "model", "challenge"))})
    preview = upload(admin, raw)
    assert preview["status"] == "PREVIEW" and not preview["result"] and len(preview["problems"]) == 3
    assert upload(admin, raw)["id"] == preview["id"]
    confirmed = admin.call("admin/ai/packages/confirm", "POST", {"id": preview["id"], "publish": False})
    batch = wait_import(admin, confirmed)
    report["imports"].append(batch["id"])
    codes = [item["id"] for item in batch["result"]]
    check("Batch preview, duplicate upload, asynchronous registration and default hidden visibility passed")
    for code in codes:
        student.call("ai/problems", data={"problem_id": code}, fail=True)

    query = urllib.parse.urlencode([("problem_id", code) for code in codes])
    request = urllib.request.Request(admin.base + "admin/ai/packages/export?" + query, headers=admin.headers)
    with admin.opener.open(request, timeout=30) as response:
        exported = response.read()
    parsed = parse_package(exported)
    original = parse_package(raw)
    assert [p["asset_sha256"] for p in parsed] == [p["asset_sha256"] for p in original]
    assert all("phase_id" not in p["metadata"]["evaluation"] for p in parsed)
    copy_preview = upload(admin, exported)
    copy_batch = wait_import(admin, admin.call("admin/ai/packages/confirm", "POST", {"id": copy_preview["id"], "publish": False}))
    report["imports"].append(copy_batch["id"])
    copy_codes = [item["id"] for item in copy_batch["result"]]
    assert not set(codes).intersection(copy_codes)
    for a, b in zip(codes, copy_codes):
        first = admin.call("admin/ai/problems", data={"id": a})
        second = admin.call("admin/ai/problems", data={"id": b})
        assert first["judge"]["phase_id"] != second["judge"]["phase_id"]
    check("Full export/reimport preserves evaluation assets and allocates independent question/phase IDs")

    future = datetime.now(timezone.utc) + timedelta(minutes=5)
    contest_data = {"title": "AI package acceptance " + nonce, "description": "Synthetic import verification", "rule_type": "AI",
                    "visible": True, "password": uuid.uuid4().hex, "real_time_rank": True, "allowed_ip_ranges": [],
                    "start_time": future.isoformat(), "end_time": (future + timedelta(minutes=10)).isoformat()}
    contest = admin.call("admin/contest", "POST", contest_data)
    report["contest_id"] = contest["id"]
    config = {"contest_id": contest["id"], "selection": "best", "private_published": False, "practice_enabled": True,
              "problems": [{"id": code, "points": 100} for code in codes + copy_codes]}
    admin.call("admin/ai/contest", "PUT", config)
    try:
        student.call("contest/register", "POST", {"contest_id": contest["id"], "password": contest_data["password"]})
        past = datetime.now(timezone.utc) - timedelta(minutes=2)
        contest_data.update(start_time=past.isoformat(), end_time=(past + timedelta(minutes=1)).isoformat())
        admin.call("admin/contest", "PUT", {**contest_data, "id": contest["id"]})
        answers = [["def solve(x):\n    return x"],
                   ["import torch\nmodel = torch.nn.Linear(1, 1, bias=False)\nwith torch.no_grad():\n    model.weight.fill_(7)\ndef solve(x):\n    return model(torch.ones(1, 1)).item()"],
                   ["from pathlib import Path\nPath('predictions.csv').write_text('id,value\\n0,7\\n')\nprint('ready')"]]
        for index, code in enumerate(codes + copy_codes):
            category = ("logic", "model", "challenge")[index % 3]
            cells = answers[index % 3]
            notebook = student.wait(student.submit(code, cells, contest["id"], kind="notebook"))
            assert notebook["status"] == "SUCCEEDED", notebook["status"]
            result = student.wait(student.submit(code, cells, contest["id"], predictions=notebook["output"].get("predictions") if category == "challenge" else None))
            assert result["status"] in ("ACCEPTED", "SCORED") and result["publicScore"] == 100, result["status"]
            assert result["privateScore"] is None and not result["official"]
            if category == "model":
                assert result["accuracy"] == 1
            report["jobs"].append(result["id"])
            check(category + " real Notebook and isolated evaluation passed for " + code)
        wrong = student.wait(student.submit(codes[0], ["def solve(x):\n    return 0"], contest["id"]))
        assert wrong["status"] == "WRONG_ANSWER" and wrong["publicScore"] == 0
        student.call("admin/ai/packages/export", data={"problem_id": codes[0]}, fail=True)
        check("Incorrect answer scored zero and student export access denied")
        edited = admin.call("admin/ai/problems", data={"id": codes[0]})
        edited["outputSpec"] = "one scalar"
        saved = admin.call("admin/ai/problems", "POST", edited)
        assert saved["version"] == edited["version"] and saved["revision"] == edited["revision"] + 1
        admin.call("admin/ai/problems", "POST", edited, fail=True)
        check("Statement editing preserves grade version and rejects stale revisions")
    finally:
        admin.call("admin/contest", "PUT", {**contest_data, "id": contest["id"], "visible": False})
        check("Synthetic contest hidden; imported problems remain hidden and evidence retained")


if __name__ == "__main__":
    main()
