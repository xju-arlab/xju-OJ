"""Run with Codabench's manage.py shell, after migrations. Credentials stay private."""
import hashlib
import io
import json
import os
from pathlib import Path
import secrets
import sys
import zipfile
from datetime import timedelta

import boto3
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.timezone import now
from rest_framework.authtoken.models import Token

from competitions.models import Competition, CompetitionParticipant, Phase, PhaseTaskInstance, Submission
from datasets.models import Data
from leaderboards.models import Column, Leaderboard
from tasks.models import Task

sys.path.insert(0, "/opt/xju/practice")
from problems import generate

os.umask(0o077)
root = Path("/exports")
seed_path = root / "practice-seed"
if not seed_path.exists():
    seed_path.write_text(secrets.token_hex(32))
seed = seed_path.read_text().strip()
problems = generate(seed)
s3 = boto3.client("s3", endpoint_url=os.environ["AWS_S3_ENDPOINT_URL"])
for bucket in ("public", "bundles"):
    try:
        s3.head_bucket(Bucket=bucket)
    except s3.exceptions.ClientError as exc:
        if str(exc.response["Error"]["Code"]) not in {"404", "NoSuchBucket"}:
            raise
        s3.create_bucket(Bucket=bucket)


def archive(files):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w", zipfile.ZIP_DEFLATED) as bundle:
        for name, content in files.items():
            entry = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            entry.compress_type = zipfile.ZIP_DEFLATED
            bundle.writestr(entry, content)
    return stream.getvalue()


def dataset(owner, code, kind, files):
    content = archive(files)
    digest = hashlib.sha256(content).hexdigest()
    name = "xju-practice-v1-" + code + "-" + kind
    existing = Data.objects.filter(name=name, created_by=owner).first()
    if existing:
        if existing.description != digest or not existing.upload_completed_successfully:
            raise ValueError("Existing practice bundle differs: " + name)
        return existing
    data = Data(name=name, description=digest, type=kind, created_by=owner, is_public=False,
                file_size=len(content), upload_completed_successfully=True)
    data.data_file.save(name + ".zip", ContentFile(content))
    return data


with transaction.atomic():
    user, created = get_user_model().objects.get_or_create(username="oj-ai-service", defaults={"email": "oj-ai@localhost.invalid"})
    if created:
        user.set_unusable_password()
        user.save()
    token, _ = Token.objects.get_or_create(user=user)
    (root / "coda-token").write_text(token.key + "\n")
    image = os.environ["XJU_EVALUATION_IMAGE"]
    competition, created = Competition.objects.get_or_create(title="XJU AI practice v1", created_by=user, defaults={
        "published": False, "description": "Private evaluation service for OJ practice tasks",
        "docker_image": image, "registration_auto_approve": False, "forum_enabled": False,
        "can_participants_make_submissions_public": False, "make_programs_available": False,
        "make_input_data_available": False, "show_detailed_results_in_submission_panel": False})
    if competition.docker_image != image:
        if Submission.objects.filter(phase__competition=competition).exclude(status__in=["Finished", "Failed", "Cancelled"]).exists():
            raise ValueError("Drain Codabench before changing the evaluation image")
        competition.docker_image = image
        competition.save(update_fields=["docker_image"])
    CompetitionParticipant.objects.get_or_create(user=user, competition=competition,
                                                  defaults={"status": CompetitionParticipant.APPROVED})
    for index, problem in enumerate(problems):
        code = problem["id"]
        reference = dataset(user, code, Data.REFERENCE_DATA, {"reference.json": json.dumps(problem["reference"])})
        scoring = dataset(user, code, Data.SCORING_PROGRAM, {
            "metadata.yaml": "command: python -I /app/program/scoring.py\n",
            "scoring.py": Path("/opt/xju/practice/scoring.py").read_text()})
        ingestion = inputs = None
        if "input" in problem:
            ingestion = dataset(user, code, Data.INGESTION_PROGRAM, {
                "metadata.yaml": "command: python -I /app/program/ingestion.py\n",
                "ingestion.py": Path("/opt/xju/practice/ingestion.py").read_text()})
            inputs = dataset(user, code, Data.INPUT_DATA, {"input.json": json.dumps(problem["input"])})
        task, _ = Task.objects.get_or_create(name="xju-practice-v1-" + code, created_by=user, defaults={
            "reference_data": reference, "scoring_program": scoring, "ingestion_program": ingestion, "input_data": inputs})
        phase = Phase.objects.filter(competition=competition, index=index).first()
        if not phase:
            board = Leaderboard.objects.create(title=code, key=code, hidden=True)
            for position, key in enumerate(("public_score", "private_score", "accuracy")):
                Column.objects.create(leaderboard=board, title=key, key=key, index=position, hidden=key == "private_score")
            phase = Phase.objects.create(competition=competition, index=index, name=code, start=now() - timedelta(days=1),
                execution_time_limit=120, has_max_submissions=False, hide_output=True, hide_prediction_output=True,
                hide_score_output=True, leaderboard=board)
            PhaseTaskInstance.objects.create(phase=phase, task=task, order_index=0)
        problem["judge"] = {"phase_id": phase.pk, "task_id": task.pk, "public_column": "public_score",
                             "pass_score": 100, "run_seconds": 120}
        if problem["type"] == "model":
            problem["judge"]["accuracy_column"] = "accuracy"
        if problem["type"] == "challenge":
            problem["judge"]["private_column"] = "private_score"

# Only this manifest is imported by OJ. No reference labels, seed or solutions.
manifest = [{key: value for key, value in problem.items() if key not in {"reference", "input", "reference_cells"}}
            for problem in problems]
(root / "oj-practice.json").write_text(json.dumps(manifest, ensure_ascii=False))
(root / "acceptance-solutions.json").write_text(json.dumps([
    {"id": problem["id"], "cells": problem["reference_cells"]} for problem in problems]))
print("Prepared five private Codabench phases and the OJ practice manifest")
