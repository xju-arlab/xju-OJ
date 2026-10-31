import copy
import io
import json
import os
import tempfile
from datetime import timedelta
from unittest import mock
from zipfile import ZipFile

from django.core.cache import cache
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone
from PIL import Image as PILImage

from judge.statistics import refresh_submission_statistics
from problem.contest_authoring import alphabetic_display_id, order_contest_problems
from problem.models import Problem, ProblemTag
from problem.publication import publish_due_contest_problems
from problem.tests import DEFAULT_PROBLEM_DATA
from submission.models import JudgeStatus, Submission
from utils.api.tests import APITestCase
from utils.constants import (CacheKey, ContestPrepRole, ContestPrepState, PREP_PLACEHOLDER_DAYS,
                             PUBLISH_DEFAULT_HOURS)
from .models import (ACMContestRank, Contest, ContestAnnouncement, ContestParticipation, ContestPrepInvite,
                     ContestPrepMember, ContestPrepPlanItem)

PREP_CONTEST_DATA = {"title": "Regional prep", "description": "<p>prep</p>", "rule_type": "ACM",
                     "password": "secret", "real_time_rank": True, "allowed_ip_ranges": ["10.0.0.0/8"]}


class ContestPrepTestBase(APITestCase):
    def setUp(self):
        self.creator = self.create_admin("creator", "creator-pass", login=False)
        self.organizer = self.create_user("organizer", "organizer-pass", login=False)
        self.teammate = self.create_user("teammate", "teammate-pass", login=False)
        self.stranger = self.create_user("stranger", "stranger-pass", login=False)
        self.contest = self.make_prep_contest()

    def make_prep_contest(self, start_offset=timedelta(days=-2), duration=timedelta(hours=5)):
        # Default window already ended: an ended contest is public practice
        # material, so this also checks that preparation privacy wins.
        start = timezone.now() + start_offset
        contest = Contest.objects.create(created_by=self.creator, start_time=start, end_time=start + duration,
                                         prep_state=ContestPrepState.PREPARATION, **PREP_CONTEST_DATA)
        for user in (self.organizer, self.teammate):
            ContestPrepMember.objects.create(contest=contest, user=user, role=ContestPrepRole.ORGANIZER)
        return contest

    def add_problem(self, contest, visible=True, tagged=True, **extra):
        data = copy.deepcopy(DEFAULT_PROBLEM_DATA)
        tags = data.pop("tags") if tagged else []
        data.pop("tags", None)
        data.update(_id=extra.pop("_id", None) or self.next_label(contest), contest=contest,
                    created_by=extra.pop("created_by", self.organizer), visible=visible, **extra)
        problem = Problem.objects.create(**data)
        for name in tags:
            problem.tags.add(ProblemTag.objects.get_or_create(name=name)[0])
        return problem

    @staticmethod
    def next_label(contest):
        return alphabetic_display_id(Problem.objects.filter(contest=contest).count())

    def login(self, user):
        self.client.force_login(user)

    def problem_payload(self, **extra):
        data = copy.deepcopy(DEFAULT_PROBLEM_DATA)
        data.pop("visible")
        data["contest_id"] = self.contest.id
        data.update(extra)
        return data


class ContestPrepCreationTest(ContestPrepTestBase):
    def test_admin_creates_private_preparation_contest(self):
        self.login(self.creator)
        payload = dict(PREP_CONTEST_DATA, visible=False, preparation=True)
        before = timezone.now()
        response = self.client.post(self.reverse("contest_admin_api"), data=payload)
        self.assertSuccess(response)
        contest = Contest.objects.get(id=response.data["data"]["id"])
        self.assertEqual(contest.prep_state, ContestPrepState.PREPARATION)
        self.assertTrue(contest.visible)
        # The window is only chosen on publish; the workspace keeps a placeholder.
        self.assertGreaterEqual(contest.start_time, before)
        self.assertEqual(contest.end_time - contest.start_time, timedelta(days=PREP_PLACEHOLDER_DAYS))

        normal = dict(PREP_CONTEST_DATA, visible=True)
        self.assertFailed(self.client.post(self.reverse("contest_admin_api"), data=normal),
                          "Start time and end time are required")

        payload["rule_type"] = "AI"
        self.assertFailed(self.client.post(self.reverse("contest_admin_api"), data=payload),
                          "Preparation contests support ACM and OI only")

    def test_regular_user_cannot_create(self):
        self.login(self.organizer)
        response = self.client.post(self.reverse("contest_admin_api"), data=dict(PREP_CONTEST_DATA, preparation=True))
        self.assertEqual(response.data["error"], "login-required")


