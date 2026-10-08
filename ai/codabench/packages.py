"""Register portable packages in the private Codabench service without running code."""
import hashlib
import json
import os
import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.db import transaction
from django.utils.timezone import now

from competitions.models import Competition, CompetitionParticipant, Phase, PhaseTaskInstance
from datasets.models import Data
from leaderboards.models import Column, Leaderboard
from tasks.models import Task
from package_format import MAX_EXPANDED, make_zip, parse_package

SERVICE_USER = "oj-ai-service"


def check(condition):
    if not condition:
        raise ValueError("Existing package registration differs from the archive")


def register(batch_id, source_sha256, raw):
    identity = str(uuid.UUID(batch_id))
    check(hashlib.sha256(raw).hexdigest() == source_sha256)
    problems = parse_package(raw)
    uploaded = []
    try:
        with transaction.atomic():
            # The upstream name fields are not unique. Serialize all package agents.
            owner = get_user_model().objects.select_for_update().get(username=SERVICE_USER)
            title = "xju-oj-package-" + identity
            competition, created = Competition.objects.get_or_create(title=title, created_by=owner, defaults={
                "description": source_sha256, "published": False, "docker_image": os.environ["XJU_EVALUATION_IMAGE"],
                "registration_auto_approve": False, "forum_enabled": False,
                "can_participants_make_submissions_public": False, "make_programs_available": False,
                "make_input_data_available": False, "show_detailed_results_in_submission_panel": False})
            check(competition.description == source_sha256 and not competition.published and
                  competition.docker_image == os.environ["XJU_EVALUATION_IMAGE"])
            CompetitionParticipant.objects.get_or_create(user=owner, competition=competition,
                                                        defaults={"status": CompetitionParticipant.APPROVED})
            results = []
            for index, item in enumerate(problems):
                name = title + "-" + str(index)
                datasets = {}
                for kind, files in item["assets"].items():
                    if not files:
                        datasets[kind] = None
                        continue
                    contents = dict(files)
                    if kind in ("scoring_program", "ingestion_program"):
                        contents["metadata.yaml"] = "command: python -I /app/program/program.py\n"
                    bundle = make_zip(contents, limit=MAX_EXPANDED)
                    digest = hashlib.sha256(bundle).hexdigest()
                    dataset_name = name + "-" + kind
                    dataset = Data.objects.filter(name=dataset_name, created_by=owner).first()
                    if dataset:
                        check(dataset.description == digest and dataset.type == kind and not dataset.is_public and
                              dataset.upload_completed_successfully)
                        with dataset.data_file.open("rb") as stream:
                            check(hashlib.sha256(stream.read(MAX_EXPANDED + 1)).hexdigest() == digest)
                    else:
                        dataset = Data(name=dataset_name, created_by=owner, type=kind, description=digest,
                                       is_public=False, file_size=len(bundle), upload_completed_successfully=True)
                        dataset.data_file.save(dataset_name + ".zip", ContentFile(bundle), save=False)
                        uploaded.append((dataset.data_file.storage, dataset.data_file.name))
                        dataset.save()
                    datasets[kind] = dataset
                evaluation = item["metadata"]["evaluation"]
                signature = json.dumps({"assets": item["asset_sha256"], "evaluation": evaluation}, sort_keys=True)
                task, _ = Task.objects.get_or_create(name=name, created_by=owner,
                                                     defaults={"description": signature, **datasets})
                check(task.description == signature and not task.is_public and
                      all(getattr(task, kind + "_id") == (value.pk if value else None) for kind, value in datasets.items()))
                phase = Phase.objects.filter(competition=competition, index=index).first()
                columns = [evaluation[key] for key in ("public_column", "private_column", "accuracy_column") if key in evaluation]
                if not phase:
                    board = Leaderboard.objects.create(title=name, key="problem-" + str(index), hidden=True)
                    for position, column in enumerate(columns):
                        Column.objects.create(leaderboard=board, title=column, key=column, index=position,
                                              hidden=column == evaluation.get("private_column"))
                    phase = Phase.objects.create(competition=competition, index=index, name="problem-" + str(index),
                                                 start=now() - timedelta(days=1), execution_time_limit=evaluation["run_seconds"],
                                                 has_max_submissions=False, hide_output=True, hide_prediction_output=True,
                                                 hide_score_output=True, leaderboard=board)
                    PhaseTaskInstance.objects.create(phase=phase, task=task, order_index=0)
                check(phase.execution_time_limit == evaluation["run_seconds"] and phase.end is None and
                      list(phase.tasks.values_list("id", flat=True)) == [task.pk] and
                      list(Column.objects.filter(leaderboard=phase.leaderboard).order_by("index").values_list("key", flat=True)) == columns)
                results.append({"index": index, "asset_sha256": item["asset_sha256"],
                                "judge": {"phase_id": phase.pk, "task_id": task.pk, **evaluation}})
            return results
    except Exception:
        # Only files uploaded by this rolled-back transaction may be removed.
        # Never delete a previously registered batch after a lost OJ response.
        for storage, name in uploaded:
            try:
                # A database connection can fail while COMMIT's outcome is unknown.
                # Retain the object unless a fresh query proves it is unreferenced.
                if not Data.objects.filter(data_file=name).exists():
                    storage.delete(name)
            except Exception:
                pass
        raise
