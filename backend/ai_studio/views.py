import hmac
import os
import re
import uuid
from datetime import timedelta
from pathlib import Path

from django.db import transaction
from django.db.models import Q
from django.http import HttpResponse
from django.utils.timezone import now

from account.decorators import admin_role_required, ensure_created_by, login_required
from contest.models import Contest
from utils.api import APIError, APIView, CSRFExemptAPIView
from .contracts import ACTIVE, TERMINAL, cells_input, finite_score, judge_input, notebook_output, public_files_input, require
from .models import AIContestConfig, AIContestProblem, AIDraft, AIJob, AIProblem, AIServiceState, AIWorker
from .services import (contest_access, contest_detail, create_job, leaderboard, problem_access,
                       public_job, public_problem, save_draft)


def page(request, queryset, serialize):
    try:
        offset = max(0, int(request.GET.get("offset", 0)))
        limit = min(100, max(1, int(request.GET.get("limit", 20))))
    except ValueError:
        raise APIError("Invalid pagination")
    return {"total": queryset.count(), "results": [serialize(item) for item in queryset[offset:offset + limit]]}


class ProblemsAPI(APIView):
    def get(self, request):
        if request.GET.get("problem_id"):
            problem, contest, _ = problem_access(request, request.GET)
            result = public_problem(problem, full=True)
            if contest:
                result["points"] = AIContestProblem.objects.get(contest=contest, problem=problem).points
                result["practice"] = contest.end_time < now()
                siblings = list(AIContestProblem.objects.filter(contest=contest).values_list("problem__code", flat=True))
            else:
                siblings = list(AIProblem.objects.filter(visible=True).values_list("code", flat=True))
            position = siblings.index(problem.code)
            result["previous"] = siblings[position - 1] if position else None
            result["next"] = siblings[position + 1] if position + 1 < len(siblings) else None
            return self.success(result)
        queryset = AIProblem.objects.filter(visible=True)
        if request.GET.get("type"):
            queryset = queryset.filter(category=request.GET["type"])
        if request.GET.get("keyword"):
            queryset = queryset.filter(Q(title__icontains=request.GET["keyword"]) | Q(code__icontains=request.GET["keyword"]))
        result = page(request, queryset, public_problem)
        if request.user.is_authenticated:
            codes = [item["id"] for item in result["results"]]
            jobs = AIJob.objects.filter(user=request.user, contest=None, kind="evaluation", problem__code__in=codes)
            latest = {job.problem.code: public_job(job) for job in
                      jobs.select_related("problem", "contest").order_by("problem_id", "-created_at", "-id").distinct("problem_id")}
            for item in result["results"]:
                item["latest"] = latest.get(item["id"])
        return self.success(result)


class DraftAPI(APIView):
    @login_required
    def get(self, request):
        problem, contest, _ = problem_access(request, request.GET)
        draft = AIDraft.objects.filter(user=request.user, problem=problem,
                                       scope=str(contest.id) if contest else "practice").first()
        return self.success({"cells": draft.cells if draft else problem.cells, "revision": draft.revision if draft else 0})

    @login_required
    def put(self, request):
        return self.success(save_draft(request, request.data))


