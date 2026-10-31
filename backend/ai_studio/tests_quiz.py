"""Quiz answer cards: package contract, OJ-side grading, attempt limits and private answer keys."""
import io
import json
import os
import tempfile
import uuid
import zipfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.utils.timezone import now

from contest.models import Contest
from utils.api.tests import APITestCase
from .models import AIContestConfig, AIContestProblem, AIDraft, AIJob, AIProblem, AIProblemImport, AIServiceState, AIWorker
from .package_format import FORMAT, PackageError, make_zip, parse_package
from .quiz import answers_input, grade
from .tests_packages import fixture as code_fixture

PNG = b"\x89PNG\r\n\x1a\n" + b"\x00" * 32
CARD = {
    "materials": [
        {"id": "m1", "title": "字段", "kind": "table", "columns": ["字段", "含义"], "rows": [["temp", "温度"], ["load", 3.5]]},
        {"id": "m2", "title": "曲线", "kind": "image", "file": "curve.png", "alt": "训练与验证损失"},
        {"id": "m3", "kind": "text", "text": "epoch 1, loss 0.9"},
    ],
    "questions": [
        {"id": "q1", "kind": "single", "prompt": "任务类型", "options": ["回归", "分类"], "points": 10, "materials": ["m1"]},
        {"id": "q2", "kind": "multiple", "prompt": "泄露特征", "options": ["a", "b", "c"], "points": 20},
        {"id": "q3", "kind": "multiple", "prompt": "补救手段", "options": ["a", "b", "c", "d"], "points": 20},
        {"id": "q4", "kind": "number", "prompt": "RMSE", "unit": "kWh", "points": 30, "materials": ["m2"]},
        {"id": "q5", "kind": "order", "prompt": "流程顺序", "options": ["x", "y", "z"], "points": 20},
    ],
}
KEY = {"q1": {"answer": 0}, "q2": {"answer": [2, 0]}, "q3": {"answer": [0, 1], "scoring": "partial"},
       "q4": {"answer": 1.5, "tolerance": 0.01}, "q5": {"answer": [2, 0, 1]}}
FULL = {"q1": 0, "q2": [0, 2], "q3": [1, 0], "q4": 1.505, "q5": [2, 0, 1]}


def quiz_fixture(title="用电量场景分析", card=None, key=None, media=None, evaluation=None, extra=None):
    metadata = {"format": FORMAT, "version": 1, "title": title, "type": "quiz",
                "statement": {"objective": "阅读材料并作答", "requirements": ["每题只计一次"]},
                "evaluation": evaluation or {"pass_score": 100, "max_attempts": 2}, "quiz": card or CARD}
    files = {"problem.json": json.dumps(metadata, ensure_ascii=False).encode(),
             "evaluation/reference/answers.json": json.dumps(key or KEY).encode(), "data/readings.csv": b"hour,load\n1,3.5\n"}
    files.update({"media/" + name: content for name, content in (media if media is not None else {"curve.png": PNG}).items()})
    files.update(extra or {})
    return make_zip(files)


