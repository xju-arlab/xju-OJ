import base64
import hashlib
import json
import logging
import os
import re
import secrets
import stat
import time
import unicodedata
from urllib.parse import urlencode, urlparse, urlunparse

import requests
from authlib.jose import JsonWebKey, jwt
from authlib.jose.errors import BadSignatureError, DecodeError, JoseError
from django.conf import settings
from django.contrib import auth
from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.shortcuts import redirect
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_GET
from otpauth import OtpAuth

from utils.api import APIView, serializers, validate_serializer
from utils.captcha import Captcha
from .models import AdminType, ExternalIdentity, ProblemPermission, User, UserProfile

logger = logging.getLogger(__name__)

_PROVIDER = "authentik"
_PENDING_SESSION_KEY = "authentik_oidc_pending"
_LEGACY_LINK_ATTEMPT_LIMIT = 5
_LEGACY_LINK_ATTEMPT_WINDOW = 15 * 60
_DISCOVERY_TTL = 300
_JWKS_TTL = 600
_HTTP_TIMEOUT = (4, 12)
_USERNAME_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,31}$")
_STUDIO_ACCOUNT_ID_RE = re.compile(r"^[1-9][0-9]{7}$")
_CANONICAL_ISSUER = "https://auth.icthub.top/application/o/xju-oj"
_CANONICAL_REDIRECT_URI = "https://oj.icthub.top/api/auth/oidc/callback/"
_CANONICAL_POST_LOGOUT_URI = "https://oj.icthub.top"
_ALLOWED_NEXT_PATHS = frozenset({"/", "/user-home", "/setting/profile", "/setting/security"})
_ADMIN_GROUP = "icthub-admins"


class OIDCError(Exception):
    """A safe, user-facing OIDC failure without upstream response data."""

    def __init__(self, code="oidc_error"):
        self.code = code
        super().__init__(code)


def enabled():
    return bool(settings.AUTHENTIK_OIDC_ENABLED)


def _issuer():
    value = settings.AUTHENTIK_OIDC_ISSUER.rstrip("/")
    parsed = urlparse(value)
    if parsed.scheme != "https" or parsed.netloc != "auth.icthub.top" or value != _CANONICAL_ISSUER:
        raise OIDCError("oidc_configuration")
    return value


def _issuer_document():
    """Return the exact issuer URL form used in discovery and ID tokens."""

    return f"{_issuer()}/"


def _safe_next(value, default="/"):
    if not value:
        return default
    parsed = urlparse(value)
    if (
        not value.startswith("/")
        or value.startswith("//")
        or parsed.scheme
        or parsed.netloc
        or parsed.query
        or parsed.fragment
        or "\\" in value
        or parsed.path not in _ALLOWED_NEXT_PATHS
    ):
        return default
    return parsed.path


def _error_redirect(next_path, code):
    next_path = _safe_next(next_path)
    parsed = urlparse(next_path)
    query = dict()
    # Only fixed error codes are ever added to the browser URL.
    query["auth_error"] = code
    merged = urlencode(query)
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, parsed.params, merged, parsed.fragment))


def _http_session():
    session = requests.Session()
    # Runtime containers must not inherit workstation proxy settings.
    session.trust_env = False
    session.headers.update({"Accept": "application/json"})
    return session


def _cache_key(kind):
    digest = hashlib.sha256(_issuer().encode("utf-8")).hexdigest()[:24]
    return f"xju-oj:oidc:{kind}:{digest}"


def _endpoint_is_safe(value):
    parsed = urlparse(value or "")
    issuer = urlparse(_issuer())
    return (
        parsed.scheme == issuer.scheme
        and parsed.hostname == issuer.hostname
        and parsed.port == issuer.port
        and not parsed.username
        and not parsed.password
        and not parsed.params
        and not parsed.query
        and not parsed.fragment
    )


def _redirect_uri_is_safe(value):
    return value == _CANONICAL_REDIRECT_URI


