import hashlib
import ipaddress
import json
import uuid
from datetime import timedelta

from django.db import transaction
from django.db.models import Q
from django.utils.timezone import now

from account.models import UserProfile, User
from contest.models import Contest
from contest.serializers import ContestSerializer
from utils.api import APIError
from utils.constants import ContestRuleType, ContestStatus
from .contracts import ACTIVE, MAX_PREDICTION_BYTES, cells_input, require
from .models import AIContestConfig, AIContestProblem, AIDraft, AIJob, AIProblem, AIServiceState, AIWorker
from .quiz import answers_input, grade, manual_input, review_ceiling, text_questions


def contest_access(request, contest_id, *, content=True, write=False):
    require(str(contest_id).isdigit(), "Invalid contest")
    contest = Contest.objects.public().filter(pk=contest_id, rule_type=ContestRuleType.AI).first()
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
                       for key in ("objective", "requirements", "signature", "inputSpec", "outputSpec", "data", "evaluation")})
        result["cells"] = problem.cells
        result["files"] = list(problem.public_files)
        if problem.category == "quiz":
            # The card and its images are public; the answer key stays in judge.
            result.update(quiz=problem.statement.get("quiz", {}), media=problem.statement.get("media", {}),
                          maxAttempts=problem.judge.get("max_attempts"))
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
                   "scorePolicy": config.selection, "ranking": config.ranking, "privatePublished": config.private_published and contest.end_time < now(),
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
    quiz = problem.category == "quiz"
    # A quiz draft stores the answer object in the same JSON column instead of code cells.
    content = answers_input(problem.statement.get("quiz", {}), data.get("answers")) if quiz else cells_input(data.get("cells"))
    require(type(data.get("revision")) is int and data["revision"] >= 0, "Draft revision is required")
    # Serializes first creation too; a unique constraint alone cannot lock a missing draft.
    User.objects.select_for_update().get(pk=request.user.pk)
    draft, _ = AIDraft.objects.get_or_create(user=request.user, problem=problem,
                                            scope=str(contest.id) if contest else "practice")
    if draft.revision != data["revision"]:
        raise APIError("Draft changed in another window. Export your work before reloading.", "draft-conflict")
    draft.cells = content
    draft.revision += 1
    draft.save()
    return {"answers" if quiz else "cells": draft.cells, "revision": draft.revision}


def quiz_attempts(user, problem, contest):
    return AIJob.objects.filter(user=user, problem=problem, contest=contest, kind="evaluation", official=True).count()


def create_quiz_job(request, data, problem, contest, job_id):
    """Grade an answer card synchronously; no compute worker or admission gate is involved."""
    require(data.get("kind", "evaluation") == "evaluation", "模型理解题无需运行代码")
    payload = {"answers": answers_input(problem.statement.get("quiz", {}), data.get("answers"))}
    digest = hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False).encode()).hexdigest()
    user = User.objects.select_for_update().get(pk=request.user.pk)
    require(not user.is_disabled, "Your account is disabled")
    existing = AIJob.objects.filter(pk=job_id).first()
    if existing:
        require(existing.user_id == user.id and existing.problem_id == problem.id and
                existing.contest_id == (contest.id if contest else None) and existing.kind == "evaluation" and
                existing.source_sha256 == digest, "Submission UUID has already been used")
        return existing
    require(bool(problem.judge.get("answers")), "Evaluation is not configured")
    if contest:
        contest = Contest.objects.select_for_update().get(pk=contest.pk)
        problem_access(request, data, write=True)
    stamp = now()
    official = bool(contest and contest.start_time <= stamp <= contest.end_time and not user.is_contest_admin(contest))
    limit = problem.judge.get("max_attempts")
    if official and limit:
        # The user row lock above serializes this count against concurrent submissions.
        require(quiz_attempts(user, problem, contest) < limit, f"本题在比赛中最多提交 {limit} 次")
    quiz, key, pass_score = problem.statement["quiz"], problem.judge["answers"], problem.judge.get("pass_score", 100)
    fields = {"status": quiz_status(grade(quiz, key, payload["answers"]), pass_score),
              "public_score": grade(quiz, key, payload["answers"]), "finished_at": stamp}
    ranking = AIContestConfig.objects.filter(contest=contest).values_list("ranking", flat=True).first() if contest else None
    answered = any(payload["answers"][q["id"]] for q in text_questions(quiz))
    if answered and (ranking in ("oi", "score") or review_ceiling(quiz, key, payload["answers"]) >= pass_score):
        # Every point counts on a points board; under ACM only a card that can still pass waits
        # for a teacher. A newer card replaces an unreviewed one.
        fields = {"status": "REVIEWING", "public_score": None, "finished_at": None, "message": "客观题已判分，主观题待老师评阅。"}
        AIJob.objects.filter(user=user, problem=problem, contest=contest, kind="evaluation", status="REVIEWING").update(
            status="SUPERSEDED", finished_at=stamp, message="已被新的提交替代，未评阅。")
    return AIJob.objects.create(id=job_id, user=user, problem=problem, contest=contest, kind="evaluation",
                               official=official, category="quiz", problem_version=problem.version,
                               payload=payload, source_sha256=digest, judge=problem.judge.copy(), **fields)


