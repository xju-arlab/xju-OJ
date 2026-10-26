"""Contest preparation workspace API.

These views live outside /api/admin/ because organizers may be regular users.
Every view resolves its contest through load_prep_contest, which hides the
contest from everyone outside the team (the creator, organizers and super
admins). The workspace is always open for setting problems; review rounds run
beside it as 5-hour mock contests of the selected problems.
"""
import hashlib
import secrets
from datetime import timedelta

from django.core.cache import cache
from django.db import transaction
from django.db.models import Count, Q
from django.utils.timezone import now

from account.decorators import login_required
from account.models import User
from problem.contest_authoring import (create_contest_problem, next_contest_display_id,
                                       order_contest_problems, reorder_contest_problems,
                                       update_contest_problem)
from problem.models import Problem, ProblemTag
from problem.serializers import (CreatePrepContestProblemSerializer, EditPrepContestProblemSerializer,
                                 ProblemAdminSerializer)
from problem.views.admin import CompileSPJAPI, ImportProblemAPI, ProblemBase, TestCaseAPI
from utils.api import APIError, APIView, validate_serializer
from utils.constants import CacheKey, ContestPrepRole, PREP_INVITE_DAYS
from utils.shortcuts import datetime2str
from ..models import Contest, ContestPrepInvite, ContestPrepMember, ContestProblemFeedback
from ..prep_publish import publish_prep_contest
from ..prep_rank import review_rank
from ..serializers import (AcceptContestPrepInviteSerializer, ContestPrepMemberSerializer,
                           ContestPrepProblemCountSerializer, ContestPrepProblemMetaSerializer,
                           ContestPrepProblemOrderSerializer, ContestPrepProblemSelectSerializer,
                           ContestPrepPublicProblemSerializer, ContestPrepPublishSerializer,
                           ContestPrepReviewSerializer, ContestProblemFeedbackSerializer,
                           CreateContestPrepInviteSerializer, CreateContestPrepMemberSerializer,
                           CreateContestProblemFeedbackSerializer, EditContestProblemFeedbackSerializer)

VIEW, MANAGE = "view", "manage"
MAX_OPEN_INVITES = 20
INVITE_FAILURE_LIMIT = 10
INVITE_FAILURE_WINDOW = 10 * 60


