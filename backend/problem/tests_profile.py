import copy

from contest.models import Contest
from django.utils import timezone
from utils.api.tests import APITestCase

from .models import Problem, ProblemFavorite
from .tests import DEFAULT_PROBLEM_DATA


class ProfileProblemTestBase(APITestCase):
    def setUp(self):
        self.owner = self.create_admin("owner", "owner-pass", login=False)
        self.viewer = self.create_user("viewer", "viewer-pass", login=False)

    def add_problem(self, display_id, created_by=None, visible=True, contest=None):
        data = copy.deepcopy(DEFAULT_PROBLEM_DATA)
        data.pop("tags")
        data.update(_id=display_id, title=f"problem {display_id}", created_by=created_by or self.owner,
                    visible=visible, contest=contest)
        return Problem.objects.create(**data)

    def profile_list(self, list_type, username=None):
        url = self.reverse("profile_problem_list_api") + f"?type={list_type}&limit=50"
        if username:
            url += f"&username={username}"
        return self.client.get(url)


class ProblemFavoriteTest(ProfileProblemTestBase):
    def test_favorite_toggle_and_detail_flag(self):
        problem = self.add_problem("1001")
        url = self.reverse("problem_favorite_api")
        self.assertFailed(self.client.post(url, data={"problem_id": problem.id}))

        self.client.force_login(self.viewer)
        self.assertSuccess(self.client.post(url, data={"problem_id": problem.id}))
        self.assertSuccess(self.client.post(url, data={"problem_id": problem.id}))
        self.assertEqual(ProblemFavorite.objects.filter(user=self.viewer).count(), 1)
        detail = self.client.get(self.reverse("problem_api") + "?problem_id=1001").data["data"]
        self.assertTrue(detail["favorited"])

        self.assertSuccess(self.client.delete(url + f"?problem_id={problem.id}"))
        detail = self.client.get(self.reverse("problem_api") + "?problem_id=1001").data["data"]
        self.assertFalse(detail["favorited"])

    def test_only_public_visible_problems_can_be_favorited(self):
        hidden = self.add_problem("1002", visible=False)
        now = timezone.now()
        contest = Contest.objects.create(title="c", description="", rule_type="ACM", real_time_rank=True,
                                         start_time=now, end_time=now, created_by=self.owner)
        contest_problem = self.add_problem("A", contest=contest)
        self.client.force_login(self.viewer)
        for problem in (hidden, contest_problem):
            self.assertFailed(self.client.post(self.reverse("problem_favorite_api"), data={"problem_id": problem.id}),
                              "Problem does not exist")


class ProfileProblemListTest(ProfileProblemTestBase):
    def test_uploaded_lists_public_visible_problems_only(self):
        self.add_problem("1001")
        self.add_problem("1002", visible=False)
        now = timezone.now()
        contest = Contest.objects.create(title="c", description="", rule_type="ACM", real_time_rank=True,
                                         start_time=now, end_time=now, created_by=self.owner,
                                         prep_state="Preparation")
        self.add_problem("A", contest=contest)
        self.client.force_login(self.viewer)
        data = self.profile_list("uploaded", "owner").data["data"]
        self.assertEqual([item["_id"] for item in data["results"]], ["1001"])

    def test_solved_reads_public_accepted_marks(self):
        solved = self.add_problem("1001")
        attempted = self.add_problem("1002")
        profile = self.viewer.userprofile
        profile.acm_problems_status = {
            "problems": {str(solved.id): {"_id": "1001", "status": 0},
                         str(attempted.id): {"_id": "1002", "status": -1}},
            "contest_problems": {"999": {"_id": "A", "status": 0}},
        }
        profile.save()
        self.client.force_login(self.owner)
        data = self.profile_list("solved", "viewer").data["data"]
        self.assertEqual([item["_id"] for item in data["results"]], ["1001"])

    def test_favorites_are_private_to_their_owner(self):
        problem = self.add_problem("1001")
        ProblemFavorite.objects.create(user=self.viewer, problem=problem)
        self.client.force_login(self.viewer)
        data = self.profile_list("favorites").data["data"]
        self.assertEqual([item["id"] for item in data["results"]], [problem.id])
        self.client.force_login(self.owner)
        self.assertFailed(self.profile_list("favorites", "viewer"), "Favorites are private")
        self.assertFailed(self.profile_list("unknown"), "Invalid type")