def quiz_status(score, pass_score):
    return "ACCEPTED" if score >= pass_score else "PARTIAL" if score > 0 else "WRONG_ANSWER"


def reviewable_jobs(user):
    """Quiz submissions this admin may score: own or All-permission problems, or contests they administer."""
    jobs = AIJob.objects.filter(category="quiz", kind="evaluation").select_related("problem", "contest", "user", "user__userprofile")
    if user.is_super_admin():
        return jobs
    owned = Q(problem__created_by=user) | Q(contest__created_by=user)
    return jobs if user.can_mgmt_all_problem() else jobs.filter(owned)


def review_item(job):
    quiz, key = job.problem.statement.get("quiz", {}), job.judge.get("answers", {})
    return {"id": str(job.id), "problemId": job.problem.code, "title": job.problem.title, "username": job.user.username,
            "realName": getattr(getattr(job.user, "userprofile", None), "real_name", None),
            "contestId": job.contest_id, "official": job.official, "createdAt": job.created_at.isoformat(),
            "status": job.status, "publicScore": job.public_score, "review": job.output.get("review"),
            "objectiveScore": grade(quiz, key, job.payload["answers"]),
            "questions": [{"id": q["id"], "prompt": q["prompt"], "points": q["points"], "rubric": key[q["id"]]["rubric"],
                           "answer": job.payload["answers"].get(q["id"])} for q in text_questions(quiz)]}


@transaction.atomic
def review_job(user, data):
    try:
        job_id = uuid.UUID(str(data.get("id", "")))
    except ValueError:
        raise APIError("Invalid submission ID")
    job = reviewable_jobs(user).select_for_update(of=("self",)).filter(pk=job_id).first()
    require(job is not None, "提交不存在或无评阅权限")
    quiz, key = job.problem.statement["quiz"], job.judge["answers"]
    # Pending cards, and decided cards with answered essays (a teacher may score or rescore them).
    require(job.status == "REVIEWING" or (job.status in ("ACCEPTED", "PARTIAL", "WRONG_ANSWER") and
            any(job.payload["answers"].get(q["id"]) for q in text_questions(quiz))), "该提交不在可评阅状态")
    manual = manual_input(quiz, job.payload["answers"], data.get("scores"))
    job.public_score = grade(quiz, key, job.payload["answers"], manual)
    job.status = quiz_status(job.public_score, job.judge.get("pass_score", 100))
    job.output = {**job.output, "review": {"scores": manual, "reviewer": user.username, "at": now().isoformat()}}
    job.message = ""
    job.finished_at = now()
    job.save()
    return job


