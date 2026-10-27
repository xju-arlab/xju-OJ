import copy
import hashlib
import io
import json
import os
import shutil
import tempfile
from datetime import timedelta
from unittest.mock import Mock, patch
from zipfile import ZipFile

from django.conf import settings
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.utils import timezone

from utils.api.tests import APITestCase

from .models import ProblemTag, ProblemIOMode
from .models import Problem, ProblemRuleType, ProblemJudgeMode, RemoteOJ
from .remote.codeforces import (parse_codeforces_problem_page,
                                parse_codeforces_reference)
from .remote.common import markdown_to_html, render_residual_markdown_links
from .remote.luogu import parse_luogu_problem_page, parse_luogu_reference
from .remote.nowcoder import (parse_nowcoder_acm_problem_page,
                              parse_nowcoder_problem_page,
                              parse_nowcoder_reference)
from .publication import publish_due_contest_problems
from .tasks import schedule_contest_problem_publication
from contest.models import Contest
from contest.tests import DEFAULT_CONTEST_DATA

from .views.admin import TestCaseAPI
from .utils import parse_problem_template

DEFAULT_PROBLEM_DATA = {"_id": "A-110", "title": "test", "description": "<p>test</p>", "input_description": "test",
                        "output_description": "test", "time_limit": 1000, "memory_limit": 256, "difficulty": "Low",
                        "visible": True, "tags": ["test"], "languages": ["C", "C++", "Java", "Python3"], "template": {},
                        "samples": [{"input": "test", "output": "test"}], "spj": False, "spj_language": "C",
                        "spj_code": "", "spj_compile_ok": True, "test_case_id": "499b26290cc7994e0b497212e842ea85",
                        "test_case_score": [{"output_name": "1.out", "input_name": "1.in", "output_size": 0,
                                             "stripped_output_md5": "d41d8cd98f00b204e9800998ecf8427e",
                                             "input_size": 0, "score": 0}],
                        "io_mode": {"io_mode": ProblemIOMode.standard, "input": "input.txt", "output": "output.txt"},
                        "share_submission": False,
                        "rule_type": "ACM", "hint": "<p>test</p>", "source": "test"}

NOWCODER_PROBLEM_UUID = "c4030190499f4da3acd744d33f39627b"
NOWCODER_PROBLEM_HTML = f"""
<html>
  <body>
    <h1 class="crumbs-end js-question-title">Remote test problem</h1>
    <span>时间限制：C/C++ 1秒，其他语言2秒</span>
    <span>空间限制：C/C++ 256M，其他语言512M</span>
    <div class="nc-post-content"><p>Count the answer.</p><script>bad()</script></div>
    <h5><b>输入描述:</b></h5><pre>Two integers.<br />Read them.</pre>
    <h5><b>输出描述:</b></h5><pre>Print the answer.</pre>
    <div class="question-oi-hd">示例1</div>
    <h2>输入</h2><div class="question-oi-cont"><pre>1 2</pre></div>
    <h2>输出</h2><div class="question-oi-cont"><pre>3</pre></div>
    <script>
      window.problem = {{ id: 11742270, uuid: '{NOWCODER_PROBLEM_UUID}', type: 4 }};
      window.codeJudgeType = '0';
      window.supportLang = 'java,cpp';
    </script>
  </body>
</html>
"""

NOWCODER_ACM_PROBLEM_HTML = r"""
<html><body>
  <div class="question-title"><i class="icon-list"></i>小月的数组</div>
  <span>时间限制：C/C++/Rust/Pascal 2秒，其他语言4秒</span>
  <span>空间限制：C/C++/Rust/Pascal 256 M，其他语言512 M</span>
  <div class="subject-question">
    <div><p>\hspace{15pt}数组 a = \{a_1, a_2,\dots, a_n\}。对于所有 i\left(1 \leq i \leq n \right)，元素均合法。</p></div>
    <div>
      <img src="https://www.nowcoder.com/equation?tex=x%2Ai">
      <img src="https://hr.nowcoder.com/equation?tex=y_1">
      <img src="https://hr.nowcoder.com/equation?tex=%5Chspace%7B15pt%7D">
      <a href="https://example.com/note">说明</a>
      <img alt="diagram" src="https://uploadfiles.nowcoder.com/example.png">
    </div>
    <script>bad()</script>
  </div>
  <h2>输入描述:</h2><pre>两个整数 n,r\left(1 \le n; 0 \le r&lt;4\right)。</pre>
  <h2>输出描述:</h2><pre>输出答案。</pre>
  <textarea data-clipboard-text-id="input1">1 0
</textarea>
  <textarea data-clipboard-text-id="output1">1
</textarea>
  <script>
    window.codeJudgeType = '0';
    window.supportLang = 'java,cpp';
    window.pageInfo = {
      questionId: '11776488',
      problemId: '322024',
      uuid: '7cb1f9696c1048e5bc790256bb7f2bac',
      tagId: '4'
    };
  </script>
</body></html>
"""

