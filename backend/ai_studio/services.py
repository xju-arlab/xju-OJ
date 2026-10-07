import hashlib
import ipaddress
import json
import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils.timezone import now

from account.models import User
from contest.models import Contest
from contest.serializers import ContestSerializer
from utils.api import APIError
from utils.constants import ContestRuleType, ContestStatus
from .contracts import ACTIVE, MAX_PREDICTION_BYTES, cells_input, require
from .models import AIContestConfig, AIContestProblem, AIDraft, AIJob, AIProblem, AIServiceState, AIWorker


def contest_access(request, contest_id, *, content=True, write=False):
    require(str(contest_id).isdigit(), "Invalid contest")
    contest = Contest.objects.filter(pk=contest_id, rule_type=ContestRuleType.AI, visible=True).first()
    require(contest is not None, "AI contest does not exist")
    config = AIContestConfig.objects.filter(contest=contest).first()
    require(config is not None, "AI contest is not configured")
    if not content:
        return contest, config
    user = request.user
    require(user.is_authenticated and not user.is_disabled, "Please login first")
    if user.is_contest_admin(contest):
        return contest, config
    require(contest.status != ContestStatus.CONTEST_NOT_START, "Contest has not started yet")
    if contest.status == ContestStatus.CONTEST_ENDED:
        require(not write or config.practice_enabled, "Practice is not open")
    else:
        require(contest.is_registered(user), "Please register for the contest first")
        if write and contest.allowed_ip_ranges:
            try:
                address = ipaddress.ip_address(request.ip)
                allowed = any(address in ipaddress.ip_network(cidr, strict=False) for cidr in contest.allowed_ip_ranges)
            except ValueError:
                allowed = False
            require(allowed, "Your IP is not allowed in this contest")
    return contest, config


def problem_access(request, data, *, write=False):
    code = data.get("problem_id")
    require(isinstance(code, str), "problem_id is required")
    problem = AIProblem.objects.filter(code=code).first()
    require(problem is not None, "AI problem does not exist")
    contest_id = data.get("contest_id")
    if contest_id:
        contest, config = contest_access(request, contest_id, write=write)
        require(AIContestProblem.objects.filter(contest=contest, problem=problem).exists(), "Problem is not in this contest")
        return problem, contest, config
    require(problem.visible, "AI problem does not exist")
    return problem, None, None


def public_problem(problem, points=None, full=False):
    result = {"id": problem.code, "title": problem.title, "type": problem.category,
              "metric": problem.metric, "points": problem.points if points is None else points,
              "version": problem.version}
    if full:
        result.update({key: problem.statement.get(key, [] if key == "requirements" else "")
                       for key in ("objective", "requirements", "signature", "data", "evaluation")})
        result["cells"] = problem.cells
        result["files"] = list(problem.public_files)
    return result


def public_job(job, *, detail=False):
    published = False
    if job.contest_id:
        published = (job.contest.end_time < now() and
                     AIContestConfig.objects.filter(contest_id=job.contest_id, private_published=True).exists())
    result = {"id": str(job.id), "problemId": job.problem.code, "title": job.problem.title,
              "type": job.category, "kind": job.kind, "contestId": str(job.contest_id) if job.contest_id else "",
              "official": job.official, "createdAt": job.created_at.isoformat(), "status": job.status,
              "publicScore": job.public_score, "privateScore": job.private_score if published else None,
              "privatePublished": published, "accuracy": job.accuracy, "message": job.message}
    if detail:
        result["payload"] = job.payload
        if job.kind == "notebook":
            result["output"] = job.output
    return result


def contest_detail(request, contest_id):
    contest, config = contest_access(request, contest_id, content=False)
    result = dict(ContestSerializer(contest).data)
    result.update({"id": str(contest.id), "now": now().isoformat(), "registered": contest.is_registered(request.user),
                   "scorePolicy": config.selection, "privatePublished": config.private_published and contest.end_time < now(),
                   "practiceEnabled": config.practice_enabled, "problems": [], "accessError": "",
                   "totalPoints": sum(AIContestProblem.objects.filter(contest=contest).values_list("points", flat=True))})
    try:
        contest_access(request, contest_id)
    except APIError as exc:
        result["accessError"] = exc.msg
    else:
        result["problems"] = [public_problem(link.problem, link.points) for link in
                              AIContestProblem.objects.filter(contest=contest).select_related("problem")]
    return result


