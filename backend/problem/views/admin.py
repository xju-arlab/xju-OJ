import hashlib
import io
import json
import os
import shutil
import tempfile
import zipfile
from pathlib import PurePosixPath
from wsgiref.util import FileWrapper

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.http import StreamingHttpResponse, FileResponse
from django.utils import timezone

from account.decorators import problem_permission_required, ensure_created_by
from contest.models import Contest, ContestStatus
from fps.parser import FPSHelper, FPSParser
from judge.dispatcher import SPJCompiler
from options.options import SysOptions
from submission.models import Submission, JudgeStatus
from utils.api import APIView, validate_serializer, APIError
from utils.constants import Difficulty
from utils.shortcuts import rand_str, natural_sort_key
from utils.tasks import delete_files
from ..models import (Problem, ProblemRuleType, ProblemTag, ProblemJudgeMode,
                      ProblemIOMode)
from ..remote import RemoteProblemError, fetch_remote_problem
from ..remote.common import markdown_to_html
from ..publication import publish_due_contest_problems
from ..tasks import schedule_contest_problem_publication
from ..serializers import (CreateContestProblemSerializer, CompileSPJSerializer,
                           CreateProblemSerializer, EditProblemSerializer, EditContestProblemSerializer,
                           ProblemAdminSerializer, TestCaseUploadForm, ContestProblemMakePublicSerializer,
                           AddContestProblemSerializer, ExportProblemSerializer,
                           ExportProblemRequestSerialzier, UploadProblemForm, ImportProblemSerializer,
                           FPSProblemSerializer, RemoteProblemImportSerializer)
from ..utils import TEMPLATE_BASE, build_problem_template


def _alphabetic_display_id(index):
    value = index + 1
    label = ""
    while value > 0:
        value -= 1
        label = chr(ord("A") + value % 26) + label
        value //= 26
    return label


def _next_contest_display_id(contest):
    used = set(Problem.objects.filter(contest=contest).values_list("_id", flat=True))
    index = 0
    while True:
        candidate = _alphabetic_display_id(index)
        if candidate not in used:
            return candidate
        index += 1


def _next_public_display_id():
    local_problem_count = Problem.objects.filter(
        contest_id__isnull=True,
        judge_mode=ProblemJudgeMode.LOCAL,
    ).count()
    candidate = 1001 + local_problem_count
    while Problem.objects.filter(_id=str(candidate), contest_id__isnull=True).exists():
        candidate += 1
    return str(candidate)


def _remote_problem_display_id(problem):
    remote_id = str(problem.remote_problem_id or "").strip()
    if problem.remote_oj == "NOWCODER":
        return remote_id if remote_id.upper().startswith("NC") else f"NC{remote_id}"
    if problem.remote_oj == "LUOGU":
        return f"LG{remote_id}"
    if problem.remote_oj == "CODEFORCES":
        return f"CF{remote_id}"
    return _next_public_display_id()


class TestCaseZipProcessor(object):
    def process_zip(self, uploaded_zip_file, spj, dir=""):
        owns_zip_file = not isinstance(uploaded_zip_file, zipfile.ZipFile)
        try:
            zip_file = (
                zipfile.ZipFile(uploaded_zip_file, "r")
                if owns_zip_file else uploaded_zip_file
            )
        except zipfile.BadZipFile:
            raise APIError("Bad zip file")
        test_case_dir = None
        try:
            name_list = zip_file.namelist()
            test_case_list = self.filter_name_list(name_list, spj=spj, dir=dir)
            if not test_case_list:
                raise APIError("Empty file")

            test_case_id = rand_str()
            test_case_dir = os.path.join(settings.TEST_CASE_DIR, test_case_id)
            os.mkdir(test_case_dir)
            os.chmod(test_case_dir, 0o710)

            size_cache = {}
            md5_cache = {}

            for item in test_case_list:
                with open(os.path.join(test_case_dir, item), "wb") as f:
                    content = zip_file.read(f"{dir}{item}").replace(b"\r\n", b"\n")
                    size_cache[item] = len(content)
                    if item.endswith(".out"):
                        md5_cache[item] = hashlib.md5(content.rstrip()).hexdigest()
                    f.write(content)
            test_case_info = {"spj": spj, "test_cases": {}}

            info = []

            if spj:
                for index, item in enumerate(test_case_list):
                    data = {"input_name": item, "input_size": size_cache[item]}
                    info.append(data)
                    test_case_info["test_cases"][str(index + 1)] = data
            else:
                # ["1.in", "1.out", "2.in", "2.out"] => [("1.in", "1.out"), ("2.in", "2.out")]
                test_case_list = zip(*[test_case_list[i::2] for i in range(2)])
                for index, item in enumerate(test_case_list):
                    data = {"stripped_output_md5": md5_cache[item[1]],
                            "input_size": size_cache[item[0]],
                            "output_size": size_cache[item[1]],
                            "input_name": item[0],
                            "output_name": item[1]}
                    info.append(data)
                    test_case_info["test_cases"][str(index + 1)] = data

            with open(os.path.join(test_case_dir, "info"), "w", encoding="utf-8") as f:
                f.write(json.dumps(test_case_info, indent=4))

            for item in os.listdir(test_case_dir):
                os.chmod(os.path.join(test_case_dir, item), 0o640)

            return info, test_case_id
        except Exception:
            if test_case_dir:
                shutil.rmtree(test_case_dir, ignore_errors=True)
            raise
        finally:
            if owns_zip_file:
                zip_file.close()

    def filter_name_list(self, name_list, spj, dir=""):
        ret = []
        prefix = 1
        if spj:
            while True:
                in_name = f"{prefix}.in"
                if f"{dir}{in_name}" in name_list:
                    ret.append(in_name)
                    prefix += 1
                    continue
                else:
                    return sorted(ret, key=natural_sort_key)
        else:
            while True:
                in_name = f"{prefix}.in"
                out_name = f"{prefix}.out"
                if f"{dir}{in_name}" in name_list and f"{dir}{out_name}" in name_list:
                    ret.append(in_name)
                    ret.append(out_name)
                    prefix += 1
                    continue
                else:
                    return sorted(ret, key=natural_sort_key)


