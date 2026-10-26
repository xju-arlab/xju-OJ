import random
from django.db.models import Q, Count
from utils.api import APIView, validate_serializer
from account.decorators import check_contest_permission, login_required
from account.models import User
from submission.models import JudgeStatus, Submission
from ..contest_authoring import order_contest_problems
from ..models import ProblemFavorite, ProblemTag, Problem, ProblemRuleType
from ..serializers import (ProblemFavoriteSerializer, ProblemSerializer, ProfileProblemSerializer,
                           TagSerializer, ProblemSafeSerializer)
from contest.models import ContestRuleType, ContestStatus
from ..publication import publish_due_contest_problems


class ProblemTagAPI(APIView):
    def get(self, request):
        qs = ProblemTag.objects
        keyword = request.GET.get("keyword")
        if keyword:
            qs = ProblemTag.objects.filter(name__icontains=keyword)
        # Problems of private preparation contests must not reveal their tags.
        tags = qs.annotate(problem_count=Count(
            "problem", filter=Q(problem__contest__prep_state__isnull=True))).filter(problem_count__gt=0)
        return self.success(TagSerializer(tags, many=True).data)


class PickOneAPI(APIView):
    def get(self, request):
        problems = Problem.objects.filter(contest_id__isnull=True, visible=True)
        count = problems.count()
        if count == 0:
            return self.error("No problem to pick")
        return self.success(problems[random.randint(0, count - 1)]._id)


class ProblemAPI(APIView):
    @staticmethod
    def _add_problem_status(request, queryset_values):
        if request.user.is_authenticated:
            profile = request.user.userprofile
            acm_problems_status = profile.acm_problems_status.get("problems", {})
            oi_problems_status = profile.oi_problems_status.get("problems", {})
            # paginate data
            results = queryset_values.get("results")
            if results is not None:
                problems = results
            else:
                problems = [queryset_values, ]
            for problem in problems:
                if problem["rule_type"] == ProblemRuleType.ACM:
                    problem["my_status"] = acm_problems_status.get(str(problem["id"]), {}).get("status")
                else:
                    problem["my_status"] = oi_problems_status.get(str(problem["id"]), {}).get("status")

    def get(self, request):
        publish_due_contest_problems()
        # 问题详情页
        problem_id = request.GET.get("problem_id")
        if problem_id:
            try:
                problem = Problem.objects.select_related("created_by") \
                    .get(_id=problem_id, contest_id__isnull=True, visible=True)
                problem_data = ProblemSerializer(problem).data
                self._add_problem_status(request, problem_data)
                problem_data["favorited"] = request.user.is_authenticated and \
                    ProblemFavorite.objects.filter(user=request.user, problem=problem).exists()
                return self.success(problem_data)
            except Problem.DoesNotExist:
                return self.error("Problem does not exist")

        limit = request.GET.get("limit")
        if not limit:
            return self.error("Limit is needed")

        problems = Problem.objects.select_related("created_by").filter(contest_id__isnull=True, visible=True)
        # 按照标签筛选
        tag_text = request.GET.get("tag")
        if tag_text:
            problems = problems.filter(tags__name=tag_text)

        # 搜索的情况
        keyword = request.GET.get("keyword", "").strip()
        if keyword:
            problems = problems.filter(Q(title__icontains=keyword) | Q(_id__icontains=keyword))

        # 难度筛选
        difficulty = request.GET.get("difficulty")
        if difficulty:
            problems = problems.filter(difficulty=difficulty)
        # 根据profile 为做过的题目添加标记
        data = self.paginate_data(request, problems, ProblemSerializer)
        self._add_problem_status(request, data)
        return self.success(data)


