"""Synthetic packages only: archive boundaries, permissions, leases and atomic publication."""
import copy
import hashlib
import io
import json
import os
import stat
import tempfile
import uuid
import zipfile
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings
from django.utils.timezone import now
from rest_framework.test import APIClient

from account.models import AdminType, ProblemPermission
from utils.api import APIError
from utils.api.tests import APITestCase
from .models import AIDraft, AIJob, AIProblem, AIProblemImport, AIServiceState
from .package_format import FORMAT, PackageError, export_problem, make_zip, parse_package
from .packages import adopt_existing, confirm_batch, preview_package, private_path


def fixture(category="logic", title="Package contract fixture", source_id="OLD1"):
    metadata = {"format": FORMAT, "version": 1, "source_id": source_id, "title": title, "type": category,
                "statement": {"objective": "Return the supplied value", "inputSpec": "one number", "outputSpec": "one number"},
                "evaluation": {"public_column": "score"}}
    if category == "challenge":
        metadata["evaluation"]["private_column"] = "private_score"
    if category == "model":
        metadata["evaluation"]["accuracy_column"] = "accuracy"
    assets = {"scoring_program": {"program.py": b"# synthetic scorer"}, "reference_data": {"answer.json": b'{"expected": 7}'}}
    if category != "challenge":
        assets["ingestion_program"] = {"program.py": b"# synthetic interface"}
        assets["input_data"] = {"case.json": b'{"x": 7}'}
    return export_problem(metadata, ["# source", "print(7)"], {"sample.csv": "id,x\n1,7\n"}, assets)


def members(raw):
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


class PackageFormatTests(SimpleTestCase):
    def test_three_types_roundtrip_without_machine_ids_or_execution_output(self):
        for category in ("logic", "model", "challenge"):
            files = members(fixture(category))
            notebook = json.loads(files["starter.ipynb"])
            notebook["cells"][0].update(outputs=[{"text": "private old output"}], execution_count=9)
            notebook["cells"].insert(0, {"cell_type": "markdown", "source": "stale description"})
            files["starter.ipynb"] = json.dumps(notebook)
            item = parse_package(make_zip(files))[0]
            exported = members(export_problem(item["metadata"], item["cells"], item["public_files"], item["assets"]))
            self.assertNotIn("private old output", exported["starter.ipynb"].decode())
            self.assertNotIn("stale description", exported["starter.ipynb"].decode())
            self.assertNotIn("phase_id", exported["problem.json"].decode())
            self.assertEqual(item["assets"]["reference_data"]["answer.json"], b'{"expected": 7}')

    def test_batch_natural_order_and_no_partial_parse(self):
        raw = make_zip({"10.zip": fixture(title="Ten"), "2.zip": fixture(title="Two")})
        self.assertEqual([p["metadata"]["title"] for p in parse_package(raw)], ["Two", "Ten"])
        with self.assertRaises(PackageError):
            parse_package(make_zip({"1.zip": fixture(), "2.zip": b"broken"}))
        with self.assertRaises(PackageError):
            parse_package(make_zip({"nested.zip": raw}))

    def test_unsafe_paths_duplicates_links_and_file_directory_conflicts(self):
        for name in ("../escape", "/absolute", "x\\y", "a/./b", "a//b", "C:drive", "evil\x00name"):
            files = members(fixture()); files[name] = b"bad"
            # ZipInfo truncates NUL on write; patch raw headers to retain the original unsafe name.
            raw = make_zip(files) if "\x00" not in name else make_zip({**members(fixture()), "evilZname": b"bad"}).replace(b"evilZname", b"evil\x00name")
            with self.subTest(name=name), self.assertRaises(PackageError):
                parse_package(raw)
        for names in (("problem.json", "problem.json"), ("problem.json", "PROBLEM.JSON"),
                      ("evaluation/reference/a", "evaluation/reference/a/b"), ("evaluation/reference/a/b", "evaluation/reference/a")):
            out = io.BytesIO()
            with zipfile.ZipFile(out, "w") as archive:
                for base_name, content in members(fixture()).items():
                    if base_name not in names:
                        archive.writestr(base_name, content)
                for name in names:
                    archive.writestr(name, "bad")
            with self.assertRaises(PackageError):
                parse_package(out.getvalue())
        for mode in (stat.S_IFLNK, stat.S_IFIFO, stat.S_IFSOCK):
            out = io.BytesIO()
            with zipfile.ZipFile(out, "w") as archive:
                for base_name, content in members(fixture()).items():
                    archive.writestr(base_name, content)
                entry = zipfile.ZipInfo("link"); entry.external_attr = (mode | 0o600) << 16
                archive.writestr(entry, "outside")
            with self.assertRaises(PackageError):
                parse_package(out.getvalue())

    def test_limits_crc_and_encryption(self):
        raw = fixture()
        for limit in ("MAX_UPLOAD", "MAX_EXPANDED", "MAX_MEMBER", "MAX_MEMBERS"):
            with patch("ai_studio.package_format." + limit, 1), self.assertRaises(PackageError):
                parse_package(raw)
        damaged = bytearray(raw); damaged[40] ^= 255
        with self.assertRaises(PackageError):
            parse_package(damaged)
        encrypted = bytearray(raw)
        pos = encrypted.index(b"PK\x01\x02"); encrypted[pos + 8] |= 1
        with self.assertRaises(PackageError):
            parse_package(encrypted)

    def test_schema_missing_assets_and_server_bound_config_rejected(self):
        base = members(fixture())
        for change in ({"version": True}, {"type": "unknown"}, {"title": ""}, {"points": 0},
                       {"evaluation": {"phase_id": 1}}, {"evaluation": {"run_seconds": 601}},
                       {"evaluation": {"public_column": "score", "private_column": "score"}},
                       {"evaluation": {"pass_score": float("inf")}}):
            meta = json.loads(base["problem.json"]); meta.update(change)
            with self.subTest(change=change), self.assertRaises(PackageError):
                parse_package(make_zip({**base, "problem.json": json.dumps(meta)}))
        for missing in ("problem.json", "starter.ipynb", "evaluation/scoring/program.py", "evaluation/ingestion/program.py"):
            files = dict(base); del files[missing]
            with self.assertRaises(PackageError):
                parse_package(make_zip(files))
        for extra in ("evaluation/scoring/metadata.yaml", "data/secret.txt", "secrets/token"):
            with self.assertRaises(PackageError):
                parse_package(make_zip({**base, extra: b"bad"}))
        with self.assertRaises(PackageError):
            parse_package(make_zip({**base, "problem.json": b'{"format":"xju-ai-problem","format":"duplicate"}'}))