class ContestPrepVisibilityTest(ContestPrepTestBase):
    def test_hidden_from_strangers_even_after_the_window(self):
        self.add_problem(self.contest)
        cid = self.contest.id
        for user in (None, self.stranger):
            self.client.logout()
            if user:
                self.login(user)
            listing = self.client.get(self.reverse("contest_list_api") + "?limit=50").data["data"]
            self.assertNotIn(cid, [item["id"] for item in listing["results"]])
            self.assertFailed(self.client.get(self.reverse("contest_api") + f"?id={cid}"))
            self.assertFailed(self.client.get(self.reverse("contest_problem_api") + f"?contest_id={cid}"))
            self.assertFailed(self.client.get(self.reverse("contest_rank_api") + f"?contest_id={cid}"))
            self.assertFailed(self.client.get(
                self.reverse("contest_announcement_api") + f"?contest_id={cid}"))
            self.assertFailed(self.client.get(
                self.reverse("contest_submission_list_api") + f"?contest_id={cid}&limit=10"))
        self.assertFailed(self.client.get(self.reverse("contest_access_api") + f"?contest_id={cid}"),
                          "Contest does not exist")
        self.assertFailed(self.client.post(self.reverse("contest_password_api"),
                                           data={"contest_id": cid, "password": "secret"}))
        self.assertFailed(self.client.post(self.reverse("contest_registration_api"),
                                           data={"contest_id": cid, "password": "secret"}))
        prep_list = self.client.get(self.reverse("contest_list_api") + "?limit=50&prep=1").data["data"]
        self.assertEqual(prep_list["total"], 0)

    def test_admins_outside_the_team_cannot_reach_it(self):
        from account.models import AdminType, ProblemPermission
        problem = self.add_problem(self.contest, visible=False)
        run = Submission.objects.create(user_id=self.teammate.id, username="teammate", code="int main(){}",
                                        language="C", problem=problem, contest=self.contest)
        outsider = self.create_user("outsider", "outsider-pass", admin_type=AdminType.ADMIN,
                                    problem_permission=ProblemPermission.ALL, login=False)
        root = self.create_super_admin(login=False)
        cid = self.contest.id
        self.login(outsider)
        self.assertFailed(self.client.get(self.reverse("contest_api") + f"?id={cid}"))
        self.assertFailed(self.client.get(self.reverse("contest_admin_api") + f"?id={cid}"))
        self.assertFailed(self.client.get(self.reverse("contest_problem_admin_api") + f"?contest_id={cid}"))
        self.assertFailed(self.client.get(self.reverse("problem_admin_api") + f"?id={problem.id}"),
                          "Problem does not exist")
        self.assertFailed(self.client.get(self.reverse("submission_api") + f"?id={run.id}"),
                          "No permission for this submission")
        prep_list = self.client.get(self.reverse("contest_list_api") + "?limit=50&prep=1").data["data"]
        self.assertEqual(prep_list["total"], 0)
        # Super admins and the creator use the admin console; every organizer reads the team's runs.
        for user in (root, self.creator):
            self.login(user)
            self.assertSuccess(self.client.get(self.reverse("problem_admin_api") + f"?id={problem.id}"))
            self.assertSuccess(self.client.get(self.reverse("submission_api") + f"?id={run.id}"))
        self.login(self.organizer)
        self.assertSuccess(self.client.get(self.reverse("submission_api") + f"?id={run.id}"))
        self.assertFailed(self.client.get(self.reverse("problem_admin_api") + f"?id={problem.id}"))

    def test_members_find_it_in_the_preparation_list(self):
        self.contest.prep_problem_count = 13
        self.contest.save()
        for user, role in ((self.creator, "Creator"), (self.organizer, "Organizer"), (self.teammate, "Organizer")):
            self.login(user)
            listing = self.client.get(self.reverse("contest_list_api") + "?limit=50&prep=1").data["data"]
            self.assertEqual([item["id"] for item in listing["results"]], [self.contest.id])
            # Members also find it in the full list, but not under a time status filter.
            full = self.client.get(self.reverse("contest_list_api") + "?limit=50").data["data"]
            self.assertIn(self.contest.id, [item["id"] for item in full["results"]])
            ended = self.client.get(self.reverse("contest_list_api") + "?limit=50&status=-1").data["data"]
            self.assertNotIn(self.contest.id, [item["id"] for item in ended["results"]])
            detail = self.client.get(self.reverse("contest_api") + f"?id={self.contest.id}").data["data"]
            self.assertEqual((detail["prep_role"], detail["prep_problem_count"]), (role, 13))
            self.assertTrue(detail["registered"])
            self.assertEqual("password" in detail, role == "Creator")
            # The review view asks the whole team for the contest password, like the real contest.
            access_url = self.reverse("contest_access_api") + f"?contest_id={self.contest.id}"
            self.assertEqual(self.client.get(access_url).data["data"], {"access": False})
            self.assertFailed(self.client.post(self.reverse("contest_password_api"),
                                               data={"contest_id": self.contest.id, "password": "wrong"}))
            self.assertSuccess(self.client.post(self.reverse("contest_password_api"),
                                                data={"contest_id": self.contest.id, "password": "secret"}))
            self.assertEqual(self.client.get(access_url).data["data"], {"access": True})

    def test_tags_of_preparation_problems_stay_private(self):
        problem = self.add_problem(self.contest)
        problem.tags.set([ProblemTag.objects.create(name="secret-prep-tag")])
        names = [item["name"] for item in self.client.get(self.reverse("problem_tag_list_api")).data["data"]]
        self.assertNotIn("secret-prep-tag", names)


@mock.patch("submission.views.oj.judge_task.send")
class ContestPrepVerificationTest(ContestPrepTestBase):
    def setUp(self):
        super().setUp()
        self.contest = self.make_prep_contest(start_offset=timedelta(days=3))
        self.first = self.add_problem(self.contest)
        self.second = self.add_problem(self.contest, created_by=self.teammate)

    def submit(self, problem):
        return self.client.post(self.reverse("submission_api"), data={
            "problem_id": problem.id, "language": "C", "code": "int main(){}", "contest_id": self.contest.id})

    def test_the_team_tests_every_problem_without_registration(self, judge_send):
        self.login(self.teammate)
        listing = self.client.get(self.reverse("contest_problem_api") + f"?contest_id={self.contest.id}")
        self.assertEqual([item["id"] for item in listing.data["data"]], [self.first.id, self.second.id])
        self.assertSuccess(self.client.get(self.reverse("contest_problem_api") +
                                           f"?contest_id={self.contest.id}&problem_id={self.second._id}"))
        # Outside the window, without password and outside the venue IP ranges.
        response = self.submit(self.first)
        self.assertSuccess(response)
        self.assertIn("submission_id", response.data["data"])
        self.assertSuccess(self.submit(self.second))
        submissions = self.client.get(self.reverse("contest_submission_list_api") +
                                      f"?contest_id={self.contest.id}&limit=10").data["data"]
        self.assertEqual(submissions["total"], 2)
        workspace = self.client.get(self.reverse("contest_prep_problem_api") + f"?contest_id={self.contest.id}")
        self.assertEqual(len(workspace.data["data"]), 2)
        self.login(self.stranger)
        self.assertFailed(self.submit(self.first))

    def test_statistics_ignore_verification_runs(self, judge_send):
        contest = self.make_prep_contest()
        problem = self.add_problem(contest)
        submission = Submission.objects.create(user_id=self.teammate.id, username="teammate", code="x",
                                               language="C", problem=problem, contest=contest,
                                               result=JudgeStatus.ACCEPTED, statistic_info={})
        refresh_submission_statistics(submission)
        problem.refresh_from_db()
        self.assertEqual(problem.accepted_number, 0)
        self.assertFalse(ACMContestRank.objects.filter(contest=contest).exists())
        self.teammate.userprofile.refresh_from_db()
        self.assertEqual(self.teammate.userprofile.acm_problems_status.get("contest_problems", {}), {})