class TestCaseAPI(APIView, TestCaseZipProcessor):
    request_parsers = ()

    def get(self, request):
        problem_id = request.GET.get("problem_id")
        if not problem_id:
            return self.error("Parameter error, problem_id is required")
        try:
            problem = Problem.objects.get(id=problem_id)
        except Problem.DoesNotExist:
            return self.error("Problem does not exists")

        if problem.contest:
            ensure_created_by(problem.contest, request.user)
        else:
            ensure_created_by(problem, request.user)

        test_case_dir = os.path.join(settings.TEST_CASE_DIR, problem.test_case_id)
        if not os.path.isdir(test_case_dir):
            return self.error("Test case does not exists")
        name_list = self.filter_name_list(os.listdir(test_case_dir), problem.spj)
        name_list.append("info")
        file_name = os.path.join(test_case_dir, problem.test_case_id + ".zip")
        with zipfile.ZipFile(file_name, "w") as file:
            for test_case in name_list:
                file.write(f"{test_case_dir}/{test_case}", test_case)
        response = StreamingHttpResponse(FileWrapper(open(file_name, "rb")),
                                         content_type="application/octet-stream")

        response["Content-Disposition"] = f"attachment; filename=problem_{problem.id}_test_cases.zip"
        response["Content-Length"] = os.path.getsize(file_name)
        return response

    def post(self, request):
        form = TestCaseUploadForm(request.POST, request.FILES)
        if form.is_valid():
            spj = form.cleaned_data["spj"] == "true"
            file = form.cleaned_data["file"]
        else:
            return self.error("Upload failed")
        zip_file = f"/tmp/{rand_str()}.zip"
        with open(zip_file, "wb") as f:
            for chunk in file:
                f.write(chunk)
        info, test_case_id = self.process_zip(zip_file, spj=spj)
        os.remove(zip_file)
        return self.success({"id": test_case_id, "info": info, "spj": spj})


class CompileSPJAPI(APIView):
    @validate_serializer(CompileSPJSerializer)
    def post(self, request):
        data = request.data
        spj_version = rand_str(8)
        error = SPJCompiler(data["spj_code"], spj_version, data["spj_language"]).compile_spj()
        if error:
            return self.error(error)
        else:
            return self.success()


class ProblemBase(APIView):
    def common_checks(self, request):
        data = request.data
        if data["spj"]:
            if not data["spj_language"] or not data["spj_code"]:
                return "Invalid spj"
            if not data["spj_compile_ok"]:
                return "SPJ code must be compiled successfully"
            data["spj_version"] = hashlib.md5(
                (data["spj_language"] + ":" + data["spj_code"]).encode("utf-8")).hexdigest()
        else:
            data["spj_language"] = None
            data["spj_code"] = None
        if data["rule_type"] == ProblemRuleType.OI:
            total_score = 0
            for item in data["test_case_score"]:
                if item["score"] <= 0:
                    return "Invalid score"
                else:
                    total_score += item["score"]
            data["total_score"] = total_score
        data["languages"] = list(data["languages"])


