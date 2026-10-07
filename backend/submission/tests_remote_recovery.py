from unittest import mock
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from django.core.management import call_command
from django.test import SimpleTestCase

from problem.models import ProblemJudgeMode, RemoteOJ
from .models import JudgeStatus, RemoteSubmissionStatus, Submission, SubmissionJudgeMode
from .serializers import RemoteSubmissionEventSerializer
from .tests import SubmissionPrepare


class RemoteStatisticsTests(SimpleTestCase):
    def test_optional_bad_metrics_and_long_compiler_output_do_not_reject_verdict(self):
        for score in [None, "NaN", "Infinity", "-", -1, True, "", 10 ** 400]:
            with self.subTest(score=str(score)[:20]):
                serializer = RemoteSubmissionEventSerializer(data={
                    "submission_id": "synthetic", "provider": "NOWCODER", "status": "FINISHED",
                    "remote_submission_id": "1", "verdict": "编译错误", "score": score,
                    "time_ms": "-", "memory_bytes": -1, "message": "error\x00" * 1000,
                })
                self.assertTrue(serializer.is_valid(), serializer.errors)
                self.assertIsNone(serializer.validated_data.get("score"))
                self.assertIsNone(serializer.validated_data.get("time_ms"))
                self.assertIsNone(serializer.validated_data.get("memory_bytes"))
                self.assertEqual(len(serializer.validated_data["message"]), 2048)
                self.assertNotIn("\x00", serializer.validated_data["message"])

    def test_fractional_or_unsafe_integer_is_omitted_and_percentage_is_normalized(self):
        serializer = RemoteSubmissionEventSerializer(data={
            "submission_id": "s", "provider": "NOWCODER", "status": "FINISHED",
            "score": "75.5%", "time_ms": 1.5, "memory_bytes": 2 ** 53,
        })
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["score"], 75.5)
        self.assertIsNone(serializer.validated_data["time_ms"])
        self.assertIsNone(serializer.validated_data["memory_bytes"])


