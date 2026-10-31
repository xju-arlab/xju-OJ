import re
import shutil
import unittest
from datetime import timedelta
from unittest import mock

from django.test import override_settings
from django.utils import timezone

from account.models import User
from problem.models import Problem
from submission.models import Submission
from submission.tests import DEFAULT_PROBLEM_DATA
from utils.api.tests import APITestCase

from .models import ACMContestRank, Contest, ContestParticipation, ContestTeam
from .team_sheet import compile_team_sheet, render_team_sheet


class ContestTeamTest(APITestCase):
    def setUp(self):
        self.root = self.create_super_admin()
        self.contest = Contest.objects.create(
            title="Team contest", description="", real_time_rank=True, rule_type="ACM", created_by=self.root,
            password="secret", start_time=timezone.now() - timedelta(hours=1),
            end_time=timezone.now() + timedelta(hours=4))
        self.url = self.reverse("contest_team_admin_api")

    def generate(self, *teams):
        response = self.client.post(self.url, data={"contest_id": self.contest.id, "teams": [
            {"name": name, "members": members} for name, members in teams]}, format="json")
        self.assertSuccess(response)
        return response.data["data"]

    def login(self, username, password):
        self.client.logout()
        return self.client.post(self.reverse("user_login_api"), data={"username": username, "password": password},
                                format="json")

    def test_each_roster_row_becomes_a_registered_team_account(self):
        first, second = self.generate(("算法一队", [" 张三 ", "李四", ""]), ("Team B", ["Ann"]))
        for item in (first, second):
            self.assertRegex(item["username"], r"^team-[a-z]{4}$")
            self.assertRegex(item["password"], r"^[A-Za-z0-9]{8}$")
            self.assertTrue(re.search(r"\d", item["password"]) and re.search(r"[A-Za-z]", item["password"]))
        self.assertNotEqual(first["username"], second["username"])
        team = ContestTeam.objects.get(name="算法一队")
        self.assertEqual(team.members, ["张三", "李四"])
        self.assertEqual(team.user.userprofile.real_name, "张三,李四")
        self.assertEqual(ContestTeam.objects.get(name="Team B").user.userprofile.real_name, "Ann")
        self.assertTrue(ContestParticipation.objects.filter(contest=self.contest, user=team.user).exists())
        self.assertTrue(ACMContestRank.objects.filter(contest=self.contest, user=team.user).exists())
        listed = self.client.get(self.url, data={"contest_id": self.contest.id}).data["data"]
        self.assertEqual([item["name"] for item in listed], ["算法一队", "Team B"])
        self.assertNotIn("password", listed[0])

    @override_settings(AUTHENTIK_OIDC_ENABLED=True, AUTHENTIK_LOCAL_LOGIN_ENABLED=False)
    def test_team_accounts_keep_password_login_when_only_sso_is_allowed(self):
        item = self.generate(("Team A", []))[0]
        self.create_user("student", "student123", login=False)
        self.assertFailed(self.login("student", "student123"), "Please login with Authentik")
        self.assertSuccess(self.login(item["username"], item["password"]))
        # The light generation hash is upgraded to Django's default on first login.
        self.assertNotIn("$20000$", User.objects.get(username=item["username"]).password)
        access = self.client.get(self.reverse("contest_access_api"), data={"contest_id": self.contest.id})
        self.assertTrue(access.data["data"]["access"])
        rank = self.client.get(self.reverse("contest_rank_api"), data={"contest_id": self.contest.id, "limit": 10})
        self.assertEqual(rank.data["data"]["results"][0]["team"], {"name": "Team A", "members": []})
        profile = self.client.get(self.reverse("user_profile_api")).data["data"]
        self.assertEqual(profile["team"]["contest_id"], self.contest.id)

    def test_duplicate_team_names_are_rejected(self):
        self.generate(("Team A", []))
        for teams in ([{"name": "Team A", "members": []}],
                      [{"name": "Team C", "members": []}, {"name": "Team C", "members": []}]):
            response = self.client.post(self.url, data={"contest_id": self.contest.id, "teams": teams}, format="json")
            self.assertFailed(response)
        self.assertEqual(ContestTeam.objects.count(), 1)

    def test_only_contest_admins_manage_team_accounts(self):
        self.create_admin()
        response = self.client.post(self.url, data={"contest_id": self.contest.id,
                                                    "teams": [{"name": "Team A", "members": []}]}, format="json")
        self.assertFailed(response)
        self.assertFalse(ContestTeam.objects.exists())

    def test_team_accounts_stay_out_of_site_accounts(self):
        item = self.generate(("Team A", []))[0]
        users = self.client.get(self.reverse("user_admin_api"), data={"limit": 50}).data["data"]["results"]
        self.assertNotIn(item["username"], [user["username"] for user in users])
        data = dict(DEFAULT_PROBLEM_DATA, created_by=self.root)
        data.pop("tags")
        problem = Problem.objects.create(**data)
        self.login(item["username"], item["password"])
        response = self.client.post(self.reverse("submission_api"), data={
            "problem_id": problem.id, "language": "C", "code": "int main() {}"}, format="json")
        self.assertFailed(response, "A team account only submits in its own contest")

    def test_reset_password_and_delete(self):
        item, busy = self.generate(("Team A", []), ("Team B", []))
        reset = self.client.put(self.url, data={"contest_id": self.contest.id, "id": item["id"]}, format="json")
        self.assertSuccess(reset)
        password = reset.data["data"]["password"]
        self.assertNotEqual(password, item["password"])
        self.assertTrue(User.objects.get(id=item["user_id"]).check_password(password))

        data = dict(DEFAULT_PROBLEM_DATA, contest=self.contest, created_by=self.root, _id="A")
        data.pop("tags")
        problem = Problem.objects.create(**data)
        Submission.objects.create(problem=problem, contest=self.contest, user_id=busy["user_id"],
                                  username=busy["username"], code="int main() {}", language="C")
        self.assertFailed(self.client.delete(f"{self.url}?contest_id={self.contest.id}&id={busy['id']}"))
        self.assertSuccess(self.client.delete(f"{self.url}?contest_id={self.contest.id}&id={item['id']}"))
        self.assertFalse(User.objects.filter(id=item["user_id"]).exists())
        self.assertTrue(User.objects.filter(id=busy["user_id"]).exists())

    def test_running_team_contest_is_reached_by_link_and_opens_to_all_when_it_ends(self):
        self.generate(("Team A", []))
        data = dict(DEFAULT_PROBLEM_DATA, contest=self.contest, created_by=self.root, _id="A")
        data.pop("tags")
        Problem.objects.create(**data)
        self.create_user("student", "student123")
        listed = self.client.get(self.reverse("contest_list_api"), data={"limit": 10}).data["data"]["results"]
        self.assertNotIn(self.contest.id, [item["id"] for item in listed])
        self.assertFailed(self.client.post(self.reverse("contest_registration_api"),
                                           data={"contest_id": self.contest.id}, format="json"))
        self.client.logout()
        problems = self.reverse("contest_problem_api")
        self.assertFailed(self.client.get(problems, data={"contest_id": self.contest.id}))

        Contest.objects.filter(pk=self.contest.pk).update(start_time=timezone.now() - timedelta(hours=6),
                                                          end_time=timezone.now() - timedelta(hours=1))
        listed = self.client.get(self.reverse("contest_list_api"), data={"limit": 10}).data["data"]["results"]
        self.assertIn(self.contest.id, [item["id"] for item in listed])
        self.assertSuccess(self.client.get(problems, data={"contest_id": self.contest.id}))
        self.assertSuccess(self.client.get(problems, data={"contest_id": self.contest.id, "problem_id": "A"}))
        self.assertSuccess(self.client.get(self.reverse("contest_rank_api"),
                                           data={"contest_id": self.contest.id, "limit": 10}))
        self.assertSuccess(self.client.get(self.reverse("contest_submission_list_api"),
                                           data={"contest_id": self.contest.id, "limit": 10}))


