from utils.constants import ContestRuleType  # noqa
from django.db import models
from django.utils.timezone import now
from utils.models import JSONField

from utils.constants import ContestPrepRole, ContestStatus, ContestType
from account.models import User
from utils.models import RichTextField


class ContestQuerySet(models.QuerySet):
    def public(self):
        """Contests anyone may discover: not soft-deleted and not a private preparation workspace."""
        return self.filter(visible=True, prep_state__isnull=True)


class Contest(models.Model):
    title = models.TextField()
    description = RichTextField()
    # show real time rank or cached rank
    real_time_rank = models.BooleanField()
    password = models.TextField(null=True)
    # enum of ContestRuleType
    rule_type = models.TextField()
    start_time = models.DateTimeField()
    end_time = models.DateTimeField()
    create_time = models.DateTimeField(auto_now_add=True)
    last_update_time = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    # 是否可见 false的话相当于删除
    visible = models.BooleanField(default=True)
    allowed_ip_ranges = JSONField(default=list)
    # enum of ContestPrepState; null for a normal contest. A preparation
    # contest is a private workspace that is only ever published as a copy.
    prep_state = models.TextField(null=True)
    published_from = models.ForeignKey("self", null=True, blank=True, on_delete=models.SET_NULL,
                                       related_name="published_contests")
    # When the latest review round started; the review leaderboard counts
    # submissions from this moment, like a contest start time.
    review_started_at = models.DateTimeField(null=True, blank=True)
    # Set when the creator ends that round; a round has no time limit, so it
    # runs until then.
    review_ended_at = models.DateTimeField(null=True, blank=True)
    # How many problems the creator plans for the contest. The plan holds at
    # most this many items and publishing needs exactly this many problems.
    # Null means not decided yet.
    prep_problem_count = models.PositiveIntegerField(null=True, blank=True)
    # ACM only. From this moment everyone but contest admins sees the board as
    # it stood, with later attempts pending, until an admin unfreezes it.
    rank_freeze_time = models.DateTimeField(null=True, blank=True)
    rank_unfrozen = models.BooleanField(default=False)

    objects = ContestQuerySet.as_manager()

    @property
    def status(self):
        if self.start_time > now():
            # 没有开始 返回1
            return ContestStatus.CONTEST_NOT_START
        elif self.end_time < now():
            # 已经结束 返回-1
            return ContestStatus.CONTEST_ENDED
        else:
            # 正在进行 返回0
            return ContestStatus.CONTEST_UNDERWAY

    @property
    def contest_type(self):
        if self.password:
            return ContestType.PASSWORD_PROTECTED_CONTEST
        return ContestType.PUBLIC_CONTEST

    @property
    def is_preparation(self):
        return self.prep_state is not None

    def prep_role(self, user):
        """Return the user's ContestPrepRole in a preparation contest, or None.

        Super admins act as the creator. Normal contests have no prep roles.
        """
        if not self.is_preparation or not user or not user.is_authenticated:
            return None
        cache = self.__dict__.setdefault("_prep_role_cache", {})
        if user.id not in cache:
            if self.created_by_id == user.id or user.is_super_admin():
                cache[user.id] = ContestPrepRole.CREATOR
            else:
                member = ContestPrepMember.objects.filter(contest=self, user=user).first()
                cache[user.id] = member.role if member else None
        return cache[user.id]

    def review_window(self):
        """(start, end) of the latest review round, or None if there never was one.

        A round has no time limit, so end stays None until the creator ends it.
        """
        if not self.review_started_at:
            return None
        return self.review_started_at, self.review_ended_at

    def review_running(self):
        window = self.review_window()
        return window is not None and window[1] is None

    @property
    def is_team_contest(self):
        """Contested by generated team accounts only; open to all once it ends."""
        if "_is_team_contest" not in self.__dict__:
            self.__dict__["_is_team_contest"] = self.teams.exists()
        return self.__dict__["_is_team_contest"]

    def rank_frozen(self, user=None):
        """Whether this viewer gets the frozen ACM board; contest admins always see it live."""
        if self.rule_type != ContestRuleType.ACM or not self.rank_freeze_time or self.rank_unfrozen:
            return False
        if now() < self.rank_freeze_time:
            return False
        return not (user and user.is_authenticated and user.is_contest_admin(self))

    def prep_can_manage(self, user):
        return self.prep_role(user) == ContestPrepRole.CREATOR

    # 是否有权查看problem 的一些统计信息 诸如submission_number, accepted_number 等
    def problem_details_permission(self, user):
        return self.rule_type == ContestRuleType.ACM or \
               self.status == ContestStatus.CONTEST_ENDED or \
               user.is_authenticated and user.is_contest_admin(self) or \
               self.real_time_rank or \
               self.prep_role(user) is not None

    class Meta:
        db_table = "contest"
        ordering = ("-start_time",)

    def is_registered(self, user):
        if not user or not user.is_authenticated:
            return False
        if self.is_preparation:
            return self.prep_role(user) is not None
        if user.is_contest_admin(self):
            return True
        return ContestParticipation.objects.filter(contest=self, user=user).exists()


