"""Contest preparation workspace API.

These views live outside /api/admin/ because problem setters and verifiers may
be regular users. Every view resolves its contest through load_prep_contest,
which hides the contest from everyone without a preparation role.
"""
from django.core.cache import cache

from account.decorators import login_required
from account.models import User
from problem.contest_authoring import (create_contest_problem, next_contest_display_id,
                                       order_contest_problems, reorder_contest_problems,
                                       update_contest_problem)
from problem.models import Problem
from problem.serializers import (CreatePrepContestProblemSerializer, EditPrepContestProblemSerializer,
                                 ProblemAdminSerializer)
from problem.views.admin import CompileSPJAPI, ImportProblemAPI, ProblemBase, TestCaseAPI
from utils.api import APIError, APIView, validate_serializer
from utils.constants import CacheKey, ContestPrepRole, ContestPrepState
from ..models import Contest, ContestPrepMember
from ..prep_publish import publish_prep_contest
from ..serializers import (ContestPrepMemberSerializer, ContestPrepProblemOrderSerializer,
                           ContestPrepProblemVisibleSerializer, ContestPrepPublishSerializer,
                           ContestPrepStateSerializer, CreateContestPrepMemberSerializer,
                           EditContestPrepMemberSerializer)

VIEW, AUTHOR, EDIT, MANAGE = "view", "author", "edit", "manage"


def load_prep_contest(request, contest_id, need=VIEW):
    """Return the preparation contest for this member or raise APIError.

    need: VIEW (any role), AUTHOR (creator or setter), EDIT (AUTHOR while in
    Preparation) or MANAGE (creator only).
    """
    if not str(contest_id or "").isdigit():
        raise APIError("Invalid parameter, contest_id is required")
    try:
        contest = Contest.objects.select_related("created_by").get(
            id=contest_id, visible=True, prep_state__isnull=False)
    except Contest.DoesNotExist:
        raise APIError("Contest does not exist")
    role = contest.prep_role(request.user)
    if role is None:
        raise APIError("Contest does not exist")
    if need == MANAGE and role != ContestPrepRole.CREATOR:
        raise APIError("Only the contest creator can do this")
    if need in (AUTHOR, EDIT) and role not in (ContestPrepRole.CREATOR, ContestPrepRole.SETTER):
        raise APIError("Only problem setters can do this")
    if need == EDIT and contest.prep_state != ContestPrepState.PREPARATION:
        raise APIError("Switch the contest back to preparation before editing problems")
    return contest


def clear_rank_cache(contest):
    cache.delete(f"{CacheKey.contest_rank_cache}:{contest.id}")


def get_contest_problem(contest, problem_id):
    try:
        return Problem.objects.get(id=problem_id, contest=contest)
    except (Problem.DoesNotExist, ValueError, TypeError):
        raise APIError("Problem does not exist")


class ContestPrepStateAPI(APIView):
    @validate_serializer(ContestPrepStateSerializer)
    @login_required
    def put(self, request):
        contest = load_prep_contest(request, request.data["contest_id"], MANAGE)
        contest.prep_state = request.data["state"]
        contest.save(update_fields=["prep_state", "last_update_time"])
        clear_rank_cache(contest)
        return self.success({"prep_state": contest.prep_state})


class ContestPrepMemberAPI(APIView):
    @login_required
    def get(self, request):
        contest = load_prep_contest(request, request.GET.get("contest_id"))
        members = ContestPrepMember.objects.filter(contest=contest).select_related("user")
        return self.success({
            "creator": {"id": contest.created_by.id, "username": contest.created_by.username},
            "members": ContestPrepMemberSerializer(members, many=True).data,
        })

    @validate_serializer(CreateContestPrepMemberSerializer)
    @login_required
    def post(self, request):
        data = request.data
        contest = load_prep_contest(request, data["contest_id"], MANAGE)
        try:
            user = User.objects.get(username=data["username"], is_disabled=False)
        except User.DoesNotExist:
            return self.error("User does not exist")
        if user.id == contest.created_by_id:
            return self.error("The creator already has every permission")
        member, created = ContestPrepMember.objects.get_or_create(
            contest=contest, user=user, defaults={"role": data["role"]})
        if not created:
            return self.error("The user is already a member")
        return self.success(ContestPrepMemberSerializer(member).data)

    @validate_serializer(EditContestPrepMemberSerializer)
    @login_required
    def put(self, request):
        data = request.data
        contest = load_prep_contest(request, data["contest_id"], MANAGE)
        updated = ContestPrepMember.objects.filter(contest=contest, user_id=data["user_id"]).update(
            role=data["role"])
        if not updated:
            return self.error("Member does not exist")
        return self.success()

    @login_required
    def delete(self, request):
        contest = load_prep_contest(request, request.GET.get("contest_id"), MANAGE)
        deleted, _ = ContestPrepMember.objects.filter(
            contest=contest, user_id=request.GET.get("user_id")).delete()
        if not deleted:
            return self.error("Member does not exist")
        return self.success()


