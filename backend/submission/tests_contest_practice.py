from copy import deepcopy
from datetime import timedelta
from unittest import mock

from django.utils import timezone

from contest.models import ACMContestRank, Contest, ContestParticipation, OIContestRank
from judge.dispatcher import JudgeDispatcher
from problem.models import ProblemJudgeMode, RemoteOJ

from .models import JudgeStatus, Submission
from .tests import SubmissionPrepare


class ContestPracticeSubmissionTests(SubmissionPrepare):
    def setUp(self):
        self._create_problem_and_submission()
        self.user = self.create_user("practice-user", "test123")
        self.url = self.reverse("submission_api")
        self.contest = Contest.objects.create(
            title="Finished contest", description="", real_time_rank=False,
            rule_type="ACM", created_by=self.problem.created_by,
            start_time=timezone.now() - timedelta(hours=2),
            end_time=timezone.now() - timedelta(hours=1),
            allowed_ip_ranges=["192.0.2.0/24"],
        )
        self.problem.contest = self.contest
        self.problem.save()
        self.submission_data["contest_id"] = self.contest.id
        for target, value in (
            ("submission.views.oj.judge_task.send", None),
            ("submission.views.oj.SubmissionAPI.throttling", None),
        ):
            patcher = mock.patch(target, return_value=value)
            patched = patcher.start()
            self.addCleanup(patcher.stop)
            if target.endswith("judge_task.send"):
                self.judge_task = patched

    def snapshot(self):
        self.problem.refresh_from_db()
        self.user.userprofile.refresh_from_db()
        return deepcopy({
            "problem": (self.problem.submission_number, self.problem.accepted_number,
                        self.problem.statistic_info),
            "profile_statistics": (self.user.userprofile.submission_number,
                                   self.user.userprofile.accepted_number,
                                   self.user.userprofile.total_score),
            "acm_rank": list(ACMContestRank.objects.filter(contest=self.contest).values()),
            "oi_rank": list(OIContestRank.objects.filter(contest=self.contest).values()),
            "participations": ContestParticipation.objects.filter(contest=self.contest).count(),
        })

    def finish_local(self, submission):
        dispatcher = JudgeDispatcher(submission.id, self.problem.id)
        dispatcher.submission.result = JudgeStatus.ACCEPTED
        dispatcher.submission.statistic_info = {"score": 100}
        dispatcher.submission.save()
        dispatcher.finalize_submission()

    def test_local_practice_is_judged_without_changing_contest_statistics(self):
        for rule in ("ACM", "OI"):
            with self.subTest(rule=rule):
                self.contest.rule_type = self.problem.rule_type = rule
                self.contest.save()
                self.problem.save()
                before = self.snapshot()
                response = self.client.post(self.url, self.submission_data)
                self.assertSuccess(response)
                submission = Submission.objects.get(id=response.data["data"]["submission_id"])
                self.judge_task.assert_called_with(submission.id, self.problem.id)
                self.finish_local(submission)
                submission.refresh_from_db()
                self.assertEqual(submission.result, JudgeStatus.ACCEPTED)
                self.assertEqual(submission.contest_id, self.contest.id)
                self.assertEqual(self.snapshot(), before)
                self.assert_practice_mark(rule)

    def test_remote_practice_preserves_existing_acm_and_oi_rankings(self):
        ACMContestRank.objects.create(contest=self.contest, user=self.user, submission_number=3)
        OIContestRank.objects.create(contest=self.contest, user=self.user, total_score=50)
        self.problem.judge_mode = ProblemJudgeMode.REMOTE
        self.problem.remote_oj = RemoteOJ.CODEFORCES
        self.problem.remote_problem_id = "4A"
        self.problem.remote_problem_data = {
            "url": "https://codeforces.com/problemset/problem/4/A",
            "contest_id": 4, "index": "A", "language_ids": {"C": "43"},
        }
        for rule in ("ACM", "OI"):
            with self.subTest(rule=rule):
                self.contest.rule_type = self.problem.rule_type = rule
                self.contest.save()
                self.problem.save()
                before = self.snapshot()
                created = self.client.post(self.url, self.submission_data)
                self.assertSuccess(created)
                self.assertIn("remote_task", created.data["data"])
                response = self.client.post(self.reverse("remote_submission_event_api"), {
                    "submission_id": created.data["data"]["submission_id"],
                    "provider": RemoteOJ.CODEFORCES, "status": "FINISHED",
                    "remote_submission_id": "practice-1001", "verdict": "ACCEPTED", "score": 100,
                })
                self.assertSuccess(response)
                self.assertEqual(response.data["data"]["result"], JudgeStatus.ACCEPTED)
                self.assertEqual(self.snapshot(), before)
                self.assert_practice_mark(rule)
        self.judge_task.assert_not_called()

    def assert_practice_mark(self, rule):
        self.user.userprofile.refresh_from_db()
        statuses = getattr(self.user.userprofile, f"{rule.lower()}_problems_status")
        self.assertEqual(statuses["contest_problems"][str(self.problem.id)]["status"], JudgeStatus.ACCEPTED)

    def test_official_submission_finished_after_deadline_still_counts(self):
        for rule, rank_model in (("ACM", ACMContestRank), ("OI", OIContestRank)):
            with self.subTest(rule=rule):
                self.contest.rule_type = self.problem.rule_type = rule
                self.contest.save()
                self.problem.save()
                submission = Submission.objects.create(
                    problem=self.problem, contest=self.contest, user_id=self.user.id,
                    username=self.user.username, language="C", code="int main() {}",
                )
                Submission.objects.filter(pk=submission.id).update(
                    create_time=self.contest.end_time - timedelta(seconds=10),
                )
                before = self.problem.submission_number
                with mock.patch("judge.dispatcher.cache.delete") as invalidate:
                    self.finish_local(submission)
                self.problem.refresh_from_db()
                self.assertEqual(self.problem.submission_number, before + 1)
                rank = rank_model.objects.get(contest=self.contest, user=self.user)
                if rule == "ACM":
                    self.assertEqual(rank.accepted_number, 1)
                else:
                    self.assertEqual(rank.total_score, 100)
                invalidate.assert_called_once()

    def test_pre_contest_test_finished_during_contest_does_not_count(self):
        self.contest.end_time = timezone.now() + timedelta(hours=1)
        self.contest.save()
        submission = Submission.objects.create(
            problem=self.problem, contest=self.contest, user_id=self.user.id,
            username=self.user.username, language="C", code="int main() {}",
        )
        Submission.objects.filter(pk=submission.id).update(
            create_time=self.contest.start_time - timedelta(seconds=1),
        )
        before = self.snapshot()
        self.finish_local(submission)
        self.assertEqual(self.snapshot(), before)

    def test_ended_password_contest_is_public_practice_without_registration(self):
        self.contest.password = "private-contest"
        self.contest.allowed_ip_ranges = ["192.0.2.0/24"]
        self.contest.save()
        self.problem._id = "A"
        self.problem.save(update_fields=["_id"])
        self.assertFalse(ContestParticipation.objects.filter(contest=self.contest, user=self.user).exists())

        # A user who never registered or entered the password can still practice.
        self.assertSuccess(self.client.post(self.url, self.submission_data))
        self.judge_task.assert_called_once()

        contest_id = self.contest.id
        contest_problem_url = self.reverse("contest_problem_api")
        self.assertSuccess(self.client.get(f"{contest_problem_url}?contest_id={contest_id}"))
        detail = self.client.get(f"{contest_problem_url}?contest_id={contest_id}&problem_id=A")
        self.assertSuccess(detail)
        self.assertIn("submission_number", detail.data["data"])
        self.assertSuccess(self.client.get(
            f"{self.reverse('contest_announcement_api')}?contest_id={contest_id}"))
        self.assertSuccess(self.client.get(
            f"{self.reverse('contest_submission_list_api')}?contest_id={contest_id}&limit=10"))
        self.assertSuccess(self.client.get(
            f"{self.reverse('contest_rank_api')}?contest_id={contest_id}&limit=10"))

    def test_active_password_contest_still_requires_registration(self):
        self.contest.password = "private-contest"
        self.contest.end_time = timezone.now() + timedelta(hours=1)
        self.contest.save()
        self.assertFailed(self.client.post(self.url, self.submission_data),
                          "Please register for the contest first")

    def test_active_contest_still_requires_registration_and_allowed_ip(self):
        self.contest.end_time = timezone.now() + timedelta(hours=1)
        self.contest.save()
        self.assertFailed(self.client.post(self.url, self.submission_data),
                          "Please register for the contest first")
        ContestParticipation.objects.create(contest=self.contest, user=self.user)
        self.assertFailed(self.client.post(self.url, self.submission_data),
                          "Your IP is not allowed in this contest")
        self.judge_task.assert_not_called()
