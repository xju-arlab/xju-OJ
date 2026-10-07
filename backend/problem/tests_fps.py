import json
from pathlib import Path
import tempfile
from unittest.mock import patch

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase

from fps.parser import FPSHelper, FPSParser
from problem.models import Problem
from utils.api.tests import APITestCase


ITEM = '''<item><title>FPS regression</title><description>statement</description>
<input>input</input><output>output</output><time_limit unit="s">1</time_limit>
<memory_limit unit="KB">65536</memory_limit><test_input>中文</test_input><test_output></test_output></item>'''


class FPSParserTests(SimpleTestCase):
    def test_string_input_unicode_byte_sizes_and_empty_output(self):
        problem = FPSParser(string_data=f'<fps version="1.2">{ITEM}</fps>').parse()[0]
        self.assertEqual(problem["memory_limit"], {"unit": "MB", "value": 64})
        with tempfile.TemporaryDirectory() as directory:
            info = FPSHelper().save_test_case(problem, directory)
            self.assertEqual(info["test_cases"]["1"]["input_size"], 6)
            self.assertEqual(info["test_cases"]["1"]["output_size"], 0)
            self.assertEqual(Path(directory, "1.out").read_bytes(), b"")
            self.assertEqual(json.loads(Path(directory, "info").read_text()), info)

    def test_unpaired_normal_testcase_is_rejected(self):
        with self.assertRaises(ValueError):
            FPSParser(string_data=f'<fps version="1.2">{ITEM.replace("<test_output></test_output>", "")}</fps>').parse()


class FPSImportTests(APITestCase):
    def setUp(self):
        self.create_super_admin()
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.runtime = self.settings(TEST_CASE_DIR=self.directory.name, UPLOAD_DIR=self.directory.name)
        self.runtime.enable()
        self.addCleanup(self.runtime.disable)

    def upload(self, items):
        return self.client.post('/api/admin/import_fps', {
            "file": SimpleUploadedFile("problems.xml", f'<fps version="1.2">{items}</fps>'.encode())
        }, format="multipart")

    def test_bad_second_problem_does_not_leave_partial_import(self):
        original = Problem.objects.count()
        response = self.upload(ITEM + ITEM.replace('<time_limit unit="s">1</time_limit>', ''))
        self.assertFailed(response)
        self.assertEqual(Problem.objects.count(), original)
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])

    def test_valid_import_preserves_files_and_memory_units(self):
        self.assertSuccess(self.upload(ITEM))
        problem = Problem.objects.get(title="FPS regression")
        self.assertEqual(problem.memory_limit, 64)
        self.assertTrue(Path(self.directory.name, problem.test_case_id, "1.out").is_file())

    def test_database_failure_rolls_back_files(self):
        with patch("problem.views.admin.FPSProblemImport._create_problem", side_effect=ValueError("test failure")):
            self.assertFailed(self.upload(ITEM))
        self.assertEqual(list(Path(self.directory.name).iterdir()), [])