class ProblemAPI(ProblemBase):
    @problem_permission_required
    @validate_serializer(CreateProblemSerializer)
    def post(self, request):
        data = request.data
        data["_id"] = _next_public_display_id()

        error_info = self.common_checks(request)
        if error_info:
            return self.error(error_info)

        # todo check filename and score info
        tags = data.pop("tags")
        data["created_by"] = request.user
        problem = Problem.objects.create(**data)

        for item in tags:
            try:
                tag = ProblemTag.objects.get(name=item)
            except ProblemTag.DoesNotExist:
                tag = ProblemTag.objects.create(name=item)
            problem.tags.add(tag)
        return self.success(ProblemAdminSerializer(problem).data)

    @problem_permission_required
    def get(self, request):
        problem_id = request.GET.get("id")
        rule_type = request.GET.get("rule_type")
        user = request.user
        if problem_id:
            try:
                problem = Problem.objects.get(id=problem_id)
                ensure_created_by(problem, request.user)
                return self.success(ProblemAdminSerializer(problem).data)
            except Problem.DoesNotExist:
                return self.error("Problem does not exist")

        publish_due_contest_problems()
        problems = Problem.objects.filter(contest_id__isnull=True).order_by("-create_time")
        if rule_type:
            if rule_type not in ProblemRuleType.choices():
                return self.error("Invalid rule_type")
            else:
                problems = problems.filter(rule_type=rule_type)

        keyword = request.GET.get("keyword", "").strip()
        if keyword:
            problems = problems.filter(Q(title__icontains=keyword) | Q(_id__icontains=keyword))
        if not user.can_mgmt_all_problem():
            problems = problems.filter(created_by=user)
        return self.success(self.paginate_data(request, problems, ProblemAdminSerializer))

    @problem_permission_required
    @validate_serializer(EditProblemSerializer)
    def put(self, request):
        data = request.data
        problem_id = data.pop("id")

        try:
            problem = Problem.objects.get(id=problem_id)
            ensure_created_by(problem, request.user)
        except Problem.DoesNotExist:
            return self.error("Problem does not exist")

        data["_id"] = problem._id

        error_info = self.common_checks(request)
        if error_info:
            return self.error(error_info)
        # todo check filename and score info
        tags = data.pop("tags")
        data["languages"] = list(data["languages"])

        for k, v in data.items():
            setattr(problem, k, v)
        problem.save()

        problem.tags.remove(*problem.tags.all())
        for tag in tags:
            try:
                tag = ProblemTag.objects.get(name=tag)
            except ProblemTag.DoesNotExist:
                tag = ProblemTag.objects.create(name=tag)
            problem.tags.add(tag)

        return self.success()

    @problem_permission_required
    def delete(self, request):
        id = request.GET.get("id")
        if not id:
            return self.error("Invalid parameter, id is required")
        try:
            problem = Problem.objects.get(id=id, contest_id__isnull=True)
        except Problem.DoesNotExist:
            return self.error("Problem does not exists")
        ensure_created_by(problem, request.user)
        # d = os.path.join(settings.TEST_CASE_DIR, problem.test_case_id)
        # if os.path.isdir(d):
        #     shutil.rmtree(d, ignore_errors=True)
        problem.delete()
        return self.success()


