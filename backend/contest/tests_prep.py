import copy
import io
import json
import tempfile
from datetime import timedelta
from unittest import mock
from zipfile import ZipFile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from judge.statistics import refresh_submission_statistics
from problem.contest_authoring import alphabetic_display_id, order_contest_problems
from problem.models import Problem, ProblemTag
from problem.publication import publish_due_contest_problems
from problem.tests import DEFAULT_PROBLEM_DATA
from submission.models import JudgeStatus, Submission
from utils.api.tests import APITestCase
from utils.constants import ContestPrepRole, ContestPrepState
from .models import ACMContestRank, Contest, ContestAnnouncement, ContestPrepMember

PREP_CONTEST_DATA = {"title": "Regional prep", "description": "<p>prep</p>", "rule_type": "ACM",
                     "password": "secret", "real_time_rank": True, "allowed_ip_ranges": ["10.0.0.0/8"]}


class ContestPrepTestBase(APITestCase):
    def setUp(self):
        self.creator = self.create_admin("creator", "creator-pass", login=False)
        self.setter = self.create_user("setter", "setter-pass", login=False)
        self.verifier = self.create_user("verifier", "verifier-pass", login=False)
        self.stranger = self.create_user("stranger", "stranger-pass", login=False)
        self.contest = self.make_prep_contest()

    def make_prep_contest(self, start_offset=timedelta(days=-2), duration=timedelta(hours=5)):
        # Default window already ended: an ended contest is public practice
        # material, so this also checks that preparation privacy wins.
        start = timezone.now() + start_offset
        contest = Contest.objects.create(created_by=self.creator, start_time=start, end_time=start + duration,
                                         prep_state=ContestPrepState.PREPARATION, **PREP_CONTEST_DATA)
        ContestPrepMember.objects.create(contest=contest, user=self.setter, role=ContestPrepRole.SETTER)
        ContestPrepMember.objects.create(contest=contest, user=self.verifier, role=ContestPrepRole.VERIFIER)
        return contest

    def add_problem(self, contest, visible=True, **extra):
        data = copy.deepcopy(DEFAULT_PROBLEM_DATA)
        tags = data.pop("tags")
        data.update(_id=extra.pop("_id", None) or self.next_label(contest), contest=contest,
                    created_by=self.setter, visible=visible, **extra)
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
        start = timezone.now() + timedelta(days=1)
        payload = dict(PREP_CONTEST_DATA, start_time=start.isoformat(),
                       end_time=(start + timedelta(hours=5)).isoformat(), visible=False, preparation=True)
        response = self.client.post(self.reverse("contest_admin_api"), data=payload)
        self.assertSuccess(response)
        contest = Contest.objects.get(id=response.data["data"]["id"])
        self.assertEqual(contest.prep_state, ContestPrepState.PREPARATION)
        self.assertTrue(contest.visible)

        payload["rule_type"] = "AI"
        self.assertFailed(self.client.post(self.reverse("contest_admin_api"), data=payload),
                          "Preparation contests support ACM and OI only")

    def test_regular_user_cannot_create(self):
        self.login(self.setter)
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
        self.assertFailed(self.client.post(self.reverse("contest_password_api"),
                                           data={"contest_id": cid, "password": "secret"}))
        self.assertFailed(self.client.post(self.reverse("contest_registration_api"),
                                           data={"contest_id": cid, "password": "secret"}))
        prep_list = self.client.get(self.reverse("contest_list_api") + "?limit=50&prep=1").data["data"]
        self.assertEqual(prep_list["total"], 0)

    def test_members_find_it_in_the_preparation_list(self):
        for user, role in ((self.creator, "Creator"), (self.setter, "Setter"), (self.verifier, "Verifier")):
            self.login(user)
            listing = self.client.get(self.reverse("contest_list_api") + "?limit=50&prep=1").data["data"]
            self.assertEqual([item["id"] for item in listing["results"]], [self.contest.id])
            public = self.client.get(self.reverse("contest_list_api") + "?limit=50").data["data"]
            self.assertNotIn(self.contest.id, [item["id"] for item in public["results"]])
            detail = self.client.get(self.reverse("contest_api") + f"?id={self.contest.id}").data["data"]
            self.assertEqual(detail["prep_role"], role)
            self.assertTrue(detail["registered"])
            self.assertEqual("password" in detail, role == "Creator")

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
        self.released = self.add_problem(self.contest, visible=True)
        self.draft = self.add_problem(self.contest, visible=False)

    def submit(self, problem):
        return self.client.post(self.reverse("submission_api"), data={
            "problem_id": problem.id, "language": "C", "code": "int main(){}", "contest_id": self.contest.id})

    def test_verifier_tests_released_problems_without_registration(self, judge_send):
        self.login(self.verifier)
        listing = self.client.get(self.reverse("contest_problem_api") + f"?contest_id={self.contest.id}")
        self.assertEqual([item["id"] for item in listing.data["data"]], [self.released.id])
        self.assertFailed(self.client.get(self.reverse("contest_problem_api") +
                                          f"?contest_id={self.contest.id}&problem_id={self.draft._id}"))
        # Outside the window, without password and outside the venue IP ranges.
        response = self.submit(self.released)
        self.assertSuccess(response)
        self.assertIn("submission_id", response.data["data"])
        self.assertFailed(self.submit(self.draft), "Problem not exist")
        self.assertFailed(self.client.get(self.reverse("contest_prep_problem_api") +
                                          f"?contest_id={self.contest.id}"))

    def test_setter_tests_hidden_drafts(self, judge_send):
        self.login(self.setter)
        self.assertSuccess(self.client.get(self.reverse("contest_problem_api") +
                                           f"?contest_id={self.contest.id}&problem_id={self.draft._id}"))
        self.assertSuccess(self.submit(self.draft))
        submissions = self.client.get(self.reverse("contest_submission_list_api") +
                                      f"?contest_id={self.contest.id}&limit=10").data["data"]
        self.assertEqual(submissions["total"], 1)

    def test_statistics_ignore_verification_runs(self, judge_send):
        contest = self.make_prep_contest()
        problem = self.add_problem(contest)
        submission = Submission.objects.create(user_id=self.verifier.id, username="verifier", code="x",
                                               language="C", problem=problem, contest=contest,
                                               result=JudgeStatus.ACCEPTED, statistic_info={})
        refresh_submission_statistics(submission)
        problem.refresh_from_db()
        self.assertEqual(problem.accepted_number, 0)
        self.assertFalse(ACMContestRank.objects.filter(contest=contest).exists())
        self.verifier.userprofile.refresh_from_db()
        self.assertEqual(self.verifier.userprofile.acm_problems_status.get("contest_problems", {}), {})


