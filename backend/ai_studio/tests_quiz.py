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