def members(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


class QuizFormatTests(SimpleTestCase):
    def test_card_media_and_private_key_parse(self):
        item = parse_package(quiz_fixture())[0]
        self.assertEqual(item["cells"], [])
        self.assertEqual(item["quiz_key"]["q2"], {"answer": [0, 2], "scoring": "all"})
        self.assertTrue(item["media"]["curve.png"].startswith("data:image/png;base64,"))
        self.assertEqual(set(item["asset_sha256"]), {"reference_data"})
        self.assertEqual(item["metadata"]["evaluation"]["max_attempts"], 2)
        self.assertEqual(item["metadata"]["quiz"]["questions"][1]["materials"], [])

    def test_rejects_invalid_cards_keys_media_and_layouts(self):
        broken_ref = json.loads(json.dumps(CARD)); broken_ref["questions"][0]["materials"] = ["missing"]
        duplicate = json.loads(json.dumps(CARD)); duplicate["questions"][1]["id"] = "q1"
        for raw in (quiz_fixture(card=broken_ref), quiz_fixture(card=duplicate),
                    quiz_fixture(key={**KEY, "q1": {"answer": 5}}), quiz_fixture(key={k: v for k, v in KEY.items() if k != "q5"}),
                    quiz_fixture(key={**KEY, "q5": {"answer": [0, 0, 1]}}), quiz_fixture(key={**KEY, "q1": {"answer": True}}),
                    quiz_fixture(media={}), quiz_fixture(media={"curve.png": b"<svg onload=alert(1)>"}),
                    quiz_fixture(media={"curve.png": PNG, "extra.png": PNG}),
                    quiz_fixture(extra={"starter.ipynb": b'{"nbformat": 4, "cells": []}'}),
                    quiz_fixture(extra={"evaluation/scoring/program.py": b"print(1)"}),
                    quiz_fixture(evaluation={"max_attempts": 0}), quiz_fixture(evaluation={"accuracy_column": "accuracy"})):
            with self.subTest(), self.assertRaises(PackageError):
                parse_package(raw)

    def test_quiz_and_code_problems_are_never_mixed_and_code_problems_cannot_limit_attempts(self):
        with self.assertRaises(PackageError):
            parse_package(make_zip({"1.zip": quiz_fixture(), "2.zip": code_fixture()}))
        self.assertEqual(len(parse_package(make_zip({"1.zip": quiz_fixture(), "2.zip": quiz_fixture("外卖")}))), 2)
        files = members(code_fixture())
        meta = json.loads(files["problem.json"]); meta["evaluation"]["max_attempts"] = 1
        with self.assertRaises(PackageError):
            parse_package(make_zip({**files, "problem.json": json.dumps(meta).encode()}))

    def test_grading_rules(self):
        quiz = parse_package(quiz_fixture())[0]
        card, key = quiz["metadata"]["quiz"], quiz["quiz_key"]
        self.assertEqual(grade(card, key, answers_input(card, FULL)), 100)
        self.assertEqual(grade(card, key, answers_input(card, {})), 0)
        # q2 is all-or-nothing, q3 partial (one hit, no wrong = half), q4 outside tolerance, q5 order wrong.
        partial = answers_input(card, {"q1": 0, "q2": [0], "q3": [0], "q4": 1.6, "q5": [0, 1, 2]})
        self.assertEqual(grade(card, key, partial), 20)
        wrong_pick = answers_input(card, {"q3": [0, 1, 2]})  # two hits minus one wrong over two expected
        self.assertEqual(grade(card, key, wrong_pick), 10)
        relative = {**key, "q4": {"answer": 200, "tolerance": 0, "relative": 0.05}}
        self.assertEqual(grade(card, relative, answers_input(card, {"q4": 209})), 30)
        for bad in ({"q1": 2}, {"q2": [0, 0]}, {"q4": "1.5"}, {"q4": float("inf")}, {"q5": [0, 1]}, {"zz": 1}, []):
            with self.subTest(bad=bad), self.assertRaises(Exception):
                answers_input(card, bad)


class QuizAPITests(APITestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        settings = override_settings(DATA_DIR=self.root.name)
        settings.enable(); self.addCleanup(settings.disable)
        self.admin = self.create_admin()

    def publish(self, raw=None, visible=True):
        stream = io.BytesIO(raw or quiz_fixture()); stream.name = "quiz.zip"
        upload = self.client.post("/api/admin/ai/packages", {"file": stream}, format="multipart")
        self.assertSuccess(upload)
        self.assertNotIn("answers.json", json.dumps(upload.data)); self.assertNotIn("tolerance", json.dumps(upload.data))
        self.assertEqual(upload.data["data"]["problems"][0]["questions"], 5)
        confirm = self.client.post("/api/admin/ai/packages/confirm", {"id": upload.data["data"]["id"], "publish": visible}, format="json")
        self.assertSuccess(confirm)
        self.assertEqual(confirm.data["data"]["status"], "SUCCEEDED")
        return AIProblem.objects.get(code=confirm.data["data"]["result"][0]["id"])

    def submit(self, problem, answers, **values):
        return self.client.post("/api/ai/jobs", {"id": str(uuid.uuid4()), "problem_id": problem.code, "answers": answers, **values},
                                format="json")

    def test_quiz_batch_publishes_without_evaluation_service_and_keeps_key_private(self):
        AIServiceState.objects.update_or_create(pk=1, defaults={"paused": True})
        problem = self.publish()
        self.assertEqual((problem.category, problem.cells, problem.judge["answers"]["q1"]), ("quiz", [], {"answer": 0}))
        self.assertNotIn("answers", json.dumps(AIProblemImport.objects.get().manifest))
        self.create_user("student", "student")
        detail = self.client.get("/api/ai/problems", {"problem_id": problem.code})
        self.assertSuccess(detail)
        body = json.dumps(detail.data)
        self.assertNotIn("tolerance", body); self.assertNotIn("judge", detail.data["data"])
        self.assertEqual(detail.data["data"]["quiz"]["questions"][3]["unit"], "kWh")
        self.assertTrue(detail.data["data"]["media"]["curve.png"].startswith("data:image/png;base64,"))
        self.assertEqual(detail.data["data"]["maxAttempts"], 2)

    def test_drafts_and_synchronous_grading_without_workers(self):
        problem = self.publish()
        self.create_user("student", "student")
        self.assertFalse(AIWorker.objects.exists())
        draft = self.client.get("/api/ai/draft", {"problem_id": problem.code}).data["data"]
        self.assertEqual(draft, {"answers": {}, "revision": 0})
        saved = self.client.put("/api/ai/draft", {"problem_id": problem.code, "answers": {"q1": 1}, "revision": 0}, format="json")
        self.assertSuccess(saved); self.assertEqual(saved.data["data"]["answers"]["q1"], 1)
        self.assertFailed(self.client.put("/api/ai/draft", {"problem_id": problem.code, "answers": {"q1": 9}, "revision": 1}, format="json"))
        self.assertFailed(self.client.put("/api/ai/draft", {"problem_id": problem.code, "cells": ["x"], "revision": 1}, format="json"))
        self.assertEqual(self.client.get("/api/ai/draft", {"problem_id": problem.code}).data["data"]["answers"]["q2"], None)
        result = self.submit(problem, FULL)
        self.assertSuccess(result)
        self.assertEqual((result.data["data"]["status"], result.data["data"]["publicScore"]), ("ACCEPTED", 100))
        partial = self.submit(problem, {"q1": 0}).data["data"]
        self.assertEqual((partial["status"], partial["publicScore"]), ("PARTIAL", 10))
        self.assertEqual(self.submit(problem, {}).data["data"]["status"], "WRONG_ANSWER")
        self.assertFailed(self.submit(problem, FULL, kind="notebook"))
        self.assertFailed(self.submit(problem, {"q1": 7}))
        job = AIJob.objects.filter(public_score=100).get()
        self.assertEqual((job.category, job.official, job.payload["answers"]["q5"]), ("quiz", False, [2, 0, 1]))
        self.assertIsNotNone(job.finished_at)

    def test_official_attempt_limit_and_leaderboard(self):
        problem = self.publish(visible=False)
        contest = Contest.objects.create(title="考核", description="", rule_type="AI", start_time=now() - timedelta(minutes=5),
                                         end_time=now() + timedelta(minutes=30), password="exam", real_time_rank=True,
                                         visible=True, created_by=self.admin)
        AIContestConfig.objects.create(contest=contest, selection="best")
        AIContestProblem.objects.create(contest=contest, problem=problem, position=0, points=30)
        self.create_user("student", "student")
        self.assertSuccess(self.client.post("/api/contest/register", {"contest_id": contest.id, "password": "exam"}, format="json"))
        scope = {"contest_id": contest.id}
        self.assertEqual(self.client.get("/api/ai/problems", {"problem_id": problem.code, **scope}).data["data"]["attemptsUsed"], 0)
        self.assertSuccess(self.submit(problem, {"q1": 0}, **scope))
        self.assertSuccess(self.submit(problem, FULL, **scope))
        self.assertFailed(self.submit(problem, FULL, **scope))
        self.assertEqual(self.client.get("/api/ai/problems", {"problem_id": problem.code, **scope}).data["data"]["attemptsUsed"], 2)
        board = self.client.get("/api/ai/leaderboard", scope).data["data"]["results"]
        self.assertEqual((board[0]["total"], board[0]["scores"][problem.code]["status"]), (30, "ACCEPTED"))
        # Practice after the contest is unlimited and never official.
        Contest.objects.filter(pk=contest.pk).update(end_time=now() - timedelta(minutes=1))
        practice = self.submit(problem, FULL, **scope)
        self.assertSuccess(practice); self.assertFalse(practice.data["data"]["official"])

    def test_admin_edit_keeps_card_and_rejects_key_changes_and_export_roundtrips(self):
        problem = self.publish()
        data = self.client.get("/api/admin/ai/problems", {"id": problem.code}).data["data"]
        data["objective"] = "重新表述的任务"
        self.assertSuccess(self.client.post("/api/admin/ai/problems", data, format="json"))
        problem.refresh_from_db()
        self.assertEqual((problem.statement["objective"], problem.statement["quiz"]["questions"][0]["id"]), ("重新表述的任务", "q1"))
        self.assertIn("curve.png", problem.statement["media"])
        data["revision"] = problem.revision; data["judge"]["answers"]["q1"] = {"answer": 1}
        self.assertFailed(self.client.post("/api/admin/ai/problems", data, format="json"))
        data["judge"] = problem.judge; data["cells"] = ["print(1)"]
        self.assertFailed(self.client.post("/api/admin/ai/problems", data, format="json"))
        response = self.client.get("/api/admin/ai/packages/export", {"problem_id": problem.code})
        exported = b"".join(response.streaming_content)
        files = members(exported)
        self.assertEqual(files["media/curve.png"], PNG)
        self.assertNotIn("starter.ipynb", files)
        self.assertNotIn("answers", json.loads(files["problem.json"])["evaluation"])
        copy = self.publish(exported)
        self.assertEqual((copy.statement, copy.judge), (problem.statement, problem.judge))
        self.assertNotEqual(copy.code, problem.code)
        self.assertFalse(AIDraft.objects.exists())


TEXT_CARD = {"questions": [
    {"id": "q1", "kind": "single", "prompt": "任务类型", "options": ["回归", "分类"], "points": 40},
    {"id": "essay", "kind": "text", "prompt": "说明你的建模方案", "points": 60},
]}
TEXT_KEY = {"q1": {"answer": 0}, "essay": {"rubric": "特征处理 20；模型与损失 20；验证方式 20"}}


class QuizReviewAndACMTests(APITestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        settings = override_settings(DATA_DIR=self.root.name)
        settings.enable(); self.addCleanup(settings.disable)
        self.teacher = self.create_admin()
        stream = io.BytesIO(quiz_fixture(card=TEXT_CARD, key=TEXT_KEY, media={}, evaluation={"pass_score": 80})); stream.name = "essay.zip"
        upload = self.client.post("/api/admin/ai/packages", {"file": stream}, format="multipart")
        confirm = self.client.post("/api/admin/ai/packages/confirm", {"id": upload.data["data"]["id"], "publish": False}, format="json")
        self.problem = AIProblem.objects.get(code=confirm.data["data"]["result"][0]["id"])
        self.contest = Contest.objects.create(title="ACM", description="", rule_type="AI", start_time=now() - timedelta(minutes=30),
                                              end_time=now() + timedelta(minutes=30), real_time_rank=True, visible=True,
                                              created_by=self.teacher)
        AIContestConfig.objects.create(contest=self.contest, ranking="acm")
        AIContestProblem.objects.create(contest=self.contest, problem=self.problem, position=0, points=10)
        self.scope = {"contest_id": self.contest.id}

    def submit(self, answers):
        result = self.client.post("/api/ai/jobs", {"id": str(uuid.uuid4()), "problem_id": self.problem.code, "answers": answers,
                                                  **self.scope}, format="json")
        self.assertSuccess(result)
        return result.data["data"]

    def test_text_questions_require_rubric_and_bound_answers(self):
        with self.assertRaises(PackageError):
            parse_package(quiz_fixture(card=TEXT_CARD, key={**TEXT_KEY, "essay": {"answer": 1}}, media={}))
        card = parse_package(quiz_fixture(card=TEXT_CARD, key=TEXT_KEY, media={}))[0]["metadata"]["quiz"]
        self.assertEqual(answers_input(card, {"essay": "  "}), {"q1": None, "essay": None})
        with self.assertRaises(Exception):
            answers_input(card, {"essay": "x" * 2001})

    def test_review_flow_supersedes_scores_and_ranks(self):
        self.create_user("student", "student")
        self.client.post("/api/contest/register", {"contest_id": self.contest.id}, format="json")
        hopeless = self.submit({"q1": 1, "essay": "方案"})  # 0 + 60 < 80: decided at once, the essay is not reviewed
        self.assertEqual((hopeless["status"], hopeless["publicScore"]), ("WRONG_ANSWER", 0))
        first = self.submit({"q1": 0, "essay": "初稿"})
        self.assertEqual((first["status"], first["publicScore"]), ("REVIEWING", None))
        second = self.submit({"q1": 0, "essay": "完整方案"})
        self.assertEqual(AIJob.objects.get(pk=first["id"]).status, "SUPERSEDED")
        board = self.client.get("/api/ai/leaderboard", self.scope).data["data"]
        cell = board["results"][0]["scores"][self.problem.code]
        self.assertEqual((board["ranking"], cell["pending"], cell["tries"], cell["accepted"]), ("acm", 1, 1, False))
        self.assertFailed(self.client.post("/api/admin/ai/reviews", {"id": second["id"], "scores": {"essay": 50}}, format="json"))
        self.client.force_login(self.teacher)
        pending = self.client.get("/api/admin/ai/reviews").data["data"]["results"]
        self.assertEqual([item["id"] for item in pending], [second["id"]])
        self.assertEqual(pending[0]["questions"][0]["rubric"], TEXT_KEY["essay"]["rubric"])
        self.assertEqual(pending[0]["questions"][0]["answer"], "完整方案")
        self.assertFailed(self.client.post("/api/admin/ai/reviews", {"id": second["id"], "scores": {"essay": 61}}, format="json"))
        graded = self.client.post("/api/admin/ai/reviews", {"id": second["id"], "scores": {"essay": 45}}, format="json")
        self.assertSuccess(graded)
        self.assertEqual((graded.data["data"]["status"], graded.data["data"]["publicScore"]), ("ACCEPTED", 85))
        # A graded card may be rescored; the superseded one may not.
        self.assertSuccess(self.client.post("/api/admin/ai/reviews", {"id": second["id"], "scores": {"essay": 45}}, format="json"))
        self.assertFailed(self.client.post("/api/admin/ai/reviews", {"id": first["id"], "scores": {"essay": 45}}, format="json"))
        row = self.client.get("/api/ai/leaderboard", self.scope).data["data"]["results"][0]
        cell = row["scores"][self.problem.code]
        # One wrong try before the accepted card; the superseded card costs nothing.
        self.assertEqual((row["solved"], cell["tries"], cell["accepted"]), (1, 1, True))
        self.assertEqual(row["penalty"], cell["time"] + 20 * 60)
        self.assertEqual(self.client.get("/api/admin/ai/reviews").data["data"]["total"], 0)
        self.assertEqual(self.client.get("/api/admin/ai/reviews", {"status": "done"}).data["data"]["total"], 1)

    def test_acm_order_ties_and_ignored_failures(self):
        users = [self.create_user(name, name, login=False) for name in ("ann", "bob", "cat")]
        base = self.contest.start_time
        def job(user, status, minutes):
            item = AIJob.objects.create(user=user, problem=self.problem, contest=self.contest, kind="evaluation", official=True,
                                        category="quiz", problem_version=1, source_sha256="a" * 64, status=status)
            AIJob.objects.filter(pk=item.pk).update(created_at=base + timedelta(minutes=minutes))
        job(users[0], "SYSTEM_ERROR", 1); job(users[0], "ACCEPTED", 10)  # 10 min, system errors are free
        job(users[1], "PARTIAL", 2); job(users[1], "ACCEPTED", 5); job(users[1], "WRONG_ANSWER", 6)  # 5 + 20 min
        job(users[2], "WRONG_ANSWER", 3)
        self.client.force_login(self.teacher)
        rows = self.client.get("/api/ai/leaderboard", self.scope).data["data"]["results"]
        self.assertEqual([(r["username"], r["rank"], r["solved"], r["penalty"] // 60) for r in rows],
                         [("ann", 1, 1, 10), ("bob", 2, 1, 25), ("cat", 3, 0, 0)])
        detail = self.client.get("/api/ai/contest", self.scope).data["data"]
        self.assertEqual(detail["ranking"], "acm")

    def test_oi_sums_best_points_and_breaks_ties_by_penalty(self):
        AIContestConfig.objects.filter(contest=self.contest).update(ranking="oi")
        users = [self.create_user(name, name, login=False) for name in ("ann", "bob", "cat", "dan")]
        base = self.contest.start_time
        def job(user, status, minutes, score):
            item = AIJob.objects.create(user=user, problem=self.problem, contest=self.contest, kind="evaluation", official=True,
                                        category="quiz", problem_version=1, source_sha256="a" * 64, status=status, public_score=score)
            AIJob.objects.filter(pk=item.pk).update(created_at=base + timedelta(minutes=minutes))
        job(users[0], "PARTIAL", 4, 60); job(users[0], "WRONG_ANSWER", 9, 0)  # 6 points at 4 min; a worse retry is free
        job(users[1], "SYSTEM_ERROR", 1, None); job(users[1], "RUNTIME_ERROR", 2, None); job(users[1], "PARTIAL", 3, 60)  # 3 + 20 min
        job(users[2], "WRONG_ANSWER", 1, 0); job(users[2], "ACCEPTED", 30, 100)
        job(users[3], "REVIEWING", 5, None)
        self.client.force_login(self.teacher)
        board = self.client.get("/api/ai/leaderboard", self.scope).data["data"]
        rows = board["results"]
        self.assertEqual(board["ranking"], "oi")
        # Penalty is only the time of each problem's best submission.
        self.assertEqual([(r["username"], r["rank"], r["total"], r["penalty"] // 60) for r in rows],
                         [("cat", 1, 10, 30), ("bob", 2, 6, 3), ("ann", 3, 6, 4), ("dan", 4, 0, 0)])
        self.assertEqual(rows[2]["scores"][self.problem.code]["time"], 240)
        self.assertTrue(all("realName" in row for row in rows))  # contest admins see real names
        self.assertEqual((rows[3]["scores"][self.problem.code]["pending"], rows[3]["scores"][self.problem.code]["score"]), (1, None))

    def test_points_boards_review_every_essay_and_admins_read_submissions(self):
        AIContestConfig.objects.filter(contest=self.contest).update(ranking="oi")
        student = self.create_user("student", "student")
        self.client.post("/api/contest/register", {"contest_id": self.contest.id}, format="json")
        card = self.submit({"q1": 1, "essay": "方案"})  # cannot pass, but every point counts on an OI board
        self.assertEqual(card["status"], "REVIEWING")
        self.assertEqual(self.client.get("/api/ai/jobs", {"id": card["id"]}).data["data"]["payload"]["answers"]["essay"], "方案")
        self.assertNotIn("realName", self.client.get("/api/ai/leaderboard", self.scope).data["data"]["results"][0])
        self.create_user("other", "other")
        self.assertFailed(self.client.get("/api/ai/jobs", {"id": card["id"]}))
        self.client.force_login(self.teacher)
        detail = self.client.get("/api/ai/jobs", {"id": card["id"]}).data["data"]
        self.assertEqual((detail["user"]["username"], detail["payload"]["answers"]["essay"]), ("student", "方案"))
        self.assertEqual(self.client.get("/api/admin/ai/reviews", {"id": card["id"]}).data["data"]["questions"][0]["answer"], "方案")
        graded = self.client.post("/api/admin/ai/reviews", {"id": card["id"], "scores": {"essay": 30}}, format="json")
        self.assertEqual((graded.data["data"]["status"], graded.data["data"]["publicScore"]), ("PARTIAL", 30))
        # A decided card can be rescored.
        rescored = self.client.post("/api/admin/ai/reviews", {"id": card["id"], "scores": {"essay": 40}}, format="json")
        self.assertEqual(rescored.data["data"]["publicScore"], 40)
        self.assertEqual(AIJob.objects.get(pk=card["id"]).user, student)

    def test_contest_ranking_setting_is_frozen_after_start(self):
        payload = {"contest_id": self.contest.id, "selection": "latest", "ranking": "score", "private_published": False,
                   "practice_enabled": True, "problems": [{"id": self.problem.code, "points": 10}]}
        self.assertEqual(self.client.get("/api/admin/ai/contest", {"contest_id": self.contest.id}).data["data"]["ranking"], "acm")
        self.assertFailed(self.client.put("/api/admin/ai/contest", payload, format="json"))
        Contest.objects.filter(pk=self.contest.pk).update(start_time=now() + timedelta(minutes=5), end_time=now() + timedelta(hours=1))
        self.assertSuccess(self.client.put("/api/admin/ai/contest", payload, format="json"))
        self.assertEqual(AIContestConfig.objects.get(contest=self.contest).ranking, "score")