class ContestPrepManagementTest(ContestPrepTestBase):
    def test_only_the_creator_manages_roles(self):
        url = self.reverse("contest_prep_member_api")
        newcomer = self.create_user("newcomer", "newcomer-pass", login=False)
        self.login(self.setter)
        self.assertFailed(self.client.post(url, data={"contest_id": self.contest.id, "username": "newcomer",
                                                      "role": "Verifier"}), "Only the contest creator can do this")
        members = self.client.get(url + f"?contest_id={self.contest.id}").data["data"]
        self.assertEqual(members["creator"]["username"], "creator")
        self.assertEqual({item["user"]["username"] for item in members["members"]}, {"setter", "verifier"})

        self.login(self.creator)
        self.assertSuccess(self.client.post(url, data={"contest_id": self.contest.id, "username": "newcomer",
                                                       "role": "Verifier"}))
        self.assertFailed(self.client.post(url, data={"contest_id": self.contest.id, "username": "newcomer",
                                                      "role": "Setter"}), "The user is already a member")
        self.assertFailed(self.client.post(url, data={"contest_id": self.contest.id, "username": "creator",
                                                      "role": "Setter"}))
        self.assertSuccess(self.client.put(url, data={"contest_id": self.contest.id, "user_id": newcomer.id,
                                                      "role": "Setter"}))
        self.assertEqual(self.contest.prep_members.get(user=newcomer).role, "Setter")
        self.assertSuccess(self.client.delete(url + f"?contest_id={self.contest.id}&user_id={newcomer.id}"))
        search = self.client.get(self.reverse("contest_prep_user_search_api") +
                                 f"?contest_id={self.contest.id}&keyword=new").data["data"]
        self.assertEqual(search, [{"id": newcomer.id, "username": "newcomer"}])

    def test_setter_uploads_hidden_problems_and_preview_freezes_them(self):
        url = self.reverse("contest_prep_problem_api")
        self.login(self.verifier)
        self.assertFailed(self.client.post(url, data=self.problem_payload()), "Only problem setters can do this")

        self.login(self.setter)
        response = self.client.post(url, data=self.problem_payload())
        self.assertSuccess(response)
        problem = Problem.objects.get(id=response.data["data"]["id"])
        self.assertEqual((problem._id, problem.visible, problem.contest_id), ("A", False, self.contest.id))
        self.assertFailed(self.client.put(self.reverse("contest_prep_state_api"),
                                          data={"contest_id": self.contest.id, "state": "Preview"}))

        self.login(self.creator)
        self.assertSuccess(self.client.put(self.reverse("contest_prep_state_api"),
                                           data={"contest_id": self.contest.id, "state": "Preview"}))
        self.login(self.setter)
        edit = self.problem_payload(id=problem.id, visible=True, title="renamed")
        self.assertFailed(self.client.put(url, data=edit),
                          "Switch the contest back to preparation before editing problems")
        self.assertFailed(self.client.delete(url + f"?contest_id={self.contest.id}&id={problem.id}"))

        self.contest.prep_state = ContestPrepState.PREPARATION
        self.contest.save()
        self.assertSuccess(self.client.put(url, data=edit))
        problem.refresh_from_db()
        self.assertEqual((problem.title, problem.visible, problem._id), ("renamed", True, "A"))
        self.assertSuccess(self.client.put(self.reverse("contest_prep_problem_visible_api"),
                                           data={"contest_id": self.contest.id, "id": problem.id, "visible": False}))
        problem.refresh_from_db()
        self.assertFalse(problem.visible)

    def test_delete_keeps_working_after_verification_runs(self):
        problem = self.add_problem(self.contest)
        Submission.objects.create(user_id=self.verifier.id, username="verifier", code="x", language="C",
                                  problem=problem, contest=self.contest)
        self.login(self.setter)
        self.assertSuccess(self.client.delete(self.reverse("contest_prep_problem_api") +
                                              f"?contest_id={self.contest.id}&id={problem.id}"))
        self.assertFalse(Problem.objects.filter(id=problem.id).exists())

    def test_reorder_relabels_problems(self):
        first, second, third = (self.add_problem(self.contest) for _ in range(3))
        url = self.reverse("contest_prep_problem_order_api")
        self.login(self.setter)
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

    def test_setter_imports_package_as_hidden_contest_problem(self):
        self.add_problem(self.contest)
        url = self.reverse("contest_prep_import_problem_api")
        self.login(self.verifier)
        self.assertFailed(self.client.post(url, data={"contest_id": self.contest.id, "file": self.package()},
                                           format="multipart"))
        self.login(self.setter)
        response = self.client.post(url, data={"contest_id": self.contest.id, "file": self.package()},
                                    format="multipart")
        self.assertSuccess(response)
        problem = Problem.objects.get(id=response.data["data"]["imported"][0]["id"])
        self.assertEqual((problem.contest_id, problem._id, problem.visible), (self.contest.id, "B", False))

        response = self.client.post(url, data={"contest_id": self.contest.id, "file": self.package("OI")},
                                    format="multipart")
        self.assertFailed(response)
        self.assertEqual(Problem.objects.filter(contest=self.contest).count(), 2)

    def test_setter_uploads_test_cases(self):
        buffer = io.BytesIO()
        with ZipFile(buffer, "w") as archive:
            archive.writestr("1.in", "1\n")
            archive.writestr("1.out", "2\n")
        url = self.reverse("contest_prep_test_case_api")

        def upload():
            return self.client.post(url, data={"contest_id": self.contest.id, "spj": "false",
                                               "file": SimpleUploadedFile("cases.zip", buffer.getvalue())},
                                    format="multipart")
        self.login(self.verifier)
        self.assertFailed(upload())
        self.login(self.setter)
        response = upload()
        self.assertSuccess(response)
        self.assertEqual(len(response.data["data"]["info"]), 1)


