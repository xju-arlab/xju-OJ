from concurrent.futures import ThreadPoolExecutor
import io
import os
import tempfile
import time
import uuid

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import SimpleTestCase, override_settings
from PIL import Image
from django_redis import get_redis_connection
from rest_framework.test import APIClient

from utils.api.tests import APITestCase
from utils.cache import cache
from utils.throttling import TokenBucket
from utils.xss_filter import XSSHtml


class TokenBucketConcurrencyTests(SimpleTestCase):
    def test_parallel_requests_cannot_spend_the_same_tokens(self):
        key = "test:bucket:" + uuid.uuid4().hex
        redis = get_redis_connection("default", write=True)
        self.addCleanup(redis.delete, key)
        bucket = TokenBucket(key, 5, 0.01, 5, cache)
        with ThreadPoolExecutor(max_workers=16) as executor:
            results = list(executor.map(lambda _: bucket.consume(), range(32)))
        self.assertEqual(sum(allowed for allowed, _ in results), 5)
        self.assertTrue(all(wait > 0 for allowed, wait in results if not allowed))
        self.assertGreater(redis.ttl(key), 0)

    def test_existing_bucket_refills_without_exceeding_capacity(self):
        key = "test:bucket:" + uuid.uuid4().hex
        redis = get_redis_connection("default", write=True)
        self.addCleanup(redis.delete, key)
        redis.hset(key, mapping={"last_capacity": 0, "last_timestamp": time.time() - 100})
        bucket = TokenBucket(key, 2, 0.01, 1, cache)
        self.assertTrue(bucket.consume()[0])
        self.assertFalse(bucket.consume()[0])


class UploadCsrfTests(APITestCase):
    def test_authenticated_upload_requires_csrf_token(self):
        self.create_super_admin("upload-admin", "password")
        client = APIClient(enforce_csrf_checks=True)
        client.login(username="upload-admin", password="password")
        for url in ("/api/admin/upload_image/", "/api/admin/upload_file/", "/api/admin/import_fps",
                    "/api/admin/import_problem", "/api/admin/test_case"):
            self.assertEqual(client.post(url, {}, format="multipart").status_code, 403)


class AdminImageUploadTests(APITestCase):
    def setUp(self):
        self.create_super_admin("image-admin", "password")
        self.upload_root = tempfile.TemporaryDirectory()
        self.settings_override = override_settings(UPLOAD_DIR=self.upload_root.name)
        self.settings_override.enable()

    def tearDown(self):
        self.settings_override.disable()
        self.upload_root.cleanup()

    def test_webp_is_accepted_and_disguised_files_are_not(self):
        buffer = io.BytesIO()
        Image.new("RGBA", (2, 2), (0, 0, 0, 0)).save(buffer, format="WEBP", lossless=True)
        response = self.client.post("/api/admin/upload_image/", {
            "image": SimpleUploadedFile("diagram.webp", buffer.getvalue())}, format="multipart")
        self.assertTrue(response.data["success"])
        self.assertTrue(response.data["file_path"].endswith(".webp"))
        response = self.client.post("/api/admin/upload_image/", {
            "image": SimpleUploadedFile("page.png", b"<html>not an image</html>")}, format="multipart")
        self.assertFalse(response.data["success"])
        self.assertEqual(len(os.listdir(self.upload_root.name)), 1)


class RichTextSafetyTests(SimpleTestCase):
    def test_empty_attributes_do_not_crash_cleaning(self):
        cleaned = XSSHtml().clean('<p style class>text</p><a href>link</a><img src onerror="alert(1)">')
        self.assertIn("text", cleaned)
        self.assertNotIn("onerror", cleaned)