CODEFORCES_PROBLEM_HTML = """
<div class="problem-statement">
  <div class="header">
    <div class="title">A. Watermelon</div>
    <div class="time-limit"><div class="property-title">time limit per test</div>1 second</div>
    <div class="memory-limit"><div class="property-title">memory limit per test</div>64 megabytes</div>
  </div>
  <div><p>Decide whether it can be split.<script>bad()</script></p></div>
  <div class="input-specification"><div class="section-title">Input</div><p>An integer.</p></div>
  <div class="output-specification"><div class="section-title">Output</div><p>YES or NO.</p></div>
  <div class="sample-tests"><div class="sample-test">
    <div class="input"><div class="title">Input</div><pre>8<br /></pre></div>
    <div class="output"><div class="title">Output</div><pre>YES<br /></pre></div>
  </div></div>
  <div class="note"><div class="section-title">Note</div><p>A note.</p></div>
</div>
"""

LUOGU_PROBLEM_HTML = """
<script id="lentille-context" type="application/json">{context}</script>
""".format(context=json.dumps({
    "template": "problem.show",
    "data": {
        "problem": {
            "pid": "P1001",
            "type": "P",
            "name": "A+B Problem",
            "difficulty": 1,
            "contenu": {
                "background": "**Background**",
                "description": "Add two integers.",
                "formatI": "Two integers.",
                "formatO": "Their sum.",
                "hint": "No hint.",
            },
            "acceptLanguages": [2, 12, 33, 7, 14, 9],
            "samples": [["20 30\n", "50\n"]],
            "limits": {"time": [1000], "memory": [524288]},
        }
    },
}))


class ProblemCreateTestBase(APITestCase):
    @staticmethod
    def add_problem(problem_data, created_by):
        data = copy.deepcopy(problem_data)
        if data["spj"]:
            if not data["spj_language"] or not data["spj_code"]:
                raise ValueError("Invalid spj")
            data["spj_version"] = hashlib.md5(
                (data["spj_language"] + ":" + data["spj_code"]).encode("utf-8")).hexdigest()
        else:
            data["spj_language"] = None
            data["spj_code"] = None
        if data["rule_type"] == ProblemRuleType.OI:
            total_score = 0
            for item in data["test_case_score"]:
                if item["score"] <= 0:
                    raise ValueError("invalid score")
                else:
                    total_score += item["score"]
            data["total_score"] = total_score
        data["created_by"] = created_by
        tags = data.pop("tags")

        data["languages"] = list(data["languages"])

        problem = Problem.objects.create(**data)

        for item in tags:
            try:
                tag = ProblemTag.objects.get(name=item)
            except ProblemTag.DoesNotExist:
                tag = ProblemTag.objects.create(name=item)
            problem.tags.add(tag)
        return problem


class ProblemTagListAPITest(APITestCase):
    def test_get_tag_list(self):
        ProblemTag.objects.create(name="name1")
        ProblemTag.objects.create(name="name2")
        resp = self.client.get(self.reverse("problem_tag_list_api"))
        self.assertSuccess(resp)


class TestCaseUploadAPITest(APITestCase):
    def setUp(self):
        self.api = TestCaseAPI()
        self.url = self.reverse("test_case_api")
        self.create_super_admin()

    def test_filter_file_name(self):
        self.assertEqual(self.api.filter_name_list(["1.in", "1.out", "2.in", ".DS_Store"], spj=False),
                         ["1.in", "1.out"])
        self.assertEqual(self.api.filter_name_list(["2.in", "2.out"], spj=False), [])

        self.assertEqual(self.api.filter_name_list(["1.in", "1.out", "2.in"], spj=True), ["1.in", "2.in"])
        self.assertEqual(self.api.filter_name_list(["2.in", "3.in"], spj=True), [])

    def make_test_case_zip(self):
        base_dir = os.path.join("/tmp", "test_case")
        shutil.rmtree(base_dir, ignore_errors=True)
        os.mkdir(base_dir)
        file_names = ["1.in", "1.out", "2.in", ".DS_Store"]
        for item in file_names:
            with open(os.path.join(base_dir, item), "w", encoding="utf-8") as f:
                f.write(item + "\n" + item + "\r\n" + "end")
        zip_file = os.path.join(base_dir, "test_case.zip")
        with ZipFile(os.path.join(base_dir, "test_case.zip"), "w") as f:
            for item in file_names:
                f.write(os.path.join(base_dir, item), item)
        return zip_file

    def test_upload_spj_test_case_zip(self):
        with open(self.make_test_case_zip(), "rb") as f:
            resp = self.client.post(self.url,
                                    data={"spj": "true", "file": f}, format="multipart")
            self.assertSuccess(resp)
            data = resp.data["data"]
            self.assertEqual(data["spj"], True)
            test_case_dir = os.path.join(settings.TEST_CASE_DIR, data["id"])
            self.assertTrue(os.path.exists(test_case_dir))
            for item in data["info"]:
                name = item["input_name"]
                with open(os.path.join(test_case_dir, name), "r", encoding="utf-8") as f:
                    self.assertEqual(f.read(), name + "\n" + name + "\n" + "end")

    def test_upload_test_case_zip(self):
        with open(self.make_test_case_zip(), "rb") as f:
            resp = self.client.post(self.url,
                                    data={"spj": "false", "file": f}, format="multipart")
            self.assertSuccess(resp)
            data = resp.data["data"]
            self.assertEqual(data["spj"], False)
            test_case_dir = os.path.join(settings.TEST_CASE_DIR, data["id"])
            self.assertTrue(os.path.exists(test_case_dir))
            for item in data["info"]:
                name = item["input_name"]
                with open(os.path.join(test_case_dir, name), "r", encoding="utf-8") as f:
                    self.assertEqual(f.read(), name + "\n" + name + "\n" + "end")


