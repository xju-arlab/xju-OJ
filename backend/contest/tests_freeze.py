from datetime import timedelta

from django.utils import timezone

from judge.statistics import refresh_submission_statistics
from problem.models import Problem
from submission.models import JudgeStatus, Submission
from submission.tests import DEFAULT_PROBLEM_DATA
from utils.api.tests import APITestCase

from .models import ACMContestRank, Contest, ContestParticipation


class RankFreezeTest(APITestCase):
    """The board froze 4 hours into a 5 hour contest that has now ended."""

    def setUp(self):
        self.root = self.create_super_admin(login=False)
        start = timezone.now() - timedelta(hours=6)
        self.contest = Contest.objects.create(
            title="Freeze", description="", real_time_rank=True, rule_type="ACM", created_by=self.root,
            start_time=start, end_time=start + timedelta(hours=5), rank_freeze_time=start + timedelta(hours=4))
        data = dict(DEFAULT_PROBLEM_DATA, contest=self.contest, created_by=self.root, _id="A")
        data.pop("tags")
        self.problem = Problem.objects.create(**data)
        self.alice = self.create_user("alice", "alice123", login=False)
        self.bob = self.create_user("bob", "bob1234", login=False)
        for user in (self.alice, self.bob):
            ContestParticipation.objects.create(contest=self.contest, user=user)
            ACMContestRank.objects.create(contest=self.contest, user=user)
        self.submit(self.alice, JudgeStatus.WRONG_ANSWER, 10)
        self.submit(self.alice, JudgeStatus.ACCEPTED, 30)
        self.submit(self.bob, JudgeStatus.WRONG_ANSWER, 20)
        self.late = self.submit(self.bob, JudgeStatus.ACCEPTED, 245)
        self.rank_url = self.reverse("contest_rank_api")

    def submit(self, user, result, minutes):
        submission = Submission.objects.create(problem=self.problem, contest=self.contest, user_id=user.id,
                                               username=user.username, code="int main() {}", language="C",
                                               result=result)
        Submission.objects.filter(pk=submission.pk).update(
            create_time=self.contest.start_time + timedelta(minutes=minutes))
        submission.refresh_from_db()
        refresh_submission_statistics(submission)
        return submission

    def login(self, username, password):
        self.client.logout()
        self.client.login(username=username, password=password)

    def rank(self, **params):
        response = self.client.get(self.rank_url, data={"contest_id": self.contest.id, "limit": 10, **params})
        self.assertSuccess(response)
        return response.data["data"]

    def test_participants_see_the_board_as_it_stood_with_later_attempts_pending(self):
        self.login("alice", "alice123")
        board = self.rank()
        self.assertTrue(board["frozen"])
        self.assertEqual([row["user"]["username"] for row in board["results"]], ["alice", "bob"])
        alice, bob = board["results"]
        self.assertEqual((alice["accepted_number"], alice["total_time"]), (1, 30 * 60 + 1200))
        self.assertTrue(alice["submission_info"][str(self.problem.id)]["is_first_ac"])
        info = bob["submission_info"][str(self.problem.id)]
        self.assertEqual((bob["accepted_number"], info["is_ac"], info["error_number"], info["frozen_number"]),
                         (0, False, 1, 1))

    def test_contest_admin_sees_the_live_board_and_may_preview_the_frozen_one(self):
        self.login("root", "root")
        live = self.rank()
        self.assertFalse(live["frozen"])
        self.assertEqual(sorted(row["accepted_number"] for row in live["results"]), [1, 1])
        preview = self.rank(frozen="1")
        self.assertTrue(preview["frozen"])
        self.assertEqual([row["accepted_number"] for row in preview["results"]], [1, 0])

    def test_unfreezing_publishes_the_final_board(self):
        url = self.reverse("contest_rank_freeze_api")
        self.create_admin("other", "other123")
        self.assertFailed(self.client.post(url, data={"contest_id": self.contest.id, "unfrozen": True}))
        self.login("root", "root")
        self.assertSuccess(self.client.post(url, data={"contest_id": self.contest.id, "unfrozen": True}))
        self.login("alice", "alice123")
        board = self.rank()
        self.assertFalse(board["frozen"])
        self.assertEqual(sorted(row["accepted_number"] for row in board["results"]), [1, 1])

    def test_nothing_is_hidden_before_the_freeze_time(self):
        Contest.objects.filter(pk=self.contest.pk).update(rank_freeze_time=timezone.now() + timedelta(hours=1),
                                                          end_time=timezone.now() + timedelta(hours=2))
        self.login("alice", "alice123")
        self.assertFalse(self.rank()["frozen"])

    def test_problem_counters_stop_at_the_freeze(self):
        url = self.reverse("contest_problem_api")
        self.login("alice", "alice123")
        problem = self.client.get(url, data={"contest_id": self.contest.id}).data["data"][0]
        self.assertEqual((problem["submission_number"], problem["accepted_number"]), (3, 1))
        detail = self.client.get(url, data={"contest_id": self.contest.id, "problem_id": "A"}).data["data"]
        self.assertEqual(detail["statistic_info"], {str(JudgeStatus.WRONG_ANSWER): 2, str(JudgeStatus.ACCEPTED): 1})
        self.login("root", "root")
        problem = self.client.get(url, data={"contest_id": self.contest.id}).data["data"][0]
        self.assertEqual((problem["submission_number"], problem["accepted_number"]), (4, 2))

    def test_later_attempts_of_others_stay_hidden(self):
        url = self.reverse("contest_submission_list_api")
        self.login("alice", "alice123")
        listed = self.client.get(url, data={"contest_id": self.contest.id, "limit": 10}).data["data"]["results"]
        self.assertEqual(len(listed), 3)
        self.assertNotIn(self.late.id, [item["id"] for item in listed])
        detail = self.client.get(self.reverse("submission_api"), data={"id": self.late.id})
        self.assertFailed(detail)
        self.login("bob", "bob1234")
        listed = self.client.get(url, data={"contest_id": self.contest.id, "limit": 10}).data["data"]["results"]
        self.assertIn(self.late.id, [item["id"] for item in listed])

    def test_freeze_time_must_fall_inside_an_acm_contest(self):
        self.login("root", "root")
        url = self.reverse("contest_admin_api")
        start = timezone.now() + timedelta(days=1)
        data = {"title": "Next", "description": "", "rule_type": "ACM", "password": "", "visible": True,
                "real_time_rank": True, "allowed_ip_ranges": [], "start_time": start.isoformat(),
                "end_time": (start + timedelta(hours=5)).isoformat()}
        outside = dict(data, rank_freeze_time=(start + timedelta(hours=6)).isoformat())
        self.assertFailed(self.client.post(url, data=outside, format="json"))
        inside = dict(data, rank_freeze_time=(start + timedelta(hours=4)).isoformat())
        response = self.client.post(url, data=inside, format="json")
        self.assertSuccess(response)
        contest = Contest.objects.get(id=response.data["data"]["id"])
        self.assertEqual(contest.rank_freeze_time, start + timedelta(hours=4))
        oi = self.client.post(url, data=dict(inside, rule_type="OI"), format="json")
        self.assertIsNone(Contest.objects.get(id=oi.data["data"]["id"]).rank_freeze_time)