class ContestTeamSheetTest(APITestCase):
    def setUp(self):
        self.root = self.create_super_admin()
        self.contest = Contest.objects.create(
            title="Team contest", description="", real_time_rank=True, rule_type="ACM", created_by=self.root,
            start_time=timezone.now(), end_time=timezone.now() + timedelta(hours=5))
        self.url = self.reverse("contest_team_sheet_api")
        self.teams = [{"name": "A&B_%队", "members": ["赵一"], "username": "team-abcd", "password": "Ab3dEf7g"}]

    def test_every_field_is_escaped_and_each_team_gets_a_row(self):
        source = render_team_sheet("Team & contest", self.teams * 31)
        self.assertIn(r"\xjurow{A\&B\_\%队}{赵一}{team-abcd}{Ab3dEf7g}", source)
        self.assertIn(r"Team \& contest", source)
        self.assertEqual(source.count(r"\xjurow{"), 31)

    def test_contest_admins_download_the_sheet(self):
        with mock.patch("contest.views.admin.compile_team_sheet", return_value=b"%PDF-1.7") as compile_sheet:
            response = self.client.post(self.url, data={"contest_id": self.contest.id, "link": "https://oj/arena/1",
                                                        "teams": self.teams}, format="json")
        self.assertEqual(response["Content-Type"], "application/pdf")
        self.assertEqual(compile_sheet.call_args[0][0], "Team contest · 登录 https://oj/arena/1")
        self.create_admin()
        self.assertFailed(self.client.post(self.url, data={"contest_id": self.contest.id, "teams": self.teams},
                                           format="json"))

    @unittest.skipUnless(shutil.which("xelatex"), "XeLaTeX is not installed")
    def test_the_sheet_typesets(self):
        self.assertTrue(compile_team_sheet("Team contest", self.teams * 7).startswith(b"%PDF"))
