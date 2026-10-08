"""Private package storage and atomic OJ-side import publication."""
import hashlib
import os
import re
import stat
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils.timezone import now

from account.models import User, ProblemPermission
from utils.api import APIError
from .contracts import judge_input, require
from .models import AIProblem, AIProblemImport, AIServiceState
from .package_format import FORMAT, MAX_EXPANDED, MAX_UPLOAD, PackageError, export_problem, make_zip, parse_package

IMPORT_ACTIVE = ("PENDING", "RUNNING")


def can_manage(user):
    return user.is_authenticated and not user.is_disabled and user.is_admin_role() and user.problem_permission != ProblemPermission.NONE


def managed_problems(user):
    problems = AIProblem.objects.all()
    return problems if user.is_super_admin() or user.can_mgmt_all_problem() else problems.filter(created_by=user)


def private_path(batch_id):
    # The caller passes a model UUID, never a client filename or path.
    root = Path(settings.DATA_DIR) / "ai_problem_packages"
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    return root / (str(batch_id) + ".zip")


def read_archive(batch):
    path = private_path(batch.pk)
    try:
        require(stat.S_ISREG(path.lstat().st_mode) and not path.is_symlink(), "题包文件不可用")
        with path.open("rb") as stream:
            raw = stream.read(MAX_UPLOAD + 1)
    except OSError:
        raise APIError("题包文件不可用，请检查私有存储备份") from None
    require(len(raw) <= MAX_UPLOAD and hashlib.sha256(raw).hexdigest() == batch.source_sha256, "题包校验失败，请检查私有存储")
    return raw


def parse(raw):
    try:
        return parse_package(raw)
    except PackageError as exc:
        raise APIError(str(exc)) from None


def package_manifest(problems):
    return [{key: value for key, value in item.items() if key != "assets"} for item in problems]


def preview_package(user, filename, raw):
    require(can_manage(user), "没有题目管理权限")
    manifest = package_manifest(parse(raw))
    digest = hashlib.sha256(raw).hexdigest()
    created_path = None
    try:
        with transaction.atomic():
            User.objects.select_for_update().get(pk=user.pk)
            existing = AIProblemImport.objects.filter(created_by=user, source_sha256=digest).first()
            if existing:
                read_archive(existing)
                return existing
            require(AIProblemImport.objects.filter(created_by=user, status__in=("PREVIEW", "PENDING", "RUNNING")).count() < 10,
                    "待处理题包已达 10 个，请先完成或删除已有记录")
            batch = AIProblemImport(created_by=user, source_sha256=digest, filename=Path(filename).name[:128], manifest=manifest)
            path = private_path(batch.pk)
            descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            created_path = path
            with os.fdopen(descriptor, "wb") as stream:
                stream.write(raw)
                stream.flush()
                os.fsync(stream.fileno())
            batch.save()
        return batch
    except Exception:
        if created_path:
            created_path.unlink(missing_ok=True)
        raise


def batch_summary(batch):
    return {"id": str(batch.pk), "filename": batch.filename, "status": batch.status, "publish": batch.publish,
            "message": batch.message, "createdAt": batch.created_at.isoformat(), "result": batch.result,
            "problems": [{"title": item["metadata"]["title"], "type": item["metadata"]["type"],
                          "sourceId": item["metadata"].get("source_id", ""), "cells": len(item["cells"]),
                          "files": list(item["public_files"]), "metric": item["metadata"]["metric"]} for item in batch.manifest]}


def service_lock():
    AIServiceState.objects.get_or_create(pk=1)
    return AIServiceState.objects.select_for_update().get(pk=1)


