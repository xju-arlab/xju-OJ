import time
from unittest.mock import patch

from django.test import TestCase, override_settings

from account import oidc

AUTHORIZE = "https://auth.icthub.top/application/o/authorize/?state=fresh"


@override_settings(AUTHENTIK_OIDC_ENABLED=True, AUTHENTIK_OIDC_STATE_TTL_SECONDS=300)
class StaleCallbackRestartTests(TestCase):
    """A mailed registration link brings back a state this browser no longer holds."""

    def setUp(self):
        patcher = patch("account.oidc.start", return_value=AUTHORIZE)
        self.start = patcher.start()
        self.addCleanup(patcher.stop)
        self.url = "/api/auth/oidc/callback/"

    def set_pending(self, state, **item):
        session = self.client.session
        pending = session.get(oidc._PENDING_SESSION_KEY, {})
        pending[state] = {"created_at": int(time.time()), "nonce": "n", "code_verifier": "v",
                          "mode": "login", "next": "/", "user_id": None, **item}
        session[oidc._PENDING_SESSION_KEY] = pending
        session.save()

    def test_unknown_state_starts_one_fresh_login(self):
        response = self.client.get(self.url, {"state": "from-another-browser", "code": "c"})
        self.assertRedirects(response, AUTHORIZE, fetch_redirect_response=False)
        self.start.assert_called_once()
        self.assertEqual(self.start.call_args.args[1:], ("login", "/"))

    def test_expired_state_restarts_towards_its_page(self):
        self.set_pending("old", created_at=int(time.time()) - 3600, next="/user-home")
        response = self.client.get(self.url, {"state": "old", "code": "c"})
        self.assertRedirects(response, AUTHORIZE, fetch_redirect_response=False)
        self.assertEqual(self.start.call_args.args[1:], ("login", "/user-home"))
        self.assertNotIn("old", self.client.session[oidc._PENDING_SESSION_KEY])

    def test_second_stale_callback_within_a_minute_fails(self):
        self.client.get(self.url, {"state": "a", "code": "c"})
        response = self.client.get(self.url, {"state": "b", "code": "c"})
        self.assertRedirects(response, "/?auth_error=state_invalid", fetch_redirect_response=False)
        self.start.assert_called_once()

    def test_account_linking_is_not_restarted(self):
        self.set_pending("link", created_at=int(time.time()) - 3600, mode="link", next="/setting/security")
        response = self.client.get(self.url, {"state": "link", "code": "c"})
        self.assertRedirects(response, "/setting/security?auth_error=state_expired", fetch_redirect_response=False)
        self.start.assert_not_called()

    def test_authorization_errors_and_missing_codes_are_not_restarted(self):
        response = self.client.get(self.url, {"state": "x", "error": "access_denied"})
        self.assertRedirects(response, "/?auth_error=state_invalid", fetch_redirect_response=False)
        response = self.client.get(self.url, {"state": "x"})
        self.assertRedirects(response, "/?auth_error=state_invalid", fetch_redirect_response=False)
        self.start.assert_not_called()