class ContestProblemAPI(APIView):
    def _add_problem_status(self, request, queryset_values):
        if request.user.is_authenticated:
            profile = request.user.userprofile
            if self.contest.rule_type == ContestRuleType.ACM:
                problems_status = profile.acm_problems_status.get("contest_problems", {})
            else:
                problems_status = profile.oi_problems_status.get("contest_problems", {})
            for problem in queryset_values:
                problem["my_status"] = problems_status.get(str(problem["id"]), {}).get("status")

    def _add_prep_facts(self, request, problems):
        """Preparation contests keep no statistics; derive them from verification runs."""
        runs = Submission.objects.filter(contest=self.contest).exclude(
            result__in=(JudgeStatus.PENDING, JudgeStatus.JUDGING))
        # While a review round runs, count it like a contest; otherwise every run counts.
        if self.contest.review_running():
            start, end = self.contest.review_window()
            runs = runs.filter(create_time__gte=start, create_time__lt=end)
        counts = {item["problem_id"]: item for item in runs.values("problem_id").annotate(
            total=Count("id"), accepted=Count("id", filter=Q(result=JudgeStatus.ACCEPTED)))}
        my_status = {}
        for problem_id, result in runs.filter(user_id=request.user.id).order_by("create_time", "id") \
                .values_list("problem_id", "result"):
            if my_status.get(problem_id) != JudgeStatus.ACCEPTED:
                my_status[problem_id] = result
        for problem in problems:
            facts = counts.get(problem["id"], {})
            problem["submission_number"] = facts.get("total", 0)
            problem["accepted_number"] = facts.get("accepted", 0)
            problem["my_status"] = my_status.get(problem["id"])

    @check_contest_permission(check_type="problem_list")
    def get(self, request):
        problem_id = request.GET.get("problem_id")
        if problem_id:
            # Preparation members already passed check_contest_permission.
            if not request.user.is_contest_admin(self.contest) and not self.contest.is_preparation:
                if self.contest.status == ContestStatus.CONTEST_NOT_START:
                    return self.error("Contest has not started yet.")
                # Before the deadline a non-registered user cannot open the
                # problem detail (the password gate is part of registration).
                # Once the contest ends it becomes public practice material.
                if self.contest.status != ContestStatus.CONTEST_ENDED and \
                        not self.contest.is_registered(request.user):
                    return self.error("Please register for the contest first")
            problems = Problem.objects.select_related("created_by").filter(contest=self.contest)
            # The preparation team opens every candidate; contestants only the contest's problems.
            if self.contest.prep_role(request.user) is None:
                problems = problems.filter(visible=True)
            try:
                problem = problems.get(_id=problem_id)
            except Problem.DoesNotExist:
                return self.error("Problem does not exist.")
            if self.contest.problem_details_permission(request.user):
                problem_data = ProblemSerializer(problem).data
                self._add_problem_status(request, [problem_data, ])
            else:
                problem_data = ProblemSafeSerializer(problem).data
            if self.contest.is_preparation:
                self._add_prep_facts(request, [problem_data])
            return self.success(problem_data)

        contest_problems = order_contest_problems(
            Problem.objects.select_related("created_by").filter(contest=self.contest, visible=True))
        if self.contest.problem_details_permission(request.user):
            data = ProblemSerializer(contest_problems, many=True).data
            self._add_problem_status(request, data)
        else:
            data = ProblemSafeSerializer(contest_problems, many=True).data
        if self.contest.is_preparation:
            self._add_prep_facts(request, data)
        return self.success(data)


class ProblemFavoriteAPI(APIView):
    @validate_serializer(ProblemFavoriteSerializer)
    @login_required
    def post(self, request):
        try:
            problem = Problem.objects.get(id=request.data["problem_id"], contest_id__isnull=True, visible=True)
        except Problem.DoesNotExist:
            return self.error("Problem does not exist")
        ProblemFavorite.objects.get_or_create(user=request.user, problem=problem)
        return self.success({"favorited": True})

    @login_required
    def delete(self, request):
        problem_id = request.GET.get("problem_id")
        if not problem_id or not problem_id.isdigit():
            return self.error("Invalid parameter, problem_id is required")
        ProblemFavorite.objects.filter(user=request.user, problem_id=int(problem_id)).delete()
        return self.success({"favorited": False})


class ProfileProblemListAPI(APIView):
    """Public library problems a user solved, uploaded or (own profile only) favorited."""
    LIST_TYPES = ("solved", "uploaded", "favorites")

    @login_required
    def get(self, request):
        list_type = request.GET.get("type", "solved")
        if list_type not in self.LIST_TYPES:
            return self.error("Invalid type")
        username = request.GET.get("username")
        if username:
            try:
                user = User.objects.select_related("userprofile").get(username=username, is_disabled=False)
            except User.DoesNotExist:
                return self.error("User does not exist")
        else:
            user = request.user
        if list_type == "favorites" and user.id != request.user.id:
            return self.error("Favorites are private")

        problems = Problem.objects.filter(contest_id__isnull=True, visible=True)
        if list_type == "uploaded":
            problems = problems.filter(created_by=user).order_by("-create_time")
        elif list_type == "favorites":
            problems = problems.filter(problemfavorite__user=user).order_by("-problemfavorite__create_time")
        else:
            profile = user.userprofile
            solved_ids = [
                int(key)
                for statuses in (profile.acm_problems_status, profile.oi_problems_status)
                for key, mark in statuses.get("problems", {}).items()
                if mark.get("status") == JudgeStatus.ACCEPTED and str(key).isdigit()
            ]
            problems = problems.filter(id__in=solved_ids).order_by("id")
        data = self.paginate_data(request, problems.prefetch_related("tags"), ProfileProblemSerializer)
        return self.success(data)
