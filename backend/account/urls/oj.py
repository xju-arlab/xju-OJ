from django.urls import re_path

from ..views.oj import (ApplyResetPasswordAPI, ResetPasswordAPI,
                        UserChangePasswordAPI, UserRegisterAPI, UserChangeEmailAPI,
                        UserLoginAPI, UserLogoutAPI, UsernameOrEmailCheck,
                        AvatarUploadAPI, TwoFactorAuthAPI, UserProfileAPI,
                        UserRankAPI, CheckTFARequiredAPI, SessionManagementAPI,
                        ProfileProblemDisplayIDRefreshAPI, OpenAPIAppkeyAPI, SSOAPI)

from utils.captcha.views import CaptchaAPIView
from ..oidc import LegacyEmailLinkAPI, ProvidersAPI, oidc_callback, oidc_link, oidc_login, oidc_logout

urlpatterns = [
    re_path(r"^login/?$", UserLoginAPI.as_view(), name="user_login_api"),
    re_path(r"^logout/?$", UserLogoutAPI.as_view(), name="user_logout_api"),
    re_path(r"^register/?$", UserRegisterAPI.as_view(), name="user_register_api"),
    re_path(r"^change_password/?$", UserChangePasswordAPI.as_view(), name="user_change_password_api"),
    re_path(r"^change_email/?$", UserChangeEmailAPI.as_view(), name="user_change_email_api"),
    re_path(r"^apply_reset_password/?$", ApplyResetPasswordAPI.as_view(), name="apply_reset_password_api"),
    re_path(r"^reset_password/?$", ResetPasswordAPI.as_view(), name="reset_password_api"),
    re_path(r"^captcha/?$", CaptchaAPIView.as_view(), name="show_captcha"),
    re_path(r"^check_username_or_email", UsernameOrEmailCheck.as_view(), name="check_username_or_email"),
    re_path(r"^profile/?$", UserProfileAPI.as_view(), name="user_profile_api"),
    re_path(r"^profile/fresh_display_id", ProfileProblemDisplayIDRefreshAPI.as_view(), name="display_id_fresh"),
    re_path(r"^upload_avatar/?$", AvatarUploadAPI.as_view(), name="avatar_upload_api"),
    re_path(r"^tfa_required/?$", CheckTFARequiredAPI.as_view(), name="tfa_required_check"),
    re_path(r"^two_factor_auth/?$", TwoFactorAuthAPI.as_view(), name="two_factor_auth_api"),
    re_path(r"^user_rank/?$", UserRankAPI.as_view(), name="user_rank_api"),
    re_path(r"^sessions/?$", SessionManagementAPI.as_view(), name="session_management_api"),
    re_path(r"^open_api_appkey/?$", OpenAPIAppkeyAPI.as_view(), name="open_api_appkey_api"),
    re_path(r"^sso?$", SSOAPI.as_view(), name="sso_api"),
    re_path(r"^auth/providers/?$", ProvidersAPI.as_view(), name="auth_providers_api"),
    re_path(r"^auth/oidc/login/?$", oidc_login, name="oidc_login"),
    re_path(r"^auth/oidc/callback/?$", oidc_callback, name="oidc_callback"),
    re_path(r"^auth/oidc/link/?$", oidc_link, name="oidc_link"),
    re_path(r"^auth/oidc/legacy-email-link/?$", LegacyEmailLinkAPI.as_view(), name="oidc_legacy_email_link"),
    re_path(r"^auth/oidc/logout/?$", oidc_logout, name="oidc_logout"),
]