class ContestPrepManagementTest(ContestPrepTestBase):
    def test_only_the_creator_manages_roles(self):
        url = self.reverse("contest_prep_member_api")
        newcomer = self.create_user("newcomer", "newcomer-pass", login=False)
        self.login(self.organizer)
        self.assertFailed(self.client.post(url, data={"contest_id": self.contest.id, "username": "newcomer"}),
                          "Only the contest creator can do this")
        self.organizer.userprofile.real_name = "李出题"
        self.organizer.userprofile.save()
        members = self.client.get(url + f"?contest_id={self.contest.id}").data["data"]
        self.assertEqual(members["creator"]["username"], "creator")
        self.assertIn("real_name", members["creator"])
        self.assertEqual({item["user"]["username"]: item["user"]["real_name"]
                          for item in members["members"]}["organizer"], "李出题")
        self.assertEqual({(item["user"]["username"], item["role"]) for item in members["members"]},
                         {("organizer", "Organizer"), ("teammate", "Organizer")})

        self.login(self.creator)
        self.assertSuccess(self.client.post(url, data={"contest_id": self.contest.id, "username": "newcomer"}))
        self.assertEqual(self.contest.prep_members.get(user=newcomer).role, "Organizer")
        self.assertFailed(self.client.post(url, data={"contest_id": self.contest.id, "username": "newcomer"}),
                          "The user is already a member")
        self.assertFailed(self.client.post(url, data={"contest_id": self.contest.id, "username": "creator"}))
        self.assertSuccess(self.client.delete(url + f"?contest_id={self.contest.id}&user_id={newcomer.id}"))
        newcomer.userprofile.real_name = "张三"
        newcomer.userprofile.save()
        for keyword in ("new", "张"):
            search = self.client.get(self.reverse("contest_prep_user_search_api") +
                                     f"?contest_id={self.contest.id}&keyword={keyword}").data["data"]
            self.assertEqual(search, [{"id": newcomer.id, "username": "newcomer", "real_name": "张三"}])

    def test_organizers_add_problems_and_keep_editing_during_review(self):
        url = self.reverse("contest_prep_problem_api")
        self.login(self.stranger)
        self.assertFailed(self.client.post(url, data=self.problem_payload()), "Contest does not exist")

        self.login(self.organizer)
        # Every problem belongs to the contest, whatever the form sends.
        response = self.client.post(url, data=self.problem_payload(visible=False))
        self.assertSuccess(response)
        problem = Problem.objects.get(id=response.data["data"]["id"])
        self.assertEqual((problem._id, problem.visible, problem.contest_id), ("A", True, self.contest.id))

        self.login(self.creator)
        self.assertSuccess(self.client.post(self.reverse("contest_prep_review_api"),
                                            data={"contest_id": self.contest.id}))
        self.login(self.teammate)
        # The workspace stays open while a review round runs.
        edit = self.problem_payload(id=problem.id, visible=False, title="renamed")
        self.assertSuccess(self.client.put(url, data=edit))
        problem.refresh_from_db()
        self.assertEqual((problem.title, problem.visible, problem._id), ("renamed", True, "A"))
        self.assertSuccess(self.client.delete(url + f"?contest_id={self.contest.id}&id={problem.id}"))

    def test_delete_keeps_working_after_verification_runs_and_closes_the_gap(self):
        first = self.add_problem(self.contest)
        second = self.add_problem(self.contest)
        Submission.objects.create(user_id=self.teammate.id, username="teammate", code="x", language="C",
                                  problem=first, contest=self.contest)
        self.login(self.organizer)
        self.assertSuccess(self.client.delete(self.reverse("contest_prep_problem_api") +
                                              f"?contest_id={self.contest.id}&id={first.id}"))
        self.assertFalse(Problem.objects.filter(id=first.id).exists())
        second.refresh_from_db()
        self.assertEqual(second._id, "A")

    def test_reorder_relabels_problems(self):
        first, second, third = (self.add_problem(self.contest) for _ in range(3))
        url = self.reverse("contest_prep_problem_order_api")
        self.login(self.organizer)
        response = self.client.put(url, data={"contest_id": self.contest.id,
                                              "problem_ids": [third.id, first.id, second.id]})
        self.assertSuccess(response)
        self.assertEqual([(item["id"], item["_id"]) for item in response.data["data"]],
                         [(third.id, "A"), (first.id, "B"), (second.id, "C")])
        self.assertFailed(self.client.put(url, data={"contest_id": self.contest.id,
                                                     "problem_ids": [third.id, first.id]}))
        self.assertFailed(self.client.put(url, data={"contest_id": self.contest.id,
                                                     "problem_ids": [third.id, third.id, first.id]}))

    def test_order_sorts_double_letter_labels_after_z(self):
        labels = [alphabetic_display_id(index) for index in range(28)]
        for label in reversed(labels):
            self.add_problem(self.contest, _id=label)
        ordered = list(order_contest_problems(Problem.objects.filter(contest=self.contest))
                       .values_list("_id", flat=True))
        self.assertEqual(ordered, labels)
        self.assertEqual(ordered[-3:], ["Z", "AA", "AB"])

    def test_admin_console_rules_for_preparation_problems(self):
        problem = self.add_problem(self.contest)
        self.login(self.creator)
        self.assertFailed(self.client.post(self.reverse("make_public_api"), data={"id": problem.id}),
                          "Problems of a preparation contest can't be made public")
        problem.publish_after_contest = True
        problem.save()
        self.assertEqual(publish_due_contest_problems([self.contest.id]), [])
        self.assertFalse(Problem.objects.filter(contest__isnull=True, title=problem.title).exists())


