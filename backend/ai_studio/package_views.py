import io
import re
import uuid

from django.db import transaction
from django.http import FileResponse
from django.utils.timezone import now

from account.decorators import problem_permission_required
from utils.api import APIError, APIView, CSRFExemptAPIView
from .contracts import require
from .models import AIProblemImport, AIWorker
from .package_format import MAX_PROBLEMS, MAX_UPLOAD
from .packages import (batch_summary, check_lease, claim_batch, confirm_batch, export_packages, managed_problems,
                       preview_package, private_path, read_archive, update_batch)
from .worker_auth import authenticate_worker


def identifier(value):
    try:
        return uuid.UUID(str(value))
    except (ValueError, TypeError, AttributeError):
        raise APIError("Invalid import identifier") from None


def zip_response(content, filename):
    response = FileResponse(io.BytesIO(content), as_attachment=True, filename=filename, content_type="application/zip")
    response["Cache-Control"] = "private, no-store"
    response["X-Content-Type-Options"] = "nosniff"
    return response


class PackageImportAPI(APIView):
    request_parsers = ()  # Multipart uses Django's upload handlers; retain browser CSRF protection.

    @problem_permission_required
    def get(self, request):
        imports = AIProblemImport.objects.all()
        if not request.user.is_super_admin():
            imports = imports.filter(created_by=request.user)
        if request.GET.get("id"):
            batch = imports.filter(pk=identifier(request.GET["id"])).first()
            require(batch is not None, "导入记录不存在")
            return self.success(batch_summary(batch))
        return self.success([batch_summary(batch) for batch in imports[:20]])

    @problem_permission_required
    def post(self, request):
        upload = request.FILES.get("file")
        require(upload is not None and upload.name.lower().endswith(".zip"), "请选择 ZIP 题包")
        require(upload.size <= MAX_UPLOAD, "ZIP 文件超过 16 MiB")
        return self.success(batch_summary(preview_package(request.user, upload.name, upload.read(MAX_UPLOAD + 1))))

    @problem_permission_required
    @transaction.atomic
    def delete(self, request):
        batch = AIProblemImport.objects.select_for_update().filter(pk=identifier(request.GET.get("id"))).first()
        require(batch is not None and (request.user.is_super_admin() or batch.created_by_id == request.user.id), "导入记录不存在")
        require(batch.status == "PREVIEW" and not batch.problems.exists(), "只能删除尚未提交的预览题包")
        path = private_path(batch.pk)
        batch.delete()
        transaction.on_commit(lambda: path.unlink(missing_ok=True))
        return self.success()


class PackageConfirmAPI(APIView):
    @problem_permission_required
    def post(self, request):
        require(isinstance(request.data, dict), "请求必须为 JSON 对象")
        require(type(request.data.get("publish")) is bool, "请选择导入后是否公开")
        batch = confirm_batch(identifier(request.data.get("id")), request.user, request.data["publish"])
        return self.success(batch_summary(batch))


class PackageExportAPI(APIView):
    @problem_permission_required
    def get(self, request):
        codes = request.GET.getlist("problem_id")
        require(1 <= len(codes) <= MAX_PROBLEMS and len(set(codes)) == len(codes), "请选择 1–20 道题目")
        problems = list(managed_problems(request.user).filter(code__in=codes).select_related("package_import"))
        require(len(problems) == len(codes), "题目不存在或无管理权限")
        return zip_response(export_packages(problems), (problems[0].code if len(problems) == 1 else "ai-problems") + ".zip")


class PackageWorkerAPI(CSRFExemptAPIView):
    def get(self, request):
        authenticate_worker(request)
        batch = AIProblemImport.objects.filter(pk=identifier(request.GET.get("id"))).first()
        check_lease(batch, request.GET.get("worker"), identifier(request.GET.get("lease")))
        require(batch.status == "RUNNING" and batch.lease_until and batch.lease_until > now(), "Import lease has expired")
        return zip_response(read_archive(batch), "package.zip")

    def post(self, request):
        authenticate_worker(request)
        data = request.data
        require(isinstance(data, dict), "Expected a JSON object")
        worker = data.get("worker", "")
        require(isinstance(worker, str) and re.fullmatch(r"[A-Za-z0-9_.-]{1,64}", worker), "Invalid worker name")
        AIWorker.objects.update_or_create(name=worker, defaults={"kinds": ["package"], "last_seen": now()})
        require(data.get("action") in ("claim", "heartbeat", "finish"), "Invalid package action")
        if data["action"] == "claim":
            return self.success(claim_batch(worker))
        result = update_batch(identifier(data.get("id")), worker, identifier(data.get("lease")), data["action"], data)
        return self.success(result)