class RemoteProblemImportAPI(APIView):
    @problem_permission_required
    @validate_serializer(RemoteProblemImportSerializer)
    def post(self, request):
        data = request.data
        try:
            if data.get("page_html"):
                remote = fetch_remote_problem(
                    data["provider"], data["remote_id"], page_html=data["page_html"]
                )
            else:
                remote = fetch_remote_problem(data["provider"], data["remote_id"])
        except RemoteProblemError as exc:
            return self.error(str(exc))

        contest = None
        contest_id = data.get("contest_id")
        if contest_id:
            try:
                contest = Contest.objects.get(id=contest_id)
                ensure_created_by(contest, request.user)
            except Contest.DoesNotExist:
                return self.error("Contest does not exist")
            if contest.status == ContestStatus.CONTEST_ENDED:
                return self.error("Contest has ended")
            if contest.rule_type != ProblemRuleType.ACM:
                return self.error("Remote problems only support ACM contests")
            contest_display_id = _next_contest_display_id(contest)
            if Problem.objects.filter(contest=contest, _id=contest_display_id).exists():
                return self.error("Duplicate display id in this contest")
            if Problem.objects.filter(
                contest=contest,
                remote_oj=data["provider"],
                remote_problem_id=remote["remote_id"],
            ).exists():
                return self.error("Remote problem already exists in this contest")

        public_problem = Problem.objects.filter(
            contest_id__isnull=True,
            judge_mode=ProblemJudgeMode.REMOTE,
            remote_oj=data["provider"],
            remote_problem_id=remote["remote_id"],
        ).first()
        if contest is None and public_problem is not None:
            return self.error("Remote problem already exists")

        display_id = contest_display_id if contest is not None else remote["default_display_id"]
        future_public_id = remote["default_display_id"]
        if contest is None and Problem.objects.filter(_id=display_id, contest_id__isnull=True).exists():
            return self.error("Display ID already exists")
        if contest is not None and public_problem is None and Problem.objects.filter(
            _id=future_public_id, contest_id__isnull=True
        ).exists():
            return self.error("Future public display ID already exists")

        with transaction.atomic():
            if contest is not None and public_problem is not None:
                tags = list(public_problem.tags.all())
                public_problem.pk = None
                public_problem.contest = contest
                public_problem._id = display_id
                public_problem.is_public = True
                public_problem.visible = True
                public_problem.publish_after_contest = False
                public_problem.post_contest_display_id = None
                public_problem.submission_number = 0
                public_problem.accepted_number = 0
                public_problem.statistic_info = {}
                public_problem.save()
                public_problem.tags.set(tags)
                return self.success(ProblemAdminSerializer(public_problem).data)

            problem = Problem.objects.create(
                _id=display_id,
                contest=contest,
                title=remote["title"],
                description=remote["description"],
                input_description=remote["input_description"],
                output_description=remote["output_description"],
                samples=remote["samples"],
                test_case_id="",
                test_case_score=[],
                hint=remote.get("hint", ""),
                languages=remote["languages"],
                template={},
                last_update_time=timezone.now(),
                created_by=request.user,
                time_limit=remote["time_limit"],
                memory_limit=remote["memory_limit"],
                io_mode={"io_mode": ProblemIOMode.standard, "input": "input.txt", "output": "output.txt"},
                spj=False,
                spj_language=None,
                spj_code=None,
                spj_compile_ok=False,
                rule_type=ProblemRuleType.ACM,
                visible=True,
                difficulty=remote["difficulty"],
                source=remote["source"],
                share_submission=False,
                judge_mode=ProblemJudgeMode.REMOTE,
                remote_oj=data["provider"],
                remote_problem_id=remote["remote_id"],
                remote_problem_data=remote["metadata"],
                publish_after_contest=contest is not None,
                post_contest_display_id=future_public_id if contest is not None else None,
            )
            tag, _ = ProblemTag.objects.get_or_create(name=remote["tag"])
            problem.tags.add(tag)
            if contest is not None:
                transaction.on_commit(lambda: schedule_contest_problem_publication(
                    contest.id, contest.end_time
                ))
        return self.success(ProblemAdminSerializer(problem).data)


class ContestProblemAPI(ProblemBase):
    @validate_serializer(CreateContestProblemSerializer)
    def post(self, request):
        data = request.data
        try:
            contest = Contest.objects.get(id=data.pop("contest_id"))
            ensure_created_by(contest, request.user)
        except Contest.DoesNotExist:
            return self.error("Contest does not exist")

        if data["rule_type"] != contest.rule_type:
            return self.error("Invalid rule type")

        _id = _next_contest_display_id(contest)
        data["_id"] = _id

        if Problem.objects.filter(_id=_id, contest=contest).exists():
            return self.error("Duplicate Display id")

        error_info = self.common_checks(request)
        if error_info:
            return self.error(error_info)

        # todo check filename and score info
        data["contest"] = contest
        tags = data.pop("tags")
        data["created_by"] = request.user
        problem = Problem.objects.create(**data)

        for item in tags:
            try:
                tag = ProblemTag.objects.get(name=item)
            except ProblemTag.DoesNotExist:
                tag = ProblemTag.objects.create(name=item)
            problem.tags.add(tag)
        return self.success(ProblemAdminSerializer(problem).data)

    def get(self, request):
        problem_id = request.GET.get("id")
        contest_id = request.GET.get("contest_id")
        user = request.user
        if problem_id:
            try:
                problem = Problem.objects.get(id=problem_id)
                ensure_created_by(problem.contest, user)
            except Problem.DoesNotExist:
                return self.error("Problem does not exist")
            return self.success(ProblemAdminSerializer(problem).data)

        if not contest_id:
            return self.error("Contest id is required")
        try:
            contest = Contest.objects.get(id=contest_id)
            ensure_created_by(contest, user)
        except Contest.DoesNotExist:
            return self.error("Contest does not exist")
        problems = Problem.objects.filter(contest=contest).order_by("_id")
        if user.is_admin():
            problems = problems.filter(contest__created_by=user)
        keyword = request.GET.get("keyword")
        if keyword:
            problems = problems.filter(title__contains=keyword)
        return self.success(self.paginate_data(request, problems, ProblemAdminSerializer))

    @validate_serializer(EditContestProblemSerializer)
    def put(self, request):
        data = request.data
        user = request.user

        try:
            contest = Contest.objects.get(id=data.pop("contest_id"))
            ensure_created_by(contest, user)
        except Contest.DoesNotExist:
            return self.error("Contest does not exist")

        if data["rule_type"] != contest.rule_type:
            return self.error("Invalid rule type")

        problem_id = data.pop("id")

        try:
            problem = Problem.objects.get(id=problem_id, contest=contest)
        except Problem.DoesNotExist:
            return self.error("Problem does not exist")

        data["_id"] = problem._id

        error_info = self.common_checks(request)
        if error_info:
            return self.error(error_info)
        # todo check filename and score info
        tags = data.pop("tags")
        data["languages"] = list(data["languages"])

        for k, v in data.items():
            setattr(problem, k, v)
        problem.save()

        problem.tags.remove(*problem.tags.all())
        for tag in tags:
            try:
                tag = ProblemTag.objects.get(name=tag)
            except ProblemTag.DoesNotExist:
                tag = ProblemTag.objects.create(name=tag)
            problem.tags.add(tag)
        return self.success()

    def delete(self, request):
        id = request.GET.get("id")
        if not id:
            return self.error("Invalid parameter, id is required")
        try:
            problem = Problem.objects.get(id=id, contest_id__isnull=False)
        except Problem.DoesNotExist:
            return self.error("Problem does not exists")
        ensure_created_by(problem.contest, request.user)
        if Submission.objects.filter(problem=problem).exists():
            return self.error("Can't delete the problem as it has submissions")
        # d = os.path.join(settings.TEST_CASE_DIR, problem.test_case_id)
        # if os.path.isdir(d):
        #    shutil.rmtree(d, ignore_errors=True)
        problem.delete()
        return self.success()