class ContestPrepPlanTest(ContestPrepTestBase):
    def setUp(self):
        super().setUp()
        self.url = self.reverse("contest_prep_plan_api")
        self.count_url = self.reverse("contest_prep_problem_count_api")

    def add(self, difficulty="Low", **extra):
        return self.client.post(self.url, data={"contest_id": self.contest.id, "difficulty": difficulty, **extra})

    def test_only_the_creator_sets_the_problem_count(self):
        self.login(self.organizer)
        self.assertFailed(self.client.put(self.count_url, data={"contest_id": self.contest.id, "problem_count": 2}),
                          "Only the contest creator can do this")
        self.login(self.creator)
        self.assertSuccess(self.client.put(self.count_url, data={"contest_id": self.contest.id, "problem_count": 2}))
        self.contest.refresh_from_db()
        self.assertEqual(self.contest.prep_problem_count, 2)
        self.assertFailed(self.client.put(self.count_url, data={"contest_id": self.contest.id, "problem_count": 0}))
        self.assertSuccess(self.client.put(self.count_url, data={"contest_id": self.contest.id,
                                                                 "problem_count": None}))

    def test_organizers_plan_problems_up_to_the_count(self):
        self.contest.prep_problem_count = 2
        self.contest.save()
        self.login(self.teammate)
        self.assertFailed(self.add("Mid", assignee_id=self.stranger.id),
                          "Only the creator or an organizer can take this problem")
        first = self.add("Low", assignee_id=self.organizer.id, tags=["图论", "图论", " 最短路 "])
        self.assertSuccess(first)
        item = first.data["data"]
        self.assertEqual((item["difficulty"], item["assignee"]["username"], item["tags"]),
                         ("Low", "organizer", ["图论", "最短路"]))
        second = self.add("High")
        self.assertSuccess(second)
        self.assertIsNone(second.data["data"]["assignee"])
        self.assertFailed(self.add("Mid"), "This contest takes 2 problems and the plan is full")

        # Anyone on the team edits any item: claim it, move it, retag it.
        edit = self.client.put(self.url, data={"contest_id": self.contest.id, "id": second.data["data"]["id"],
                                               "assignee_id": self.teammate.id, "difficulty": "Mid", "tags": ["DP"]})
        self.assertSuccess(edit)
        self.assertEqual((edit.data["data"]["assignee"]["username"], edit.data["data"]["difficulty"]),
                         ("teammate", "Mid"))
        self.assertFailed(self.client.put(self.url, data={"contest_id": self.contest.id, "id": item["id"],
                                                          "assignee_id": self.stranger.id}))

        self.login(self.creator)
        self.assertFailed(self.client.put(self.count_url, data={"contest_id": self.contest.id, "problem_count": 1}),
                          "2 problems are planned; remove some before lowering the count")
        self.login(self.organizer)
        self.assertSuccess(self.client.delete(self.url + f"?contest_id={self.contest.id}&id={item['id']}"))
        listing = self.client.get(self.url + f"?contest_id={self.contest.id}").data["data"]
        self.assertEqual([entry["difficulty"] for entry in listing["items"]], ["Mid"])

        self.login(self.stranger)
        self.assertFailed(self.client.get(self.url + f"?contest_id={self.contest.id}"), "Contest does not exist")

    def test_progress_counts_uploads_against_assignments(self):
        for user in (self.organizer, self.organizer, self.teammate):
            ContestPrepPlanItem.objects.create(contest=self.contest, difficulty="Low", assignee=user)
        ContestPrepPlanItem.objects.create(contest=self.contest, difficulty="High")
        self.add_problem(self.contest)
        self.add_problem(self.contest, created_by=self.creator)
        self.login(self.teammate)
        progress = self.client.get(self.url + f"?contest_id={self.contest.id}").data["data"]["progress"]
        self.assertEqual([(row["username"], row["assigned"], row["uploaded"]) for row in progress],
                         [("creator", 0, 1), ("organizer", 2, 1), ("teammate", 1, 0)])


class ContestPrepPackageTest(ContestPrepTestBase):
    def setUp(self):
        super().setUp()
        self.test_case_root = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(TEST_CASE_DIR=self.test_case_root.name)
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        self.test_case_root.cleanup()

    def package(self, rule_type="ACM", visible=True):
        info = {"title": "Imported", "description": {"format": "html", "value": "<p>d</p>"},
                "input_description": {"format": "html", "value": "i"},
                "output_description": {"format": "html", "value": "o"},
                "hint": {"format": "html", "value": ""},
                "test_case_score": [{"score": 100, "input_name": "1.in", "output_name": "1.out"}],
                "time_limit": 1000, "memory_limit": 256, "samples": [{"input": "1", "output": "2"}],
                "template": {}, "spj": None, "rule_type": rule_type, "source": "", "tags": ["imported"],
                "difficulty": "Low", "visible": visible, "languages": ["C++"]}
        buffer = io.BytesIO()
        with ZipFile(buffer, "w") as archive:
            archive.writestr("problem.json", json.dumps(info))
            archive.writestr("testcase/1.in", "1\n")
            archive.writestr("testcase/1.out", "2\n")
        return SimpleUploadedFile("problem.zip", buffer.getvalue(), content_type="application/zip")

    def test_organizers_import_packages_into_the_contest(self):
        self.add_problem(self.contest)
        url = self.reverse("contest_prep_import_problem_api")
        self.login(self.stranger)
        self.assertFailed(self.client.post(url, data={"contest_id": self.contest.id, "file": self.package()},
                                           format="multipart"))
        self.login(self.teammate)
        response = self.client.post(url, data={"contest_id": self.contest.id, "file": self.package()},
                                    format="multipart")
        self.assertSuccess(response)
        problem = Problem.objects.get(id=response.data["data"]["imported"][0]["id"])
        self.assertEqual((problem.contest_id, problem._id, problem.visible, problem.share_submission),
                         (self.contest.id, "B", True, True))

        response = self.client.post(url, data={"contest_id": self.contest.id, "file": self.package("OI")},
                                    format="multipart")
        self.assertFailed(response)
        self.assertEqual(Problem.objects.filter(contest=self.contest).count(), 2)

    def test_organizers_upload_test_cases(self):
        buffer = io.BytesIO()
        with ZipFile(buffer, "w") as archive:
            archive.writestr("1.in", "1\n")
            archive.writestr("1.out", "2\n")
        url = self.reverse("contest_prep_test_case_api")

        def upload():
            return self.client.post(url, data={"contest_id": self.contest.id, "spj": "false",
                                               "file": SimpleUploadedFile("cases.zip", buffer.getvalue())},
                                    format="multipart")
        self.login(self.stranger)
        self.assertFailed(upload())
        self.login(self.teammate)
        response = upload()
        self.assertSuccess(response)
        self.assertEqual(len(response.data["data"]["info"]), 1)