def _fetch_json(url, error_code):
    if not _endpoint_is_safe(url):
        raise OIDCError("oidc_configuration")
    try:
        response = _http_session().get(url, timeout=_HTTP_TIMEOUT)
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Authentik OIDC %s request failed: %s", error_code, exc.__class__.__name__)
        raise OIDCError(error_code) from exc
    if not isinstance(data, dict):
        raise OIDCError(error_code)
    return data


def _cached_json(key, url, ttl, error_code, force=False):
    if not force:
        try:
            cached = cache.get(key)
        except Exception:
            cached = None
        if isinstance(cached, dict):
            return cached
    data = _fetch_json(url, error_code)
    try:
        cache.set(key, data, ttl)
    except Exception:
        logger.warning("Authentik OIDC cache write failed")
    return data


def discovery(force=False):
    issuer = _issuer()
    metadata = _cached_json(
        _cache_key("discovery"),
        f"{issuer}/.well-known/openid-configuration",
        _DISCOVERY_TTL,
        "discovery_unavailable",
        force=force,
    )
    if metadata.get("issuer") != _issuer_document():
        raise OIDCError("issuer_mismatch")
    required = ("authorization_endpoint", "token_endpoint", "jwks_uri")
    if any(not _endpoint_is_safe(metadata.get(key, "")) for key in required):
        raise OIDCError("oidc_configuration")
    if metadata.get("userinfo_endpoint") and not _endpoint_is_safe(metadata["userinfo_endpoint"]):
        raise OIDCError("oidc_configuration")
    if metadata.get("end_session_endpoint") and not _endpoint_is_safe(metadata["end_session_endpoint"]):
        raise OIDCError("oidc_configuration")
    return metadata


def _client_secret():
    path = settings.AUTHENTIK_OIDC_CLIENT_SECRET_FILE
    try:
        mode = stat.S_IMODE(os.stat(path).st_mode)
        # Docker Compose secrets are commonly mounted read-only as 0444; reject
        # writable group/other modes without requiring a specific mount mode.
        if mode & 0o022:
            raise OIDCError("oidc_configuration")
        with open(path, "r", encoding="utf-8") as handle:
            value = handle.read().rstrip("\r\n")
    except OIDCError:
        raise
    except OSError as exc:
        logger.warning("Authentik OIDC client secret file unavailable: %s", exc.__class__.__name__)
        raise OIDCError("oidc_configuration") from exc
    if not value or "\n" in value or "\r" in value:
        raise OIDCError("oidc_configuration")
    return value


def _require_config():
    client_id = settings.AUTHENTIK_OIDC_CLIENT_ID
    redirect_uri = settings.AUTHENTIK_OIDC_REDIRECT_URI
    if not client_id or not _redirect_uri_is_safe(redirect_uri):
        raise OIDCError("oidc_configuration")
    if settings.AUTHENTIK_OIDC_POST_LOGOUT_REDIRECT_URI.rstrip("/") != _CANONICAL_POST_LOGOUT_URI:
        raise OIDCError("oidc_configuration")
    if settings.AUTHENTIK_OIDC_STATE_TTL_SECONDS < 60 or settings.AUTHENTIK_OIDC_STATE_TTL_SECONDS > 900:
        raise OIDCError("oidc_configuration")
    if settings.AUTHENTIK_OIDC_CLOCK_SKEW_SECONDS < 0 or settings.AUTHENTIK_OIDC_CLOCK_SKEW_SECONDS > 300:
        raise OIDCError("oidc_configuration")
    if not settings.AUTHENTIK_OIDC_ALLOWED_ALGORITHMS:
        raise OIDCError("oidc_configuration")
    return client_id, redirect_uri


def _pkce_challenge(verifier):
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def _pending_states(request):
    value = request.session.get(_PENDING_SESSION_KEY, {})
    return value if isinstance(value, dict) else {}


