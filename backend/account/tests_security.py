from concurrent.futures import ThreadPoolExecutor
from importlib import import_module
from threading import Event
from types import SimpleNamespace

from django.conf import settings
from django.test import RequestFactory, SimpleTestCase
from rest_framework.test import APIClient

from account.decorators import login_required
from account.middleware import SessionRecordMiddleware
from account.models import AdminType, User
from submission.tests import SubmissionPrepare
from utils.api.tests import APITestCase


class PermissionConcurrencyTests(SimpleTestCase):
    def test_disabled_request_cannot_borrow_another_requests_user(self):
        entered, released = Event(), Event()

        class DisabledUser:
            is_disabled = True

            @property
            def is_authenticated(self):
                entered.set()
                if not released.wait(3):
                    raise AssertionError("second request did not finish")
                return True

        class View:
            @login_required
            def get(self, request):
                return "allowed"

        with ThreadPoolExecutor(max_workers=1) as pool:
            pending = pool.submit(View().get, SimpleNamespace(user=DisabledUser()))
            try:
                self.assertTrue(entered.wait(3))
                self.assertEqual(View().get(SimpleNamespace(user=SimpleNamespace(
                    is_authenticated=True, is_disabled=False))), "allowed")
            finally:
                released.set()
            self.assertNotEqual(pending.result(), "allowed")


class SessionSecurityTests(APITestCase):
    def test_foreign_session_delete_does_not_revoke_its_owner(self):
        victim = self.create_user("victim", "password", login=False)
        victim_client = APIClient()
        victim_client.login(username=victim.username, password="password")
        victim_client.get(self.reverse("user_profile_api"))
        victim_key = victim_client.session.session_key
        self.create_user("attacker", "password")
        response = self.client.delete(
            self.reverse("session_management_api") + "?session_key=" + victim_key)
        self.assertFailed(response)
        store = import_module(settings.SESSION_ENGINE).SessionStore(victim_key)
        self.assertEqual(int(store["_auth_user_id"]), victim.pk)

    def test_session_record_preserves_concurrent_role_change(self):
        stale_user = self.create_user("stale", "password", login=False)
        User.objects.filter(pk=stale_user.pk).update(admin_type=AdminType.SUPER_ADMIN)
        request = RequestFactory().get("/")
        request.user = stale_user
        request.session = import_module(settings.SESSION_ENGINE).SessionStore()
        request.session.create()
        SessionRecordMiddleware(lambda request: None).process_request(request)
        stale_user.refresh_from_db()
        self.assertEqual(stale_user.admin_type, AdminType.SUPER_ADMIN)
        self.assertEqual(stale_user.session_keys, [request.session.session_key])

    def test_api_key_request_does_not_create_browser_session(self):
        request = RequestFactory().get("/")
        request.user = self.create_user("api", "password", login=False)
        request.auth_method = "api_key"
        request.session = import_module(settings.SESSION_ENGINE).SessionStore()
        SessionRecordMiddleware(lambda request: None).process_request(request)
        self.assertFalse(request.session.modified)
        request.user.refresh_from_db()
        self.assertEqual(request.user.session_keys, [])


class ProfileDisplayIdTests(SubmissionPrepare):
    def test_refresh_maps_by_primary_key_and_preserves_missing_or_hidden_ids(self):
        self._create_problem_and_submission()
        user = self.create_user("profile-map", "password")
        original = self.problem.pk
        self.problem.pk = None
        self.problem._id = "second"
        self.problem.save()
        second = self.problem.pk
        profile = user.userprofile
        profile.acm_problems_status = {"problems": {
            str(second): {"_id": "old-second", "status": 0},
            "999999": {"_id": "deleted", "status": 0},
            str(original): {"_id": "old-first", "status": 0},
        }}
        profile.save()
        response = self.client.get(self.reverse("display_id_fresh"))
        self.assertSuccess(response)
        profile.refresh_from_db()
        values = profile.acm_problems_status["problems"]
        self.assertEqual(values[str(second)]["_id"], "second")
        self.assertEqual(values[str(original)]["_id"], "A-110")
        self.assertEqual(values["999999"]["_id"], "deleted")