def load_prep_contest(request, contest_id, need=VIEW):
    """Return the preparation contest for this member or raise APIError.

    need: VIEW (any member, who may also set and select problems) or MANAGE
    (creator only: roles, invites, the problem count, review rounds, publish).
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
    return contest


def clear_rank_cache(contest):
    cache.delete(f"{CacheKey.contest_rank_cache}:{contest.id}")


def with_feedback_counts(contest, problems):
    counts = dict(ContestProblemFeedback.objects.filter(contest=contest).values("problem_id")
                  .annotate(open=Count("id", filter=Q(resolved=False))).values_list("problem_id", "open"))
    for problem in problems:
        problem["feedback_count"] = counts.get(problem["id"], 0)
    return problems


def get_contest_problem(contest, problem_id):
    try:
        return Problem.objects.get(id=problem_id, contest=contest)
    except (Problem.DoesNotExist, ValueError, TypeError):
        raise APIError("Problem does not exist")


def problem_list(contest):
    problems = order_contest_problems(Problem.objects.filter(contest=contest)
                                      .select_related("created_by").prefetch_related("tags"))
    return with_feedback_counts(contest, ProblemAdminSerializer(problems, many=True).data)


@transaction.atomic
def keep_selected_first(contest, problem_ids=None):
    """Relabel the problems so the selected ones come first, in their current order.

    The selected problems are the contest: review and publish show them as A,
    B, C... and the candidates that were not picked follow them.
    """
    problems = list(order_contest_problems(Problem.objects.select_for_update().filter(contest=contest)))
    selected = {problem.id for problem in problems if problem.visible}
    if problem_ids is None:
        problem_ids = [problem.id for problem in problems]
    ordered = [pk for pk in problem_ids if pk in selected] + [pk for pk in problem_ids if pk not in selected]
    reorder_contest_problems(contest, ordered)


class ContestPrepReviewAPI(APIView):
    """Start a review round: a fresh 5-hour mock contest of the selected problems."""

    @validate_serializer(ContestPrepReviewSerializer)
    @login_required
    def post(self, request):
        data = request.serializer.validated_data
        contest = load_prep_contest(request, data["contest_id"], MANAGE)
        if not Problem.objects.filter(contest=contest, visible=True).exists():
            return self.error("Select the contest problems before starting a review")
        # The clock and the review board start over with every round.
        contest.review_started_at = now()
        if "password" in data:
            contest.password = data["password"] or None
        contest.save(update_fields=["password", "review_started_at", "last_update_time"])
        clear_rank_cache(contest)
        return self.success({"review_started_at": datetime2str(contest.review_started_at),
                             "password": contest.password})


class ContestPrepMemberAPI(APIView):
    @login_required
    def get(self, request):
        contest = load_prep_contest(request, request.GET.get("contest_id"))
        members = ContestPrepMember.objects.filter(contest=contest).select_related("user__userprofile")
        creator = contest.created_by
        return self.success({
            "creator": {"id": creator.id, "username": creator.username,
                        "real_name": getattr(getattr(creator, "userprofile", None), "real_name", None)},
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
            contest=contest, user=user, defaults={"role": ContestPrepRole.ORGANIZER})
        if not created:
            return self.error("The user is already a member")
        return self.success(ContestPrepMemberSerializer(member).data)

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
        users = (User.objects.filter(Q(username__icontains=keyword) | Q(userprofile__real_name__icontains=keyword),
                                     is_disabled=False)
                 .exclude(id=contest.created_by_id).select_related("userprofile").order_by("username")[:10])
        return self.success([{"id": user.id, "username": user.username,
                              "real_name": getattr(getattr(user, "userprofile", None), "real_name", None)}
                             for user in users])


class ContestPrepProblemAPI(ProblemBase):
    @login_required
    def get(self, request):
        contest = load_prep_contest(request, request.GET.get("contest_id"))
        problem_id = request.GET.get("id")
        if problem_id:
            return self.success(ProblemAdminSerializer(get_contest_problem(contest, problem_id)).data)
        return self.success(problem_list(contest))

    @validate_serializer(CreatePrepContestProblemSerializer)
    @login_required
    def post(self, request):
        data = request.data
        contest = load_prep_contest(request, data.pop("contest_id"))
        if data["rule_type"] != contest.rule_type:
            return self.error("Invalid rule type")
        # New problems join the candidates; picking them is a separate step.
        data["visible"] = False
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
        contest = load_prep_contest(request, data.pop("contest_id"))
        if data["rule_type"] != contest.rule_type:
            return self.error("Invalid rule type")
        problem = get_contest_problem(contest, data.pop("id"))
        # Selection belongs to the selection tab; an editor tab may hold a stale value.
        data["visible"] = problem.visible
        error_info = self.common_checks(request)
        if error_info:
            return self.error(error_info)
        update_contest_problem(problem, data)
        return self.success()

    @login_required
    def delete(self, request):
        contest = load_prep_contest(request, request.GET.get("contest_id"))
        problem = get_contest_problem(contest, request.GET.get("id"))
        # Verification runs are deleted with the problem; they never reached
        # any rank, mark or counter.
        problem.delete()
        # Close the gap so the selected problems stay A, B, C...
        keep_selected_first(contest)
        clear_rank_cache(contest)
        return self.success()


class ContestPrepProblemSelectAPI(APIView):
    """Pick a candidate for the contest, or put it back among the candidates."""

    @validate_serializer(ContestPrepProblemSelectSerializer)
    @login_required
    def put(self, request):
        data = request.data
        contest = load_prep_contest(request, data["contest_id"])
        with transaction.atomic():
            # Lock every problem so concurrent picks cannot overshoot the count.
            problems = list(Problem.objects.select_for_update().filter(contest=contest))
            problem = next((item for item in problems if item.id == data["id"]), None)
            if problem is None:
                return self.error("Problem does not exist")
            if data["selected"] and not problem.visible:
                if not problem.difficulty or not problem.tags.exists():
                    return self.error("Fill in the difficulty and knowledge points before selecting this problem")
                limit = contest.prep_problem_count
                if limit and sum(item.visible for item in problems) >= limit:
                    return self.error(f"This contest takes {limit} problems; unselect one first")
            problem.visible = data["selected"]
            problem.save(update_fields=["visible"])
            keep_selected_first(contest)
        clear_rank_cache(contest)
        return self.success(problem_list(contest))


class ContestPrepProblemMetaAPI(APIView):
    """Difficulty and knowledge points, filled in while picking the problem set."""

    @validate_serializer(ContestPrepProblemMetaSerializer)
    @login_required
    def put(self, request):
        data = request.data
        contest = load_prep_contest(request, data["contest_id"])
        problem = get_contest_problem(contest, data["id"])
        names = list(dict.fromkeys(name for name in data["tags"] if name))
        if not names:
            return self.error("Add at least one knowledge point")
        problem.difficulty = data["difficulty"]
        problem.save(update_fields=["difficulty"])
        problem.tags.set([ProblemTag.objects.get_or_create(name=name)[0] for name in names])
        return self.success(ProblemAdminSerializer(problem).data)


class ContestPrepProblemCountAPI(APIView):
    @validate_serializer(ContestPrepProblemCountSerializer)
    @login_required
    def put(self, request):
        data = request.data
        contest = load_prep_contest(request, data["contest_id"], MANAGE)
        count = data["problem_count"]
        selected = Problem.objects.filter(contest=contest, visible=True).count()
        if count is not None and count < selected:
            return self.error(f"{selected} problems are selected; unselect some before lowering the count")
        contest.prep_problem_count = count
        contest.save(update_fields=["prep_problem_count", "last_update_time"])
        return self.success({"prep_problem_count": count})


class ContestPrepProblemOrderAPI(APIView):
    @validate_serializer(ContestPrepProblemOrderSerializer)
    @login_required
    def put(self, request):
        contest = load_prep_contest(request, request.data["contest_id"])
        # A drag never moves a problem across the selected / candidate boundary.
        keep_selected_first(contest, request.data["problem_ids"])
        clear_rank_cache(contest)
        return self.success(problem_list(contest))


class ContestPrepTestCaseAPI(TestCaseAPI):
    @login_required
    def get(self, request):
        contest = load_prep_contest(request, request.GET.get("contest_id"))
        return self.test_case_response(get_contest_problem(contest, request.GET.get("problem_id")))

    @login_required
    def post(self, request):
        load_prep_contest(request, request.POST.get("contest_id"))
        return TestCaseAPI.post(self, request)


class ContestPrepCompileSPJAPI(CompileSPJAPI):
    @login_required
    def post(self, request):
        load_prep_contest(request, request.data.get("contest_id"))
        return CompileSPJAPI.post(self, request)


class ContestPrepImportProblemAPI(ImportProblemAPI):
    @login_required
    def post(self, request):
        contest = load_prep_contest(request, request.POST.get("contest_id"))
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


class ContestPrepFeedbackAPI(APIView):
    @login_required
    def get(self, request):
        contest = load_prep_contest(request, request.GET.get("contest_id"))
        feedback = ContestProblemFeedback.objects.filter(contest=contest).select_related("user", "problem")
        problem_id = request.GET.get("problem_id")
        if problem_id:
            feedback = feedback.filter(problem=get_contest_problem(contest, problem_id))
        return self.success(ContestProblemFeedbackSerializer(feedback, many=True).data)

    @validate_serializer(CreateContestProblemFeedbackSerializer)
    @login_required
    def post(self, request):
        data = request.data
        contest = load_prep_contest(request, data["contest_id"])
        problem = get_contest_problem(contest, data["problem_id"])
        feedback = ContestProblemFeedback.objects.create(contest=contest, problem=problem, user=request.user,
                                                         content=data["content"].strip())
        return self.success(ContestProblemFeedbackSerializer(feedback).data)

    @validate_serializer(EditContestProblemFeedbackSerializer)
    @login_required
    def put(self, request):
        data = request.data
        contest = load_prep_contest(request, data["contest_id"])
        updated = ContestProblemFeedback.objects.filter(contest=contest, id=data["id"]).update(
            resolved=data["resolved"])
        if not updated:
            return self.error("Feedback does not exist")
        return self.success()

    @login_required
    def delete(self, request):
        contest = load_prep_contest(request, request.GET.get("contest_id"))
        feedback = ContestProblemFeedback.objects.filter(contest=contest, id=request.GET.get("id")).first()
        if feedback is None:
            return self.error("Feedback does not exist")
        if feedback.user_id != request.user.id and not contest.prep_can_manage(request.user):
            return self.error("Only the author can delete this feedback")
        feedback.delete()
        return self.success()


class ContestPrepRankAPI(APIView):
    @login_required
    def get(self, request):
        contest = load_prep_contest(request, request.GET.get("contest_id"))
        return self.success(review_rank(contest))


class ContestPrepPublicProblemAPI(APIView):
    """Copy a released library problem into the contest as an unselected candidate."""

    @validate_serializer(ContestPrepPublicProblemSerializer)
    @login_required
    def post(self, request):
        contest = load_prep_contest(request, request.data["contest_id"])
        try:
            problem = Problem.objects.get(id=request.data["problem_id"], contest_id__isnull=True, visible=True)
        except Problem.DoesNotExist:
            return self.error("Problem does not exist")
        if problem.rule_type != contest.rule_type:
            return self.error(f"This is a {problem.rule_type} problem, but the contest uses {contest.rule_type}")
        tags = list(problem.tags.all())
        problem.pk = None
        problem.contest = contest
        problem._id = next_contest_display_id(contest)
        problem.created_by = request.user
        problem.is_public = True
        problem.visible = False
        problem.publish_after_contest = False
        problem.post_contest_display_id = None
        problem.submission_number = problem.accepted_number = 0
        problem.statistic_info = {}
        problem.save()
        problem.tags.set(tags)
        return self.success(ProblemAdminSerializer(problem).data)


def invite_token_hash(token):
    return hashlib.sha256(token.encode()).hexdigest()


def open_invites(contest):
    return ContestPrepInvite.objects.filter(contest=contest, used_time__isnull=True, revoked_time__isnull=True,
                                            expire_time__gt=now())


def invite_status(invite, at):
    if invite.used_time:
        return "used"
    if invite.revoked_time:
        return "revoked"
    return "expired" if invite.expire_time <= at else "active"


class ContestPrepInviteAPI(APIView):
    """One-time invite links; the raw token is shown once and never stored."""

    @login_required
    def get(self, request):
        contest = load_prep_contest(request, request.GET.get("contest_id"), MANAGE)
        counts = open_invites(contest).values("role").annotate(count=Count("id")).values_list("role", "count")
        at = now()
        invites = ContestPrepInvite.objects.filter(contest=contest).select_related("created_by", "used_by")[:100]
        return self.success({
            "open": dict(counts),
            "invites": [{
                "id": invite.id,
                "role": invite.role,
                "status": invite_status(invite, at),
                "created_by": invite.created_by.username,
                "create_time": datetime2str(invite.create_time),
                "expire_time": datetime2str(invite.expire_time),
                "used_by": invite.used_by.username if invite.used_by else None,
                "used_time": datetime2str(invite.used_time) if invite.used_time else None,
                "revoked_time": datetime2str(invite.revoked_time) if invite.revoked_time else None,
            } for invite in invites],
        })

    @validate_serializer(CreateContestPrepInviteSerializer)
    @login_required
    def post(self, request):
        contest = load_prep_contest(request, request.data["contest_id"], MANAGE)
        if open_invites(contest).count() >= MAX_OPEN_INVITES:
            return self.error("Too many unused invite links; revoke them first")
        # The link itself is the credential, so it carries 256 random bits.
        token = secrets.token_urlsafe(32)
        invite = ContestPrepInvite.objects.create(
            contest=contest, role=ContestPrepRole.ORGANIZER, token_hash=invite_token_hash(token),
            created_by=request.user, expire_time=now() + timedelta(days=PREP_INVITE_DAYS))
        return self.success({"token": token, "role": invite.role, "expire_time": datetime2str(invite.expire_time)})

    @login_required
    def delete(self, request):
        contest = load_prep_contest(request, request.GET.get("contest_id"), MANAGE)
        invites = open_invites(contest)
        invite_id = request.GET.get("id")
        if invite_id:
            if not invite_id.isdigit():
                return self.error("Invalid parameter, id must be an integer")
            invites = invites.filter(id=int(invite_id))
        # Mark rather than delete, so redeemed and revoked links stay auditable.
        revoked = invites.update(revoked_time=now())
        return self.success({"revoked": revoked})


class ContestPrepInviteAcceptAPI(APIView):
    @validate_serializer(AcceptContestPrepInviteSerializer)
    @login_required
    def post(self, request):
        user = request.user
        failures_key = f"{CacheKey.prep_invite_failures}:{user.id}"
        if (cache.get(failures_key) or 0) >= INVITE_FAILURE_LIMIT:
            return self.error("Too many invalid invite links, try again later")
        with transaction.atomic():
            # The row lock keeps the link single-use under concurrent requests.
            invite = (ContestPrepInvite.objects.select_for_update().select_related("contest")
                      .filter(token_hash=invite_token_hash(request.data["token"])).first())
            contest = invite.contest if invite else None
            if invite is None or invite.used_time is not None or invite.revoked_time is not None or \
                    invite.expire_time <= now() or not contest.visible or not contest.is_preparation:
                cache.add(failures_key, 0, INVITE_FAILURE_WINDOW)
                cache.incr(failures_key)
                return self.error("This invite link is invalid or has expired")
            # Members keep their role and leave the link unused for its intended person.
            if contest.prep_role(user) is not None:
                return self.error("You are already a member of this contest")
            _, created = ContestPrepMember.objects.get_or_create(contest=contest, user=user,
                                                                 defaults={"role": invite.role})
            if not created:
                return self.error("You are already a member of this contest")
            invite.used_by = user
            invite.used_time = now()
            invite.save(update_fields=["used_by", "used_time"])
        return self.success({"contest_id": contest.id, "title": contest.title, "role": invite.role})
