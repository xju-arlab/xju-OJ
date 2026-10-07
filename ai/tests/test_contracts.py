"""Offline tests for archive isolation, transport, and uncertain dispatch recovery."""
import importlib.util
import io
import json
from pathlib import Path
import stat
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "compute"))
from codabench import Codabench, submission_bundle
from transport import Client, NoRedirect, RemoteError


def load_boundary():
    # Archive helpers are exercised without installing or starting Codabench.
    upstream = SimpleNamespace(app=None, Run=type("Run", (), {"_update_status": Mock()}),
                               SubmissionStatus=SimpleNamespace(SCORING="Scoring"), SubmissionException=ValueError)
    spec = importlib.util.spec_from_file_location("xju_secure_boundary", ROOT / "codabench/secure_worker.py")
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {"compute_worker": upstream, "docker": SimpleNamespace()}):
        spec.loader.exec_module(module)
    return module


boundary = load_boundary()


def bundle(name, content=b"hello", mode=0):
    output = io.BytesIO()
    with zipfile.ZipFile(output, "w") as archive:
        item = zipfile.ZipInfo(name)
        item.external_attr = mode << 16
        archive.writestr(item, content)
    return output.getvalue()


class ArchiveTests(unittest.TestCase):
    def test_failed_ingestion_does_not_schedule_scoring(self):
        run = SimpleNamespace(is_scoring=False, ingestion_program_data="trusted-harness", ingestion_program_exit_code=137, xju_failure="XJU_MEMORY_LIMIT")
        with self.assertRaisesRegex(ValueError, "XJU_MEMORY_LIMIT"):
            boundary.update_status(run, "Scoring")
        boundary.upstream_update_status.assert_not_called()
        predictions = SimpleNamespace(is_scoring=False, ingestion_program_data=None, ingestion_program_exit_code=None)
        boundary.update_status(predictions, "Scoring")
        boundary.upstream_update_status.assert_called_once_with(predictions, "Scoring", "")
        boundary.upstream_update_status.reset_mock()

    def test_traversal_absolute_and_links_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            for name, mode in [("../escaped", 0), ("/escaped", 0), ("a\\b", 0), ("link", stat.S_IFLNK | 0o777)]:
                with self.subTest(name=name), self.assertRaises(ValueError):
                    boundary.bounded_extract(bundle(name, mode=mode), directory)
            self.assertEqual(list(Path(directory).iterdir()), [])

    def test_extraction_budget_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(boundary, "MAX_BUNDLE", 4), self.assertRaises(ValueError):
                boundary.bounded_extract(bundle("large", b"12345"), directory)
            boundary.bounded_extract(bundle("code/solution.py"), directory)
            with self.assertRaises(FileExistsError):
                boundary.bounded_extract(bundle("code/solution.py", b"overwritten"), directory)
            self.assertEqual(Path(directory, "code/solution.py").read_bytes(), b"hello")

    def test_result_symlink_and_hardlink_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            target = root / "target"
            target.write_text("result")
            (root / "link").symlink_to(target)
            with self.assertRaises(OSError):
                boundary.safe_archive(root)
            (root / "link").unlink()
            (root / "link").hardlink_to(target)
            with self.assertRaises(ValueError):
                boundary.safe_archive(root)

    def test_result_fifo_directory_link_and_limits(self):
        import os
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            os.mkfifo(root / "pipe")
            with self.assertRaises(ValueError):
                boundary.safe_archive(root)
            (root / "pipe").unlink()
            (root / "dir").symlink_to("/tmp", target_is_directory=True)
            with self.assertRaises(ValueError):
                boundary.safe_archive(root)
            (root / "dir").unlink()
            (root / "output").write_bytes(b"12345")
            with patch.object(boundary, "MAX_RESULTS", 4), self.assertRaises(ValueError):
                boundary.safe_archive(root)
            with zipfile.ZipFile(io.BytesIO(boundary.safe_archive(root))) as result:
                self.assertEqual(result.read("output"), b"12345")


class TransportTests(unittest.TestCase):
    def test_redirects_and_external_storage_rejected(self):
        with self.assertRaises(RemoteError):
            NoRedirect().redirect_request(None, None, 302, None, {}, "https://untrusted.invalid")
        client = Client("http://service/api/", "private-test-token", "Bearer")
        client.opener = Mock()
        for url in ("https://other.invalid/upload", "http://user@store/upload", "http://store/upload#fragment"):
            with self.assertRaises(RemoteError):
                client.put_zip(url, b"zip", "http://store")
        client.opener.open.assert_not_called()

    def test_object_upload_has_no_service_authorization(self):
        client = Client("http://service/api/", "private-test-token", "Bearer")
        response = Mock()
        response.__enter__ = Mock(return_value=response)
        response.__exit__ = Mock(return_value=False)
        client.opener = Mock()
        client.opener.open.return_value = response
        client.put_zip("http://store/upload?signature=private", b"zip", "http://store")
        request = client.opener.open.call_args.args[0]
        self.assertIsNone(request.get_header("Authorization"))

    def test_credentials_are_absent_from_errors(self):
        client = Client("http://service/api/", "private-test-token", "Bearer")
        client.opener = Mock()
        client.opener.open.side_effect = OSError("signed-url-and-secret")
        with self.assertRaisesRegex(RemoteError, r"^Service request failed \(OSError\)$"):
            client.call("GET", "jobs/")


