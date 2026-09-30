from django.test import SimpleTestCase

from . import oidc


class OIDCContractTests(SimpleTestCase):
    def test_account_id_is_exactly_eight_digits_and_nonzero_first(self):
        for value in ("12345678", "99999999"):
            self.assertEqual(oidc._account_id_from_claims({"icthub_account_id": value}), value)
        for value in ("01234567", "1234567", "123456789", "abcdefgh", 12345678, None):
            with self.assertRaises(oidc.OIDCError) as context:
                oidc._account_id_from_claims({"icthub_account_id": value})
            self.assertEqual(context.exception.code, "account_claim_invalid")

    def test_return_path_is_a_fixed_internal_allowlist(self):
        self.assertEqual(oidc._safe_next("/"), "/")
        self.assertEqual(oidc._safe_next("/setting/security"), "/setting/security")
        for value in ("https://evil.example/", "//evil.example", "/setting/security?next=/", "/../admin", "\\\\evil"):
            self.assertEqual(oidc._safe_next(value), "/")

    def test_callback_uri_is_exact(self):
        self.assertTrue(oidc._redirect_uri_is_safe("https://oj.icthub.top/api/auth/oidc/callback/"))
        for value in (
            "https://oj.icthub.top/api/auth/oidc/callback",
            "https://oj.icthub.top/api/auth/oidc/callback/?next=/",
            "https://evil.example/api/auth/oidc/callback/",
        ):
            self.assertFalse(oidc._redirect_uri_is_safe(value))

    def test_issuer_document_uses_authentik_wire_form(self):
        self.assertEqual(
            oidc._issuer_document(),
            "https://auth.icthub.top/application/o/xju-oj/",
        )

    def test_claim_storage_contains_no_token_fields(self):
        stored = oidc._claims_for_storage(
            {
                "preferred_username": "studio-user",
                "name": "Studio User",
                "icthub_account_id": "12345678",
                "access_token": "must-not-be-stored",
                "id_token": "must-not-be-stored",
            },
            "user@example.test",
        )
        self.assertEqual(stored["icthub_account_id"], "12345678")
        self.assertNotIn("access_token", stored)
        self.assertNotIn("id_token", stored)

    def test_admin_group_claim_maps_to_oj_super_admin(self):
        user = type("User", (), {
            "admin_type": oidc.AdminType.REGULAR_USER,
            "problem_permission": oidc.ProblemPermission.NONE,
            "save": lambda self, update_fields: setattr(self, "saved", update_fields),
        })()
        oidc._apply_admin_claims(user, {"groups": ["studio-users", "icthub-admins"]})
        self.assertEqual(user.admin_type, oidc.AdminType.SUPER_ADMIN)
        self.assertEqual(user.problem_permission, oidc.ProblemPermission.ALL)
        self.assertEqual(user.saved, ["admin_type", "problem_permission"])

    def test_non_admin_group_claim_does_not_retain_oj_admin_role(self):
        user = type("User", (), {
            "admin_type": oidc.AdminType.SUPER_ADMIN,
            "problem_permission": oidc.ProblemPermission.ALL,
            "save": lambda self, update_fields: setattr(self, "saved", update_fields),
        })()
        oidc._apply_admin_claims(user, {"groups": ["studio-users"]})
        self.assertEqual(user.admin_type, oidc.AdminType.REGULAR_USER)
        self.assertEqual(user.problem_permission, oidc.ProblemPermission.NONE)

    def test_missing_group_claim_keeps_existing_admin_role(self):
        user = type("User", (), {
            "admin_type": oidc.AdminType.SUPER_ADMIN,
            "problem_permission": oidc.ProblemPermission.ALL,
            "save": lambda self, update_fields: setattr(self, "saved", update_fields),
        })()
        oidc._apply_admin_claims(user, {})
        self.assertEqual(user.admin_type, oidc.AdminType.SUPER_ADMIN)
        self.assertEqual(user.problem_permission, oidc.ProblemPermission.ALL)
        self.assertFalse(hasattr(user, "saved"))

    def test_malformed_group_claim_keeps_existing_admin_role(self):
        user = type("User", (), {
            "admin_type": oidc.AdminType.SUPER_ADMIN,
            "problem_permission": oidc.ProblemPermission.ALL,
            "save": lambda self, update_fields: setattr(self, "saved", update_fields),
        })()
        oidc._apply_admin_claims(user, {"groups": "studio-users"})
        self.assertEqual(user.admin_type, oidc.AdminType.SUPER_ADMIN)
        self.assertEqual(user.problem_permission, oidc.ProblemPermission.ALL)
        self.assertFalse(hasattr(user, "saved"))

    def test_manual_admin_role_survives_explicit_non_admin_groups(self):
        user = type("User", (), {
            "admin_type": oidc.AdminType.SUPER_ADMIN,
            "problem_permission": oidc.ProblemPermission.ALL,
            "admin_role_manual_override": True,
            "save": lambda self, update_fields: setattr(self, "saved", update_fields),
        })()
        oidc._apply_admin_claims(user, {"groups": ["studio-users"]})
        self.assertEqual(user.admin_type, oidc.AdminType.SUPER_ADMIN)
        self.assertEqual(user.problem_permission, oidc.ProblemPermission.ALL)
        self.assertFalse(hasattr(user, "saved"))