class ContestPrepUserSearchAPI(APIView):
    @login_required
    def get(self, request):
        contest = load_prep_contest(request, request.GET.get("contest_id"), MANAGE)
        keyword = request.GET.get("keyword", "").strip()
        if not keyword:
            return self.success([])
        users = (User.objects.filter(username__icontains=keyword, is_disabled=False)
                 .exclude(id=contest.created_by_id).order_by("username")[:10])
        return self.success([{"id": user.id, "username": user.username} for user in users])


class ContestPrepProblemAPI(ProblemBase):
    @login_required
    def get(self, request):
        contest = load_prep_contest(request, request.GET.get("contest_id"), AUTHOR)
        problem_id = request.GET.get("id")
        if problem_id:
            return self.success(ProblemAdminSerializer(get_contest_problem(contest, problem_id)).data)
        problems = order_contest_problems(Problem.objects.filter(contest=contest).select_related("created_by"))
        return self.success(ProblemAdminSerializer(problems, many=True).data)

    @validate_serializer(CreatePrepContestProblemSerializer)
    @login_required
    def post(self, request):
        data = request.data
        contest = load_prep_contest(request, data.pop("contest_id"), EDIT)
        if data["rule_type"] != contest.rule_type:
            return self.error("Invalid rule type")
        data["_id"] = next_contest_display_id(contest)
        error_info = self.common_checks(request)
        if error_info:
            return self.error(error_info)
        problem = create_contest_problem(contest, data, request.user)
        return self.success(ProblemAdminSerializer(problem).data)

    @validate_serializer(EditPrepContestProblemSerializer)
    @login_required
    def put(self, request):
        data = request.data
        contest = load_prep_contest(request, data.pop("contest_id"), EDIT)
        if data["rule_type"] != contest.rule_type:
            return self.error("Invalid rule type")
        problem = get_contest_problem(contest, data.pop("id"))
        error_info = self.common_checks(request)
        if error_info:
            return self.error(error_info)
        update_contest_problem(problem, data)
        return self.success()

    @login_required
    def delete(self, request):
        contest = load_prep_contest(request, request.GET.get("contest_id"), EDIT)
        problem = get_contest_problem(contest, request.GET.get("id"))
        # Verification runs are deleted with the problem; they never reached
        # any rank, mark or counter.
        problem.delete()
        clear_rank_cache(contest)
        return self.success()


class ContestPrepProblemVisibleAPI(APIView):
    @validate_serializer(ContestPrepProblemVisibleSerializer)
    @login_required
    def put(self, request):
        data = request.data
        contest = load_prep_contest(request, data["contest_id"], EDIT)
        problem = get_contest_problem(contest, data["id"])
        problem.visible = data["visible"]
        problem.save(update_fields=["visible"])
        return self.success({"visible": problem.visible})


class ContestPrepProblemOrderAPI(APIView):
    @validate_serializer(ContestPrepProblemOrderSerializer)
    @login_required
    def put(self, request):
        contest = load_prep_contest(request, request.data["contest_id"], EDIT)
        reorder_contest_problems(contest, request.data["problem_ids"])
        clear_rank_cache(contest)
        problems = order_contest_problems(Problem.objects.filter(contest=contest).select_related("created_by"))
        return self.success(ProblemAdminSerializer(problems, many=True).data)


class ContestPrepTestCaseAPI(TestCaseAPI):
    @login_required
    def get(self, request):
        contest = load_prep_contest(request, request.GET.get("contest_id"), AUTHOR)
        return self.test_case_response(get_contest_problem(contest, request.GET.get("problem_id")))

    @login_required
    def post(self, request):
        load_prep_contest(request, request.POST.get("contest_id"), EDIT)
        return TestCaseAPI.post(self, request)


class ContestPrepCompileSPJAPI(CompileSPJAPI):
    @login_required
    def post(self, request):
        load_prep_contest(request, request.data.get("contest_id"), EDIT)
        return CompileSPJAPI.post(self, request)


class ContestPrepImportProblemAPI(ImportProblemAPI):
    @login_required
    def post(self, request):
        contest = load_prep_contest(request, request.POST.get("contest_id"), EDIT)
        return self.import_upload(request, contest=contest)


class ContestPrepPublishAPI(APIView):
    @validate_serializer(ContestPrepPublishSerializer)
    @login_required
    def post(self, request):
        # validated_data holds only the fields the creator actually sent.
        overrides = dict(request.serializer.validated_data)
        prep = load_prep_contest(request, overrides.pop("contest_id"), MANAGE)
        contest = publish_prep_contest(prep, overrides)
        return self.success({"id": contest.id, "title": contest.title})
