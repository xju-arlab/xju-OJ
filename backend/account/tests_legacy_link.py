from unittest.mock import patch
import hashlib

from django.test import override_settings

from account import oidc
from account.models import ExternalIdentity, User
from utils.api.tests import APITestCase
from utils.cache import cache


@override_settings(AUTHENTIK_OIDC_ENABLED=True,
                   AUTHENTIK_OIDC_ISSUER="https://auth.icthub.top/application/o/xju-oj/")
class LegacyAccountLinkTests(APITestCase):
    def setUp(self):
        self.user = self.create_user("legacy-link", "test-password", login=False)
        self.user.email = None
        self.user.save(update_fields=["email"])
        self.url = self.reverse("oidc_legacy_email_link")
        self.payload = {"username": self.user.username, "password": "test-password", "captcha": "1234"}
        bucket = hashlib.sha256(f"{self.user.username}\0{ '127.0.0.1'}".encode()).hexdigest()
        key = "xju-oj:legacy-email-link:" + bucket
        cache.delete(key)
        self.addCleanup(cache.delete, key)
        patcher = patch("account.oidc.Captcha.check", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = patch("account.oidc.start", return_value="https://auth.icthub.top/authorize")
        self.start = patcher.start()
        self.addCleanup(patcher.stop)

    def test_password_proof_starts_binding_but_does_not_log_in(self):
        response = self.client.post(self.url, self.payload)
        self.assertSuccess(response)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(self.start.call_args.kwargs["linked_user_id"], self.user.pk)

    def test_bound_email_or_disabled_user_cannot_use_legacy_flow(self):
        for changes in ({"email": "present@example.test"}, {"email": None, "is_disabled": True}):
            User.objects.filter(pk=self.user.pk).update(**changes)
            self.assertFailed(self.client.post(self.url, self.payload))
        self.start.assert_not_called()

    def test_two_factor_is_still_required(self):
        User.objects.filter(pk=self.user.pk).update(two_factor_auth=True, tfa_token="secret")
        self.assertFailed(self.client.post(self.url, self.payload))
        self.start.assert_not_called()

    def test_callback_rechecks_eligibility_under_user_lock(self):
        # The mailbox changed after password verification but before token exchange finished.
        User.objects.filter(pk=self.user.pk).update(email="new@example.test")
        claims = {"sub": "subject", "email": "studio@example.test", "email_verified": True,
                  "icthub_account_id": "23456789", "preferred_username": "studio"}
        with self.assertRaisesRegex(oidc.OIDCError, "link_session_changed"):
            oidc.provision_or_get(claims, mode="link", linked_user_id=self.user.pk, legacy_link=True)
        self.assertFalse(ExternalIdentity.objects.filter(user=self.user).exists())