class ContestProblemFeedback(models.Model):
    """A review note on a problem of a preparation contest, read by the whole team."""
    contest = models.ForeignKey(Contest, on_delete=models.CASCADE, related_name="problem_feedback")
    problem = models.ForeignKey("problem.Problem", on_delete=models.CASCADE, related_name="feedback")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    content = models.TextField()
    resolved = models.BooleanField(default=False)
    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "contest_problem_feedback"
        ordering = ("-create_time", "-id")


class ContestPrepPlanItem(models.Model):
    """A planned problem of a preparation contest.

    The team plans the contest by difficulty: each item names the organizer
    who writes it and its knowledge points. Items are not tied to particular
    uploads; an organizer's part is done when the number of problems they
    uploaded matches the items assigned to them.
    """
    contest = models.ForeignKey(Contest, on_delete=models.CASCADE, related_name="prep_plan")
    # enum of utils.constants.Difficulty
    difficulty = models.TextField()
    assignee = models.ForeignKey(User, null=True, blank=True, on_delete=models.SET_NULL, related_name="+")
    tags = JSONField(default=list)
    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "contest_prep_plan_item"
        ordering = ("create_time", "id")


class ContestPrepMember(models.Model):
    """An organizer of a preparation contest; the creator is Contest.created_by."""
    contest = models.ForeignKey(Contest, on_delete=models.CASCADE, related_name="prep_members")
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    # ContestPrepRole.ORGANIZER
    role = models.TextField()
    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "contest_prep_member"
        unique_together = (("contest", "user"),)
        ordering = ("create_time", "id")


class ContestPrepInvite(models.Model):
    """A one-time link that makes whoever redeems it an organizer.

    Only the SHA-256 digest of the random token is stored, so neither the
    database nor a backup can be turned back into a working link.
    """
    contest = models.ForeignKey(Contest, on_delete=models.CASCADE, related_name="prep_invites")
    # ContestPrepRole.ORGANIZER
    role = models.TextField()
    token_hash = models.CharField(max_length=64, unique=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name="+")
    create_time = models.DateTimeField(auto_now_add=True)
    expire_time = models.DateTimeField()
    used_by = models.ForeignKey(User, null=True, on_delete=models.SET_NULL, related_name="+")
    used_time = models.DateTimeField(null=True)
    revoked_time = models.DateTimeField(null=True)

    class Meta:
        db_table = "contest_prep_invite"
        ordering = ("-create_time", "-id")


class ContestTeam(models.Model):
    """A team account generated for one contest from a roster.

    The account logs in with its password even where only SSO login is
    otherwise allowed, and the board shows the team name.
    """
    contest = models.ForeignKey(Contest, on_delete=models.CASCADE, related_name="teams")
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="contest_team")
    name = models.TextField()
    members = JSONField(default=list)
    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "contest_team"
        ordering = ("id",)


class ContestParticipation(models.Model):
    contest = models.ForeignKey(Contest, on_delete=models.CASCADE)
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    join_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "contest_participation"
        unique_together = (("contest", "user"),)
        ordering = ("join_time",)


class AbstractContestRank(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    contest = models.ForeignKey(Contest, on_delete=models.CASCADE)
    submission_number = models.IntegerField(default=0)

    class Meta:
        abstract = True


class ACMContestRank(AbstractContestRank):
    accepted_number = models.IntegerField(default=0)
    # total_time is only for ACM contest, total_time =  ac time + none-ac times * 20 * 60
    total_time = models.IntegerField(default=0)
    # {"23": {"is_ac": True, "ac_time": 8999, "error_number": 2, "is_first_ac": True}}
    # key is problem id
    submission_info = JSONField(default=dict)

    class Meta:
        db_table = "acm_contest_rank"
        unique_together = (("user", "contest"),)


class OIContestRank(AbstractContestRank):
    total_score = models.IntegerField(default=0)
    # {"23": 333}
    # key is problem id, value is current score
    submission_info = JSONField(default=dict)

    class Meta:
        db_table = "oi_contest_rank"
        unique_together = (("user", "contest"),)


class ContestAnnouncement(models.Model):
    contest = models.ForeignKey(Contest, on_delete=models.CASCADE)
    title = models.TextField()
    content = RichTextField()
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    visible = models.BooleanField(default=True)
    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "contest_announcement"
        ordering = ("-create_time",)