@transaction.atomic
def create_job(request, data):
    problem, contest, _ = problem_access(request, data, write=True)
    kind = data.get("kind", "evaluation")
    require(kind in ("notebook", "evaluation"), "Invalid job kind")
    try:
        job_id = uuid.UUID(str(data.get("id", "")))
    except ValueError:
        raise APIError("A submission UUID is required")
    if problem.category == "quiz":
        return create_quiz_job(request, data, problem, contest, job_id)
    payload = {"cells": cells_input(data.get("cells")), "files": problem.public_files}
    if kind == "notebook" and "kernel" in data:
        try:
            kernel = str(uuid.UUID(str(data["kernel"])))
        except (ValueError, TypeError):
            raise APIError("Invalid Notebook session")
        cell_index = data.get("cell_index")
        require(cell_index is None or (type(cell_index) is int and 0 <= cell_index < len(payload["cells"])),
                "Invalid cell index")
        generation = data.get("kernel_generation", "")
        require(isinstance(generation, str) and (not generation or (len(generation) == 32 and
                all(char in "0123456789abcdef" for char in generation))), "Invalid kernel generation")
        # Never let a browser-chosen UUID attach to another user's or contest's kernel.
        identity = [request.user.pk, problem.pk, problem.version, contest.pk if contest else None, kernel]
        payload.update(kernel_id=hashlib.sha256(json.dumps(identity).encode()).hexdigest(),
                       kernel_generation=generation, cell_index=cell_index)
    else:
        require("cell_index" not in data, "Single-cell execution requires a Notebook session")
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
    if payload.get("kernel_id"):
        require(not AIJob.objects.filter(user=user, kind="notebook", status__in=ACTIVE,
                                         payload__kernel_id=payload["kernel_id"]).exists(), "This Notebook is already running")
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


def select_scores(jobs, selection, private):
    selected = {}
    for job in jobs:  # newest first: latest includes unsuccessful and unfinished submissions
        key = (job.user_id, job.problem_id)
        score = job.private_score if private and job.category == "challenge" else job.public_score
        previous = selected.get(key)
        if previous is None or (selection == "best" and score is not None and
                                (previous[1] is None or score > previous[1])):
            selected[key] = (job, score)
    return selected


def problem_leaderboard(request, data):
    problem, contest, config = problem_access(request, data)
    private = bool(contest and config.private_published and contest.end_time < now())
    jobs = AIJob.objects.filter(problem=problem, contest=contest, kind="evaluation", user__is_disabled=False)
    selection = config.selection if contest else "best"
    if contest:
        require(contest.real_time_rank or contest.end_time < now() or request.user.is_contest_admin(contest),
                "Leaderboard is hidden during this contest")
        jobs = jobs.filter(official=True)
    else:
        # Practice never mixes contest submissions or scores from a changed judge contract.
        jobs = jobs.filter(problem_version=problem.version, public_score__isnull=False)
    selected = select_scores(jobs.select_related("user"), selection, private)
    rows = [{"userId": job.user_id, "username": job.user.username, "score": score,
             "record": {"type": job.category, "status": job.status, "accuracy": job.accuracy,
                        "publicScore": job.public_score, "privateScore": job.private_score if private else None,
                        "privatePublished": private}} for job, score in selected.values()]
    rows.sort(key=lambda row: (-round(row["score"] or 0, 4), row["username"], row["userId"]))
    last_score, rank = None, 0
    for index, row in enumerate(rows):
        score = round(row["score"] or 0, 4)
        if index == 0 or score != last_score:
            rank = index + 1
        row["rank"], last_score = rank, score
    return {"privatePublished": private, "selection": selection, "results": rows}


ACM_PENALTY_SECONDS = 20 * 60
# Platform failures and unreviewed, replaced quiz cards never cost penalty time.
ACM_IGNORED = ("SYSTEM_ERROR", "CANCELLED", "SUPERSEDED")


