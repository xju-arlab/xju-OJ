from django.conf import settings
from django.db import connection, transaction
from django.utils.timezone import now
from django.utils.deprecation import MiddlewareMixin

from utils.api import JSONResponse
from account.models import User


class APITokenAuthMiddleware(MiddlewareMixin):
    def process_request(self, request):
        appkey = request.META.get("HTTP_APPKEY")
        if appkey:
            try:
                request.user = User.objects.get(open_api_appkey=appkey, open_api=True, is_disabled=False)
                request.csrf_processing_done = True
                request.auth_method = "api_key"
            except User.DoesNotExist:
                pass


class SessionRecordMiddleware(MiddlewareMixin):
    def process_request(self, request):
        request.ip = request.META.get(settings.IP_HEADER, request.META.get("REMOTE_ADDR"))
        if request.user.is_authenticated and getattr(request, "auth_method", None) != "api_key":
            session = request.session
            session["user_agent"] = request.META.get("HTTP_USER_AGENT", "")
            session["ip"] = request.ip
            session["last_activity"] = now()
            if session.session_key is None:
                session.save()
            if session.session_key not in request.user.session_keys:
                # Authentication loaded this user before concurrent account
                # changes. Only update the locked session list, never the
                # stale password, disabled flag, or administrator role.
                with transaction.atomic():
                    user = User.objects.select_for_update().get(pk=request.user.pk)
                    user.session_keys = [key for key in user.session_keys if key]
                    if session.session_key not in user.session_keys:
                        user.session_keys.append(session.session_key)
                        user.save(update_fields=["session_keys"])
                    request.user.session_keys = user.session_keys


class AdminRoleRequiredMiddleware(MiddlewareMixin):
    def process_request(self, request):
        path = request.path_info
        if path.startswith("/admin/") or path.startswith("/api/admin/"):
            if not (request.user.is_authenticated and request.user.is_admin_role()):
                return JSONResponse.response({"error": "login-required", "data": "Please login in first"})


class LogSqlMiddleware(MiddlewareMixin):
    def process_response(self, request, response):
        print("\033[94m", "#" * 30, "\033[0m")
        time_threshold = 0.03
        for query in connection.queries:
            if float(query["time"]) > time_threshold:
                print("\033[93m", query, "\n", "-" * 30, "\033[0m")
            else:
                print(query, "\n", "-" * 30)
        return response
