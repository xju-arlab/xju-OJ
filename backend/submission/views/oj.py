import ipaddress
import logging

from account.decorators import login_required, check_contest_permission
from contest.models import ContestStatus, ContestRuleType
from django.db import transaction
from django.utils import timezone
from judge.tasks import judge_task
from options.options import SysOptions
# from judge.dispatcher import JudgeDispatcher
from problem.models import Problem, ProblemJudgeMode, ProblemRuleType
from utils.api import APIView, validate_serializer
from utils.cache import cache
from utils.captcha import Captcha
from utils.throttling import TokenBucket
from ..models import (JudgeStatus, RemoteSubmissionStatus, Submission,
                      SubmissionJudgeMode)
from ..remote import (RemoteSubmissionError, apply_remote_submission_event,
                      build_remote_task)
from ..serializers import (CreateSubmissionSerializer, SubmissionModelSerializer,
                           RemoteSubmissionEventSerializer,
                           ShareSubmissionSerializer)
from ..serializers import SubmissionSafeModelSerializer, SubmissionListSerializer

logger = logging.getLogger(__name__)


class SubmissionAPI(APIView):
    def throttling(self, request):
        # 使用 open_api 的请求暂不做限制
        auth_method = getattr(request, "auth_method", "")
        if auth_method == "api_key":
            return
        user_bucket = TokenBucket(key=str(request.user.id),
                                  redis_conn=cache, **SysOptions.throttling["user"])
        can_consume, wait = user_bucket.consume()
        if not can_consume:
            return "Please wait %d seconds" % (int(wait))

        # ip_bucket = TokenBucket(key=request.session["ip"],
        #                         redis_conn=cache, **SysOptions.throttling["ip"])
        # can_consume, wait = ip_bucket.consume()
        # if not can_consume:
        #     return "Captcha is required"

    @check_contest_permission(check_type="problems")
    def check_contest_permission(self, request):
        contest = self.contest
        if contest.status == ContestStatus.CONTEST_ENDED:
            # Ended password contests retain the existing public-practice
            # policy. Registration, password and venue IP restrictions end.
            return
        if not request.user.is_contest_admin(contest):
            user_ip = ipaddress.ip_address(request.ip)
            if contest.allowed_ip_ranges:
                if not any(user_ip in ipaddress.ip_network(cidr, strict=False) for cidr in contest.allowed_ip_ranges):
                    return self.error("Your IP is not allowed in this contest")

    @validate_serializer(CreateSubmissionSerializer)
    @login_required
    def post(self, request):
        data = request.data
        hide_id = False
        if data.get("contest_id"):
            error = self.check_contest_permission(request)
            if error:
                return error
            contest = self.contest
            if not contest.problem_details_permission(request.user):
                hide_id = True

        if data.get("captcha"):
            if not Captcha(request).check(data["captcha"]):
                return self.error("Invalid captcha")
        error = self.throttling(request)
        if error:
            return self.error(error)

        try:
            problem = Problem.objects.get(id=data["problem_id"], contest_id=data.get("contest_id"), visible=True)
        except Problem.DoesNotExist:
            return self.error("Problem not exist")
        if data["language"] not in problem.languages:
            language_name = data["language"]
            return self.error(f"{language_name} is not allowed in the problem")
        remote_task = None
        try:
            with transaction.atomic():
                is_remote = problem.judge_mode == ProblemJudgeMode.REMOTE
                submission = Submission.objects.create(
                    user_id=request.user.id,
                    username=request.user.username,
                    language=data["language"],
                    code=data["code"],
                    problem_id=problem.id,
                    ip=request.ip,
                    contest_id=data.get("contest_id"),
                    judge_mode=SubmissionJudgeMode.REMOTE if is_remote else SubmissionJudgeMode.LOCAL,
                    remote_oj=problem.remote_oj if is_remote else None,
                    remote_status=RemoteSubmissionStatus.QUEUED if is_remote else None,
                    remote_update_time=timezone.now() if is_remote else None,
                )
                if is_remote:
                    remote_task = build_remote_task(problem, submission)
        except RemoteSubmissionError as exc:
            return self.error(str(exc))

        # use this for debug
        # JudgeDispatcher(submission.id, problem.id).judge()
        if remote_task is None:
            judge_task.send(submission.id, problem.id)
        if hide_id and remote_task is None:
            return self.success()
        else:
            response = {"submission_id": submission.id}
            if remote_task is not None:
                response["remote_task"] = remote_task
            return self.success(response)

    @login_required
    def get(self, request):
        submission_id = request.GET.get("id")
        if not submission_id:
            return self.error("Parameter id doesn't exist")
        try:
            submission = Submission.objects.select_related("problem").get(id=submission_id)
        except Submission.DoesNotExist:
            return self.error("Submission doesn't exist")
        if not submission.check_user_permission(request.user):
            return self.error("No permission for this submission")

        if submission.problem.rule_type == ProblemRuleType.OI or request.user.is_admin_role():
            submission_data = SubmissionModelSerializer(submission).data
        else:
            submission_data = SubmissionSafeModelSerializer(submission).data
        # 是否有权限取消共享
        submission_data["can_unshare"] = submission.check_user_permission(request.user, check_share=False)
        return self.success(submission_data)

    @validate_serializer(ShareSubmissionSerializer)
    @login_required
    def put(self, request):
        """
        share submission
        """
        try:
            submission = Submission.objects.select_related("problem").get(id=request.data["id"])
        except Submission.DoesNotExist:
            return self.error("Submission doesn't exist")
        if not submission.check_user_permission(request.user, check_share=False):
            return self.error("No permission to share the submission")
        if submission.contest and submission.contest.status == ContestStatus.CONTEST_UNDERWAY:
            return self.error("Can not share submission now")
        submission.shared = request.data["shared"]
        submission.save(update_fields=["shared"])
        return self.success()