def start(request, mode="login", next_path="/", linked_user_id=None):
    if not enabled():
        raise OIDCError("oidc_disabled")
    client_id, redirect_uri = _require_config()
    metadata = discovery()
    _client_secret()  # Fail before redirect when the server is misconfigured.
    state = secrets.token_urlsafe(32)
    nonce = secrets.token_urlsafe(32)
    verifier = secrets.token_urlsafe(64)
    pending = _pending_states(request)
    now = int(time.time())
    pending = {
        key: item
        for key, item in pending.items()
        if isinstance(item, dict) and now - int(item.get("created_at", 0)) <= settings.AUTHENTIK_OIDC_STATE_TTL_SECONDS
    }
    pending[state] = {
        "created_at": now,
        "nonce": nonce,
        "code_verifier": verifier,
        "mode": mode,
        "next": _safe_next(next_path, "/"),
        "user_id": (
            request.user.id if mode == "link" and request.user.is_authenticated
            else linked_user_id if mode == "legacy_link" else None
        ),
    }
    # Bound the session footprint and make old browser tabs expire first.
    for old_state in sorted(pending, key=lambda key: pending[key].get("created_at", 0))[:-4]:
        pending.pop(old_state, None)
    request.session[_PENDING_SESSION_KEY] = pending
    request.session.modified = True
    query = {
        "client_id": client_id,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": settings.AUTHENTIK_OIDC_SCOPES,
        "state": state,
        "nonce": nonce,
        "code_challenge": _pkce_challenge(verifier),
        "code_challenge_method": "S256",
    }
    return f"{metadata['authorization_endpoint']}?{urlencode(query)}"


def consume_state(request, state):
    if not state:
        raise OIDCError("state_missing")
    pending = _pending_states(request)
    item = pending.pop(state, None)
    request.session[_PENDING_SESSION_KEY] = pending
    request.session.modified = True
    if not isinstance(item, dict):
        raise OIDCError("state_invalid")
    if int(time.time()) - int(item.get("created_at", 0)) > settings.AUTHENTIK_OIDC_STATE_TTL_SECONDS:
        raise OIDCError("state_expired")
    return item


def _exchange_code(metadata, code, verifier):
    client_id, redirect_uri = _require_config()
    secret = _client_secret()
    try:
        response = _http_session().post(
            metadata["token_endpoint"],
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "code_verifier": verifier,
            },
            auth=(client_id, secret),
            timeout=_HTTP_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Authentik OIDC token exchange failed: %s", exc.__class__.__name__)
        raise OIDCError("token_exchange_failed") from exc
    if not isinstance(data, dict) or not data.get("id_token"):
        raise OIDCError("id_token_missing")
    return data


