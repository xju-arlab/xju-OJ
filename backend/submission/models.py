from django.db import models

from utils.constants import ContestPrepRole, ContestStatus
from utils.models import JSONField
from problem.models import Problem
from contest.models import Contest

from utils.shortcuts import rand_str


class JudgeStatus:
    COMPILE_ERROR = -2
    WRONG_ANSWER = -1
    ACCEPTED = 0
    CPU_TIME_LIMIT_EXCEEDED = 1
    REAL_TIME_LIMIT_EXCEEDED = 2
    MEMORY_LIMIT_EXCEEDED = 3
    RUNTIME_ERROR = 4
    SYSTEM_ERROR = 5
    PENDING = 6
    JUDGING = 7
    PARTIALLY_ACCEPTED = 8


class SubmissionJudgeMode:
    LOCAL = "LOCAL"
    REMOTE = "REMOTE"


class RemoteSubmissionStatus:
    QUEUED = "QUEUED"
    OPENING = "OPENING"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    VERIFICATION_REQUIRED = "VERIFICATION_REQUIRED"
    SUBMITTED = "SUBMITTED"
    JUDGING = "JUDGING"
    FINISHED = "FINISHED"
    FAILED = "FAILED"

    TERMINAL = frozenset({FINISHED, FAILED})


class Submission(models.Model):
    id = models.TextField(default=rand_str, primary_key=True, db_index=True)
    contest = models.ForeignKey(Contest, null=True, on_delete=models.CASCADE)
    problem = models.ForeignKey(Problem, on_delete=models.CASCADE)
    create_time = models.DateTimeField(auto_now_add=True)
    user_id = models.IntegerField(db_index=True)
    username = models.TextField()
    code = models.TextField()
    result = models.IntegerField(db_index=True, default=JudgeStatus.PENDING)
    # 从JudgeServer返回的判题详情
    info = JSONField(default=dict)
    language = models.TextField()
    shared = models.BooleanField(default=False)
    # 存储该提交所用时间和内存值，方便提交列表显示
    # {time_cost: "", memory_cost: "", err_info: "", score: 0}
    statistic_info = JSONField(default=dict)
    ip = models.TextField(null=True)
    judge_mode = models.TextField(default=SubmissionJudgeMode.LOCAL)
    remote_oj = models.TextField(null=True)
    remote_submission_id = models.TextField(null=True, db_index=True)
    remote_status = models.TextField(null=True)
    remote_url = models.TextField(null=True)
    remote_message = models.TextField(null=True)
    remote_data = JSONField(default=dict)
    remote_update_time = models.DateTimeField(null=True)

    def check_user_permission(self, user, check_share=True):
        if self.contest_id and self.contest.is_preparation:
            # Verification runs stay inside the preparation team whatever the
            # admin rights: the author, plus the creator and setters reviewing them.
            return self.user_id == user.id or \
                self.contest.prep_role(user) in (ContestPrepRole.CREATOR, ContestPrepRole.SETTER)

        if self.user_id == user.id or user.is_super_admin() or user.can_mgmt_all_problem() or self.problem.created_by_id == user.id:
            return True

        if check_share:
            if self.contest:
                # Once a contest has ended, all of its code is open to read.
                return self.contest.status == ContestStatus.CONTEST_ENDED
            if self.problem.share_submission or self.shared:
                return True
        return False

    class Meta:
        db_table = "submission"
        ordering = ("-create_time",)

    def __str__(self):
        return self.id