class MakeContestProblemPublicAPIView(APIView):
    @validate_serializer(ContestProblemMakePublicSerializer)
    @problem_permission_required
    def post(self, request):
        data = request.data

        try:
            problem = Problem.objects.get(id=data["id"])
        except Problem.DoesNotExist:
            return self.error("Problem does not exist")

        if not problem.contest or problem.is_public:
            return self.error("Already be a public problem")
        ensure_created_by(problem.contest, request.user)
        display_id = (
            _remote_problem_display_id(problem)
            if problem.judge_mode == ProblemJudgeMode.REMOTE
            else _next_public_display_id()
        )
        if Problem.objects.filter(_id=display_id, contest_id__isnull=True).exists():
            return self.error("Display ID already exists")
        problem.is_public = True
        problem.publish_after_contest = False
        problem.post_contest_display_id = None
        problem.save(update_fields=("is_public", "publish_after_contest", "post_contest_display_id"))
        # https://docs.djangoproject.com/en/1.11/topics/db/queries/#copying-model-instances
        tags = problem.tags.all()
        problem.pk = None
        problem.contest = None
        problem._id = display_id
        problem.visible = False
        problem.publish_after_contest = False
        problem.post_contest_display_id = None
        problem.submission_number = problem.accepted_number = 0
        problem.statistic_info = {}
        problem.save()
        problem.tags.set(tags)
        return self.success()


class AddContestProblemAPI(APIView):
    @validate_serializer(AddContestProblemSerializer)
    def post(self, request):
        data = request.data
        try:
            contest = Contest.objects.get(id=data["contest_id"])
            problem = Problem.objects.get(id=data["problem_id"])
        except (Contest.DoesNotExist, Problem.DoesNotExist):
            return self.error("Contest or Problem does not exist")

        ensure_created_by(contest, request.user)
        if problem.contest_id is not None:
            return self.error("Only public library problems can be added")

        if contest.status == ContestStatus.CONTEST_ENDED:
            return self.error("Contest has ended")
        display_id = _next_contest_display_id(contest)
        if Problem.objects.filter(contest=contest, _id=display_id).exists():
            return self.error("Duplicate display id in this contest")

        tags = problem.tags.all()
        problem.pk = None
        problem.contest = contest
        problem.is_public = True
        problem.visible = True
        problem._id = display_id
        problem.submission_number = problem.accepted_number = 0
        problem.statistic_info = {}
        problem.publish_after_contest = False
        problem.post_contest_display_id = None
        problem.save()
        problem.tags.set(tags)
        return self.success()