def _unverified_header(encoded):
    try:
        segment = encoded.split(".", 1)[0]
        segment += "=" * (-len(segment) % 4)
        header = json.loads(base64.urlsafe_b64decode(segment.encode("ascii")))
    except (ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise OIDCError("id_token_invalid") from exc
    if not isinstance(header, dict):
        raise OIDCError("id_token_invalid")
    return header


def _jwks(metadata, force=False):
    return _cached_json(
        _cache_key("jwks"),
        metadata["jwks_uri"],
        _JWKS_TTL,
        "jwks_unavailable",
        force=force,
    )


def _verify_id_token(encoded, metadata, nonce, force=False):
    header = _unverified_header(encoded)
    algorithm = header.get("alg")
    kid = header.get("kid")
    if algorithm not in settings.AUTHENTIK_OIDC_ALLOWED_ALGORITHMS or not kid:
        raise OIDCError("id_token_algorithm")
    try:
        key_set = JsonWebKey.import_key_set(_jwks(metadata, force=force))
        key = key_set.find_by_kid(kid)
        if getattr(key, "kty", None) != "RSA":
            raise OIDCError("id_token_key")
        key_algorithm = getattr(key, "alg", None)
        if key_algorithm and key_algorithm != algorithm:
            raise OIDCError("id_token_algorithm")
        claims = jwt.decode(
            encoded,
            key,
            claims_options={
                "iss": {"essential": True, "value": _issuer_document()},
                "sub": {"essential": True},
                "aud": {"essential": True, "value": settings.AUTHENTIK_OIDC_CLIENT_ID},
                "exp": {"essential": True},
                "iat": {"essential": True},
                "nonce": {"essential": True, "value": nonce},
            },
        )
        claims.validate(leeway=settings.AUTHENTIK_OIDC_CLOCK_SKEW_SECONDS)
    except OIDCError:
        raise
    except (BadSignatureError, DecodeError, JoseError, ValueError, TypeError) as exc:
        if not force:
            return _verify_id_token(encoded, metadata, nonce, force=True)
        logger.warning("Authentik OIDC ID token validation failed: %s", exc.__class__.__name__)
        raise OIDCError("id_token_invalid") from exc
    return dict(claims)


def _userinfo(metadata, access_token):
    endpoint = metadata.get("userinfo_endpoint")
    if not endpoint:
        return {}
    if not access_token:
        raise OIDCError("userinfo_unavailable")
    try:
        response = _http_session().get(
            endpoint,
            headers={"Authorization": f"Bearer {access_token}"},
            timeout=_HTTP_TIMEOUT,
        )
        response.raise_for_status()
        data = response.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning("Authentik OIDC userinfo request failed: %s", exc.__class__.__name__)
        raise OIDCError("userinfo_unavailable") from exc
    if not isinstance(data, dict):
        raise OIDCError("userinfo_invalid")
    return data


def verified_claims(token_data, metadata, nonce):
    claims = _verify_id_token(token_data["id_token"], metadata, nonce)
    userinfo = {}
    if not claims.get("email") or "email_verified" not in claims:
        userinfo = _userinfo(metadata, token_data.get("access_token", ""))
        if userinfo.get("sub") != claims.get("sub"):
            raise OIDCError("subject_mismatch")
        claims.update({key: value for key, value in userinfo.items() if key not in claims})
    subject_value = claims.get("sub")
    email_value = claims.get("email")
    account_id = claims.get("icthub_account_id")
    subject = subject_value.strip() if isinstance(subject_value, str) else ""
    email = email_value.strip().casefold() if isinstance(email_value, str) else ""
    if not subject or len(subject) > 255 or claims.get("email_verified") is not True:
        raise OIDCError("email_not_verified")
    if not isinstance(account_id, str) or not _STUDIO_ACCOUNT_ID_RE.fullmatch(account_id):
        raise OIDCError("account_claim_invalid")
    try:
        validate_email(email)
    except ValidationError as exc:
        raise OIDCError("email_invalid") from exc
    if len(email) > 254:
        raise OIDCError("email_invalid")
    return claims


def _safe_claim(value, max_length):
    return str(value or "").strip()[:max_length]


def _username_candidate(claims):
    raw = unicodedata.normalize("NFKC", _safe_claim(claims.get("preferred_username"), 128)).casefold()
    candidate = re.sub(r"[^a-z0-9._-]+", "-", raw).strip(".-_")
    candidate = candidate[:32]
    if not _USERNAME_RE.fullmatch(candidate):
        suffix = hashlib.sha256(str(claims["sub"]).encode("utf-8")).hexdigest()[:10]
        candidate = f"user-{suffix}"
    return candidate


def _unique_username(candidate, subject, force_suffix=False):
    if not force_suffix and not User.objects.filter(username=candidate).exists():
        return candidate
    suffix = hashlib.sha256(subject.encode("utf-8")).hexdigest()[:10]
    base = candidate[: 32 - len(suffix) - 1].rstrip(".-_") or "user"
    return f"{base}-{suffix}"


def _claims_for_storage(claims, email):
    groups = claims.get("groups", [])
    if not isinstance(groups, list):
        groups = []
    return {
        "preferred_username": _safe_claim(claims.get("preferred_username"), 128),
        "name": _safe_claim(claims.get("name"), 128),
        "email": email,
        "email_verified": True,
        "icthub_account_id": claims["icthub_account_id"],
        "groups": [str(group)[:128] for group in groups if isinstance(group, str)][:64],
    }


def _apply_admin_claims(user, claims):
    """Follow Studio groups unless an OJ administrator set the role locally."""

    if getattr(user, "admin_role_manual_override", False):
        return
    groups = claims.get("groups")
    # Missing or malformed group claims do not establish a revocation. An
    # explicit group list without the admin group does revoke access.
    if not isinstance(groups, list):
        return
    is_studio_admin = _ADMIN_GROUP in groups
    next_admin_type = AdminType.SUPER_ADMIN if is_studio_admin else AdminType.REGULAR_USER
    next_problem_permission = ProblemPermission.ALL if is_studio_admin else ProblemPermission.NONE
    changed = []
    if user.admin_type != next_admin_type:
        user.admin_type = next_admin_type
        changed.append("admin_type")
    if user.problem_permission != next_problem_permission:
        user.problem_permission = next_problem_permission
        changed.append("problem_permission")
    if changed:
        user.save(update_fields=changed)


def _account_id_from_claims(claims):
    value = claims.get("icthub_account_id")
    if not isinstance(value, str) or not _STUDIO_ACCOUNT_ID_RE.fullmatch(value):
        raise OIDCError("account_claim_invalid")
    return value


def provision_or_get(claims, mode="login", linked_user_id=None, legacy_link=False):
    issuer = _issuer()
    subject = str(claims["sub"])
    email = str(claims["email"]).strip().casefold()
    account_id = _account_id_from_claims(claims)
    stored_claims = _claims_for_storage(claims, email)
    for attempt in range(2):
        try:
            with transaction.atomic():
                identity = (
                    ExternalIdentity.objects.select_for_update()
                    .select_related("user")
                    .filter(provider=_PROVIDER, issuer=issuer, subject=subject)
                    .first()
                )
                if identity:
                    user = identity.user
                    if mode == "link" and linked_user_id and user.id != linked_user_id:
                        raise OIDCError("identity_already_linked")
                    if legacy_link:
                        raise OIDCError("link_session_changed")
                    if user.is_disabled:
                        raise OIDCError("account_disabled")
                    UserProfile.objects.get_or_create(user=user)
                    if user.studio_account_id and user.studio_account_id != account_id:
                        raise OIDCError("account_claim_mismatch")
                    if not user.studio_account_id:
                        user.studio_account_id = account_id
                        user.save(update_fields=["studio_account_id"])
                    identity.email = email
                    identity.email_verified = True
                    identity.claims = stored_claims
                    identity.save(update_fields=["email", "email_verified", "claims", "last_login_at"])
                    if user.email != email:
                        user.email = email
                        user.save(update_fields=["email"])
                    _apply_admin_claims(user, claims)
                    return user
                if mode == "link":
                    if not linked_user_id:
                        raise OIDCError("link_login_required")
                    user = User.objects.select_for_update().get(id=linked_user_id)
                    if user.is_disabled:
                        raise OIDCError("account_disabled")
                    if legacy_link and (user.email or ExternalIdentity.objects.filter(user=user, provider=_PROVIDER).exists()):
                        raise OIDCError("link_session_changed")
                    if User.objects.filter(email__iexact=email).exclude(pk=user.pk).exists():
                        raise OIDCError("account_claim_conflict")
                    UserProfile.objects.get_or_create(user=user)
                    if user.studio_account_id and user.studio_account_id != account_id:
                        raise OIDCError("account_claim_mismatch")
                    if not user.studio_account_id:
                        user.studio_account_id = account_id
                        user.save(update_fields=["studio_account_id"])
                    if user.email != email:
                        user.email = email
                        user.save(update_fields=["email"])
                else:
                    user = User.objects.select_for_update().filter(studio_account_id=account_id).first()
                    if user is not None:
                        # The current (issuer, subject) was not found above. A
                        # pre-existing local row therefore requires explicit
                        # link, while an already-linked account ID must reject a
                        # second subject instead of silently merging identities.
                        if ExternalIdentity.objects.filter(user=user, provider=_PROVIDER).exists():
                            raise OIDCError("account_claim_conflict")
                        raise OIDCError("account_link_required")
                    else:
                        if User.objects.filter(email__iexact=email).exists():
                            raise OIDCError("account_link_required")
                        username = _unique_username(
                            _username_candidate(claims),
                            subject,
                            force_suffix=attempt > 0,
                        )
                        user = User(username=username, email=email, studio_account_id=account_id)
                        user.set_unusable_password()
                        user.save()
                        UserProfile.objects.create(user=user, oj_onboarding_completed=False)
                _apply_admin_claims(user, claims)
                ExternalIdentity.objects.create(
                    user=user,
                    provider=_PROVIDER,
                    issuer=issuer,
                    subject=subject,
                    email=email,
                    email_verified=True,
                    claims=stored_claims,
                )
                return user
        except OIDCError:
            raise
        except User.DoesNotExist as exc:
            raise OIDCError("account_missing") from exc
        except IntegrityError as exc:
            # A concurrent callback may have won the identity race. Re-read it
            # without guessing by email or username. If the account ID already
            # belongs to another subject, reject the collision; if only the
            # display username collided, retry once with the subject suffix.
            identity = ExternalIdentity.objects.select_related("user").filter(
                provider=_PROVIDER, issuer=issuer, subject=subject
            ).first()
            if (
                identity
                and not identity.user.is_disabled
                and identity.user.studio_account_id == account_id
            ):
                if mode == "link" and identity.user_id != linked_user_id:
                    raise OIDCError("identity_already_linked") from exc
                if legacy_link:
                    raise OIDCError("link_session_changed") from exc
                return identity.user
            account_owner = User.objects.filter(studio_account_id=account_id).first()
            if account_owner is not None:
                logger.warning("Authentik OIDC account claim collision: %s", exc.__class__.__name__)
                raise OIDCError("account_claim_conflict") from exc
            if attempt == 0 and mode != "link":
                continue
            logger.warning("Authentik OIDC provisioning race failed: %s", exc.__class__.__name__)
            raise OIDCError("provisioning_failed") from exc


def complete(request, state, code):
    pending = consume_state(request, state)
    if not code:
        raise OIDCError("authorization_code_missing")
    if pending.get("mode") == "link":
        if not request.user.is_authenticated or request.user.id != pending.get("user_id"):
            raise OIDCError("link_session_changed")
    if pending.get("mode") == "legacy_link":
        legacy_user = User.objects.filter(pk=pending.get("user_id"), is_disabled=False).first()
        if (
            request.user.is_authenticated or legacy_user is None or legacy_user.email
            or ExternalIdentity.objects.filter(user=legacy_user, provider=_PROVIDER).exists()
        ):
            raise OIDCError("link_session_changed")
    metadata = discovery()
    token_data = _exchange_code(metadata, code, pending["code_verifier"])
    claims = verified_claims(token_data, metadata, pending["nonce"])
    user = provision_or_get(
        claims,
        mode="link" if pending.get("mode") == "legacy_link" else pending.get("mode", "login"),
        linked_user_id=pending.get("user_id"),
        legacy_link=pending.get("mode") == "legacy_link",
    )
    auth.login(request, user, backend="django.contrib.auth.backends.ModelBackend")
    return pending.get("next", "/")


def providers_data(request):
    oidc_enabled = enabled()
    linked = False
    if oidc_enabled and request.user.is_authenticated:
        linked = ExternalIdentity.objects.filter(user=request.user, provider=_PROVIDER).exists()
    return {
        "authentik": {
            "enabled": oidc_enabled,
            "login_url": "/api/auth/oidc/login/?next=/",
            "register_url": settings.AUTHENTIK_OIDC_REGISTER_URL if oidc_enabled else "",
            "link_url": "/api/auth/oidc/link/?next=/setting/security",
            "linked": linked,
        },
        "local": {
            "login_enabled": bool(settings.AUTHENTIK_LOCAL_LOGIN_ENABLED),
            "register_enabled": bool(settings.AUTHENTIK_LOCAL_REGISTER_ENABLED),
        },
    }


class ProvidersAPI(APIView):
    def get(self, request):
        return self.success(providers_data(request))


class LegacyEmailLinkSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=32)
    password = serializers.CharField()
    captcha = serializers.CharField()
    tfa_code = serializers.CharField(required=False, allow_blank=True)


