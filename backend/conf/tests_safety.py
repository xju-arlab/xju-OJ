from pathlib import Path
from tempfile import TemporaryDirectory

from django.test import override_settings

from submission.tests import SubmissionPrepare


class TestCasePruneSafetyTests(SubmissionPrepare):
    def setUp(self):
        self._create_problem_and_submission()
        self.create_super_admin()
        self.directory = TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name) / "testcases"
        self.root.mkdir()
        context = override_settings(TEST_CASE_DIR=str(self.root))
        context.enable()
        self.addCleanup(context.disable)
        self.url = self.reverse("prune_test_case_api")
        self.active = self.root / self.problem.test_case_id
        self.active.mkdir()
        (self.active / "input").write_text("keep")

    def test_cannot_delete_a_referenced_test_case(self):
        response = self.client.delete(self.url + "?id=" + self.active.name)
        self.assertFailed(response)
        self.assertEqual((self.active / "input").read_text(), "keep")

    def test_cannot_escape_the_root_or_follow_links(self):
        outside = self.root.parent / "outside"
        outside.mkdir()
        (outside / "input").write_text("keep")
        (self.root / "linked-case").symlink_to(outside, target_is_directory=True)
        for name in ("../outside", str(outside), "linked-case", "."):
            with self.subTest(name=name):
                self.assertFailed(self.client.delete(self.url, QUERY_STRING="id=" + name))
                self.assertEqual((outside / "input").read_text(), "keep")

    def test_orphan_with_non_hex_id_is_listed_and_deleted(self):
        orphan = self.root / "demo-ab-v1"
        orphan.mkdir()
        response = self.client.get(self.url)
        self.assertSuccess(response)
        self.assertIn(orphan.name, [item["id"] for item in response.data["data"]])
        self.assertSuccess(self.client.delete(self.url + "?id=" + orphan.name))
        self.assertFalse(orphan.exists())
        self.assertTrue(self.active.exists())