class ProblemZipImportAPITest(APITestCase):
    def setUp(self):
        self.url = self.reverse("import_problem_api")
        self.admin = self.create_super_admin()
        self.test_case_root = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(TEST_CASE_DIR=self.test_case_root.name)
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        self.test_case_root.cleanup()

    def problem_info(self, title="ZIP import", display_id="ignored-by-importer"):
        result = {
            "title": title,
            "description": {"format": "markdown", "value": "**Problem** description."},
            "input_description": {"format": "markdown", "value": "Read `n`."},
            "output_description": {"format": "markdown", "value": "Print the answer."},
            "hint": {"format": "markdown", "value": ""},
            "test_case_score": [
                {"score": 100, "input_name": "1.in", "output_name": "1.out"}
            ],
            "time_limit": 1500,
            "memory_limit": 512,
            "samples": [{"input": "1\n", "output": "2\n"}],
            "template": {},
            "spj": None,
            "rule_type": ProblemRuleType.ACM,
            "source": "js-problemset /",
            "tags": ["保研真题", "测试学校"],
            "difficulty": "High",
            "visible": True,
            "languages": ["C++", "Python3"],
        }
        if display_id is not None:
            result["display_id"] = display_id
        return result

    def make_problem_zip_bytes(self, problem_info, prefix=""):
        buffer = io.BytesIO()
        with ZipFile(buffer, "w") as archive:
            prefix = prefix.strip("/")
            prefix = f"{prefix}/" if prefix else ""
            archive.writestr(
                f"{prefix}problem.json",
                json.dumps(problem_info, ensure_ascii=False),
            )
            archive.writestr(f"{prefix}testcase/1.in", "1\n")
            archive.writestr(f"{prefix}testcase/1.out", "2\n")
        return buffer.getvalue()

    def make_single_package(self, problem_info, prefix=""):
        return SimpleUploadedFile(
            "problem.zip",
            self.make_problem_zip_bytes(problem_info, prefix),
            content_type="application/zip",
        )

    def make_batch_package(self, problems):
        buffer = io.BytesIO()
        with ZipFile(buffer, "w") as archive:
            for filename, problem_info in problems:
                archive.writestr(
                    filename,
                    self.make_problem_zip_bytes(problem_info),
                )
        return SimpleUploadedFile(
            "problems.zip", buffer.getvalue(), content_type="application/zip"
        )

    def test_import_root_single_problem_with_metadata_and_markdown(self):
        response = self.client.post(
            self.url,
            data={"file": self.make_single_package(
                self.problem_info(display_id=None)
            )},
            format="multipart",
        )
        self.assertSuccess(response)
        self.assertEqual(response.data["data"]["import_count"], 1)
        self.assertEqual(response.data["data"]["package_format"], "single")
        problem = Problem.objects.get(_id="1001")
        self.assertEqual(problem.difficulty, "High")
        self.assertTrue(problem.visible)
        self.assertEqual(problem.languages, ["C++", "Python3"])
        self.assertIn("<strong>Problem</strong>", problem.description)
        self.assertTrue(problem.tags.filter(name="保研真题").exists())
        self.assertTrue(os.path.isfile(os.path.join(
            self.test_case_root.name, problem.test_case_id, "info"
        )))

    def test_import_batch_of_independent_single_problem_zips(self):
        response = self.client.post(
            self.url,
            data={"file": self.make_batch_package([
                ("002-second.zip", self.problem_info("Second")),
                ("001-first.zip", self.problem_info("First")),
            ])},
            format="multipart",
        )
        self.assertSuccess(response)
        self.assertEqual(response.data["data"]["import_count"], 2)
        self.assertEqual(response.data["data"]["package_format"], "batch")
        self.assertEqual(
            list(Problem.objects.order_by("_id").values_list("_id", "title")),
            [("1001", "First"), ("1002", "Second")],
        )

    def test_import_legacy_qduoj_numbered_directory(self):
        response = self.client.post(
            self.url,
            data={"file": self.make_single_package(
                self.problem_info(), prefix="2"
            )},
            format="multipart",
        )
        self.assertSuccess(response)
        self.assertEqual(response.data["data"]["package_format"], "qduoj")
        self.assertTrue(Problem.objects.filter(_id="1001").exists())

    def test_package_display_id_is_ignored_on_repeated_imports(self):
        package = self.make_single_package(self.problem_info(display_id="9999"))
        first = self.client.post(self.url, data={"file": package}, format="multipart")
        self.assertSuccess(first)
        second_package = self.make_single_package(self.problem_info(display_id="9999"))
        second = self.client.post(
            self.url,
            data={"file": second_package},
            format="multipart",
        )
        self.assertSuccess(second)
        self.assertEqual(
            list(Problem.objects.order_by("_id").values_list("_id", flat=True)),
            ["1001", "1002"],
        )

    def test_batch_failure_rolls_back_database_and_test_case_files(self):
        invalid = self.problem_info("Second")
        del invalid["title"]
        response = self.client.post(
            self.url,
            data={"file": self.make_batch_package([
                ("001-first.zip", self.problem_info("First")),
                ("002-second.zip", invalid),
            ])},
            format="multipart",
        )
        self.assertFailed(response)
        self.assertFalse(Problem.objects.exists())
        self.assertEqual(os.listdir(self.test_case_root.name), [])

    def test_export_uses_single_problem_zips_for_single_and_batch_downloads(self):
        for title in ("First", "Second"):
            response = self.client.post(
                self.url,
                data={"file": self.make_single_package(self.problem_info(title))},
                format="multipart",
            )
            self.assertSuccess(response)

        export_url = self.reverse("export_problem_api")
        problems = list(Problem.objects.order_by("_id"))
        response = self.client.get(export_url, {"problem_id": [problems[0].id]})
        self.assertEqual(response.status_code, 200)
        with ZipFile(io.BytesIO(b"".join(response.streaming_content))) as archive:
            self.assertEqual(
                set(archive.namelist()),
                {"problem.json", "testcase/1.in", "testcase/1.out"},
            )

        response = self.client.get(
            export_url,
            {"problem_id": [problem.id for problem in problems]},
        )
        self.assertEqual(response.status_code, 200)
        with ZipFile(io.BytesIO(b"".join(response.streaming_content))) as archive:
            self.assertEqual(archive.namelist(), ["001.zip", "002.zip"])
            for name in archive.namelist():
                with ZipFile(io.BytesIO(archive.read(name))) as problem_archive:
                    self.assertEqual(
                        set(problem_archive.namelist()),
                        {"problem.json", "testcase/1.in", "testcase/1.out"},
                    )

    def test_export_and_import_keep_data_range_and_sample_explanations(self):
        info = self.problem_info("Round trip")
        info["data_range"] = {"format": "markdown", "value": "$1 \\le n \\le 10^5$"}
        info["samples"] = [{"input": "1\n", "output": "2\n", "explanation": "Add **one** to $n$."},
                           {"input": "3\n", "output": "4\n"}]
        self.assertSuccess(self.client.post(self.url, data={"file": self.make_single_package(info)},
                                            format="multipart"))
        original = Problem.objects.get()
        self.assertIn("10^5", original.data_range)
        # Packages may carry Markdown; it is stored as cleaned HTML.
        self.assertEqual([sample["explanation"] for sample in original.samples],
                         ["<p>Add <strong>one</strong> to $n$.</p>", ""])

        response = self.client.get(self.reverse("export_problem_api"), {"problem_id": [original.id]})
        with ZipFile(io.BytesIO(b"".join(response.streaming_content))) as archive:
            exported = json.loads(archive.read("problem.json"))
        self.assertEqual(exported["data_range"], {"format": "html", "value": original.data_range})
        self.assertEqual(exported["samples"][0]["explanation"], "<p>Add <strong>one</strong> to $n$.</p>")

        self.assertSuccess(self.client.post(self.url, data={"file": self.make_single_package(exported)},
                                            format="multipart"))
        copy_ = Problem.objects.exclude(id=original.id).get()
        self.assertEqual(copy_.data_range, original.data_range)
        self.assertEqual(copy_.samples, original.samples)

    def test_packages_without_data_range_or_with_a_null_hint_still_import(self):
        # Packages from before the field existed, or exported from rows with a NULL hint.
        legacy = self.problem_info("Legacy")
        self.assertNotIn("data_range", legacy)
        self.assertSuccess(self.client.post(self.url, data={"file": self.make_single_package(legacy)},
                                            format="multipart"))
        problem = Problem.objects.get()
        self.assertEqual(problem.data_range, "")
        Problem.objects.filter(id=problem.id).update(hint=None)
        response = self.client.get(self.reverse("export_problem_api"), {"problem_id": [problem.id]})
        with ZipFile(io.BytesIO(b"".join(response.streaming_content))) as archive:
            exported = json.loads(archive.read("problem.json"))
        self.assertEqual(exported["hint"], {"format": "html", "value": ""})
        self.assertSuccess(self.client.post(self.url, data={"file": self.make_single_package(exported)},
                                            format="multipart"))

    def test_import_requires_problem_permission(self):
        self.client.logout()
        response = self.client.post(
            self.url,
            data={"file": self.make_single_package(self.problem_info())},
            format="multipart",
        )
        self.assertIn(response.data["error"], ("login-required", "permission-denied"))
        self.assertFalse(Problem.objects.exists())


