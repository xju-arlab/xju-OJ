import json
import os
import tempfile
import uuid
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.utils.timezone import now
from rest_framework.test import APIClient

from contest.models import Contest, ContestParticipation, OIContestRank
from utils.api.tests import APITestCase
from .models import AIContestConfig, AIContestProblem, AIDraft, AIJob, AIProblem, AIWorker


class AIStudioTests(APITestCase):
    def setUp(self):
        self.admin = self.create_super_admin(login=False)
        self.user = self.create_user("student", "student")
        self.problem = AIProblem.objects.create(code="AI001", title="Stable softmax", category="logic",
                                               cells=["print(1)"], visible=True, created_by=self.admin,
                                               judge={"phase_id": 1, "public_column": "score", "pass_score": 100})
        self.contest = Contest.objects.create(title="AI assessment", description="", rule_type="AI",
                                             start_time=now() - timedelta(minutes=5), end_time=now() + timedelta(minutes=15),
                                             password="exam", real_time_rank=True, visible=True, created_by=self.admin)
        self.config = AIContestConfig.objects.create(contest=self.contest)
        AIContestProblem.objects.create(contest=self.contest, problem=self.problem, position=0, points=20)
        AIWorker.objects.create(name="test-worker", kinds=["notebook", "evaluation"], last_seen=now())
        self.token = "x" * 48
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        token_path = Path(self.temp.name) / "token"
        token_path.write_text(self.token)
        env = patch.dict(os.environ, {"AI_WORKER_TOKEN_FILE": str(token_path)})
        env.start()
        self.addCleanup(env.stop)

    def post(self, path, data):
        return self.client.post("/api/ai/" + path, data, format="json")

    def submit(self, **values):
        data = {"id": str(uuid.uuid4()), "problem_id": self.problem.code, "cells": ["print(1)"], **values}
        return self.post("jobs", data)

    def register(self):
        result = self.client.post("/api/contest/register", {"contest_id": self.contest.id, "password": "exam"}, format="json")
        self.assertSuccess(result)

    def claim(self):
        result = self.worker("claim")
        self.assertSuccess(result)
        return result.data["data"]

    def worker(self, action, **values):
        return self.client.post("/api/ai/worker", {"action": action, "worker": "test-worker",
                                                 "kinds": ["notebook", "evaluation"], **values}, format="json",
                                HTTP_AUTHORIZATION="Bearer " + self.token)

    def finish(self, claim, **values):
        result = self.worker("finish", id=claim["id"], lease=claim["lease"], status="SCORED", public_score=100, **values)
        self.assertSuccess(result)

    def test_public_statement_excludes_judge_and_hidden_problems(self):
        self.client.logout()
        result = self.client.get("/api/ai/problems", {"problem_id": self.problem.code})
        self.assertSuccess(result)
        self.assertNotIn("judge", result.data["data"])
        self.problem.visible = False
        self.problem.save()
        self.assertFailed(self.client.get("/api/ai/problems", {"problem_id": self.problem.code}))
        self.assertEqual(self.client.get("/api/ai/problems").data["data"]["total"], 0)

    def test_password_registration_and_no_oi_rank(self):
        self.assertFailed(self.submit(contest_id=self.contest.id))
        self.register()
        self.assertTrue(ContestParticipation.objects.filter(contest=self.contest, user=self.user).exists())
        self.assertFalse(OIContestRank.objects.filter(contest=self.contest).exists())
        result = self.submit(contest_id=self.contest.id)
        self.assertSuccess(result)
        self.assertTrue(result.data["data"]["official"])
        self.assertFailed(self.client.get("/api/contest_rank", {"contest_id": self.contest.id}))

    def test_before_start_content_and_submission_hidden(self):
        self.register()
        self.contest.start_time = now() + timedelta(minutes=1)
        self.contest.save()
        result = self.client.get("/api/ai/contest", {"contest_id": self.contest.id})
        self.assertSuccess(result)
        self.assertEqual(result.data["data"]["problems"], [])
        self.assertFailed(self.submit(contest_id=self.contest.id))

    def test_venue_ip_restriction_and_post_contest_practice(self):
        self.register()
        self.contest.allowed_ip_ranges = ["10.0.0.0/24"]
        self.contest.save()
        self.assertFailed(self.submit(contest_id=self.contest.id))
        self.contest.end_time = now() - timedelta(seconds=1)
        self.contest.save()
        ContestParticipation.objects.all().delete()
        result = self.submit(contest_id=self.contest.id)
        self.assertSuccess(result)
        self.assertFalse(result.data["data"]["official"])
        self.finish(self.claim())
        board = self.client.get("/api/ai/leaderboard", {"contest_id": self.contest.id}).data["data"]
        self.assertEqual(board["results"], [])

    def test_official_result_finishing_after_end_counts(self):
        self.register()
        self.assertSuccess(self.submit(contest_id=self.contest.id))
        claim = self.claim()
        self.contest.end_time = now() - timedelta(seconds=1)
        self.contest.save()
        self.finish(claim)
        board = self.client.get("/api/ai/leaderboard", {"contest_id": self.contest.id}).data["data"]
        self.assertEqual(board["results"][0]["total"], 20)

    def test_private_zero_score_never_leaks_before_publication(self):
        self.register()
        self.problem.category = "challenge"
        self.problem.judge["private_column"] = "private"
        self.problem.save()
        created = self.submit(contest_id=self.contest.id, predictions="id,value\n1,0\n")
        self.assertSuccess(created)
        claim = self.claim()
        result = self.worker("finish", id=claim["id"], lease=claim["lease"], status="SCORED", public_score=0, private_score=97)
        self.assertSuccess(result)
        detail = self.client.get("/api/ai/jobs", {"id": claim["id"]}).data["data"]
        self.assertEqual(detail["publicScore"], 0)
        self.assertIsNone(detail["privateScore"])
        self.assertNotIn("output", detail)
        self.assertNotIn("judge", detail)
        self.assertEqual(len(self.client.get("/api/ai/completed").data["data"]), 1)
        self.config.private_published = True
        self.config.save()
        self.assertIsNone(self.client.get("/api/ai/jobs", {"id": claim["id"]}).data["data"]["privateScore"])
        self.contest.end_time = now() - timedelta(seconds=1)
        self.contest.save()
        self.assertEqual(self.client.get("/api/ai/jobs", {"id": claim["id"]}).data["data"]["privateScore"], 97)

    def test_draft_cas_scope_and_user_isolation(self):
        self.register()
        data = {"problem_id": self.problem.code, "cells": ["answer = 2"], "revision": 0}
        self.assertSuccess(self.client.put("/api/ai/draft", data, format="json"))
        self.assertFailed(self.client.put("/api/ai/draft", data, format="json"))
        self.assertSuccess(self.client.put("/api/ai/draft", {**data, "contest_id": self.contest.id}, format="json"))
        self.assertEqual(AIDraft.objects.count(), 2)
        self.create_user("another", "another")
        draft = self.client.get("/api/ai/draft", {"problem_id": self.problem.code}).data["data"]
        self.assertEqual(draft, {"cells": ["print(1)"], "revision": 0})

    def test_submission_idempotency_and_immutable_snapshot(self):
        job_id = str(uuid.uuid4())
        self.assertSuccess(self.submit(id=job_id))
        AIWorker.objects.all().delete()
        self.assertSuccess(self.submit(id=job_id))
        self.assertEqual(AIJob.objects.count(), 1)
        self.assertFailed(self.submit(id=job_id, cells=["changed"]))
        self.problem.judge["phase_id"] = 2
        self.problem.save()
        self.assertEqual(AIJob.objects.get().judge["phase_id"], 1)

    def test_service_pause_drains_existing_jobs_and_preserves_drafts(self):
        created = self.submit().data["data"]
        paused = self.worker("service", operation="pause")
        self.assertEqual(paused.data["data"], {"paused": True, "active": 1})
        self.assertFailed(self.submit())
        self.assertSuccess(self.submit(id=created["id"]))
        self.assertSuccess(self.client.put("/api/ai/draft", {"problem_id": self.problem.code,
                                                            "cells": ["saved"], "revision": 0}, format="json"))
        self.finish(self.claim())
        self.assertEqual(self.worker("service", operation="status").data["data"]["active"], 0)
        self.assertEqual(self.client.get("/api/ai/health").data["data"], {"notebook": False, "evaluation": False})
        self.assertSuccess(self.worker("service", operation="resume"))
        self.assertSuccess(self.submit())

    def test_latest_problem_status_does_not_depend_on_recent_history_page(self):
        first = self.submit().data["data"]
        self.finish(self.claim())
        another = AIProblem.objects.create(code="AI002", title="Other", category="logic", visible=True,
                                           cells=["print(1)"], created_by=self.admin, judge=self.problem.judge)
        for _ in range(22):
            AIJob.objects.create(user=self.user, problem=another, category="logic", problem_version=1,
                                 kind="evaluation", status="WRONG_ANSWER", source_sha256="x")
        result = self.client.get("/api/ai/problems").data["data"]["results"]
        self.assertEqual(result[0]["latest"]["id"], first["id"])
        self.assertEqual(result[0]["latest"]["status"], "ACCEPTED")

    def test_logic_partial_score_and_public_files_snapshot(self):
        self.problem.public_files = {"train.csv": "id,value\n1,2\n"}
        self.problem.save()
        created = self.submit().data["data"]
        self.assertEqual(created["payload"]["files"]["train.csv"], "id,value\n1,2\n")
        claim = self.claim()
        self.assertSuccess(self.worker("finish", id=claim["id"], lease=claim["lease"], status="SCORED", public_score=50))
        self.assertEqual(AIJob.objects.get(pk=created["id"]).status, "PARTIAL")
        self.assertEqual(self.client.get("/api/ai/file", {"problem_id": self.problem.code, "name": "train.csv"}).content,
                         b"id,value\n1,2\n")
        self.problem.visible = False
        self.problem.save()
        self.assertFailed(self.client.get("/api/ai/file", {"problem_id": self.problem.code, "name": "train.csv"}))

    def test_other_user_cannot_read_job_or_reuse_id(self):
        result = self.submit()
        job_id = result.data["data"]["id"]
        self.create_user("another", "another")
        self.assertFailed(self.client.get("/api/ai/jobs", {"id": job_id}))
        self.assertFailed(self.submit(id=job_id))
        self.assertEqual(self.client.get("/api/ai/jobs").data["data"]["total"], 0)

    def test_offline_rejects_without_losing_draft(self):
        AIWorker.objects.all().delete()
        self.assertFailed(self.submit())
        self.assertEqual(AIJob.objects.count(), 0)
        self.assertSuccess(self.client.put("/api/ai/draft", {"problem_id": self.problem.code, "cells": ["x"], "revision": 0}, format="json"))

    def test_worker_fencing_and_result_retry(self):
        self.assertSuccess(self.submit())
        first = self.claim()
        AIJob.objects.filter(pk=first["id"]).update(lease_until=now() - timedelta(seconds=1))
        second = self.claim()
        self.assertNotEqual(first["lease"], second["lease"])
        self.assertFailed(self.worker("finish", id=first["id"], lease=first["lease"], status="SCORED", public_score=100))
        self.finish(second)
        self.finish(second)
        self.assertEqual(AIJob.objects.get().status, "ACCEPTED")
        self.assertIsNone(self.claim())

    def test_browser_cannot_post_scores_or_claim_jobs(self):
        self.assertFailed(self.post("worker", {"action": "claim", "worker": "x", "kinds": ["evaluation"]}))
        self.assertSuccess(self.submit(public_score=100, status="ACCEPTED"))
        self.assertEqual(AIJob.objects.get().status, "PENDING")
        self.assertIsNone(AIJob.objects.get().public_score)

    def test_nonfinite_scores_rejected_and_html_output_rejected(self):
        self.assertSuccess(self.submit())
        claim = self.claim()
        invalid = {"action": "finish", "worker": "test-worker", "kinds": ["notebook", "evaluation"],
                   "id": claim["id"], "lease": claim["lease"], "status": "SCORED", "public_score": float("nan")}
        self.assertFailed(self.client.post("/api/ai/worker", json.dumps(invalid), content_type="application/json",
                                           HTTP_AUTHORIZATION="Bearer " + self.token))
        self.assertSuccess(self.submit(kind="notebook"))
        notebook = self.claim()
        self.assertFailed(self.worker("finish", id=notebook["id"], lease=notebook["lease"], status="SUCCEEDED",
                                     output={"cells": [{"html": "<script>alert(1)</script>"}]}))

    def test_latest_is_submission_order_not_completion_order(self):
        self.register()
        self.assertSuccess(self.submit(contest_id=self.contest.id))
        first = self.claim()
        self.assertSuccess(self.submit(contest_id=self.contest.id, cells=["second"]))
        second = self.claim()
        self.assertSuccess(self.worker("finish", id=second["id"], lease=second["lease"], status="SCORED", public_score=50))
        self.finish(first)
        result = self.client.get("/api/ai/leaderboard", {"contest_id": self.contest.id})
        self.assertEqual(result.data["data"]["results"][0]["total"], 10)
        self.config.selection = "best"
        self.config.save()
        result = self.client.get("/api/ai/leaderboard", {"contest_id": self.contest.id})
        self.assertEqual(result.data["data"]["results"][0]["total"], 20)

    def test_regular_user_cannot_manage_ai(self):
        self.assertFailed(self.client.post("/api/admin/ai/problems", {}, format="json"))

    def test_browser_write_requires_csrf(self):
        client = APIClient(enforce_csrf_checks=True)
        client.force_login(self.user)
        response = client.post("/api/ai/jobs", {"id": str(uuid.uuid4()), "problem_id": self.problem.code, "cells": ["x"]}, format="json")
        self.assertEqual(response.status_code, 403)