class LegacyEmailLinkAPI(APIView):
    """Let an unbound local account prove its password before OIDC linking.

    This grants no OJ session. The normal OIDC callback must still verify a
    mailbox-backed identity before the two accounts can be linked.
    """

    @validate_serializer(LegacyEmailLinkSerializer)
    def post(self, request):
        if not enabled() or request.user.is_authenticated:
            return self.error("Legacy account binding is unavailable")
        data = request.data
        if not Captcha(request).check(data["captcha"]):
            return self.error("Invalid captcha")
        username = data["username"].strip()
        remote_address = request.ip
        bucket = hashlib.sha256(f"{username.casefold()}\0{remote_address}".encode("utf-8")).hexdigest()
        throttle_key = f"xju-oj:legacy-email-link:{bucket}"
        cache.add(throttle_key, 0, _LEGACY_LINK_ATTEMPT_WINDOW)
        try:
            attempts = cache.incr(throttle_key)
        except ValueError:
            # The key may expire between add and incr; retry initialization.
            cache.add(throttle_key, 0, _LEGACY_LINK_ATTEMPT_WINDOW)
            attempts = cache.incr(throttle_key)
        if attempts > _LEGACY_LINK_ATTEMPT_LIMIT:
            return self.error("Too many attempts; try again later")
        user = auth.authenticate(username=username, password=data["password"])
        eligible = (
            user is not None and not user.is_disabled and not user.email
            and not ExternalIdentity.objects.filter(user=user, provider=_PROVIDER).exists()
        )
        if eligible and user.two_factor_auth:
            eligible = bool(data.get("tfa_code") and OtpAuth(user.tfa_token).valid_totp(data["tfa_code"]))
        if not eligible:
            return self.error("Invalid account credentials")
        try:
            request.session.cycle_key()
            authorization_url = start(request, "legacy_link", "/", linked_user_id=user.id)
        except OIDCError as exc:
            return self.error(exc.code)
        cache.delete(throttle_key)
        return self.success({"authorization_url": authorization_url})