class SubmissionListAPI(APIView):
    def get(self, request):
        if not request.GET.get("limit"):
            return self.error("Limit is needed")
        if request.GET.get("contest_id"):
            return self.error("Parameter error")

        submissions = Submission.objects.filter(contest_id__isnull=True).select_related("problem__created_by")
        problem_id = request.GET.get("problem_id")
        myself = request.GET.get("myself")
        result = request.GET.get("result")
        username = request.GET.get("username")
        if problem_id:
            try:
                problem = Problem.objects.get(_id=problem_id, contest_id__isnull=True, visible=True)
            except Problem.DoesNotExist:
                return self.error("Problem doesn't exist")
            submissions = submissions.filter(problem=problem)
        if (myself and myself == "1") or not SysOptions.submission_list_show_all:
            submissions = submissions.filter(user_id=request.user.id)
        elif username:
            submissions = submissions.filter(username__icontains=username)
        if result:
            submissions = submissions.filter(result=result)
        data = self.paginate_data(request, submissions)
        data["results"] = SubmissionListSerializer(data["results"], many=True, user=request.user).data
        return self.success(data)


class ContestSubmissionListAPI(APIView):
    @check_contest_permission(check_type="submissions")
    def get(self, request):
        if not request.GET.get("limit"):
            return self.error("Limit is needed")

        contest = self.contest
        submissions = Submission.objects.filter(contest_id=contest.id).select_related("problem__created_by")
        problem_id = request.GET.get("problem_id")
        myself = request.GET.get("myself")
        result = request.GET.get("result")
        username = request.GET.get("username")
        if problem_id:
            try:
                problem = Problem.objects.get(_id=problem_id, contest_id=contest.id, visible=True)
            except Problem.DoesNotExist:
                return self.error("Problem doesn't exist")
            submissions = submissions.filter(problem=problem)

        if myself and myself == "1":
            submissions = submissions.filter(user_id=request.user.id)
        elif username:
            submissions = submissions.filter(username__icontains=username)
        if result:
            submissions = submissions.filter(result=result)

        # filter the test submissions submitted before contest start
        if contest.status != ContestStatus.CONTEST_NOT_START:
            submissions = submissions.filter(create_time__gte=contest.start_time)

        # 封榜的时候只能看到自己的提交
        if contest.rule_type == ContestRuleType.ACM:
            if not contest.real_time_rank and not request.user.is_contest_admin(contest):
                submissions = submissions.filter(user_id=request.user.id)

        data = self.paginate_data(request, submissions)
        data["results"] = SubmissionListSerializer(data["results"], many=True, user=request.user).data
        return self.success(data)


class SubmissionExistsAPI(APIView):
    def get(self, request):
        if not request.GET.get("problem_id"):
            return self.error("Parameter error, problem_id is required")
        return self.success(request.user.is_authenticated and
                            Submission.objects.filter(problem_id=request.GET["problem_id"],
                                                      user_id=request.user.id).exists())


class RemoteSubmissionRecoveryAPI(APIView):
    @login_required
    def get(self, request):
        # Recovery belongs to the original submitter, including for admins.
        submissions = Submission.objects.select_related("problem").filter(
            user_id=request.user.id, judge_mode=SubmissionJudgeMode.REMOTE)
        submission_id = request.GET.get("submission_id")
        if submission_id:
            submission = submissions.filter(id=submission_id).first()
            if submission is None:
                return self.error("Remote submission does not exist")
            if submission.remote_status in RemoteSubmissionStatus.TERMINAL:
                return self.success({"task": None, "submission": SubmissionModelSerializer(submission).data})
            try:
                task = build_remote_task(submission.problem, submission)
            except RemoteSubmissionError as exc:
                return self.error(str(exc))
            return self.success({"task": task, "code": submission.code if not submission.remote_submission_id else ""})
        # Only resume queries automatically. Login/verification and sending code
        # require the user's explicit recovery action, avoiding duplicate runs.
        pending = submissions.filter(result__in=[JudgeStatus.PENDING, JudgeStatus.JUDGING]).exclude(
            remote_submission_id__isnull=True).exclude(remote_submission_id="").order_by("create_time")[:50]
        tasks = []
        for submission in pending:
            try:
                tasks.append(build_remote_task(submission.problem, submission))
            except RemoteSubmissionError:
                continue
        return self.success({"user_id": request.user.id, "tasks": tasks})


class RemoteSubmissionEventAPI(APIView):
    def invalid_serializer(self, serializer):
        response = super().invalid_serializer(serializer)
        # Log field names, never credentials, source, or compiler output.
        logger.warning("Remote event rejected: %s", response.data["error"])
        return response

    @validate_serializer(RemoteSubmissionEventSerializer)
    @login_required
    def post(self, request):
        try:
            submission = apply_remote_submission_event(request.user, request.data)
        except RemoteSubmissionError as exc:
            logger.warning("Remote event rejected: submission=%s provider=%s status=%s reason=%s",
                           request.data.get("submission_id"), request.data.get("provider"),
                           request.data.get("status"), str(exc)[:180])
            return self.error(str(exc))
        return self.success(SubmissionModelSerializer(submission).data)