@transaction.atomic
def confirm_batch(batch_id, user, publish):
    service = service_lock()
    batch = AIProblemImport.objects.select_for_update().filter(pk=batch_id).first()
    require(batch is not None and (batch.created_by_id == user.id or user.is_super_admin()), "导入记录不存在")
    if batch.status in (*IMPORT_ACTIVE, "SUCCEEDED"):
        return batch
    require(batch.status in ("PREVIEW", "FAILED"), "导入状态无效")
    require(not service.paused, "AI 服务维护中，请稍后导入")
    require(can_manage(batch.created_by), "题包上传者已失去题目管理权限")
    read_archive(batch)
    batch.publish = publish
    batch.status = "PENDING"
    batch.message = ""
    batch.attempts = 0
    batch.lease = None
    batch.lease_until = None
    batch.save()
    return batch


def next_codes(count):
    used = set(AIProblem.objects.values_list("code", flat=True))
    number = max((int(code[2:]) for code in used if re.fullmatch(r"AI[0-9]{1,29}", code)), default=0)
    result = []
    while len(result) < count:
        number += 1
        code = f"AI{number:03d}"
        require(len(code) <= 32, "自动题号空间已满")
        if code not in used:
            result.append(code)
    return result


def create_problems(batch, results):
    require(isinstance(results, list) and len(results) == len(batch.manifest), "评测注册结果不完整")
    codes = next_codes(len(results))
    problems = []
    for index, (item, result, code) in enumerate(zip(batch.manifest, results, codes)):
        require(isinstance(result, dict) and result.get("index") == index and
                result.get("asset_sha256") == item["asset_sha256"], "评测注册内容不匹配")
        judge = judge_input(result.get("judge"))
        require(type(judge.get("task_id")) is int and judge["task_id"] > 0, "缺少评测任务")
        require({key: value for key, value in judge.items() if key not in ("phase_id", "task_id")} == item["metadata"]["evaluation"],
                "评测注册配置不匹配")
        metadata = item["metadata"]
        problems.append(AIProblem(code=code, title=metadata["title"], category=metadata["type"], statement=metadata["statement"],
                                  cells=item["cells"], public_files=item["public_files"], metric=metadata["metric"],
                                  points=metadata["points"], judge=judge, visible=batch.publish,
                                  created_by=batch.created_by, package_import=batch, package_index=index))
    AIProblem.objects.bulk_create(problems)
    return [{"id": problem.code, "title": problem.title, "version": problem.version} for problem in problems]


@transaction.atomic
def claim_batch(worker):
    import uuid
    batch = (AIProblemImport.objects.select_for_update(skip_locked=True).filter(status__in=IMPORT_ACTIVE)
             .filter(Q(status="PENDING") | Q(lease_until__lt=now())).order_by("created_at", "id").first())
    if not batch:
        return None
    if batch.attempts >= 3 or not can_manage(batch.created_by):
        batch.status = "FAILED"
        batch.message = "导入服务中断或上传者权限已变更，请核实后重试。"
        batch.lease_until = None
        batch.save()
        return None
    batch.worker = worker
    batch.lease = uuid.uuid4()
    batch.lease_until = now() + timedelta(seconds=90)
    batch.status = "RUNNING"
    batch.attempts += 1
    batch.save()
    return {"id": str(batch.pk), "lease": str(batch.lease), "sha256": batch.source_sha256}


def check_lease(batch, worker, lease):
    require(batch is not None and batch.worker == worker and batch.lease == lease, "Import lease has been replaced")


@transaction.atomic
def update_batch(batch_id, worker, lease, action, data):
    service_lock()  # Serialize publication, editing and adoption against the admission gate.
    batch = AIProblemImport.objects.select_for_update().filter(pk=batch_id).first()
    check_lease(batch, worker, lease)
    if batch.status in ("SUCCEEDED", "FAILED"):
        require(action == "finish", "Import has finished")
        return {"finished": True}
    require(batch.status == "RUNNING" and batch.lease_until and batch.lease_until > now(), "Import lease has expired")
    if action == "heartbeat":
        batch.lease_until = now() + timedelta(seconds=90)
    else:
        require(data.get("status") in ("SUCCEEDED", "FAILED"), "Invalid import result")
        if data["status"] == "SUCCEEDED" and can_manage(batch.created_by):
            batch.result = create_problems(batch, data.get("results"))
            batch.status = "SUCCEEDED"
            batch.message = ""
        else:
            batch.status = "FAILED"
            batch.message = "评测包注册失败或上传者权限已变更。可重试；本批尚未创建题目。"
        batch.lease_until = None
    batch.save()
    return {"finished": batch.status not in IMPORT_ACTIVE}


