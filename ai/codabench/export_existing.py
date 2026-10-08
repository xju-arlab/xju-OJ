"""Archive existing private evaluation assets for adoption, without regenerating datasets.

Run in the Codabench image with an administrator's current OJ manifest.
This utility reads existing objects only; it does not create phases or alter grades.
"""
import argparse
import hashlib
import json
import os
import re
import shlex
import sys
from pathlib import Path

sys.path.insert(0, "/app/src")
import django
django.setup()
import yaml
from competitions.models import Phase
from package_format import (ASSET_FOLDERS, FORMAT, MAX_UPLOAD, _archive,
                            export_problem, make_zip, parse_package)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("manifest", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    os.umask(0o077)
    args.output.mkdir(mode=0o700, parents=True, exist_ok=False)
    manifest = json.loads(args.manifest.read_text())
    archives, bindings = {}, {}
    for item in manifest:
        code = item["id"]
        if not re.fullmatch(r"[A-Za-z0-9_-]{1,32}", code) or code in bindings:
            raise ValueError("Invalid or repeated OJ problem code")
        judge = item["judge"]
        phase = Phase.objects.select_related("competition").get(pk=judge["phase_id"])
        if phase.competition.created_by.username != "oj-ai-service":
            raise ValueError("Phase is not owned by the OJ service")
        task = phase.tasks.get(pk=judge["task_id"])
        assets, source_hashes = {}, {}
        for kind in ASSET_FOLDERS:
            dataset = getattr(task, kind)
            assets[kind] = {}
            if dataset is None:
                continue
            if dataset.is_public or not dataset.upload_completed_successfully:
                raise ValueError("Expected a completed private evaluation asset")
            with dataset.data_file.open("rb") as stream:
                raw = stream.read(MAX_UPLOAD + 1)
            source_hashes[kind] = hashlib.sha256(raw).hexdigest()
            files = _archive(raw, [0, 0])
            if kind in ("scoring_program", "ingestion_program"):
                command = yaml.safe_load(files.pop("metadata.yaml"))["command"]
                tokens = shlex.split(command)
                if len(tokens) != 3 or tokens[:2] != ["python", "-I"] or not tokens[2].startswith("/app/program/"):
                    raise ValueError("Legacy program requires an explicit migration of its entry command")
                entry = tokens[2][len("/app/program/"):]
                if entry != "program.py" and "program.py" in files:
                    raise ValueError("Program entry conflicts with program.py")
                files["program.py"] = files.pop(entry)
            assets[kind] = files
        metadata = {"format": FORMAT, "version": 1, "source_id": code, "title": item["title"], "type": item["type"],
                    "metric": item["metric"], "points": item["points"], "statement": item["statement"],
                    "evaluation": {k: v for k, v in judge.items() if k not in ("phase_id", "task_id")}}
        archive = export_problem(metadata, item["cells"], item["public_files"], assets)
        parsed = parse_package(archive)[0]
        archives[code + ".zip"] = archive
        bindings[code] = {"id": code, "judge": judge, "asset_sha256": parsed["asset_sha256"],
                          "original_asset_sha256": source_hashes}
        (args.output / (code + ".zip")).write_bytes(archive)
    bundle = make_zip(archives)
    ordered = parse_package(bundle)
    (args.output / "problems.zip").write_bytes(bundle)
    (args.output / "bindings.json").write_text(json.dumps([bindings[p["metadata"]["source_id"]] for p in ordered], indent=2))
    print("Archived", len(ordered), "problems with original evaluation assets; no existing data changed")


if __name__ == "__main__":
    main()
