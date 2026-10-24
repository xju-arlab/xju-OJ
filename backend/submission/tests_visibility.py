from copy import deepcopy
from datetime import timedelta

from django.utils import timezone

from contest.models import Contest, ContestPrepMember
from problem.models import Problem
from utils.api.tests import APITestCase
from utils.constants import ContestPrepRole, ContestPrepState
from .models import JudgeStatus, Submission
from .tests import DEFAULT_PROBLEM_DATA


class ContestCodeVisibilityTest(APITestCase):
    """Ended contests open every submission's code; the submitter's IP stays private."""

    def setUp(self):
        self.admin = self.create_admin("contest-admin", "admin-pass", login=False)
        self.author = self.create_user("author", "author-pass", login=False)
        self.reader = self.create_user("reader", "reader-pass", login=False)

    def make_contest(self, ended, prep_state=None):
        now = timezone.now()
        start = now - timedelta(hours=3)
        end = now - timedelta(hours=1) if ended else now + timedelta(hours=1)
        return Contest.objects.create(title="c", description="", rule_type="ACM", password=None,
                                      real_time_rank=True, start_time=start, end_time=end,
                                      created_by=self.admin, prep_state=prep_state)

    def make_submission(self, contest, rule_type="ACM"):
        data = deepcopy(DEFAULT_PROBLEM_DATA)
        data.pop("tags")
        data.update(_id=f"P{Problem.objects.count()}", contest=contest, created_by=self.admin, rule_type=rule_type)
        problem = Problem.objects.create(**data)
        return Submission.objects.create(user_id=self.author.id, username="author", code="int main(){}",
                                         language="C", problem=problem, contest=contest, ip="10.1.2.3",
                                         result=JudgeStatus.ACCEPTED, statistic_info={},
                                         create_time=contest.start_time + timedelta(minutes=5) if contest else None)

    def detail(self, submission):
        return self.client.get(self.reverse("submission_api") + f"?id={submission.id}")

    def test_ended_contest_code_is_open_without_the_ip(self):
        submission = self.make_submission(self.make_contest(ended=True), rule_type="OI")
        self.client.force_login(self.reader)
        response = self.detail(submission)
        self.assertSuccess(response)
        self.assertEqual(response.data["data"]["code"], "int main(){}")
        self.assertNotIn("ip", response.data["data"])
        self.assertFalse(response.data["data"]["can_unshare"])

        listing = self.client.get(self.reverse("contest_submission_list_api") +
                                  f"?contest_id={submission.contest_id}&limit=10").data["data"]
        self.assertTrue(listing["results"][0]["show_link"])

        self.client.force_login(self.author)
        self.assertEqual(self.detail(submission).data["data"]["ip"], "10.1.2.3")

    def test_running_contest_code_stays_private(self):
        submission = self.make_submission(self.make_contest(ended=False))
        self.client.force_login(self.reader)
        self.assertFailed(self.detail(submission), "No permission for this submission")
        self.client.force_login(self.author)
        self.assertSuccess(self.detail(submission))

    def test_public_problem_code_still_needs_sharing(self):
        submission = self.make_submission(None)
        self.client.force_login(self.reader)
        self.assertFailed(self.detail(submission), "No permission for this submission")
        submission.shared = True
        submission.save()
        self.assertSuccess(self.detail(submission))

    def test_preparation_runs_are_for_creator_and_setters_only(self):
        contest = self.make_contest(ended=True, prep_state=ContestPrepState.PREVIEW)
        setter = self.create_user("setter", "setter-pass", login=False)
        verifier = self.create_user("verifier", "verifier-pass", login=False)
        ContestPrepMember.objects.create(contest=contest, user=setter, role=ContestPrepRole.SETTER)
        ContestPrepMember.objects.create(contest=contest, user=verifier, role=ContestPrepRole.VERIFIER)
        submission = self.make_submission(contest)
        for user, allowed in ((self.reader, False), (verifier, False), (setter, True)):
            self.client.force_login(user)
            response = self.detail(submission)
            if allowed:
                self.assertSuccess(response)
            else:
                self.assertFailed(response)
