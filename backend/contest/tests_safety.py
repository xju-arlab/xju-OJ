import io
import zipfile
from datetime import timedelta

from django.utils import timezone

from contest.models import ACMContestRank, Contest, OIContestRank
from submission.tests import SubmissionPrepare


class ContestManagementSafetyTests(SubmissionPrepare):
    def setUp(self):
        self._create_problem_and_submission()
        self.owner = self.create_admin("owner")
        self.other = self.create_admin("other", login=False)
        self.participant = self.create_user("participant", "test", login=False)
        data = dict(title="Contest", description="", rule_type="ACM", real_time_rank=True,
                    start_time=timezone.now() - timedelta(hours=2),
                    end_time=timezone.now() - timedelta(hours=1))
        self.contest = Contest.objects.create(created_by=self.owner, **data)
        self.other_contest = Contest.objects.create(created_by=self.other, **data)
        self.problem.contest = self.contest
        self.problem.save()
        self.info = {str(self.problem.id): {"is_ac": True, "ac_time": 10,
                                          "error_number": 0, "is_first_ac": True}}
        self.rank = ACMContestRank.objects.create(contest=self.contest, user=self.participant,
                                                 accepted_number=1, submission_info=self.info)
        self.url = self.reverse("acm_contest_helper")

    def test_other_admin_cannot_read_or_change_helper(self):
        self.client.force_login(self.other)
        self.assertFailed(self.client.get(self.url, {"contest_id": self.contest.id}))
        self.assertFailed(self.client.put(self.url, {"contest_id": self.contest.id,
                                                   "rank_id": self.rank.id,
                                                   "problem_id": str(self.problem.id), "checked": True}))
        self.rank.refresh_from_db()
        self.assertEqual(self.rank.submission_info, self.info)

    def test_rank_id_must_belong_to_authorized_contest(self):
        self.client.force_login(self.other)
        self.assertFailed(self.client.put(self.url, {"contest_id": self.other_contest.id,
                                                   "rank_id": self.rank.id,
                                                   "problem_id": str(self.problem.id), "checked": True}))
        self.rank.refresh_from_db()
        self.assertEqual(self.rank.submission_info, self.info)

    def test_owner_can_mark_a_balloon(self):
        self.assertSuccess(self.client.put(self.url, {"contest_id": self.contest.id,
                                                    "rank_id": self.rank.id,
                                                    "problem_id": str(self.problem.id), "checked": True}))
        self.rank.refresh_from_db()
        self.assertTrue(self.rank.submission_info[str(self.problem.id)]["checked"])

    def test_export_tolerates_hidden_and_removed_problem_history(self):
        self.problem.visible = False
        self.problem.save(update_fields=["visible"])
        for rule in ("ACM", "OI"):
            with self.subTest(rule=rule):
                self.contest.rule_type = rule
                self.contest.save(update_fields=["rule_type"])
                if rule == "OI":
                    OIContestRank.objects.create(contest=self.contest, user=self.participant,
                                                 total_score=100, submission_info={str(self.problem.id): 100})
                response = self.client.get(self.reverse("contest_rank_api"), {
                    "contest_id": self.contest.id, "download_csv": "1", "force_refresh": "1"})
                self.assertEqual(response.status_code, 200)
                with zipfile.ZipFile(io.BytesIO(response.content)) as workbook:
                    self.assertIn("xl/worksheets/sheet1.xml", workbook.namelist())