class ContestPrepPublishTest(ContestPrepTestBase):
    def setUp(self):
        super().setUp()
        self.second = self.add_problem(self.contest, title="second")
        self.first = self.add_problem(self.contest, title="first", accepted_number=3, submission_number=5)
        ContestAnnouncement.objects.create(contest=self.contest, title="Welcome", content="<p>hi</p>",
                                           created_by=self.creator)
        self.url = self.reverse("contest_prep_publish_api")

    def test_only_the_creator_publishes(self):
        self.login(self.organizer)
        self.assertFailed(self.client.post(self.url, data={"contest_id": self.contest.id}),
                          "Only the contest creator can do this")
        self.login(self.creator)
        self.assertSuccess(self.client.post(self.url, data={"contest_id": self.contest.id}))

    def test_publish_without_times_starts_a_fresh_default_window(self):
        # The preparation window is only a placeholder, so a publish that leaves
        # the times out gets the usual default length starting now.
        self.login(self.creator)
        before = timezone.now()
        response = self.client.post(self.url, data={"contest_id": self.contest.id})
        self.assertSuccess(response)
        published = Contest.objects.get(id=response.data["data"]["id"])
        self.assertGreaterEqual(published.start_time, before)
        self.assertEqual(published.end_time - published.start_time,
                         timedelta(hours=PUBLISH_DEFAULT_HOURS))

    def test_publish_needs_exactly_the_planned_number_of_problems(self):
        self.contest.prep_problem_count = 3
        self.contest.save()
        self.login(self.creator)
        self.assertFailed(self.client.post(self.url, data={"contest_id": self.contest.id}),
                          "This contest takes 3 problems, but 2 are uploaded")
        Problem.objects.filter(contest=self.contest).delete()
        self.contest.prep_problem_count = None
        self.contest.save()
        self.assertFailed(self.client.post(self.url, data={"contest_id": self.contest.id}),
                          "Upload the contest problems before publishing")

    @mock.patch("contest.prep_publish.schedule_contest_problem_publication")
    def test_publish_copies_the_problems_into_a_new_public_contest(self, schedule):
        self.login(self.creator)
        self.assertSuccess(self.client.put(self.reverse("contest_prep_problem_order_api"),
                                           data={"contest_id": self.contest.id,
                                                 "problem_ids": [self.first.id, self.second.id]}))

        start = timezone.now() + timedelta(days=7)
        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(self.url, data={
                "contest_id": self.contest.id, "title": "Regional final", "start_time": start.isoformat(),
                "end_time": (start + timedelta(hours=5)).isoformat()})
        self.assertSuccess(response)
        published = Contest.objects.get(id=response.data["data"]["id"])
        self.assertEqual((published.title, published.prep_state, published.published_from_id, published.visible),
                         ("Regional final", None, self.contest.id, True))
        # The review password is not carried over; the publish form sets the contest's own.
        self.assertEqual((published.password, published.rule_type, published.created_by_id),
                         (None, "ACM", self.creator.id))
        copies = list(order_contest_problems(Problem.objects.filter(contest=published)))
        self.assertEqual([(item._id, item.title) for item in copies], [("A", "first"), ("B", "second")])
        self.assertEqual(copies[0].test_case_id, self.first.test_case_id)
        self.assertEqual((copies[0].accepted_number, copies[0].submission_number), (0, 0))
        self.assertEqual(list(copies[0].tags.values_list("name", flat=True)), ["test"])
        self.assertEqual(list(published.contestannouncement_set.values_list("title", flat=True)), ["Welcome"])
        # The copies join the public library once the contest ends.
        self.assertTrue(all(item.publish_after_contest for item in copies))
        schedule.assert_called_once_with(published.id, published.end_time)

        detail = self.client.get(self.reverse("contest_api") + f"?id={self.contest.id}").data["data"]
        self.assertEqual([item["id"] for item in detail["published_contests"]], [published.id])
        self.login(self.stranger)
        public = self.client.get(self.reverse("contest_list_api") + "?limit=50").data["data"]
        ids = [item["id"] for item in public["results"]]
        self.assertIn(published.id, ids)
        self.assertNotIn(self.contest.id, ids)
        published_detail = self.client.get(self.reverse("contest_api") + f"?id={published.id}").data["data"]
        self.assertNotIn("published_from", published_detail)

        self.login(self.creator)
        bad = self.client.post(self.url, data={"contest_id": self.contest.id, "start_time": start.isoformat(),
                                               "end_time": start.isoformat()})
        self.assertFailed(bad, "Start time must occur earlier than end time")

    def test_published_problems_join_the_library_after_the_contest(self):
        library = self.add_problem(None, _id="1001", title="library")
        Problem.objects.filter(id=self.second.id).update(is_public=True, title=library.title)
        self.login(self.creator)
        start = timezone.now() - timedelta(hours=6)
        with self.captureOnCommitCallbacks(execute=False):
            response = self.client.post(self.url, data={
                "contest_id": self.contest.id, "start_time": start.isoformat(),
                "end_time": (start + timedelta(hours=5)).isoformat()})
        self.assertSuccess(response)
        published = Contest.objects.get(id=response.data["data"]["id"])
        published_ids = {item._id for item in publish_due_contest_problems([published.id])}
        library_titles = set(Problem.objects.filter(contest__isnull=True).values_list("title", flat=True))
        # The new problem is published under a fresh numeric ID; the library copy is not duplicated.
        self.assertEqual(library_titles, {"library", "first"})
        self.assertEqual(len(published_ids), 1)
        self.assertTrue(published_ids.pop().isdigit())
        self.assertTrue(Problem.objects.get(contest__isnull=True, title="first").visible)