class ProblemAdminAPITest(ProblemCreateTestBase):
    def setUp(self):
        self.url = self.reverse("problem_admin_api")
        self.admin = self.create_super_admin()
        self.data = copy.deepcopy(DEFAULT_PROBLEM_DATA)

    def test_create_problem(self):
        resp = self.client.post(self.url, data=self.data)
        self.assertSuccess(resp)
        self.assertEqual(resp.data["data"]["_id"], "1001")
        return resp

    def test_data_range_and_sample_explanation_are_stored_and_served(self):
        self.data["data_range"] = "<p>1 ≤ n ≤ 100</p><script>alert(1)</script>"
        self.data["samples"] = [
            {"input": "1", "output": "1", "explanation": '<p>Odd, so <em>one</em>.</p><img src="x" onerror="alert(1)">'},
            {"input": "2", "output": "4", "explanation": "plain\nlines"},
            {"input": "3", "output": "9"}]
        resp = self.client.post(self.url, data=self.data)
        self.assertSuccess(resp)
        problem = Problem.objects.get(id=resp.data["data"]["id"])
        # Rich text is cleaned like the other statement fields: the tag goes, inert text stays.
        self.assertTrue(problem.data_range.startswith("<p>1 ≤ n ≤ 100</p>"))
        self.assertNotIn("<script", problem.data_range)
        explanations = [sample["explanation"] for sample in problem.samples]
        # Editor HTML is cleaned like any rich text; plain text becomes paragraphs.
        self.assertTrue(explanations[0].startswith("<p>Odd, so <em>one</em>.</p><img"))
        self.assertNotIn("onerror", explanations[0])
        self.assertEqual(explanations[1:], ["<p>plain<br />lines</p>", ""])
        public = self.client.get(self.reverse("problem_api") + "?problem_id=" + problem._id)
        self.assertSuccess(public)
        self.assertEqual(public.data["data"]["data_range"], problem.data_range)
        self.assertEqual(public.data["data"]["samples"][0]["explanation"], explanations[0])

    def test_problem_without_data_range_defaults_to_empty(self):
        self.data.pop("data_range", None)
        resp = self.client.post(self.url, data=self.data)
        self.assertSuccess(resp)
        self.assertEqual(resp.data["data"]["data_range"], "")

    def test_display_id_is_assigned_sequentially(self):
        self.test_create_problem()
        resp = self.client.post(self.url, data=self.data)
        self.assertSuccess(resp)
        self.assertEqual(resp.data["data"]["_id"], "1002")

    def test_remote_problem_does_not_advance_local_display_id(self):
        remote_data = copy.deepcopy(DEFAULT_PROBLEM_DATA)
        remote_data.update({
            "_id": "CF4A",
            "judge_mode": ProblemJudgeMode.REMOTE,
            "remote_oj": RemoteOJ.CODEFORCES,
            "remote_problem_id": "4A",
            "test_case_id": "",
            "test_case_score": [],
        })
        self.add_problem(remote_data, self.admin)
        resp = self.client.post(self.url, data=self.data)
        self.assertSuccess(resp)
        self.assertEqual(resp.data["data"]["_id"], "1001")

    def test_spj(self):
        data = copy.deepcopy(self.data)
        data["spj"] = True

        resp = self.client.post(self.url, data)
        self.assertFailed(resp, "Invalid spj")

        data["spj_code"] = "test"
        resp = self.client.post(self.url, data=data)
        self.assertSuccess(resp)

    def test_get_problem(self):
        self.test_create_problem()
        resp = self.client.get(self.url)
        self.assertSuccess(resp)

    def test_get_one_problem(self):
        problem_id = self.test_create_problem().data["data"]["id"]
        resp = self.client.get(self.url + "?id=" + str(problem_id))
        self.assertSuccess(resp)

    def test_edit_problem(self):
        problem_id = self.test_create_problem().data["data"]["id"]
        data = copy.deepcopy(self.data)
        data["_id"] = "9999"
        data["id"] = problem_id
        resp = self.client.put(self.url, data=data)
        self.assertSuccess(resp)
        self.assertEqual(Problem.objects.get(id=problem_id)._id, "1001")