class DispatchTests(unittest.TestCase):
    def setUp(self):
        self.client = Mock()
        self.adapter = Codabench(self.client, "http://store")
        self.job = {"id": "a-unique-job", "lease": "fresh-lease", "category": "logic", "judge": {"phase_id": 7, "public_column": "score"}, "payload": {"cells": ["x = 1"]}}
        self.heartbeat = Mock()

    def test_unknown_post_is_never_automatically_repeated(self):
        self.client.call.return_value = {"results": []}
        with self.assertRaises(RemoteError):
            self.adapter.submit({**self.job, "dispatch_started": True}, self.heartbeat)
        self.assertEqual([call.args[0] for call in self.client.call.call_args_list], ["GET"])

    def test_uncertain_post_reconciles_existing_remote_record(self):
        self.client.call.side_effect = [
            {"results": []}, {"key": "upload-key", "sassy_url": "http://store/upload"}, {},
            RemoteError("connection lost after POST"),
            {"results": [{"id": 42, "phase": 7, "filename": "oj-a-unique-job.zip", "parent": None}]},
        ]
        self.assertEqual(self.adapter.submit(self.job, self.heartbeat), 42)
        self.heartbeat.assert_any_call(dispatch_started=True)
        self.heartbeat.assert_any_call(remote_id=42)
        self.assertEqual(sum(call.args[:2] == ("POST", "submissions/") for call in self.client.call.call_args_list), 1)

    def test_existing_remote_id_requires_no_new_upload(self):
        self.assertEqual(self.adapter.submit({**self.job, "remote_id": 42}, self.heartbeat), 42)
        self.client.call.assert_not_called()
        self.client.put_zip.assert_not_called()

    def test_nonfinite_and_duplicate_scores_fail_closed(self):
        for rows in ([{"column_key": "score", "score": "nan"}], [{"column_key": "score", "score": 1}] * 2):
            with self.subTest(rows=rows):
                self.client.call.return_value = {"phase": 7, "status": "Finished", "scores": rows}
                with self.assertRaises(RemoteError):
                    self.adapter.run({**self.job, "remote_id": 42}, self.heartbeat)

    def test_finished_before_all_scores_arrive_is_polled_without_resubmission(self):
        job = {**self.job, "remote_id": 42, "judge": {**self.job["judge"], "accuracy_column": "accuracy"}}
        rows = [{"column_key": "score", "score": 0}, {"column_key": "accuracy", "score": 0.25}]
        self.client.call.side_effect = [{"phase": 7, "status": "Finished", "scores": value}
                                       for value in ([], rows[:1], rows)]
        with patch("codabench.time.sleep"):
            result = self.adapter.run(job, self.heartbeat)
        self.assertEqual(result["public_score"], 0)
        self.assertEqual(result["accuracy"], 0.25)
        self.assertEqual([call.args[:2] for call in self.client.call.call_args_list], [("GET", "submissions/42/")] * 3)
        self.client.put_zip.assert_not_called()

    def test_permanently_missing_scores_fail_after_bounded_wait(self):
        now = [0]
        self.client.call.return_value = {"phase": 7, "status": "Finished", "scores": []}
        with patch("codabench.time.monotonic", side_effect=lambda: now[0]), \
                patch("codabench.time.sleep", side_effect=lambda seconds: now.__setitem__(0, now[0] + seconds)):
            with self.assertRaisesRegex(RemoteError, "Required score column is missing"):
                self.adapter.run({**self.job, "remote_id": 42}, self.heartbeat)
        self.assertLessEqual(now[0], 30)
        self.client.put_zip.assert_not_called()

    def test_zero_grade_and_trusted_failure_classification(self):
        self.client.call.return_value = {"phase": 7, "status": "Finished", "scores": [{"column_key": "score", "score": 0}]}
        self.assertEqual(self.adapter.run({**self.job, "remote_id": 42}, self.heartbeat)["public_score"], 0)
        for details, status in [("Execution Time Limit exceeded. Limit was 5 seconds", "TIME_LIMIT"), ("Submission failed: XJU_MEMORY_LIMIT", "MEMORY_LIMIT"), ("Child task failed", "RUNTIME_ERROR")]:
            self.client.call.return_value = {"phase": 7, "status": "Failed", "status_details": details}
            self.assertEqual(self.adapter.run({**self.job, "remote_id": 42}, self.heartbeat)["status"], status)

    def test_bundle_contains_only_student_source_and_public_data(self):
        job = {**self.job, "payload": {"cells": ["x = 1", "print(x)"], "files": {"train.csv": "x,y", "../secret.csv": "bad"}}, "judge": {"secret": "hidden"}}
        with zipfile.ZipFile(io.BytesIO(submission_bundle(job))) as result:
            self.assertEqual(result.namelist(), ["solution.py", "data/train.csv"])
            self.assertEqual(result.read("solution.py"), b"x = 1\n\nprint(x)")


if __name__ == "__main__":
    unittest.main()
