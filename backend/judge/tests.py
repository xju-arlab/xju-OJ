from datetime import timedelta
from unittest import mock

from django.utils import timezone

from contest.models import ACMContestRank, Contest, OIContestRank
from judge.dispatcher import JudgeDispatcher, process_pending_task
from submission.models import JudgeStatus, Submission, SubmissionJudgeMode
from submission.tests import SubmissionPrepare


class StatisticsRegressionTests(SubmissionPrepare):
    def setUp(self):
        self._create_problem_and_submission()
        self.user = self.create_user("competitor", "test")

    def finish(self, result, seconds=10, score=0, submission=None):
        if submission is None:
            submission = Submission.objects.create(
                problem=self.problem, contest=self.problem.contest, user_id=self.user.id,
                username=self.user.username, code="int main() {}", language="C")
            if self.problem.contest:
                Submission.objects.filter(pk=submission.pk).update(
                    create_time=self.problem.contest.start_time + timedelta(seconds=seconds))
        dispatcher = JudgeDispatcher(submission.pk, self.problem.pk)
        dispatcher.submission.result = result
        dispatcher.submission.info = {"err": None, "data": []}
        dispatcher.submission.statistic_info = {"score": score}
        dispatcher.submission.save()
        dispatcher.finalize_submission()
        self.problem.refresh_from_db()
        return dispatcher.submission

    def contest(self, rule="ACM"):
        self.problem.rule_type = rule
        self.problem.contest = Contest.objects.create(
            title="Audit", description="", created_by=self.problem.created_by, rule_type=rule,
            real_time_rank=True, start_time=timezone.now() - timedelta(hours=1),
            end_time=timezone.now() + timedelta(hours=1))
        self.problem.save()

    def test_public_ac_rejudge_to_wa_and_repeat_do_not_add_attempts(self):
        attempt = self.finish(JudgeStatus.ACCEPTED)
        before = self.problem.submission_number
        self.finish(JudgeStatus.WRONG_ANSWER, submission=attempt)
        self.finish(JudgeStatus.WRONG_ANSWER, submission=attempt)
        self.assertEqual(self.problem.submission_number, before)
        self.assertEqual(self.problem.accepted_number, 0)
        self.assertEqual(self.problem.statistic_info.get("0", 0), 0)
        self.user.userprofile.refresh_from_db()
        self.assertEqual(self.user.userprofile.accepted_number, 0)
        self.assertEqual(self.user.userprofile.submission_number, 1)
        self.assertEqual(self.user.userprofile.acm_problems_status["problems"][str(self.problem.id)]["status"], -1)

    def test_another_accepted_attempt_keeps_personal_ac(self):
        first = self.finish(JudgeStatus.ACCEPTED)
        self.finish(JudgeStatus.ACCEPTED)
        self.finish(JudgeStatus.WRONG_ANSWER, submission=first)
        self.user.userprofile.refresh_from_db()
        self.assertEqual(self.problem.accepted_number, 1)
        self.assertEqual(self.user.userprofile.accepted_number, 1)

    def test_contest_system_error_and_compile_error_have_no_penalty(self):
        self.contest()
        self.finish(JudgeStatus.SYSTEM_ERROR)
        self.finish(JudgeStatus.COMPILE_ERROR, seconds=20)
        wrong = self.finish(JudgeStatus.WRONG_ANSWER, seconds=30)
        self.finish(JudgeStatus.WRONG_ANSWER, submission=wrong)
        self.finish(JudgeStatus.ACCEPTED, seconds=60)
        rank = ACMContestRank.objects.get(user=self.user, contest=self.problem.contest)
        self.assertEqual(rank.total_time, 60 + 1200)
        self.assertEqual(rank.submission_number, 4)
        self.assertEqual(self.problem.submission_number, 4)

    def test_out_of_order_finish_and_rejudge_preserve_first_ac_and_checked(self):
        self.contest()
        later = self.finish(JudgeStatus.ACCEPTED, seconds=100)
        rank = ACMContestRank.objects.get(user=self.user, contest=self.problem.contest)
        rank.submission_info[str(self.problem.id)]["checked"] = True
        rank.save()
        self.finish(JudgeStatus.WRONG_ANSWER, seconds=10)
        self.finish(JudgeStatus.ACCEPTED, submission=later)
        rank.refresh_from_db()
        self.assertEqual(rank.submission_number, 2)
        self.assertEqual(rank.total_time, 1300)
        self.assertTrue(rank.submission_info[str(self.problem.id)]["checked"])
        self.finish(JudgeStatus.WRONG_ANSWER, submission=later)
        rank.refresh_from_db()
        self.assertEqual(rank.accepted_number, 0)
        self.assertEqual(rank.total_time, 0)

    def test_oi_uses_latest_submission_time_and_public_rejudge_corrects_score(self):
        self.problem.rule_type = "OI"
        self.problem.save()
        attempt = self.finish(JudgeStatus.ACCEPTED, score=100)
        self.finish(JudgeStatus.PARTIALLY_ACCEPTED, score=40, submission=attempt)
        self.user.userprofile.refresh_from_db()
        self.assertEqual(self.user.userprofile.total_score, 40)
        self.contest("OI")
        self.finish(JudgeStatus.PARTIALLY_ACCEPTED, seconds=100, score=80)
        self.finish(JudgeStatus.PARTIALLY_ACCEPTED, seconds=10, score=20)
        self.assertEqual(OIContestRank.objects.get(user=self.user, contest=self.problem.contest).total_score, 80)


class RejudgeAPITests(SubmissionPrepare):
    def setUp(self):
        self._create_problem_and_submission()
        self.create_super_admin()
        self.url = self.reverse("submission_rejudge_api")

    @mock.patch("submission.views.admin.judge_task.send")
    def test_rejudge_is_post_only_and_keeps_previous_verdict_until_worker_claims(self, send):
        self.submission.statistic_info = {"score": 42}
        self.submission.save()
        self.assertEqual(self.client.get(self.url, {"id": self.submission.id}).status_code, 405)
        with self.captureOnCommitCallbacks(execute=True):
            self.assertSuccess(self.client.post(self.url, {"id": self.submission.id}))
        self.submission.refresh_from_db()
        self.assertEqual(self.submission.statistic_info["score"], 42)
        self.assertEqual(self.submission.result, JudgeStatus.PENDING)
        send.assert_called_once_with(self.submission.id, self.problem.id)

    @mock.patch("submission.views.admin.judge_task.send")
    def test_remote_rejudge_is_rejected(self, send):
        self.submission.judge_mode = SubmissionJudgeMode.REMOTE
        self.submission.save()
        self.assertFailed(self.client.post(self.url, {"id": self.submission.id}))
        send.assert_not_called()

    @mock.patch("judge.dispatcher.cache")
    @mock.patch("judge.tasks.judge_task.send", side_effect=RuntimeError("broker unavailable"))
    def test_queue_item_is_restored_when_broker_send_fails(self, send, cache):
        payload = b'{"submission_id":"synthetic","problem_id":1}'
        cache.llen.return_value = 1
        cache.rpop.return_value = payload
        with self.assertRaises(RuntimeError):
            process_pending_task()
        cache.rpush.assert_called_once_with("waiting_queue", payload)