class NowcoderProblemImportTest(APITestCase):
    def setUp(self):
        self.url = self.reverse("remote_problem_import_api")
        self.admin = self.create_super_admin()

    def _response(self):
        response = Mock()
        response.status_code = 200
        response.text = NOWCODER_PROBLEM_HTML
        return response

    def test_parse_reference_and_page(self):
        self.assertEqual(
            parse_nowcoder_reference(
                f"https://www.nowcoder.com/questionTerminal/{NOWCODER_PROBLEM_UUID}"
            ),
            NOWCODER_PROBLEM_UUID,
        )
        data = parse_nowcoder_problem_page(NOWCODER_PROBLEM_HTML, NOWCODER_PROBLEM_UUID)
        self.assertEqual(data["question_id"], "11742270")
        self.assertEqual(data["languages"], ["Java", "C++"])
        self.assertEqual(data["samples"], [{"input": "1 2", "output": "3"}])
        self.assertNotIn("<script", data["description"])
        self.assertNotIn("bad()", data["description"])

        self.assertEqual(parse_nowcoder_reference("NC322024"), "NC322024")
        self.assertEqual(parse_nowcoder_reference("322024"), "NC322024")
        self.assertEqual(
            parse_nowcoder_reference("https://ac.nowcoder.com/acm/problem/322024"),
            "NC322024",
        )
        acm = parse_nowcoder_acm_problem_page(NOWCODER_ACM_PROBLEM_HTML, "322024")
        self.assertEqual(acm["remote_id"], "NC322024")
        self.assertEqual(acm["question_id"], "11776488")
        self.assertEqual(acm["samples"], [{"input": "1 0", "output": "1"}])
        self.assertEqual(acm["time_limit"], 2000)
        self.assertEqual(acm["memory_limit"], 256)
        self.assertNotIn("bad()", acm["description"])
        self.assertNotIn(r"\hspace", acm["description"])
        self.assertIn(r"\(a = \{a_1, a_2,\dots, a_n\}\)", acm["description"])
        self.assertIn(r"\(i\left(1 \leq i \leq n \right)\)", acm["description"])
        self.assertIn(r"\(x*i\)", acm["description"])
        self.assertIn(r"\(y_1\)", acm["description"])
        self.assertNotIn(r"\hspace", acm["description"])
        self.assertIn('<a href="https://example.com/note"', acm["description"])
        self.assertIn('<img src="https://uploadfiles.nowcoder.com/example.png"', acm["description"])
        self.assertIn("说明", acm["description"])
        self.assertIn(r"\(n,r\left(1 \le n; 0 \le r&lt;4\right)\)", acm["input_description"])

    def test_markdown_emphasis_never_splits_formulas(self):
        # `$a*b*c$` used to become `$a<em>b</em>c$`: the delimiters end up in
        # different elements and the statement renders no formula at all.
        self.assertEqual(
            markdown_to_html("求 $a*b*c$ 与 $2*3*4$ 的值"),
            "<p>求 $a*b*c$ 与 $2*3*4$ 的值</p>",
        )
        self.assertEqual(
            markdown_to_html(r"$x<y$ 且 $a \le b$，正文 **加粗**"),
            r"<p>$x&lt;y$ 且 $a \le b$，正文 <strong>加粗</strong></p>",
        )

    def test_parse_luogu_and_codeforces_pages(self):
        self.assertEqual(parse_luogu_reference("https://www.luogu.com.cn/problem/P1001"), "P1001")
        luogu = parse_luogu_problem_page(LUOGU_PROBLEM_HTML, "P1001")
        self.assertEqual(luogu["title"], "A+B Problem")
        self.assertEqual(luogu["samples"], [{"input": "20 30\n", "output": "50\n"}])
        self.assertEqual(luogu["memory_limit"], 512)
        self.assertIn("<strong>Background</strong>", luogu["description"])

        rendered = markdown_to_html(
            "[受信任的用户](https://help.luogu.com.cn/rules/community/discuss#permissions)\n\n"
            "> 任何一个伟大的思想。\n\n```cpp\nint main() {}\n```"
        )
        self.assertIn('<a href="https://help.luogu.com.cn/rules/community/discuss#permissions"', rendered)
        self.assertIn("<blockquote>任何一个伟大的思想。</blockquote>", rendered)
        self.assertIn('<code class="language-cpp">', rendered)
        legacy = render_residual_markdown_links(
            '<p>[受信任的用户](https://help.luogu.com.cn/rules)</p>'
            '<pre><code>[do not convert](https://example.com)</code></pre>'
        )
        self.assertIn('<a href="https://help.luogu.com.cn/rules"', legacy)
        self.assertIn('[do not convert](https://example.com)', legacy)

        self.assertEqual(parse_codeforces_reference("https://codeforces.com/problemset/problem/4/A"), (4, "A"))
        codeforces = parse_codeforces_problem_page(CODEFORCES_PROBLEM_HTML, 4, "A")
        self.assertEqual(codeforces["title"], "Watermelon")
        self.assertEqual(codeforces["samples"], [{"input": "8", "output": "YES"}])
        self.assertEqual(codeforces["time_limit"], 1000)
        self.assertEqual(codeforces["memory_limit"], 64)
        self.assertNotIn("bad()", codeforces["description"])

    @patch("problem.tasks.publish_contest_problems.send_with_options")
    def test_schedule_post_contest_publication(self, mock_send):
        end_time = timezone.now() + timedelta(seconds=60)
        schedule_contest_problem_publication(23, end_time)
        options = mock_send.call_args.kwargs
        self.assertEqual(options["args"], (23,))
        self.assertGreaterEqual(options["delay"], 59000)
        self.assertLessEqual(options["delay"], 61000)

    @patch("problem.remote.nowcoder.requests.get")
    def test_import_nowcoder_problem(self, mock_get):
        mock_get.return_value = self._response()
        resp = self.client.post(self.url, data={
            "provider": RemoteOJ.NOWCODER,
            "remote_id": NOWCODER_PROBLEM_UUID,
        })
        self.assertSuccess(resp)
        problem = Problem.objects.get(_id="NC11742270")
        self.assertEqual(problem.judge_mode, ProblemJudgeMode.REMOTE)
        self.assertEqual(problem.remote_oj, RemoteOJ.NOWCODER)
        self.assertEqual(problem.remote_problem_id, NOWCODER_PROBLEM_UUID)
        self.assertEqual(problem.remote_problem_data["question_id"], "11742270")
        self.assertEqual(problem.test_case_id, "")
        self.assertTrue(problem.visible)
        self.assertTrue(problem.tags.filter(name="牛客").exists())

        duplicate = self.client.post(self.url, data={
            "provider": RemoteOJ.NOWCODER,
            "remote_id": NOWCODER_PROBLEM_UUID,
        })
        self.assertFailed(duplicate, "Remote problem already exists")

        contest = Contest.objects.create(created_by=self.admin, **DEFAULT_CONTEST_DATA)
        add_to_contest = self.client.post(
            self.reverse("add_contest_problem_from_public_api"),
            data={
                "problem_id": problem.id,
                "contest_id": contest.id,
            },
        )
        self.assertSuccess(add_to_contest)
        contest_problem = Problem.objects.get(contest=contest, _id="A")
        self.assertEqual(contest_problem.judge_mode, ProblemJudgeMode.REMOTE)
        self.assertEqual(contest_problem.remote_problem_id, NOWCODER_PROBLEM_UUID)
        self.assertEqual(contest_problem.test_case_id, "")
        self.assertTrue(contest_problem.visible)

    @patch("problem.views.admin.fetch_remote_problem")
    def test_import_luogu_and_codeforces_problem(self, mock_fetch):
        def remote_problem(provider, reference):
            remote_id = "P1001" if provider == RemoteOJ.LUOGU else "4A"
            title = "A+B Problem" if provider == RemoteOJ.LUOGU else "Watermelon"
            return {
                "remote_id": remote_id,
                "default_display_id": f"LG{remote_id}" if provider == RemoteOJ.LUOGU else f"CF{remote_id}",
                "title": title,
                "description": "<p>Description</p>",
                "input_description": "<p>Input</p>",
                "output_description": "<p>Output</p>",
                "samples": [{"input": "1", "output": "1"}],
                "hint": "",
                "languages": ["C++"],
                "time_limit": 1000,
                "memory_limit": 256,
                "difficulty": "Low",
                "source": f"{provider} {remote_id}",
                "tag": provider,
                "metadata": {"language_ids": {"C++": "12"}},
            }

        mock_fetch.side_effect = remote_problem
        for provider, expected_id in (
                (RemoteOJ.LUOGU, "LGP1001"),
                (RemoteOJ.CODEFORCES, "CF4A")):
            response = self.client.post(self.url, data={
                "provider": provider,
                "remote_id": "P1001" if provider == RemoteOJ.LUOGU else "4A",
            })
            self.assertSuccess(response)
            problem = Problem.objects.get(_id=expected_id)
            self.assertEqual(problem.remote_oj, provider)
            self.assertEqual(problem.test_case_id, "")
            self.assertTrue(problem.visible)

    @patch("problem.remote.codeforces._fetch_problem_metadata")
    def test_import_codeforces_problem_from_browser_page(self, mock_metadata):
        mock_metadata.return_value = {
            "name": "Watermelon",
            "rating": 800,
            "tags": ["brute force", "math"],
        }
        response = self.client.post(self.url, data={
            "provider": RemoteOJ.CODEFORCES,
            "remote_id": "4A",
            "page_html": CODEFORCES_PROBLEM_HTML,
        })
        self.assertSuccess(response)
        problem = Problem.objects.get(_id="CF4A")
        self.assertEqual(problem.remote_oj, RemoteOJ.CODEFORCES)
        self.assertEqual(problem.remote_problem_id, "4A")
        self.assertEqual(problem.title, "Watermelon")
        self.assertEqual(problem.samples, [{"input": "8", "output": "YES"}])
        self.assertEqual(problem.remote_problem_data["rating"], 800)
        mock_metadata.assert_called_once_with(4, "A")

    @patch("problem.views.admin.fetch_remote_problem")
    def test_import_new_remote_problem_into_contest_and_publish_after_end(self, mock_fetch):
        mock_fetch.return_value = {
            "remote_id": "71A",
            "default_display_id": "CF71A",
            "title": "Way Too Long Words",
            "description": "<p>Description</p>",
            "input_description": "<p>Input</p>",
            "output_description": "<p>Output</p>",
            "samples": [{"input": "1", "output": "1"}],
            "hint": "",
            "languages": ["C++"],
            "time_limit": 1000,
            "memory_limit": 256,
            "difficulty": "Low",
            "source": "Codeforces 71A",
            "tag": "Codeforces",
            "metadata": {
                "contest_id": 71,
                "index": "A",
                "url": "https://codeforces.com/problemset/problem/71/A",
                "language_ids": {"C++": "54"},
            },
        }
        contest = Contest.objects.create(created_by=self.admin, **DEFAULT_CONTEST_DATA)
        response = self.client.post(self.url, data={
            "provider": RemoteOJ.CODEFORCES,
            "remote_id": "71A",
            "contest_id": contest.id,
        })
        self.assertSuccess(response)
        contest_problem = Problem.objects.get(contest=contest, _id="A")
        self.assertTrue(contest_problem.publish_after_contest)
        self.assertEqual(contest_problem.post_contest_display_id, "CF71A")
        self.assertFalse(Problem.objects.filter(contest_id__isnull=True, remote_problem_id="71A").exists())

        contest.end_time = timezone.now() - timedelta(seconds=1)
        contest.save(update_fields=("end_time",))
        published = publish_due_contest_problems([contest.id])
        self.assertEqual(len(published), 1)
        public_problem = Problem.objects.get(contest_id__isnull=True, remote_problem_id="71A")
        self.assertEqual(public_problem._id, "CF71A")
        self.assertTrue(public_problem.visible)
        contest_problem.refresh_from_db()
        self.assertTrue(contest_problem.is_public)
        self.assertFalse(contest_problem.publish_after_contest)