class PackageAPITests(APITestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        settings = override_settings(DATA_DIR=self.root.name)
        settings.enable(); self.addCleanup(settings.disable)
        self.user = self.create_admin()
        self.token = "synthetic-worker-token-" * 3
        token_path = Path(self.root.name) / "worker-token"; token_path.write_text(self.token)
        env = patch.dict(os.environ, {"AI_WORKER_TOKEN_FILE": str(token_path)})
        env.start(); self.addCleanup(env.stop)

    def upload(self, raw=None):
        stream = io.BytesIO(raw or fixture()); stream.name = "problems.zip"
        return self.client.post("/api/admin/ai/packages", {"file": stream}, format="multipart")

    def worker(self, action, **data):
        return self.client.post("/api/ai/package-worker", {"worker": "package-test", "action": action, **data},
                                format="json", HTTP_AUTHORIZATION="Bearer " + self.token)

    def start(self, raw=None):
        upload = self.upload(raw); self.assertSuccess(upload)
        pk = upload.data["data"]["id"]
        confirm = self.client.post("/api/admin/ai/packages/confirm", {"id": pk, "publish": False}, format="json")
        self.assertSuccess(confirm)
        job = self.worker("claim"); self.assertSuccess(job)
        return AIProblemImport.objects.get(pk=pk), job.data["data"]

    def results(self, batch):
        return [{"index": i, "asset_sha256": p["asset_sha256"],
                 "judge": {"phase_id": i + 40, "task_id": i + 80, **p["metadata"]["evaluation"]}} for i, p in enumerate(batch.manifest)]

    def finish(self, batch, job):
        response = self.worker("finish", id=job["id"], lease=job["lease"], status="SUCCEEDED", results=self.results(batch))
        self.assertSuccess(response)
        batch.refresh_from_db()
        return list(batch.problems.all())

    def test_preview_is_private_idempotent_and_does_not_create_problems(self):
        first, second = self.upload(), self.upload()
        self.assertSuccess(first); self.assertSuccess(second)
        self.assertEqual(first.data["data"]["id"], second.data["data"]["id"])
        self.assertEqual(AIProblem.objects.count(), 0)
        self.assertEqual(AIProblemImport.objects.count(), 1)
        self.assertNotIn("expected", json.dumps(first.data))
        self.assertNotIn("program.py", json.dumps(first.data))
        path = private_path(first.data["data"]["id"])
        self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        bad = self.upload(make_zip({"1.zip": fixture(), "2.zip": b"broken"}))
        self.assertFailed(bad); self.assertEqual(AIProblemImport.objects.count(), 1)

    def test_atomic_batch_registration_auto_ids_default_hidden_and_idempotent_finish(self):
        AIProblem.objects.create(code="AI099", title="Existing", category="logic", created_by=self.user)
        raw = make_zip({"2.zip": fixture("logic", "Two"), "10.zip": fixture("model", "Ten")})
        batch, job = self.start(raw)
        invalid = self.results(batch); invalid[1]["asset_sha256"] = {}
        self.assertFailed(self.worker("finish", id=job["id"], lease=job["lease"], status="SUCCEEDED", results=invalid))
        self.assertEqual(AIProblem.objects.count(), 1)
        problems = self.finish(batch, job)
        self.assertEqual([p.code for p in problems], ["AI100", "AI101"])
        self.assertEqual([p.title for p in problems], ["Two", "Ten"])
        self.assertFalse(any(p.visible for p in problems))
        self.finish(batch, job)
        self.assertEqual(AIProblem.objects.count(), 3)
        repeat = self.client.post("/api/admin/ai/packages/confirm", {"id": str(batch.pk), "publish": True}, format="json")
        self.assertSuccess(repeat); self.assertFalse(repeat.data["data"]["publish"])

    def test_worker_auth_download_and_lease_fencing(self):
        batch, first = self.start()
        self.assertFailed(self.client.post("/api/ai/package-worker", {"action": "claim"}, format="json"))
        response = self.client.get("/api/ai/package-worker", {"id": first["id"], "lease": first["lease"], "worker": "package-test"},
                                   HTTP_AUTHORIZATION="Bearer " + self.token)
        self.assertEqual(response["Content-Type"], "application/zip")
        self.assertEqual(hashlib.sha256(b"".join(response.streaming_content)).hexdigest(), batch.source_sha256)
        AIProblemImport.objects.filter(pk=batch.pk).update(lease_until=now() - timedelta(seconds=1))
        self.assertFailed(self.worker("heartbeat", id=first["id"], lease=first["lease"]))
        second = self.worker("claim").data["data"]
        self.assertNotEqual(second["lease"], first["lease"])
        self.assertFailed(self.worker("finish", id=first["id"], lease=first["lease"], status="FAILED"))
        self.finish(batch, second)

    def test_retries_pause_and_revoked_creator(self):
        batch, job = self.start()
        AIServiceState.objects.update_or_create(pk=1, defaults={"paused": True})
        status = self.client.post("/api/ai/worker", {"action": "service", "operation": "status"}, format="json",
                                  HTTP_AUTHORIZATION="Bearer " + self.token)
        self.assertEqual(status.data["data"], {"paused": True, "active": 1, "imports": 1})
        new = self.upload(fixture(title="Another"))
        self.assertFailed(self.client.post("/api/admin/ai/packages/confirm", {"id": new.data["data"]["id"], "publish": False}, format="json"))
        self.user.problem_permission = ProblemPermission.NONE; self.user.save()
        self.assertSuccess(self.worker("finish", id=job["id"], lease=job["lease"], status="SUCCEEDED", results=self.results(batch)))
        batch.refresh_from_db(); self.assertEqual(batch.status, "FAILED"); self.assertFalse(AIProblem.objects.exists())
        self.user.problem_permission = ProblemPermission.OWN; self.user.save()
        AIServiceState.objects.filter(pk=1).update(paused=False)
        confirm_batch(batch.pk, self.user, False)
        AIProblemImport.objects.filter(pk=batch.pk).update(attempts=3)
        self.worker("claim"); batch.refresh_from_db(); self.assertEqual(batch.status, "FAILED")
        confirm_batch(batch.pk, self.user, True)
        retry = self.worker("claim").data["data"]
        self.assertTrue(self.finish(batch, retry)[0].visible)

    def test_owner_all_none_permissions_and_export_roundtrip(self):
        batch, job = self.start(); problem = self.finish(batch, job)[0]
        other = self.create_admin("other")
        self.assertFailed(self.client.get("/api/admin/ai/packages", {"id": str(batch.pk)}))
        self.assertFailed(self.client.get("/api/admin/ai/packages/export", {"problem_id": problem.code}))
        other.problem_permission = ProblemPermission.ALL; other.save()
        response = self.client.get("/api/admin/ai/packages/export", {"problem_id": problem.code})
        self.assertEqual(response["Content-Type"], "application/zip")
        exported = b"".join(response.streaming_content)
        item = parse_package(exported)[0]
        self.assertEqual(item["asset_sha256"], batch.manifest[0]["asset_sha256"])
        self.assertEqual(item["metadata"]["source_id"], problem.code)
        second, lease = self.start(exported)
        imported = self.finish(second, lease)[0]
        self.assertNotEqual(imported.code, problem.code)
        self.assertEqual(imported.statement, problem.statement)
        other.problem_permission = ProblemPermission.NONE; other.save()
        self.assertFailed(self.upload())
        self.assertFailed(self.client.get("/api/admin/ai/problems"))

    def test_public_apis_never_expose_private_archive_and_browser_upload_requires_csrf(self):
        batch, job = self.start(); problem = self.finish(batch, job)[0]
        problem.visible = True; problem.save()
        self.create_user("student", "student")
        self.assertFailed(self.client.get("/api/admin/ai/packages/export", {"problem_id": problem.code}))
        response = self.client.get("/api/ai/problems", {"problem_id": problem.code})
        self.assertSuccess(response)
        self.assertNotIn("reference", json.dumps(response.data))
        self.assertNotIn("phase_id", json.dumps(response.data))
        self.assertFailed(self.client.get("/api/ai/file", {"problem_id": problem.code, "name": "evaluation/reference/answer.json"}))
        csrf = APIClient(enforce_csrf_checks=True); csrf.force_login(self.user)
        archive = io.BytesIO(fixture()); archive.name = "test.zip"
        self.assertEqual(csrf.post("/api/admin/ai/packages", {"file": archive}, format="multipart").status_code, 403)

    def test_metadata_revision_preserves_grades_and_stale_editor_is_rejected(self):
        batch, job = self.start(); problem = self.finish(batch, job)[0]
        draft = AIDraft.objects.create(problem=problem, user=self.user, cells=["answer"], revision=3)
        data = self.client.get("/api/admin/ai/problems", {"id": problem.code}).data["data"]
        data["outputSpec"] = "concise output"
        response = self.client.post("/api/admin/ai/problems", data, format="json"); self.assertSuccess(response)
        self.assertEqual(response.data["data"], {"id": problem.code, "version": 1, "revision": 2})
        self.assertFailed(self.client.post("/api/admin/ai/problems", data, format="json"))
        data["revision"] = 2; data["cells"] = ["new starter"]
        response = self.client.post("/api/admin/ai/problems", data, format="json"); self.assertSuccess(response)
        self.assertEqual(response.data["data"]["version"], 2)
        data["revision"] = 3; data["judge"]["phase_id"] += 1
        self.assertFailed(self.client.post("/api/admin/ai/problems", data, format="json"))
        draft.refresh_from_db(); self.assertEqual(draft.cells, ["answer"]); self.assertEqual(draft.revision, 3)

    def test_adoption_is_atomic_and_preserves_every_existing_record(self):
        admin = self.create_super_admin()
        raw = make_zip({"1.zip": fixture(source_id="EXIST1"), "2.zip": fixture("model", source_id="EXIST2")})
        batch = preview_package(admin, "archive.zip", raw)
        bindings = []
        for index, item in enumerate(batch.manifest):
            meta = item["metadata"]; judge = self.results(batch)[index]["judge"]
            problem = AIProblem.objects.create(code=meta["source_id"], title=meta["title"], category=meta["type"],
                statement=meta["statement"], cells=item["cells"], public_files=item["public_files"], metric=meta["metric"],
                points=meta["points"], judge=judge, created_by=self.user, visible=True, version=7)
            bindings.append({"id": problem.code, "judge": judge, "asset_sha256": item["asset_sha256"]})
        draft = AIDraft.objects.create(problem=problem, user=self.user, cells=["saved"], revision=5)
        result = AIJob.objects.create(user=self.user, problem=problem, kind="evaluation", category=problem.category,
                                      problem_version=7, source_sha256="a" * 64, status="ACCEPTED", public_score=100)
        before = list(AIProblem.objects.values())
        bad = copy.deepcopy(bindings); bad[1]["judge"]["phase_id"] += 1
        with self.assertRaises(APIError):
            adopt_existing(batch.pk, admin, bad)
        self.assertEqual(list(AIProblem.objects.values()), before)
        adopt_existing(batch.pk, admin, bindings); adopt_existing(batch.pk, admin, bindings)
        after = list(AIProblem.objects.values())
        for a, b in zip(before, after):
            for key in ("package_import_id", "package_index"):
                a.pop(key); b.pop(key)
            self.assertEqual(a, b)
        draft.refresh_from_db(); result.refresh_from_db()
        self.assertEqual((draft.cells, draft.revision, result.public_score, result.problem_version), (["saved"], 5, 100, 7))

    def test_corrupted_archive_is_not_exported_and_preview_cleanup_is_targeted(self):
        batch, job = self.start(); problem = self.finish(batch, job)[0]
        private_path(batch.pk).write_bytes(b"corrupt")
        self.assertFailed(self.client.get("/api/admin/ai/packages/export", {"problem_id": problem.code}))
        self.assertFailed(self.client.delete("/api/admin/ai/packages?id=" + str(batch.pk)))
        preview = self.upload(fixture(title="Disposable")).data["data"]
        with self.captureOnCommitCallbacks(execute=True):
            self.assertSuccess(self.client.delete("/api/admin/ai/packages?id=" + preview["id"]))
        self.assertFalse(private_path(preview["id"]).exists())
        self.assertTrue(private_path(batch.pk).exists())
