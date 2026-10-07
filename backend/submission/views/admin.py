from django.db import transaction

from account.decorators import super_admin_required
from judge.tasks import judge_task
from utils.api import APIView
from ..models import JudgeStatus, Submission, SubmissionJudgeMode


class SubmissionRejudgeAPI(APIView):
    @super_admin_required
    @transaction.atomic
    def post(self, request):
        id = request.data.get("id")
        if not id:
            return self.error("Parameter error, id is required")
        try:
            submission = Submission.objects.select_for_update().get(id=id, contest_id__isnull=True,
                                                                    judge_mode=SubmissionJudgeMode.LOCAL)
        except Submission.DoesNotExist:
            return self.error("Submission does not exists")
        if submission.result in (JudgeStatus.PENDING, JudgeStatus.JUDGING):
            return self.error("Submission is already waiting for judging")
        submission.result = JudgeStatus.PENDING
        submission.save(update_fields=["result"])

        transaction.on_commit(lambda: judge_task.send(submission.id, submission.problem_id))
        return self.success()