class ContestPrepPublishTest(ContestPrepTestBase):
    def setUp(self):
        super().setUp()
        self.draft = self.add_problem(self.contest, visible=False, title="draft")
        self.second = self.add_problem(self.contest, title="second")
        self.first = self.add_problem(self.contest, title="first", accepted_number=3, submission_number=5)
        ContestAnnouncement.objects.create(contest=self.contest, title="Welcome", content="<p>hi</p>",
                                           created_by=self.creator)
        self.url = self.reverse("contest_prep_publish_api")

    def test_publish_requires_preview_and_the_creator(self):
        self.login(self.creator)
        self.assertFailed(self.client.post(self.url, data={"contest_id": self.contest.id}),
                          "Switch the contest to preview before publishing")
        self.contest.prep_state = ContestPrepState.PREVIEW
        self.contest.save()
        self.login(self.setter)
        self.assertFailed(self.client.post(self.url, data={"contest_id": self.contest.id}),
                          "Only the contest creator can do this")

    def test_publish_copies_released_problems_into_a_new_public_contest(self):
        self.contest.prep_state = ContestPrepState.PREVIEW
        self.contest.save()
        self.login(self.creator)
        self.assertFailed(self.client.put(self.reverse("contest_prep_problem_order_api"),
                                          data={"contest_id": self.contest.id,
                                                "problem_ids": [self.first.id, self.draft.id, self.second.id]}))
        self.contest.prep_state = ContestPrepState.PREPARATION
        self.contest.save()
        self.assertSuccess(self.client.put(self.reverse("contest_prep_problem_order_api"),
                                           data={"contest_id": self.contest.id,
                                                 "problem_ids": [self.first.id, self.draft.id, self.second.id]}))
        self.contest.prep_state = ContestPrepState.PREVIEW
        self.contest.save()

        start = timezone.now() + timedelta(days=7)
        response = self.client.post(self.url, data={
            "contest_id": self.contest.id, "title": "Regional final", "start_time": start.isoformat(),
            "end_time": (start + timedelta(hours=5)).isoformat()})
        self.assertSuccess(response)
        published = Contest.objects.get(id=response.data["data"]["id"])
        self.assertEqual((published.title, published.prep_state, published.published_from_id, published.visible),
                         ("Regional final", None, self.contest.id, True))
        self.assertEqual((published.password, published.rule_type, published.created_by_id),
                         ("secret", "ACM", self.creator.id))
        copies = list(order_contest_problems(Problem.objects.filter(contest=published)))
        self.assertEqual([(item._id, item.title) for item in copies], [("A", "first"), ("B", "second")])
        self.assertEqual(copies[0].test_case_id, self.first.test_case_id)
        self.assertEqual((copies[0].accepted_number, copies[0].submission_number), (0, 0))
        self.assertEqual(list(copies[0].tags.values_list("name", flat=True)), ["test"])
        self.assertEqual(list(published.contestannouncement_set.values_list("title", flat=True)), ["Welcome"])

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