class RemoteRecoveryTests(SubmissionPrepare):
    def setUp(self):
        self._create_problem_and_submission()
        self.user = self.create_user("recovery-user", "test123")
        self.problem.judge_mode = ProblemJudgeMode.REMOTE
        self.problem.remote_oj = RemoteOJ.NOWCODER
        self.problem.remote_problem_id = "NC15189"
        self.problem.remote_problem_data = {
            "url": "https://ac.nowcoder.com/acm/problem/15189",
            "question_id": "1", "language_ids": {"C": "1"},
        }
        self.problem.save()
        self.remote = Submission.objects.create(
            problem=self.problem, user_id=self.user.id, username=self.user.username,
            code="int main() {}", language="C", result=JudgeStatus.JUDGING,
            judge_mode=SubmissionJudgeMode.REMOTE, remote_oj=RemoteOJ.NOWCODER,
            remote_status=RemoteSubmissionStatus.JUDGING, remote_submission_id="synthetic-1",
        )
        self.recover_url = self.reverse("remote_submission_recovery_api")
        self.event_url = self.reverse("remote_submission_event_api")

    def event(self, **overrides):
        data = {"submission_id": self.remote.id, "provider": "NOWCODER", "status": "FINISHED",
                "remote_submission_id": "synthetic-1", "verdict": "ACCEPTED", **overrides}
        return self.client.post(self.event_url, data, format="json")

    def test_recover_does_not_enqueue_or_resubmit_and_does_not_expose_source_for_known_run(self):
        with mock.patch("submission.views.oj.judge_task.send") as dispatch:
            response = self.client.get(self.recover_url, {"submission_id": self.remote.id})
        self.assertSuccess(response)
        self.assertEqual(response.data["data"]["code"], "")
        task = response.data["data"]["task"]
        self.assertEqual(task["user_id"], self.user.id)
        self.assertEqual(task["rule_type"], "ACM")
        self.assertEqual(task["remote_submission_id"], "synthetic-1")
        dispatch.assert_not_called()
        self.remote.refresh_from_db()
        self.assertEqual(self.remote.remote_status, "JUDGING")

    def test_automatic_recovery_only_returns_owned_runs_with_a_remote_id(self):
        self.remote.remote_submission_id = None
        self.remote.remote_status = "AUTH_REQUIRED"
        self.remote.save()
        response = self.client.get(self.recover_url)
        self.assertSuccess(response)
        self.assertEqual(response.data["data"]["tasks"], [])
        explicit = self.client.get(self.recover_url, {"submission_id": self.remote.id})
        self.assertEqual(explicit.data["data"]["code"], self.remote.code)

    def test_recovery_rejects_other_users_even_admins_and_local_submissions(self):
        self.assertFailed(self.client.get(self.recover_url, {"submission_id": self.submission.id}))
        self.create_super_admin("another-admin", "test123")
        self.assertFailed(self.client.get(self.recover_url, {"submission_id": self.remote.id}))
        self.assertEqual(self.client.get(self.recover_url).data["data"]["tasks"], [])
        self.client.logout()
        self.assertFailed(self.client.get(self.recover_url, {"submission_id": self.remote.id}))

    def test_compile_error_with_null_score_lands_once_and_retains_diagnostic(self):
        for _ in range(2):
            self.assertSuccess(self.event(verdict="编译错误", score=None, message="compiler error\x00" * 300))
        self.remote.refresh_from_db()
        self.problem.refresh_from_db()
        self.assertEqual(self.remote.result, JudgeStatus.COMPILE_ERROR)
        self.assertEqual(self.remote.remote_status, "FINISHED")
        self.assertIn("compiler error", self.remote.statistic_info["err_info"])
        self.assertNotIn("score", self.remote.statistic_info)
        self.assertEqual(self.problem.submission_number, 2)  # Includes the pre-existing CE fixture.
        self.assertIsNone(self.client.get(self.recover_url, {"submission_id": self.remote.id}).data["data"]["task"])

    def test_retried_final_event_and_late_progress_do_not_change_counts(self):
        for _ in range(2):
            self.assertSuccess(self.event())
        self.assertSuccess(self.event(status="JUDGING"))
        self.problem.refresh_from_db()
        self.remote.refresh_from_db()
        self.assertEqual(self.problem.submission_number, 2)  # Includes the pre-existing CE fixture.
        self.assertEqual(self.problem.accepted_number, 1)
        self.assertEqual(self.remote.result, JudgeStatus.ACCEPTED)

    def test_acm_partial_uses_concrete_failure(self):
        self.assertSuccess(self.event(verdict="UNACCEPTED", score=70, failed_verdict="TIME_LIMIT_EXCEEDED"))
        self.remote.refresh_from_db()
        self.assertEqual(self.remote.result, JudgeStatus.CPU_TIME_LIMIT_EXCEEDED)

    def test_login_can_expire_during_verification(self):
        self.assertSuccess(self.event(status="VERIFICATION_REQUIRED"))
        self.assertSuccess(self.event(status="AUTH_REQUIRED"))
        self.remote.refresh_from_db()
        self.assertEqual(self.remote.remote_status, "AUTH_REQUIRED")
        self.assertEqual(self.remote.result, JudgeStatus.PENDING)

    def test_zero_score_is_not_partial_and_an_accepted_failure_hint_is_ignored(self):
        self.assertSuccess(self.event(verdict="PARTIALLY_ACCEPTED", score=0, failed_verdict="ACCEPTED"))
        self.remote.refresh_from_db()
        self.assertEqual(self.remote.result, JudgeStatus.WRONG_ANSWER)

    def test_oi_partial_keeps_score(self):
        self.problem.rule_type = "OI"
        self.problem.total_score = 100
        self.problem.save()
        self.assertSuccess(self.event(verdict="PARTIALLY_ACCEPTED", score=70))
        self.remote.refresh_from_db()
        self.assertEqual(self.remote.result, JudgeStatus.PARTIALLY_ACCEPTED)
        self.assertEqual(self.remote.statistic_info["score"], 70)

    def test_legacy_normalization_is_backed_up_idempotent_and_preserves_ac_counters(self):
        self.remote.remote_oj = "LUOGU"
        self.remote.remote_status = "FINISHED"
        self.remote.result = JudgeStatus.PARTIALLY_ACCEPTED
        self.remote.save()
        self.problem.submission_number = 3
        self.problem.accepted_number = 2
        self.problem.statistic_info = {"8": 1, "0": 2}
        self.problem.save()
        profile = self.user.userprofile
        profile.acm_problems_status = {"problems": {str(self.problem.id): {"status": 8}}}
        profile.save()
        call_command("normalize_remote_acm_verdicts", stdout=StringIO())
        self.remote.refresh_from_db()
        self.assertEqual(self.remote.result, 8)
        with TemporaryDirectory() as directory:
            call_command("normalize_remote_acm_verdicts", apply=True, backup_dir=directory, stdout=StringIO())
            call_command("normalize_remote_acm_verdicts", apply=True, backup_dir=directory, stdout=StringIO())
            backups = list(Path(directory).glob("*.json"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
        self.remote.refresh_from_db()
        self.problem.refresh_from_db()
        profile.refresh_from_db()
        self.assertEqual(self.remote.result, JudgeStatus.WRONG_ANSWER)
        self.assertEqual(self.problem.statistic_info, {"0": 2, "-1": 1})
        self.assertEqual((self.problem.submission_number, self.problem.accepted_number), (3, 2))
        self.assertEqual(profile.acm_problems_status["problems"][str(self.problem.id)]["status"], -1)
