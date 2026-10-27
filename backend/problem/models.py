from django.db import models
from utils.models import JSONField

from account.models import User
from contest.models import Contest
from utils.models import RichTextField
from utils.constants import Choices


class ProblemTag(models.Model):
    name = models.TextField()

    class Meta:
        db_table = "problem_tag"


class ProblemRuleType(Choices):
    ACM = "ACM"
    OI = "OI"


class ProblemDifficulty(object):
    High = "High"
    Mid = "Mid"
    Low = "Low"


class ProblemIOMode(Choices):
    standard = "Standard IO"
    file = "File IO"


class ProblemJudgeMode(Choices):
    LOCAL = "LOCAL"
    REMOTE = "REMOTE"


class RemoteOJ(Choices):
    NOWCODER = "NOWCODER"
    LUOGU = "LUOGU"
    CODEFORCES = "CODEFORCES"


def _default_io_mode():
    return {"io_mode": ProblemIOMode.standard, "input": "input.txt", "output": "output.txt"}


class Problem(models.Model):
    # display ID
    _id = models.TextField(db_index=True)
    contest = models.ForeignKey(Contest, null=True, on_delete=models.CASCADE)
    # for contest problem
    is_public = models.BooleanField(default=False)
    title = models.TextField()
    # HTML
    description = RichTextField()
    input_description = RichTextField()
    output_description = RichTextField()
    # Constraints shown after the output description; empty hides the section.
    data_range = RichTextField(default="", blank=True)
    # [{input: "1", output: "2", explanation: "optional plain text"}, ...]
    samples = JSONField()
    test_case_id = models.TextField()
    # [{"input_name": "1.in", "output_name": "1.out", "score": 0}]
    test_case_score = JSONField()
    hint = RichTextField(null=True)
    languages = JSONField()
    template = JSONField()
    create_time = models.DateTimeField(auto_now_add=True)
    # we can not use auto_now here
    last_update_time = models.DateTimeField(null=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE)
    # ms
    time_limit = models.IntegerField()
    # MB
    memory_limit = models.IntegerField()
    # io mode
    io_mode = JSONField(default=_default_io_mode)
    # special judge related
    spj = models.BooleanField(default=False)
    spj_language = models.TextField(null=True)
    spj_code = models.TextField(null=True)
    spj_version = models.TextField(null=True)
    spj_compile_ok = models.BooleanField(default=False)
    rule_type = models.TextField()
    visible = models.BooleanField(default=True)
    difficulty = models.TextField()
    tags = models.ManyToManyField(ProblemTag)
    source = models.TextField(null=True)
    # for OI mode
    total_score = models.IntegerField(default=0)
    submission_number = models.BigIntegerField(default=0)
    accepted_number = models.BigIntegerField(default=0)
    # {JudgeStatus.ACCEPTED: 3, JudgeStaus.WRONG_ANSWER: 11}, the number means count
    statistic_info = JSONField(default=dict)
    share_submission = models.BooleanField(default=False)
    judge_mode = models.TextField(default=ProblemJudgeMode.LOCAL)
    remote_oj = models.TextField(null=True)
    remote_problem_id = models.TextField(null=True, db_index=True)
    remote_problem_data = JSONField(default=dict)
    # Contest-only flag: publish a copy into the public problem library after
    # the contest ends. The future public display ID is kept separately from
    # the contest's A/B/C style display ID.
    publish_after_contest = models.BooleanField(default=False)
    post_contest_display_id = models.TextField(null=True)

    class Meta:
        db_table = "problem"
        unique_together = (("_id", "contest"),)
        constraints = (
            models.UniqueConstraint(
                fields=("remote_oj", "remote_problem_id"),
                condition=models.Q(
                    contest__isnull=True,
                    judge_mode=ProblemJudgeMode.REMOTE,
                ),
                name="unique_public_remote_problem",
            ),
        )
        ordering = ("create_time",)

    def add_submission_number(self):
        self.submission_number = models.F("submission_number") + 1
        self.save(update_fields=["submission_number"])

    def add_ac_number(self):
        self.accepted_number = models.F("accepted_number") + 1
        self.save(update_fields=["accepted_number"])


class ProblemFavorite(models.Model):
    """A user's bookmark on a public library problem."""
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE)
    create_time = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "problem_favorite"
        unique_together = (("user", "problem"),)
        ordering = ("-create_time", "-id")