class ProblemAPITest(ProblemCreateTestBase):
    def setUp(self):
        self.url = self.reverse("problem_api")
        admin = self.create_admin(login=False)
        self.problem = self.add_problem(DEFAULT_PROBLEM_DATA, admin)
        self.create_user("test", "test123")

    def test_get_problem_list(self):
        resp = self.client.get(f"{self.url}?limit=10")
        self.assertSuccess(resp)

    def get_one_problem(self):
        resp = self.client.get(self.url + "?id=" + self.problem._id)
        self.assertSuccess(resp)


class ContestProblemAdminTest(APITestCase):
    def setUp(self):
        self.url = self.reverse("contest_problem_admin_api")
        self.create_admin()
        self.contest = self.client.post(self.reverse("contest_admin_api"), data=DEFAULT_CONTEST_DATA).data["data"]

    def test_create_contest_problem(self):
        data = copy.deepcopy(DEFAULT_PROBLEM_DATA)
        data["contest_id"] = self.contest["id"]
        resp = self.client.post(self.url, data=data)
        self.assertSuccess(resp)
        self.assertEqual(resp.data["data"]["_id"], "A")
        return resp.data["data"]

    def test_get_contest_problem(self):
        self.test_create_contest_problem()
        contest_id = self.contest["id"]
        resp = self.client.get(self.url + "?contest_id=" + str(contest_id))
        self.assertSuccess(resp)
        self.assertEqual(len(resp.data["data"]["results"]), 1)

    def test_get_one_contest_problem(self):
        contest_problem = self.test_create_contest_problem()
        contest_id = self.contest["id"]
        problem_id = contest_problem["id"]
        resp = self.client.get(f"{self.url}?contest_id={contest_id}&id={problem_id}")
        self.assertSuccess(resp)


