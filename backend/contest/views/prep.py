"""Contest preparation workspace API.

These views live outside /api/admin/ because organizers may be regular users.
Every view resolves its contest through load_prep_contest, which hides the
contest from everyone outside the team (the creator, organizers and super
admins). Every uploaded problem belongs to the contest. The team plans the
problem set by difficulty and organizer, the workspace is always open for
setting problems, and review rounds run beside it as 5-hour mock contests.
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
from problem.models import Problem
from problem.serializers import (CreatePrepContestProblemSerializer, EditPrepContestProblemSerializer,
                                 ProblemAdminSerializer)
from problem.views.admin import CompileSPJAPI, ImportProblemAPI, ProblemBase, TestCaseAPI
from utils.api import APIError, APIView, validate_serializer
from utils.constants import CacheKey, ContestPrepRole, PREP_INVITE_DAYS
from utils.shortcuts import datetime2str
from ..models import Contest, ContestPrepInvite, ContestPrepMember, ContestPrepPlanItem, ContestProblemFeedback
from ..prep_publish import publish_prep_contest
from ..prep_rank import review_rank
from ..serializers import (AcceptContestPrepInviteSerializer, ContestPrepMemberSerializer, ContestPrepPlanItemSerializer,
                           ContestPrepProblemCountSerializer, ContestPrepProblemOrderSerializer,
                           ContestPrepPublicProblemSerializer, ContestPrepPublishSerializer,
                           ContestPrepReviewSerializer, ContestProblemFeedbackSerializer,
                           CreateContestPrepInviteSerializer, CreateContestPrepMemberSerializer,
                           CreateContestPrepPlanItemSerializer, CreateContestProblemFeedbackSerializer,
                           EditContestPrepPlanItemSerializer, EditContestProblemFeedbackSerializer)

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


def clean_tags(tags):
    return list(dict.fromkeys(name.strip() for name in tags if name and name.strip()))


def problem_list(contest):
    problems = list(order_contest_problems(Problem.objects.filter(contest=contest)
                                           .select_related("created_by__userprofile").prefetch_related("tags")))
    data = ProblemAdminSerializer(problems, many=True).data
    # The team knows each other by real name.
    for problem, item in zip(problems, data):
        profile = getattr(problem.created_by, "userprofile", None)
        item["created_by"]["real_name"] = profile.real_name if profile else None
    return with_feedback_counts(contest, data)


def close_label_gaps(contest):
    """Relabel A, B, C... in the current order, e.g. after a deletion."""
    reorder_contest_problems(contest, list(order_contest_problems(Problem.objects.filter(contest=contest))
                                           .values_list("id", flat=True)))


class ContestPrepReviewAPI(APIView):
    """Start a review round: a fresh 5-hour mock contest of the contest's problems."""

    @validate_serializer(ContestPrepReviewSerializer)
    @login_required
    def post(self, request):
        data = request.serializer.validated_data
        contest = load_prep_contest(request, data["contest_id"], MANAGE)
        if not Problem.objects.filter(contest=contest).exists():
            return self.error("Upload the contest problems before starting a review")
        # The clock and the review board start over with every round.
        contest.review_started_at = now()
        contest.review_ended_at = None
        if "password" in data:
            contest.password = data["password"] or None
        contest.save(update_fields=["password", "review_started_at", "review_ended_at", "last_update_time"])
        clear_rank_cache(contest)
        return self.success({"review_started_at": datetime2str(contest.review_started_at),
                             "password": contest.password})

    @login_required
    def delete(self, request):
        """End the running review round early; its board keeps the runs made so far."""
        contest = load_prep_contest(request, request.GET.get("contest_id"), MANAGE)
        if not contest.review_running():
            return self.error("No review round is running")
        contest.review_ended_at = now()
        contest.save(update_fields=["review_ended_at", "last_update_time"])
        clear_rank_cache(contest)
        return self.success({"review_ended_at": datetime2str(contest.review_ended_at)})


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
        # Every problem of a preparation contest belongs to the contest.
        data["visible"] = True
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
        data["visible"] = True
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
        close_label_gaps(contest)
        clear_rank_cache(contest)
        return self.success()


def plan_items(contest):
    return ContestPrepPlanItem.objects.filter(contest=contest).select_related("assignee__userprofile")


def team_user(contest, user_id):
    """The creator or an organizer; plan items are only assigned within the team."""
    if user_id is None:
        return None
    if user_id == contest.created_by_id or ContestPrepMember.objects.filter(contest=contest, user_id=user_id).exists():
        return User.objects.get(id=user_id)
    raise APIError("Only the creator or an organizer can take this problem")