class FileAPI(APIView):
    def get(self, request):
        problem, _, _ = problem_access(request, request.GET)
        name = request.GET.get("name", "")
        require(name in problem.public_files and re.fullmatch(r"[A-Za-z0-9_-]{1,64}\.csv", name), "File does not exist")
        response = HttpResponse(problem.public_files[name], content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{name}"'
        response["X-Content-Type-Options"] = "nosniff"
        response["Cache-Control"] = "private, no-store"
        return response


class JobsAPI(APIView):
    @login_required
    def get(self, request):
        jobs = AIJob.objects.filter(user=request.user).select_related("problem", "contest")
        if request.GET.get("id"):
            try:
                job_id = uuid.UUID(request.GET["id"])
            except ValueError:
                raise APIError("Invalid submission ID")
            job = jobs.filter(pk=job_id).first()
            require(job is not None, "Submission does not exist")
            return self.success(public_job(job, detail=True))
        jobs = jobs.filter(kind="evaluation")
        if request.GET.get("problem_id"):
            jobs = jobs.filter(problem__code=request.GET["problem_id"])
        if "contest_id" in request.GET:
            scope = request.GET["contest_id"]
            require(not scope or scope.isdigit(), "Invalid contest")
            jobs = jobs.filter(contest_id=scope or None)
        if request.GET.get("latest_per_problem") == "1":
            jobs = jobs.order_by("problem_id", "-created_at", "-id").distinct("problem_id")
        return self.success(page(request, jobs, public_job))

    @login_required
    def post(self, request):
        return self.success(public_job(create_job(request, request.data), detail=True))


class CompletedAPI(APIView):
    @login_required
    def get(self, request):
        # Query the complete successful history, independent of the recent-submission page.
        jobs = AIJob.objects.filter(user=request.user, kind="evaluation", status__in=("ACCEPTED", "SCORED"))
        jobs = jobs.select_related("problem", "contest").order_by("problem_id", "-created_at", "-id").distinct("problem_id")
        records = sorted((public_job(job) for job in jobs), key=lambda item: (item["createdAt"], item["id"]), reverse=True)
        return self.success(records)


class AIContestAPI(APIView):
    def get(self, request):
        return self.success(contest_detail(request, request.GET.get("contest_id")))


class LeaderboardAPI(APIView):
    @login_required
    def get(self, request):
        return self.success(leaderboard(request, request.GET.get("contest_id")))


class HealthAPI(APIView):
    def get(self, request):
        kinds = set()
        if not AIServiceState.objects.filter(pk=1, paused=True).exists():
            for worker in AIWorker.objects.filter(last_seen__gte=now() - timedelta(seconds=90)):
                kinds.update(worker.kinds)
        return self.success({"notebook": "notebook" in kinds, "evaluation": "evaluation" in kinds})


class ProblemAdminAPI(APIView):
    @admin_role_required
    def get(self, request):
        problems = AIProblem.objects.all()
        if not request.user.is_super_admin():
            problems = problems.filter(created_by=request.user)
        def serialize(problem):
            result = public_problem(problem, full=True)
            result.update({"visible": problem.visible, "judge": problem.judge, "public_files": problem.public_files})
            return result
        return self.success(page(request, problems, serialize))

    @admin_role_required
    @transaction.atomic
    def post(self, request):
        data = request.data
        require(isinstance(data.get("id"), str) and re.fullmatch(r"[A-Za-z0-9_-]{1,32}", data["id"]), "Invalid problem code")
        require(isinstance(data.get("title"), str) and 1 <= len(data["title"].strip()) <= 128, "Invalid title")
        require(data.get("type") in ("logic", "model", "challenge"), "Invalid problem type")
        require(type(data.get("visible")) is bool, "visible is required")
        require(isinstance(data.get("metric", "Score"), str) and len(data.get("metric", "Score")) <= 64, "Invalid metric")
        require(type(data.get("points", 100)) is int and 1 <= data.get("points", 100) <= 10000, "Invalid points")
        cells = cells_input(data.get("cells"))
        judge = judge_input(data.get("judge"))
        public_files = public_files_input(data.get("public_files", {}))
        statement = {}
        for key in ("objective", "signature", "data", "evaluation"):
            value = data.get(key, "")
            require(isinstance(value, str) and len(value) <= 32000, "Invalid statement")
            statement[key] = value
        requirements = data.get("requirements", [])
        require(isinstance(requirements, list) and len(requirements) <= 50 and
                all(isinstance(item, str) and len(item) <= 2000 for item in requirements), "Invalid requirements")
        statement["requirements"] = requirements
        problem = AIProblem.objects.select_for_update().filter(code=data["id"]).first()
        if problem:
            ensure_created_by(problem, request.user)
            require(data.get("version") == problem.version, "Problem has changed; reload before saving")
            require(not AIContestProblem.objects.filter(problem=problem, contest__start_time__lte=now(),
                                                       contest__end_time__gte=now()).exists(), "Cannot edit a problem during its contest")
            problem.version += 1
        else:
            problem = AIProblem(code=data["id"], created_by=request.user)
        problem.title = data["title"].strip()
        problem.category = data["type"]
        problem.visible = data["visible"]
        problem.metric = data.get("metric", "Score")
        problem.points = data.get("points", 100)
        problem.statement = statement
        problem.cells = cells
        problem.judge = judge
        problem.public_files = public_files
        problem.save()
        return self.success({"id": problem.code, "version": problem.version})


class ContestAdminAPI(APIView):
    @admin_role_required
    def get(self, request):
        contest = self.contest(request, request.GET)
        config = AIContestConfig.objects.filter(contest=contest).first()
        return self.success({"selection": config.selection if config else "latest",
                             "private_published": bool(config and config.private_published),
                             "practice_enabled": config.practice_enabled if config else True,
                             "problems": [{"id": link.problem.code, "points": link.points} for link in
                                          AIContestProblem.objects.filter(contest=contest).select_related("problem")]})

    def contest(self, request, data):
        require(str(data.get("contest_id", "")).isdigit(), "Invalid contest")
        contest = Contest.objects.filter(pk=data["contest_id"], rule_type="AI").first()
        require(contest is not None, "AI contest does not exist")
        ensure_created_by(contest, request.user)
        return contest

    @admin_role_required
    @transaction.atomic
    def put(self, request):
        data = request.data
        contest = self.contest(request, data)
        contest = Contest.objects.select_for_update().get(pk=contest.pk)
        config, _ = AIContestConfig.objects.get_or_create(contest=contest)
        require(data.get("selection") in ("latest", "best"), "Invalid selection policy")
        require(type(data.get("private_published")) is bool and type(data.get("practice_enabled")) is bool, "Invalid publication settings")
        require(not data["private_published"] or contest.end_time < now(), "Private scores cannot be published before the contest ends")
        links = data.get("problems")
        require(isinstance(links, list) and 1 <= len(links) <= 50, "Select 1–50 problems")
        normalized = []
        for link in links:
            require(isinstance(link, dict) and type(link.get("points")) is int and 1 <= link["points"] <= 10000, "Invalid problem points")
            problem = AIProblem.objects.filter(code=link.get("id")).first()
            require(problem is not None, "AI problem does not exist")
            require(problem.visible or request.user.is_super_admin() or problem.created_by_id == request.user.id, "Problem is not available")
            normalized.append((problem.id, link["points"]))
        require(len({item[0] for item in normalized}) == len(normalized), "Duplicate problem")
        current = list(AIContestProblem.objects.filter(contest=contest).values_list("problem_id", "points"))
        frozen = contest.start_time <= now() or AIJob.objects.filter(contest=contest, official=True).exists()
        require(not frozen or (normalized == current and config.selection == data["selection"]),
                "Problems, weights and score policy are frozen after the contest starts")
        if normalized != current:
            AIContestProblem.objects.filter(contest=contest).delete()
            AIContestProblem.objects.bulk_create([AIContestProblem(contest=contest, problem_id=pk, points=points, position=index)
                                                 for index, (pk, points) in enumerate(normalized)])
        config.selection = data["selection"]
        config.private_published = data["private_published"]
        config.practice_enabled = data["practice_enabled"]
        config.save()
        return self.success()


class WorkerAPI(CSRFExemptAPIView):
    """Machine endpoint; browser sessions and APPKEY cannot authorize a compute worker."""
    def post(self, request):
        path = os.environ.get("AI_WORKER_TOKEN_FILE", "")
        try:
            expected = Path(path).read_text().strip() if path else ""
        except OSError:
            expected = ""
        supplied = request.META.get("HTTP_AUTHORIZATION", "")
        require(len(expected) >= 32 and hmac.compare_digest(supplied, "Bearer " + expected), "Invalid worker token")
        data = request.data
        require(isinstance(data, dict), "Invalid worker request")
        if data.get("action") == "service":
            require(data.get("operation") in ("pause", "resume", "status"), "Invalid service operation")
            with transaction.atomic():
                AIServiceState.objects.get_or_create(pk=1)
                service = AIServiceState.objects.select_for_update().get(pk=1)
                if data["operation"] != "status":
                    service.paused = data["operation"] == "pause"
                    service.save(update_fields=["paused"])
                return self.success({"paused": service.paused, "active": AIJob.objects.filter(status__in=ACTIVE).count()})
        worker = data.get("worker", "")
        require(isinstance(worker, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", worker), "Invalid worker name")
        kinds = data.get("kinds", [])
        require(isinstance(kinds, list) and kinds and not set(kinds) - {"notebook", "evaluation"}, "Invalid worker capabilities")
        AIWorker.objects.update_or_create(name=worker, defaults={"kinds": kinds, "last_seen": now()})
        if data.get("action") == "claim":
            return self.success(self.claim(worker, kinds))
        require(data.get("action") in ("heartbeat", "finish"), "Invalid worker action")
        try:
            job_id, lease = uuid.UUID(data["id"]), uuid.UUID(data["lease"])
        except (KeyError, ValueError, TypeError):
            raise APIError("Invalid lease")
        with transaction.atomic():
            job = AIJob.objects.select_for_update().filter(pk=job_id, lease=lease, worker=worker).first()
            require(job is not None, "Lease has been replaced")
            if job.status not in ACTIVE:
                require(data["action"] == "finish", "Job has finished")
                return self.success({"finished": True})  # identical lease's result retry is harmless
            require(job.lease_until and job.lease_until > now(), "Lease has expired")
            if data.get("remote_id") is not None:
                require(type(data["remote_id"]) is int and data["remote_id"] > 0, "Invalid remote ID")
                require(job.remote_id in (None, data["remote_id"]), "Remote ID cannot change")
                job.remote_id = data["remote_id"]
            if data.get("dispatch_started") is True:
                job.dispatch_started = True
            if data["action"] == "finish":
                self.finish(job, data)
            else:
                job.lease_until = now() + timedelta(seconds=90)
            job.save()
        return self.success({"finished": job.status not in ACTIVE})

    @transaction.atomic
    def claim(self, worker, kinds):
        jobs = AIJob.objects.select_for_update(skip_locked=True).filter(kind__in=kinds, status__in=ACTIVE)
        job = jobs.filter(Q(status="PENDING") | Q(lease_until__lt=now())).order_by("created_at", "id").first()
        if not job:
            return None
        if job.attempts >= 3 or job.user.is_disabled:
            job.status = "SYSTEM_ERROR" if job.attempts >= 3 else "CANCELLED"
            job.message = "计算节点中断，请重新提交。" if job.attempts >= 3 else "账号已停用。"
            job.finished_at = now()
            job.save()
            return None
        job.worker = worker
        job.lease = uuid.uuid4()
        job.lease_until = now() + timedelta(seconds=90)
        job.attempts += 1
        job.status = "RUNNING" if job.kind == "notebook" else {
            "logic": "JUDGING", "model": "TRAINING", "challenge": "SCORING"
        }[job.category]
        job.save()
        return {"id": str(job.id), "lease": str(job.lease), "kind": job.kind, "category": job.category,
                "payload": job.payload, "judge": job.judge, "remote_id": job.remote_id,
                "dispatch_started": job.dispatch_started}

    def finish(self, job, data):
        status = data.get("status")
        require(status in TERMINAL, "Invalid terminal status")
        errors = ("RUNTIME_ERROR", "TIME_LIMIT", "MEMORY_LIMIT", "SYSTEM_ERROR", "CANCELLED")
        if job.kind == "notebook":
            require(status in errors + ("SUCCEEDED",), "Invalid notebook status")
            job.output = notebook_output(data.get("output", {}))
        else:
            require(status in errors + ("SCORED",), "Evaluation must provide trusted scores or an error")
            if status == "SCORED":
                job.public_score = finite_score(data.get("public_score"))
                if data.get("private_score") is not None:
                    job.private_score = finite_score(data["private_score"])
                if job.judge.get("private_column"):
                    require(job.private_score is not None, "Private score is missing")
                if data.get("accuracy") is not None:
                    job.accuracy = finite_score(data["accuracy"], 1)
                if job.category != "challenge":
                    status = "ACCEPTED" if job.public_score >= job.judge.get("pass_score", 100) else "WRONG_ANSWER"
                    if status == "WRONG_ANSWER" and job.category == "logic" and job.public_score > 0:
                        status = "PARTIAL"
        job.status = status
        # Never return scoring-container logs: they can include hidden answers.
        job.message = {"RUNTIME_ERROR": "运行失败，请检查代码或提交格式。", "TIME_LIMIT": "运行超时。",
                       "MEMORY_LIMIT": "内存超限。", "SYSTEM_ERROR": "评测服务异常，请联系管理员。"}.get(status, "")
        job.finished_at = now()
        job.lease_until = None