@require_GET
@never_cache
def oidc_login(request):
    try:
        return HttpResponseRedirect(start(request, "login", request.GET.get("next", "/")))
    except OIDCError as exc:
        return redirect(_error_redirect(request.GET.get("next", "/"), exc.code))


@require_GET
@never_cache
def oidc_link(request):
    if not request.user.is_authenticated:
        return redirect(_error_redirect("/", "link_login_required"))
    try:
        return HttpResponseRedirect(start(request, "link", request.GET.get("next", "/setting/security")))
    except OIDCError as exc:
        return redirect(_error_redirect(request.GET.get("next", "/setting/security"), exc.code))


@require_GET
@never_cache
def oidc_callback(request):
    state = request.GET.get("state", "")
    next_path = "/"
    try:
        pending = _pending_states(request).get(state, {})
        next_path = _safe_next(pending.get("next", "/"))
        if request.GET.get("error"):
            # Consume state even when Authentik returned an authorization error.
            consume_state(request, state)
            raise OIDCError("authorization_denied")
        next_path = complete(request, state, request.GET.get("code", ""))
        return redirect(next_path)
    except OIDCError as exc:
        return redirect(_error_redirect(next_path, exc.code))
    except (KeyError, TypeError, ValueError) as exc:
        logger.warning("Authentik OIDC callback protocol error: %s", exc.__class__.__name__)
        return redirect(_error_redirect(next_path, "oidc_protocol_error"))


@require_GET
@never_cache
def oidc_logout(request):
    from django.contrib import auth

    next_path = _safe_next(request.GET.get("next", "/"))
    auth.logout(request)
    if not enabled():
        return redirect(next_path)
    try:
        _require_config()
        metadata = discovery()
        endpoint = metadata.get("end_session_endpoint")
        if endpoint:
            query = {
                "client_id": settings.AUTHENTIK_OIDC_CLIENT_ID,
                "post_logout_redirect_uri": (
                    f"{settings.AUTHENTIK_OIDC_POST_LOGOUT_REDIRECT_URI.rstrip('/')}"
                    f"{next_path}"
                ),
            }
            # The post-logout URI is validated by Authentik; no token is put in the URL.
            return redirect(f"{endpoint}?{urlencode(query)}")
    except OIDCError:
        pass
    return redirect(next_path)