def plan_progress(contest):
    """How many problems each team member is planned to write and has uploaded.

    Plan items are not tied to particular uploads: an organizer is done once
    the number of problems they uploaded matches the items assigned to them.
    """
    assigned = dict(ContestPrepPlanItem.objects.filter(contest=contest, assignee__isnull=False)
                    .values("assignee_id").annotate(n=Count("id")).values_list("assignee_id", "n"))
    uploaded = dict(Problem.objects.filter(contest=contest).values("created_by_id")
                    .annotate(n=Count("id")).values_list("created_by_id", "n"))
    members = ContestPrepMember.objects.filter(contest=contest).order_by("create_time", "id")
    team = [contest.created_by_id] + list(members.values_list("user_id", flat=True))
    users = {user.id: user for user in User.objects.filter(id__in=set(team) | set(uploaded))
             .select_related("userprofile")}
    order = team + sorted(set(uploaded) - set(team))
    return [{"id": user_id, "username": users[user_id].username,
             "real_name": getattr(getattr(users[user_id], "userprofile", None), "real_name", None),
             "member": user_id in team, "assigned": assigned.get(user_id, 0), "uploaded": uploaded.get(user_id, 0)}
            for user_id in order if user_id in users]


class ContestPrepPlanAPI(APIView):
    """The problem plan: planned problems by difficulty, each with its organizer and knowledge points.

    Every member may add, edit and remove items.
    """

    @login_required
    def get(self, request):
        contest = load_prep_contest(request, request.GET.get("contest_id"))
        return self.success({"items": ContestPrepPlanItemSerializer(plan_items(contest), many=True).data,
                             "progress": plan_progress(contest)})

    @validate_serializer(CreateContestPrepPlanItemSerializer)
    @login_required
    def post(self, request):
        data = request.data
        contest = load_prep_contest(request, data["contest_id"])
        with transaction.atomic():
            # Lock the contest so concurrent additions cannot overshoot the count.
            contest = Contest.objects.select_for_update().get(pk=contest.pk)
            limit = contest.prep_problem_count
            if limit and ContestPrepPlanItem.objects.filter(contest=contest).count() >= limit:
                return self.error(f"This contest takes {limit} problems and the plan is full")
            item = ContestPrepPlanItem.objects.create(
                contest=contest, difficulty=data["difficulty"], assignee=team_user(contest, data.get("assignee_id")),
                tags=clean_tags(data.get("tags", [])))
        return self.success(ContestPrepPlanItemSerializer(plan_items(contest).get(id=item.id)).data)

    @validate_serializer(EditContestPrepPlanItemSerializer)
    @login_required
    def put(self, request):
        data = request.data
        contest = load_prep_contest(request, data["contest_id"])
        item = ContestPrepPlanItem.objects.filter(contest=contest, id=data["id"]).first()
        if item is None:
            return self.error("Plan item does not exist")
        if "difficulty" in data:
            item.difficulty = data["difficulty"]
        if "assignee_id" in data:
            item.assignee = team_user(contest, data["assignee_id"])
        if "tags" in data:
            item.tags = clean_tags(data["tags"])
        item.save()
        return self.success(ContestPrepPlanItemSerializer(plan_items(contest).get(id=item.id)).data)

    @login_required
    def delete(self, request):
        contest = load_prep_contest(request, request.GET.get("contest_id"))
        deleted, _ = ContestPrepPlanItem.objects.filter(contest=contest, id=request.GET.get("id") or 0).delete()
        if not deleted:
            return self.error("Plan item does not exist")
        return self.success()


class ContestPrepProblemCountAPI(APIView):
    @validate_serializer(ContestPrepProblemCountSerializer)
    @login_required
    def put(self, request):
        data = request.data
        contest = load_prep_contest(request, data["contest_id"], MANAGE)
        count = data["problem_count"]
        planned = ContestPrepPlanItem.objects.filter(contest=contest).count()
        if count is not None and count < planned:
            return self.error(f"{planned} problems are planned; remove some before lowering the count")
        contest.prep_problem_count = count
        contest.save(update_fields=["prep_problem_count", "last_update_time"])
        return self.success({"prep_problem_count": count})


class ContestPrepProblemOrderAPI(APIView):
    @validate_serializer(ContestPrepProblemOrderSerializer)
    @login_required
    def put(self, request):
        contest = load_prep_contest(request, request.data["contest_id"])
        reorder_contest_problems(contest, request.data["problem_ids"])
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
        feedback = ContestProblemFeedback.objects.filter(contest=contest).select_related("user__userprofile", "problem")
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
    """Copy a released library problem into the contest."""

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
        problem.visible = True
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