def export_packages(problems):
    archives, expanded, cache_key, cached = {}, 0, None, None
    for problem in problems:
        require(problem.package_import_id is not None, "题目尚未归档评测包，无法完整导出：" + problem.code)
        key = problem.package_import_id
        if key != cache_key:
            cached = None  # Bound decoded archive memory even across many imports.
            cached = parse(read_archive(problem.package_import))
            cache_key = key
        item = cached[problem.package_index]
        expanded += sum(len(value) for files in item["assets"].values() for value in files.values())
        expanded += len(str(problem.statement).encode()) + sum(len(c.encode()) for c in problem.cells)
        expanded += sum(len(c.encode()) for c in problem.public_files.values())
        require(expanded <= MAX_EXPANDED, "批量题包超过 64 MiB，请减少选中的题目")
        expected = problem.package_import.manifest[problem.package_index]["asset_sha256"]
        require(item["asset_sha256"] == expected, "归档的评测文件不匹配")
        metadata = {"format": FORMAT, "version": 1, "source_id": problem.code, "title": problem.title,
                    "type": problem.category, "metric": problem.metric, "points": problem.points,
                    "statement": problem.statement, "evaluation": {k: v for k, v in problem.judge.items() if k not in ("phase_id", "task_id")}}
        try:
            archives[problem.code + ".zip"] = export_problem(metadata, problem.cells, problem.public_files, item["assets"])
        except PackageError as exc:
            raise APIError(str(exc)) from None
        require(sum(map(len, archives.values())) <= MAX_UPLOAD, "批量 ZIP 超过 16 MiB，请减少选中的题目")
    try:
        result = next(iter(archives.values())) if len(archives) == 1 else make_zip(archives)
        parse_package(result)  # Every exported batch must be importable under the same limits.
        return result
    except PackageError as exc:
        raise APIError(str(exc)) from None


@transaction.atomic
def adopt_existing(batch_id, user, bindings):
    """Attach archives exported from the current judge; do not change problem or grade versions."""
    service_lock()
    require(user.is_super_admin(), "既有题包归档仅限超级管理员")
    batch = AIProblemImport.objects.select_for_update().get(pk=batch_id, created_by=user)
    require(batch.status in ("PREVIEW", "SUCCEEDED"), "当前导入状态不允许归档")
    read_archive(batch)
    require(isinstance(bindings, list) and len(bindings) == len(batch.manifest), "归档映射不完整")
    problems = []
    for index, (item, binding) in enumerate(zip(batch.manifest, bindings)):
        code = item["metadata"]["source_id"]
        require(code and isinstance(binding, dict) and binding.get("id") == code and
                binding.get("asset_sha256") == item["asset_sha256"], "归档映射与题包不匹配")
        problem = AIProblem.objects.select_for_update().filter(code=code).first()
        require(problem is not None and problem.package_import_id in (None, batch.pk), "题目不存在或已绑定其他题包")
        expected = item["metadata"]
        require(problem.judge == binding.get("judge") and
                {k: v for k, v in problem.judge.items() if k not in ("phase_id", "task_id")} == expected["evaluation"] and
                problem.title == expected["title"] and problem.category == expected["type"] and
                problem.metric == expected["metric"] and problem.points == expected["points"] and
                problem.statement == expected["statement"] and problem.cells == item["cells"] and
                problem.public_files == item["public_files"], "归档与现有题目不一致：" + code)
        problem.package_import = batch
        problem.package_index = index
        problem.save(update_fields=["package_import", "package_index"])
        problems.append({"id": code, "title": problem.title, "version": problem.version})
    require(len({p["id"] for p in problems}) == len(problems), "归档题号重复")
    batch.status = "SUCCEEDED"
    batch.result = problems
    batch.save()
    return batch