def acm_leaderboard(contest, jobs):
    rows = {}
    for job in jobs.order_by("created_at", "id"):
        row = rows.setdefault(job.user_id, {"userId": job.user_id, "username": job.user.username,
                                            "solved": 0, "penalty": 0, "scores": {}})
        cell = row["scores"].setdefault(job.problem.code, {"accepted": False, "tries": 0, "time": None, "pending": 0,
                                                            "status": None, "submissionId": None, "pendingId": None})
        if cell["accepted"] or job.status in ACM_IGNORED:
            continue
        if job.status in ACTIVE or job.status == "REVIEWING":
            cell["pending"] += 1
            cell["pendingId"] = str(job.id)
            continue
        cell["status"], cell["submissionId"] = job.status, str(job.id)
        if job.status == "ACCEPTED":
            cell["accepted"] = True
            cell["time"] = max(0, int((job.created_at - contest.start_time).total_seconds()))
            row["solved"] += 1
            row["penalty"] += cell["time"] + ACM_PENALTY_SECONDS * cell["tries"]
        else:
            cell["tries"] += 1
    result = sorted(rows.values(), key=lambda row: (-row["solved"], row["penalty"], row["username"], row["userId"]))
    for index, row in enumerate(result):
        same = index and (row["solved"], row["penalty"]) == (result[index - 1]["solved"], result[index - 1]["penalty"])
        row["rank"] = result[index - 1]["rank"] if same else index + 1
    return result


def oi_leaderboard(contest, jobs, weights, private):
    """Best weighted points per problem; ties by penalty = sum of the times at which each
    problem's best (non-zero) score was first reached."""
    rows = {}
    for job in jobs.order_by("created_at", "id"):
        row = rows.setdefault(job.user_id, {"userId": job.user_id, "username": job.user.username,
                                            "total": 0, "penalty": 0, "scores": {}})
        cell = row["scores"].setdefault(job.problem.code, {"score": None, "time": None, "tries": 0, "pending": 0,
                                                            "status": None, "submissionId": None, "pendingId": None, "penalty": 0})
        if job.status in ACM_IGNORED:
            continue
        if job.status in ACTIVE or job.status == "REVIEWING":
            cell["pending"] += 1
            cell["pendingId"] = str(job.id)
            continue
        raw = job.private_score if private and job.private_score is not None else job.public_score
        points = None if raw is None else round(raw * weights.get(job.problem_id, 0) / 100, 4)
        if points is not None and points > (cell["score"] or 0):
            cell.update(score=points, status=job.status, submissionId=str(job.id),
                        time=max(0, int((job.created_at - contest.start_time).total_seconds())))
            cell["penalty"] = cell["time"]
        elif cell["score"] is None:
            cell.update(score=points, status=job.status, submissionId=str(job.id),
                        time=max(0, int((job.created_at - contest.start_time).total_seconds())))
        cell["tries"] += 1
    for row in rows.values():
        row["total"] = round(sum(cell["score"] or 0 for cell in row["scores"].values()), 4)
        row["penalty"] = sum(cell["penalty"] for cell in row["scores"].values() if cell["score"])
    result = sorted(rows.values(), key=lambda row: (-row["total"], row["penalty"], row["username"], row["userId"]))
    for index, row in enumerate(result):
        same = index and (row["total"], row["penalty"]) == (result[index - 1]["total"], result[index - 1]["penalty"])
        row["rank"] = result[index - 1]["rank"] if same else index + 1
    return result


def leaderboard(request, contest_id):
    contest, config = contest_access(request, contest_id)
    require(contest.real_time_rank or contest.end_time < now() or request.user.is_contest_admin(contest),
            "Leaderboard is hidden during this contest")
    private = config.private_published and contest.end_time < now()
    weights = dict(AIContestProblem.objects.filter(contest=contest).values_list("problem_id", "points"))
    jobs = AIJob.objects.filter(contest=contest, official=True, kind="evaluation", user__is_disabled=False).select_related("user", "problem")
    if config.ranking in ("acm", "oi"):
        results = acm_leaderboard(contest, jobs) if config.ranking == "acm" else oi_leaderboard(contest, jobs, weights, private)
        if request.user.is_contest_admin(contest):
            # Like the ACM rank, real names are shown to the contest's admins only.
            names = dict(UserProfile.objects.filter(user_id__in=[row["userId"] for row in results]).values_list("user_id", "real_name"))
            for row in results:
                row["realName"] = names.get(row["userId"]) or ""
        return {"privatePublished": private, "selection": "best" if config.ranking == "oi" else config.selection,
                "ranking": config.ranking, "results": results}
    selected = select_scores(jobs, config.selection, private)
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
    return {"privatePublished": private, "selection": config.selection, "ranking": "score", "results": result}