class ExportProblemAPI(APIView):
    def choose_answers(self, user, problem):
        ret = []
        for item in problem.languages:
            submission = Submission.objects.filter(problem=problem,
                                                   user_id=user.id,
                                                   language=item,
                                                   result=JudgeStatus.ACCEPTED).order_by("-create_time").first()
            if submission:
                ret.append({"language": submission.language, "code": submission.code})
        return ret

    def process_one_problem(self, zip_file, user, problem, prefix=""):
        info = ExportProblemSerializer(problem).data
        info["answers"] = self.choose_answers(user, problem=problem)
        compression = zipfile.ZIP_DEFLATED
        zip_file.writestr(zinfo_or_arcname=f"{prefix}problem.json",
                          data=json.dumps(info, indent=4),
                          compress_type=compression)
        problem_test_case_dir = os.path.join(settings.TEST_CASE_DIR, problem.test_case_id)
        with open(os.path.join(problem_test_case_dir, "info")) as f:
            info = json.load(f)
        for k, v in info["test_cases"].items():
            input_name = v["input_name"]
            zip_file.write(filename=os.path.join(problem_test_case_dir, input_name),
                           arcname=f"{prefix}testcase/{input_name}",
                           compress_type=compression)
            if not info["spj"]:
                output_name = v["output_name"]
                zip_file.write(filename=os.path.join(problem_test_case_dir, output_name),
                               arcname=f"{prefix}testcase/{output_name}",
                               compress_type=compression)

    @validate_serializer(ExportProblemRequestSerialzier)
    def get(self, request):
        problems = Problem.objects.filter(id__in=request.data["problem_id"])
        for problem in problems:
            if problem.contest:
                ensure_created_by(problem.contest, request.user)
            else:
                ensure_created_by(problem, request.user)
        path = f"/tmp/{rand_str()}.zip"
        with zipfile.ZipFile(path, "w") as zip_file:
            if len(problems) == 1:
                self.process_one_problem(
                    zip_file=zip_file, user=request.user, problem=problems[0]
                )
            else:
                for index, problem in enumerate(problems, start=1):
                    problem_buffer = io.BytesIO()
                    with zipfile.ZipFile(problem_buffer, "w") as problem_zip:
                        self.process_one_problem(
                            zip_file=problem_zip, user=request.user, problem=problem
                        )
                    zip_file.writestr(
                        f"{index:03d}.zip",
                        problem_buffer.getvalue(),
                        compress_type=zipfile.ZIP_STORED,
                    )
        delete_files.send_with_options(args=(path,), delay=300_000)
        resp = FileResponse(open(path, "rb"))
        resp["Content-Type"] = "application/zip"
        resp["Content-Disposition"] = "attachment;filename=problem-export.zip"
        return resp