class ContestProblemTest(ProblemCreateTestBase):
    def setUp(self):
        admin = self.create_admin()
        url = self.reverse("contest_admin_api")
        contest_data = copy.deepcopy(DEFAULT_CONTEST_DATA)
        contest_data["password"] = ""
        contest_data["start_time"] = contest_data["start_time"] + timedelta(hours=1)
        self.contest = self.client.post(url, data=contest_data).data["data"]
        self.problem = self.add_problem(DEFAULT_PROBLEM_DATA, admin)
        self.problem.contest_id = self.contest["id"]
        self.problem.save()
        self.url = self.reverse("contest_problem_api")

    def test_admin_get_contest_problem_list(self):
        contest_id = self.contest["id"]
        resp = self.client.get(self.url + "?contest_id=" + str(contest_id))
        self.assertSuccess(resp)
        self.assertEqual(len(resp.data["data"]), 1)

    def test_admin_get_one_contest_problem(self):
        contest_id = self.contest["id"]
        problem_id = self.problem._id
        resp = self.client.get("{}?contest_id={}&problem_id={}".format(self.url, contest_id, problem_id))
        self.assertSuccess(resp)

    def test_regular_user_get_not_started_contest_problem(self):
        self.create_user("test", "test123")
        resp = self.client.get(self.url + "?contest_id=" + str(self.contest["id"]))
        self.assertDictEqual(resp.data, {"error": "error", "data": "Contest has not started yet."})

    def test_reguar_user_get_started_contest_problem(self):
        self.create_user("test", "test123")
        contest = Contest.objects.first()
        contest.start_time = contest.start_time - timedelta(hours=1)
        contest.save()
        resp = self.client.get(self.url + "?contest_id=" + str(self.contest["id"]))
        self.assertSuccess(resp)