class ContestPrepReviewTest(ContestPrepTestBase):
    def setUp(self):
        super().setUp()
        self.released = self.add_problem(self.contest, title="released")
        self.draft = self.add_problem(self.contest, title="draft")
        self.feedback_url = self.reverse("contest_prep_feedback_api")
        self.review_url = self.reverse("contest_prep_review_api")

    def start_review(self, **extra):
        self.login(self.creator)
        response = self.client.post(self.review_url, data={"contest_id": self.contest.id, **extra})
        self.assertSuccess(response)
        self.contest.refresh_from_db()
        return response

    def run_as(self, user, problem, result, minutes):
        submission = Submission.objects.create(
            user_id=user.id, username=user.username, code="x", language="C", problem=problem,
            contest=self.contest, result=result, statistic_info={})
        # create_time is auto_now_add, so place the run on the review clock afterwards.
        Submission.objects.filter(id=submission.id).update(
            create_time=self.contest.review_started_at + timedelta(minutes=minutes))
        return submission

    def test_the_team_writes_and_resolves_feedback_at_any_time(self):
        payload = {"contest_id": self.contest.id, "problem_id": self.draft.id, "content": "Sample 2 is wrong"}
        self.login(self.teammate)
        response = self.client.post(self.feedback_url, data=payload)
        self.assertSuccess(response)
        feedback_id = response.data["data"]["id"]

        self.login(self.organizer)
        listing = self.client.get(self.feedback_url + f"?contest_id={self.contest.id}&problem_id={self.draft.id}")
        self.assertEqual([item["content"] for item in listing.data["data"]], ["Sample 2 is wrong"])
        problems = self.client.get(self.reverse("contest_prep_problem_api") + f"?contest_id={self.contest.id}")
        self.assertEqual({item["title"]: item["feedback_count"] for item in problems.data["data"]},
                         {"released": 0, "draft": 1})
        self.assertSuccess(self.client.put(self.feedback_url, data={"contest_id": self.contest.id,
                                                                    "id": feedback_id, "resolved": True}))
        problems = self.client.get(self.reverse("contest_prep_problem_api") + f"?contest_id={self.contest.id}")
        self.assertEqual(sum(item["feedback_count"] for item in problems.data["data"]), 0)
        self.assertFailed(self.client.delete(self.feedback_url + f"?contest_id={self.contest.id}&id={feedback_id}"),
                          "Only the author can delete this feedback")

        self.login(self.stranger)
        self.assertFailed(self.client.get(self.feedback_url + f"?contest_id={self.contest.id}"))

    def test_the_team_sees_real_names_on_remarks_and_problems(self):
        for user, name in ((self.organizer, "李出题"), (self.teammate, "王验题")):
            user.userprofile.real_name = name
            user.userprofile.save(update_fields=["real_name"])
        self.login(self.teammate)
        response = self.client.post(self.feedback_url, data={"contest_id": self.contest.id,
                                                             "problem_id": self.draft.id, "content": "Check n = 0"})
        self.assertEqual(response.data["data"]["user"]["real_name"], "王验题")
        listing = self.client.get(self.feedback_url + f"?contest_id={self.contest.id}")
        self.assertEqual([item["user"]["real_name"] for item in listing.data["data"]], ["王验题"])
        problems = self.client.get(self.reverse("contest_prep_problem_api") + f"?contest_id={self.contest.id}")
        self.assertEqual({item["created_by"]["real_name"] for item in problems.data["data"]}, {"李出题"})
        self.assertEqual({item["difficulty"] for item in problems.data["data"]}, {self.draft.difficulty})

    def test_review_round_is_started_by_the_creator_and_keeps_the_password(self):
        self.login(self.organizer)
        self.assertFailed(self.client.post(self.review_url, data={"contest_id": self.contest.id}),
                          "Only the contest creator can do this")
        response = self.start_review(password="mock-day")
        self.assertEqual(response.data["data"]["password"], "mock-day")
        self.assertEqual(self.contest.password, "mock-day")
        self.assertIsNotNone(self.contest.review_started_at)
        # Leaving the password out keeps it; a blank one clears it.
        self.start_review()
        self.assertEqual(self.contest.password, "mock-day")
        self.start_review(password="")
        self.assertIsNone(self.contest.password)

        Problem.objects.filter(contest=self.contest).delete()
        self.login(self.creator)
        self.assertFailed(self.client.post(self.review_url, data={"contest_id": self.contest.id}),
                          "Upload the contest problems before starting a review")

    def test_review_leaderboard_ranks_members_and_tags_authors(self):
        self.start_review()
        second = self.add_problem(self.contest, title="second")
        before = Submission.objects.create(user_id=self.teammate.id, username="teammate", code="x", language="C",
                                           problem=self.released, contest=self.contest,
                                           result=JudgeStatus.ACCEPTED, statistic_info={})
        Submission.objects.filter(id=before.id).update(
            create_time=self.contest.review_started_at - timedelta(minutes=5))
        self.run_as(self.teammate, self.released, JudgeStatus.WRONG_ANSWER, 3)
        self.run_as(self.teammate, self.released, JudgeStatus.ACCEPTED, 10)
        self.run_as(self.organizer, self.released, JudgeStatus.ACCEPTED, 12)
        self.run_as(self.organizer, second, JudgeStatus.ACCEPTED, 20)
        self.run_as(self.organizer, self.draft, JudgeStatus.ACCEPTED, 25)

        self.login(self.teammate)
        data = self.client.get(self.reverse("contest_prep_rank_api") + f"?contest_id={self.contest.id}").data["data"]
        self.assertEqual([item["_id"] for item in data["problems"]], ["A", "B", "C"])
        rows = {row["user"]["username"]: row for row in data["results"]}
        self.assertEqual([row["user"]["username"] for row in data["results"]], ["organizer", "teammate", "creator"])
        self.assertEqual((rows["organizer"]["accepted_number"], rows["organizer"]["authored"]), (3, ["A", "B", "C"]))
        self.assertEqual((rows["teammate"]["role"], rows["teammate"]["authored"]), ("Organizer", []))
        cell = rows["teammate"]["submission_info"][str(self.released.id)]
        self.assertEqual((cell["is_ac"], cell["error_number"], cell["is_first_ac"]), (True, 1, True))
        self.assertEqual(rows["teammate"]["total_time"], 10 * 60 + 20 * 60)
        self.assertEqual(rows["creator"]["accepted_number"], 0)

    def test_review_problem_list_shows_own_status_and_counts(self):
        self.start_review()
        self.run_as(self.teammate, self.released, JudgeStatus.WRONG_ANSWER, 1)
        self.run_as(self.teammate, self.released, JudgeStatus.ACCEPTED, 2)
        self.run_as(self.organizer, self.released, JudgeStatus.WRONG_ANSWER, 3)
        self.login(self.teammate)
        problems = self.client.get(self.reverse("contest_problem_api") + f"?contest_id={self.contest.id}").data["data"]
        self.assertEqual([(item["_id"], item["my_status"], item["submission_number"], item["accepted_number"])
                          for item in problems], [("A", 0, 3, 1), ("B", None, 0, 0)])

    def test_each_review_round_restarts_the_clock(self):
        self.start_review()
        started = self.contest.review_started_at
        self.start_review()
        self.assertGreater(self.contest.review_started_at, started)

    def test_a_round_has_no_time_limit(self):
        # A round keeps running however long the team takes; only the creator ends it.
        self.start_review()
        Contest.objects.filter(id=self.contest.id).update(
            review_started_at=timezone.now() - timedelta(hours=30))
        self.contest.refresh_from_db()
        self.assertEqual(self.contest.review_window(), (self.contest.review_started_at, None))
        self.assertTrue(self.contest.review_running())
        # A run made a day into the round still reaches the board and the counts.
        self.run_as(self.teammate, self.released, JudgeStatus.ACCEPTED, 29 * 60)
        self.login(self.teammate)
        board = self.client.get(self.reverse("contest_prep_rank_api")
                                + f"?contest_id={self.contest.id}").data["data"]
        self.assertEqual({row["user"]["username"]: row["accepted_number"] for row in board["results"]},
                         {"teammate": 1, "organizer": 0, "creator": 0})
        problems = self.client.get(self.reverse("contest_problem_api")
                                   + f"?contest_id={self.contest.id}").data["data"]
        self.assertEqual([(item["_id"], item["submission_number"], item["accepted_number"])
                          for item in problems], [("A", 1, 1), ("B", 0, 0)])

    def test_the_creator_ends_a_round(self):
        url = self.review_url + f"?contest_id={self.contest.id}"
        self.login(self.creator)
        self.assertFailed(self.client.delete(url), "No review round is running")
        self.start_review()
        self.run_as(self.teammate, self.released, JudgeStatus.ACCEPTED, 0)
        self.login(self.organizer)
        self.assertFailed(self.client.delete(url), "Only the contest creator can do this")
        self.login(self.creator)
        self.assertSuccess(self.client.delete(url))
        self.contest.refresh_from_db()
        self.assertFalse(self.contest.review_running())
        # Runs after the end no longer reach the board; the next round starts afresh.
        late = Submission.objects.create(user_id=self.organizer.id, username="organizer", code="x", language="C",
                                         problem=self.released, contest=self.contest,
                                         result=JudgeStatus.ACCEPTED, statistic_info={})
        Submission.objects.filter(id=late.id).update(create_time=self.contest.review_ended_at + timedelta(seconds=1))
        board = self.client.get(self.reverse("contest_prep_rank_api") + f"?contest_id={self.contest.id}").data["data"]
        self.assertEqual({row["user"]["username"]: row["accepted_number"] for row in board["results"]},
                         {"teammate": 1, "organizer": 0, "creator": 0})
        self.start_review()
        self.assertIsNone(self.contest.review_ended_at)
        self.assertTrue(self.contest.review_running())