class ImportProblemAPI(APIView, TestCaseZipProcessor):
    request_parsers = ()

    MAX_ARCHIVE_MEMBERS = 10_000
    MAX_ARCHIVE_SIZE = 1024 * 1024 * 1024
    MAX_MEMBER_SIZE = 64 * 1024 * 1024

    def _validate_archive(self, zip_file):
        members = zip_file.infolist()
        if len(members) > self.MAX_ARCHIVE_MEMBERS:
            raise APIError("Too many files in zip package")

        total_size = 0
        names = set()
        for member in members:
            name = member.filename
            path = PurePosixPath(name)
            if (not name or name.startswith("/") or "\\" in name or
                    ".." in path.parts):
                raise APIError(f"Unsafe zip entry {name}")
            if name in names:
                raise APIError(f"Duplicate zip entry {name}")
            names.add(name)
            if member.flag_bits & 0x1:
                raise APIError(f"Encrypted zip entry is not supported: {name}")
            if member.file_size > self.MAX_MEMBER_SIZE:
                raise APIError(f"Zip entry is too large: {name}")
            total_size += member.file_size
            if total_size > self.MAX_ARCHIVE_SIZE:
                raise APIError("Uncompressed zip package is too large")
        return names, total_size

    def _discover_problem_prefixes(self, names):
        prefixes = []
        for name in names:
            if name == "problem.json":
                prefixes.append("")
            elif name.endswith("/problem.json"):
                prefixes.append(name[:-len("problem.json")])
        prefixes = sorted(set(prefixes), key=natural_sort_key)
        return prefixes

    def _discover_import_layout(self, names):
        prefixes = self._discover_problem_prefixes(names)
        nested_zips = sorted(
            (
                name for name in names
                if name.lower().endswith(".zip")
                and "__MACOSX" not in PurePosixPath(name).parts
                and not PurePosixPath(name).name.startswith("._")
            ),
            key=natural_sort_key,
        )
        if nested_zips:
            non_batch_files = [
                name for name in names
                if not name.endswith("/")
                and "__MACOSX" not in PurePosixPath(name).parts
                and not PurePosixPath(name).name.startswith("._")
                and name not in nested_zips
            ]
            if non_batch_files:
                raise APIError(
                    "Batch zip may contain only independently importable single-problem zip files"
                )
            return "batch", nested_zips
        if not prefixes:
            raise APIError("No problem.json or single-problem zip found in package")
        return ("single" if prefixes == [""] else "qduoj"), prefixes

    def _load_problem_info(self, zip_file, prefix):
        problem_path = f"{prefix}problem.json"
        try:
            with zip_file.open(problem_path) as problem_file:
                problem_info = json.load(problem_file)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise APIError(f"Invalid JSON in {problem_path}", str(exc))

        serializer = ImportProblemSerializer(data=problem_info)
        if not serializer.is_valid():
            raise APIError(
                f"Invalid problem format in {problem_path}: {serializer.errors}"
            )
        problem_info = serializer.validated_data
        for language, value in problem_info["template"].items():
            if language not in SysOptions.language_names:
                raise APIError(f"Unsupported language {language}")
            problem_info["template"][language] = build_problem_template(
                value["prepend"], value["template"], value["append"]
            )
        for field in ("description", "input_description", "output_description", "hint"):
            formatted = problem_info[field]
            problem_info[field] = (
                markdown_to_html(formatted["value"])
                if formatted["format"] == "markdown"
                else formatted["value"]
            )
        return problem_info

    def _create_problem(self, request, zip_file, prefix, problem_info):
        spj = problem_info["spj"] is not None
        processed_cases, test_case_id = self.process_zip(
            zip_file, spj=spj, dir=f"{prefix}testcase/"
        )
        supplied_scores = {
            (item["input_name"], item.get("output_name", "")): item["score"]
            for item in (problem_info["test_case_score"] or [])
        }
        processed_names = {
            (item["input_name"], item.get("output_name", ""))
            for item in processed_cases
        }
        if supplied_scores and set(supplied_scores) != processed_names:
            shutil.rmtree(os.path.join(settings.TEST_CASE_DIR, test_case_id), ignore_errors=True)
            raise APIError(
                f"test_case_score does not match testcase files under {prefix or '/'}"
            )
        test_case_score = []
        for item in processed_cases:
            case = dict(item)
            key = (item["input_name"], item.get("output_name", ""))
            case["score"] = supplied_scores.get(key, 100)
            test_case_score.append(case)

        rule_type = problem_info["rule_type"]
        try:
            problem_obj = Problem.objects.create(
                _id=problem_info["display_id"],
                title=problem_info["title"],
                description=problem_info["description"],
                input_description=problem_info["input_description"],
                output_description=problem_info["output_description"],
                hint=problem_info["hint"],
                test_case_score=test_case_score,
                time_limit=problem_info["time_limit"],
                memory_limit=problem_info["memory_limit"],
                samples=problem_info["samples"],
                template=problem_info["template"],
                rule_type=rule_type,
                source=problem_info["source"],
                spj=spj,
                spj_code=problem_info["spj"]["code"] if spj else None,
                spj_language=problem_info["spj"]["language"] if spj else None,
                spj_version=rand_str(8) if spj else "",
                languages=problem_info.get("languages", SysOptions.language_names),
                created_by=request.user,
                visible=problem_info["visible"],
                difficulty=problem_info["difficulty"],
                total_score=sum(item["score"] for item in test_case_score)
                if rule_type == ProblemRuleType.OI else 0,
                test_case_id=test_case_id,
            )
            for tag_name in problem_info["tags"]:
                tag_obj, _ = ProblemTag.objects.get_or_create(name=tag_name)
                problem_obj.tags.add(tag_obj)
        except Exception:
            shutil.rmtree(os.path.join(settings.TEST_CASE_DIR, test_case_id), ignore_errors=True)
            raise
        return problem_obj, test_case_id

    @problem_permission_required
    def post(self, request):
        form = UploadProblemForm(request.POST, request.FILES)
        if not form.is_valid():
            return self.error("Upload failed")
        uploaded_file = form.cleaned_data["file"]
        created_test_case_ids = []
        imported = []
        try:
            with tempfile.NamedTemporaryFile(suffix=".zip") as tmp_file:
                for chunk in uploaded_file.chunks(4096):
                    tmp_file.write(chunk)
                tmp_file.flush()
                try:
                    with zipfile.ZipFile(tmp_file.name, "r") as zip_file:
                        names, _ = self._validate_archive(zip_file)
                        package_format, entries = self._discover_import_layout(names)
                        with transaction.atomic():
                            if package_format == "batch":
                                total_expanded_size = 0
                                for entry in entries:
                                    try:
                                        with zipfile.ZipFile(
                                                io.BytesIO(zip_file.read(entry)),
                                                "r") as problem_zip:
                                            inner_names, inner_size = self._validate_archive(
                                                problem_zip
                                            )
                                            total_expanded_size += inner_size
                                            if total_expanded_size > self.MAX_ARCHIVE_SIZE:
                                                raise APIError(
                                                    "Expanded batch contents are too large"
                                                )
                                            inner_format, prefixes = (
                                                self._discover_import_layout(inner_names)
                                            )
                                            if inner_format == "batch" or len(prefixes) != 1:
                                                raise APIError(
                                                    f"{entry} must be a single-problem zip"
                                                )
                                            problem_info = self._load_problem_info(
                                                problem_zip, prefixes[0]
                                            )
                                            problem_info["display_id"] = (
                                                _next_public_display_id()
                                            )
                                            problem, test_case_id = self._create_problem(
                                                request, problem_zip, prefixes[0], problem_info
                                            )
                                    except zipfile.BadZipFile:
                                        raise APIError(f"Bad nested zip file: {entry}")
                                    created_test_case_ids.append(test_case_id)
                                    imported.append({
                                        "id": problem.id,
                                        "display_id": problem._id,
                                        "title": problem.title,
                                    })
                            else:
                                for prefix in entries:
                                    problem_info = self._load_problem_info(zip_file, prefix)
                                    problem_info["display_id"] = _next_public_display_id()
                                    problem, test_case_id = self._create_problem(
                                        request, zip_file, prefix, problem_info
                                    )
                                    created_test_case_ids.append(test_case_id)
                                    imported.append({
                                        "id": problem.id,
                                        "display_id": problem._id,
                                        "title": problem.title,
                                    })
                except zipfile.BadZipFile:
                    raise APIError("Bad zip file")
        except Exception:
            for test_case_id in created_test_case_ids:
                shutil.rmtree(
                    os.path.join(settings.TEST_CASE_DIR, test_case_id), ignore_errors=True
                )
            raise
        return self.success({
            "import_count": len(imported),
            "package_format": package_format,
            "imported": imported,
        })