class AddProblemFromPublicProblemAPITest(ProblemCreateTestBase):
    def setUp(self):
        admin = self.create_admin()
        url = self.reverse("contest_admin_api")
        contest_data = copy.deepcopy(DEFAULT_CONTEST_DATA)
        contest_data["password"] = ""
        contest_data["start_time"] = contest_data["start_time"] + timedelta(hours=1)
        self.contest = self.client.post(url, data=contest_data).data["data"]
        self.problem = self.add_problem(DEFAULT_PROBLEM_DATA, admin)
        self.url = self.reverse("add_contest_problem_from_public_api")
        self.data = {
            "contest_id": self.contest["id"],
            "problem_id": self.problem.id
        }

    def test_add_contest_problem(self):
        resp = self.client.post(self.url, data=self.data)
        self.assertSuccess(resp)
        self.assertTrue(Problem.objects.all().exists())
        self.assertTrue(Problem.objects.filter(contest_id=self.contest["id"]).exists())

    def test_add_contest_problem_assigns_next_letter(self):
        resp = self.client.post(self.url, data=self.data)
        self.assertSuccess(resp)
        self.assertTrue(Problem.objects.filter(contest_id=self.contest["id"], _id="A").exists())


class ParseProblemTemplateTest(APITestCase):
    def test_parse(self):
        template_str = """
//PREPEND BEGIN
aaa
//PREPEND END

//TEMPLATE BEGIN
bbb
//TEMPLATE END

//APPEND BEGIN
ccc
//APPEND END
"""

        ret = parse_problem_template(template_str)
        self.assertEqual(ret["prepend"], "aaa\n")
        self.assertEqual(ret["template"], "bbb\n")
        self.assertEqual(ret["append"], "ccc\n")

    def test_parse1(self):
        template_str = """
//PREPEND BEGIN
aaa
//PREPEND END

//APPEND BEGIN
ccc
//APPEND END
//APPEND BEGIN
ddd
//APPEND END
"""

        ret = parse_problem_template(template_str)
        self.assertEqual(ret["prepend"], "aaa\n")
        self.assertEqual(ret["template"], "")
        self.assertEqual(ret["append"], "ccc\n")