class ContestPrepPublicProblemTest(ContestPrepTestBase):
    def test_organizers_copy_a_library_problem_into_the_contest(self):
        url = self.reverse("contest_prep_public_problem_api")
        library = self.add_problem(None, _id="1001", title="library")
        hidden = self.add_problem(None, _id="1002", visible=False)
        oi_problem = self.add_problem(None, _id="1003", rule_type="OI")
        self.login(self.stranger)
        self.assertFailed(self.client.post(url, data={"contest_id": self.contest.id, "problem_id": library.id}))
        self.login(self.teammate)
        response = self.client.post(url, data={"contest_id": self.contest.id, "problem_id": library.id})
        self.assertSuccess(response)
        copy = Problem.objects.get(id=response.data["data"]["id"])
        self.assertEqual((copy.contest_id, copy._id, copy.visible, copy.title, copy.created_by_id),
                         (self.contest.id, "A", True, "library", self.teammate.id))
        self.assertEqual(list(copy.tags.values_list("name", flat=True)), ["test"])
        library.refresh_from_db()
        self.assertIsNone(library.contest_id)
        self.assertFailed(self.client.post(url, data={"contest_id": self.contest.id, "problem_id": hidden.id}),
                          "Problem does not exist")
        self.assertFailed(self.client.post(url, data={"contest_id": self.contest.id, "problem_id": oi_problem.id}))