@transaction.atomic
def save_draft(request, data):
    problem, contest, _ = problem_access(request, data, write=True)
    cells = cells_input(data.get("cells"))
    require(type(data.get("revision")) is int and data["revision"] >= 0, "Draft revision is required")
    # Serializes first creation too; a unique constraint alone cannot lock a missing draft.
    User.objects.select_for_update().get(pk=request.user.pk)
    draft, _ = AIDraft.objects.get_or_create(user=request.user, problem=problem,
                                            scope=str(contest.id) if contest else "practice")
    if draft.revision != data["revision"]:
        raise APIError("Draft changed in another window. Export your work before reloading.", "draft-conflict")
    draft.cells = cells
    draft.revision += 1
    draft.save()
    return {"cells": draft.cells, "revision": draft.revision}


@transaction.atomic
def create_job(request, data):
    problem, contest, _ = problem_access(request, data, write=True)
    kind = data.get("kind", "evaluation")
    require(kind in ("notebook", "evaluation"), "Invalid job kind")
    try:
        job_id = uuid.UUID(str(data.get("id", "")))
    except ValueError:
        raise APIError("A submission UUID is required")
    payload = {"cells": cells_input(data.get("cells")), "files": problem.public_files}
    if problem.category == "challenge" and kind == "evaluation":
        predictions = data.get("predictions")
        require(isinstance(predictions, str) and 0 < len(predictions.encode()) <= MAX_PREDICTION_BYTES
                and "\x00" not in predictions, "Upload a predictions CSV (up to 1 MiB)")
        payload["predictions"] = predictions
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    user = User.objects.select_for_update().get(pk=request.user.pk)
    require(not user.is_disabled, "Your account is disabled")
    existing = AIJob.objects.filter(pk=job_id).first()
    if existing:
        require(existing.user_id == user.id and existing.problem_id == problem.id and
                existing.contest_id == (contest.id if contest else None) and existing.kind == kind and
                existing.source_sha256 == digest, "Submission UUID has already been used")
        return existing
    AIServiceState.objects.get_or_create(pk=1)
    service = AIServiceState.objects.select_for_update().get(pk=1)
    require(not service.paused, "AI compute service is being updated. Your draft can still be saved and exported.")
    require(AIJob.objects.filter(user=user, status__in=ACTIVE).count() < 3, "Wait for your current jobs to finish")
    require(AIWorker.objects.filter(last_seen__gte=now() - timedelta(seconds=90), kinds__contains=[kind]).exists(),
            "AI compute service is offline. Your draft can still be saved and exported.")
    require(kind == "notebook" or bool(problem.judge.get("phase_id")), "Evaluation is not configured")
    # Lock against administrative time/config edits before deciding official eligibility.
    if contest:
        contest = Contest.objects.select_for_update().get(pk=contest.pk)
        problem_access(request, data, write=True)
    stamp = now()
    official = bool(kind == "evaluation" and contest and contest.start_time <= stamp <= contest.end_time
                    and not user.is_contest_admin(contest))
    return AIJob.objects.create(id=job_id, user=user, problem=problem, contest=contest, kind=kind,
                               official=official, category=problem.category, problem_version=problem.version,
                               payload=payload, source_sha256=digest, judge=problem.judge.copy())


def leaderboard(request, contest_id):
    contest, config = contest_access(request, contest_id)
    require(contest.real_time_rank or contest.end_time < now() or request.user.is_contest_admin(contest),
            "Leaderboard is hidden during this contest")
    private = config.private_published and contest.end_time < now()
    weights = dict(AIContestProblem.objects.filter(contest=contest).values_list("problem_id", "points"))
    jobs = AIJob.objects.filter(contest=contest, official=True, kind="evaluation", user__is_disabled=False).select_related("user", "problem")
    selected = {}
    for job in jobs:  # newest first: latest includes unsuccessful and unfinished submissions
        key = (job.user_id, job.problem_id)
        score = job.private_score if private and job.category == "challenge" else job.public_score
        previous = selected.get(key)
        if previous is None or (config.selection == "best" and score is not None and
                                (previous[1] is None or score > previous[1])):
            selected[key] = (job, score)
    rows = {}
    for (user_id, problem_id), (job, score) in selected.items():
        row = rows.setdefault(user_id, {"userId": user_id, "username": job.user.username, "total": 0, "scores": {}})
        points = None if score is None else round(score * weights.get(problem_id, 0) / 100, 4)
        row["scores"][job.problem.code] = {"score": points, "status": job.status, "submissionId": str(job.id)}
        row["total"] += points or 0
    result = sorted(rows.values(), key=lambda row: (-round(row["total"], 4), row["username"], row["userId"]))
    rank = 0
    last_score = None
    for index, row in enumerate(result):
        row["total"] = round(row["total"], 4)
        if last_score != row["total"]:
            rank = index + 1
        row["rank"] = rank
        last_score = row["total"]
    return {"privatePublished": private, "selection": config.selection, "results": result}