class FPSProblemImport(APIView):
    request_parsers = ()

    def _create_problem(self, problem_data, creator):
        if problem_data["time_limit"]["unit"] == "ms":
            time_limit = problem_data["time_limit"]["value"]
        else:
            time_limit = problem_data["time_limit"]["value"] * 1000
        template = {}
        prepend = {}
        append = {}
        for t in problem_data["prepend"]:
            prepend[t["language"]] = t["code"]
        for t in problem_data["append"]:
            append[t["language"]] = t["code"]
        for t in problem_data["template"]:
            our_lang = lang = t["language"]
            if lang == "Python":
                our_lang = "Python3"
            template[our_lang] = TEMPLATE_BASE.format(prepend.get(lang, ""), t["code"], append.get(lang, ""))
        spj = problem_data["spj"] is not None
        Problem.objects.create(_id=f"fps-{rand_str(4)}",
                               title=problem_data["title"],
                               description=problem_data["description"],
                               input_description=problem_data["input"],
                               output_description=problem_data["output"],
                               hint=problem_data["hint"],
                               test_case_score=problem_data["test_case_score"],
                               time_limit=time_limit,
                               memory_limit=problem_data["memory_limit"]["value"],
                               samples=problem_data["samples"],
                               template=template,
                               rule_type=ProblemRuleType.ACM,
                               source=problem_data.get("source", ""),
                               spj=spj,
                               spj_code=problem_data["spj"]["code"] if spj else None,
                               spj_language=problem_data["spj"]["language"] if spj else None,
                               spj_version=rand_str(8) if spj else "",
                               visible=False,
                               languages=SysOptions.language_names,
                               created_by=creator,
                               difficulty=Difficulty.MID,
                               test_case_id=problem_data["test_case_id"])

    @problem_permission_required
    def post(self, request):
        form = UploadProblemForm(request.POST, request.FILES)
        if not form.is_valid():
            return self.error("Parse upload file error")
        file = form.cleaned_data["file"]
        from xml.etree.ElementTree import ParseError
        try:
            problems = FPSParser(string_data=file.read()).parse()
        except (ValueError, ParseError):
            return self.error("Invalid FPS document")
        if not problems:
            return self.error("FPS document has no problems")
        for problem in problems:
            serializer = FPSProblemSerializer(data=problem)
            if not serializer.is_valid() or not problem["test_cases"]:
                return self.error("Invalid FPS problem or missing test cases")
        helper = FPSHelper()
        directories, images = [], []
        try:
            with transaction.atomic():
                for problem in problems:
                    test_case_id = rand_str()
                    directory = os.path.join(settings.TEST_CASE_DIR, test_case_id)
                    os.mkdir(directory, 0o710)
                    directories.append(directory)
                    info = helper.save_test_case(problem, directory)
                    problem_data = helper.save_image(problem, settings.UPLOAD_DIR, settings.UPLOAD_PREFIX, images)
                    serializer = FPSProblemSerializer(data=problem_data)
                    if not serializer.is_valid():
                        raise APIError("Invalid FPS problem after image processing")
                    problem_data = dict(serializer.data)
                    problem_data["test_case_id"] = test_case_id
                    problem_data["test_case_score"] = [
                        {"score": 0, "input_name": item["input_name"], "output_name": item.get("output_name")}
                        for item in info["test_cases"].values()
                    ]
                    self._create_problem(problem_data, request.user)
        except Exception:
            for directory in directories:
                shutil.rmtree(directory)
            for image in images:
                os.unlink(image)
            raise
        return self.success({"import_count": len(problems)})