class ContestPrepInviteTest(ContestPrepTestBase):
    def setUp(self):
        super().setUp()
        self.newcomer = self.create_user("newcomer", "newcomer-pass", login=False)
        self.other = self.create_user("other", "other-pass", login=False)
        for user in (self.creator, self.newcomer, self.other):
            cache.delete(f"{CacheKey.prep_invite_failures}:{user.id}")

    def create_invite(self):
        self.login(self.creator)
        response = self.client.post(self.reverse("contest_prep_invite_api"), data={"contest_id": self.contest.id})
        self.assertSuccess(response)
        return response.data["data"]["token"]

    def accept(self, user, token):
        self.login(user)
        return self.client.post(self.reverse("contest_prep_invite_accept_api"), data={"token": token})

    def test_only_the_creator_creates_links_and_only_a_digest_is_stored(self):
        self.login(self.organizer)
        self.assertFailed(self.client.post(self.reverse("contest_prep_invite_api"),
                                           data={"contest_id": self.contest.id}),
                          "Only the contest creator can do this")
        token = self.create_invite()
        self.assertGreaterEqual(len(token), 40)
        invite = ContestPrepInvite.objects.get(contest=self.contest)
        self.assertNotIn(token, invite.token_hash)
        self.assertGreater(invite.expire_time, timezone.now() + timedelta(days=6))
        counts = self.client.get(self.reverse("contest_prep_invite_api") + f"?contest_id={self.contest.id}")
        self.assertEqual(counts.data["data"]["open"], {"Organizer": 1})

    def test_a_link_works_exactly_once(self):
        token = self.create_invite()
        response = self.accept(self.newcomer, token)
        self.assertSuccess(response)
        self.assertEqual(response.data["data"], {"contest_id": self.contest.id, "title": self.contest.title,
                                                 "role": "Organizer"})
        self.assertEqual(self.contest.prep_members.get(user=self.newcomer).role, "Organizer")
        invite = ContestPrepInvite.objects.get(contest=self.contest)
        self.assertEqual(invite.used_by, self.newcomer)
        self.assertFailed(self.accept(self.other, token), "This invite link is invalid or has expired")
        self.assertFalse(self.contest.prep_members.filter(user=self.other).exists())

    def test_members_do_not_consume_a_link(self):
        token = self.create_invite()
        self.assertFailed(self.accept(self.teammate, token), "You are already a member of this contest")
        self.assertFailed(self.accept(self.creator, token), "You are already a member of this contest")
        self.assertSuccess(self.accept(self.newcomer, token))

    def test_expired_revoked_and_published_links_are_refused(self):
        expired = self.create_invite()
        ContestPrepInvite.objects.update(expire_time=timezone.now() - timedelta(seconds=1))
        self.assertFailed(self.accept(self.newcomer, expired), "This invite link is invalid or has expired")

        revoked = self.create_invite()
        revoked_id = ContestPrepInvite.objects.latest("id").id
        kept = self.create_invite()
        url = self.reverse("contest_prep_invite_api") + f"?contest_id={self.contest.id}"
        listing = self.client.get(url).data["data"]["invites"]
        self.assertEqual([item["status"] for item in listing], ["active", "active", "expired"])
        self.assertEqual(self.client.delete(url + f"&id={revoked_id}").data["data"], {"revoked": 1})
        self.assertFailed(self.accept(self.newcomer, revoked), "This invite link is invalid or has expired")
        self.login(self.creator)
        self.assertEqual(self.client.delete(url).data["data"], {"revoked": 1})
        self.assertFailed(self.accept(self.newcomer, kept), "This invite link is invalid or has expired")
        self.login(self.creator)
        statuses = [item["status"] for item in self.client.get(url).data["data"]["invites"]]
        self.assertEqual(statuses, ["revoked", "revoked", "expired"])

        stale = self.create_invite()
        Contest.objects.filter(id=self.contest.id).update(prep_state=None)
        self.assertFailed(self.accept(self.newcomer, stale), "This invite link is invalid or has expired")
        self.assertFalse(ContestPrepMember.objects.filter(user=self.newcomer).exists())

    def test_guessing_is_throttled(self):
        for _ in range(10):
            self.assertFailed(self.accept(self.newcomer, "x" * 43), "This invite link is invalid or has expired")
        token = self.create_invite()
        self.assertFailed(self.accept(self.newcomer, token), "Too many invalid invite links, try again later")
        self.assertSuccess(self.accept(self.other, token))


class ContestPrepImageUploadTest(ContestPrepTestBase):
    def setUp(self):
        super().setUp()
        self.url = self.reverse("contest_prep_image_upload_api")
        self.upload_root = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(UPLOAD_DIR=self.upload_root.name)
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        self.upload_root.cleanup()

    @staticmethod
    def image_file(name, image_format):
        buffer = io.BytesIO()
        PILImage.new("RGB", (4, 3), (200, 40, 40)).save(buffer, format=image_format)
        return SimpleUploadedFile(name, buffer.getvalue())

    def upload(self, image):
        return self.client.post(self.url, data={"contest_id": self.contest.id, "image": image}, format="multipart")

    def test_organizers_upload_images_named_by_their_real_format(self):
        self.login(self.organizer)
        response = self.upload(self.image_file("statement.webp", "WEBP"))
        self.assertSuccess(response)
        path = response.data["data"]["file_path"]
        self.assertTrue(path.startswith("/public/upload/") and path.endswith(".webp"))
        self.assertTrue(os.path.isfile(os.path.join(self.upload_root.name, os.path.basename(path))))
        # A PNG called .gif is stored as what it is.
        response = self.upload(self.image_file("figure.gif", "PNG"))
        self.assertTrue(response.data["data"]["file_path"].endswith(".png"))

    def test_non_images_and_strangers_are_refused(self):
        self.login(self.organizer)
        self.assertFailed(self.upload(SimpleUploadedFile("evil.png", b"<script>alert(1)</script>")),
                          "Unsupported file format")
        self.login(self.stranger)
        self.assertFailed(self.upload(self.image_file("a.png", "PNG")), "Contest does not exist")
        self.assertEqual(os.listdir(self.upload_root.name), [])


class ContestPrepTeamPublishTest(ContestPrepTestBase):
    def setUp(self):
        super().setUp()
        self.add_problem(self.contest, title="only")
        self.url = self.reverse("contest_prep_publish_api")

    def test_team_publish_creates_registered_accounts_and_drops_the_password(self):
        self.login(self.creator)
        start = timezone.now() + timedelta(days=1)
        response = self.client.post(self.url, data={
            "contest_id": self.contest.id, "password": "ignored", "start_time": start.isoformat(),
            "end_time": (start + timedelta(hours=5)).isoformat(),
            "rank_freeze_time": (start + timedelta(hours=4)).isoformat(),
            "teams": [{"name": "Alpha", "members": ["A1", "A2"]}, {"name": "Beta", "members": []}]}, format="json")
        self.assertSuccess(response)
        published = Contest.objects.get(id=response.data["data"]["id"])
        self.assertIsNone(published.password)
        self.assertEqual(published.rank_freeze_time, start + timedelta(hours=4))
        teams = response.data["data"]["teams"]
        self.assertEqual([team["name"] for team in teams], ["Alpha", "Beta"])
        self.assertTrue(all(team["password"] for team in teams))
        self.assertEqual(ContestParticipation.objects.filter(contest=published).count(), 2)

    def test_a_bad_roster_publishes_nothing(self):
        self.login(self.creator)
        before = Contest.objects.count()
        response = self.client.post(self.url, data={
            "contest_id": self.contest.id,
            "teams": [{"name": "Alpha", "members": []}, {"name": "Alpha", "members": []}]}, format="json")
        self.assertFailed(response)
        self.assertEqual(Contest.objects.count(), before)
