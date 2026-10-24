from django.db import transaction
from django.utils import timezone

from .models import Problem


def _remote_public_problem(problem):
    if not problem.remote_oj or not problem.remote_problem_id:
        return None
    return (
        Problem.objects.filter(
            contest_id__isnull=True,
            remote_oj=problem.remote_oj,
            remote_problem_id=problem.remote_problem_id,
        )
        .order_by("id")
        .first()
    )


@transaction.atomic
def publish_due_contest_problems(contest_ids=None):
    queryset = (
        Problem.objects.select_for_update()
        .select_related("contest")
        .filter(
            contest_id__isnull=False,
            contest__end_time__lt=timezone.now(),
            # A private preparation contest never feeds the public library.
            contest__prep_state__isnull=True,
            publish_after_contest=True,
        )
        .order_by("id")
    )
    if contest_ids is not None:
        queryset = queryset.filter(contest_id__in=contest_ids)

    published = []
    for contest_problem in queryset:
        existing = _remote_public_problem(contest_problem)
        if existing is not None:
            contest_problem.is_public = True
            contest_problem.publish_after_contest = False
            contest_problem.post_contest_display_id = None
            contest_problem.save(update_fields=(
                "is_public", "publish_after_contest", "post_contest_display_id"
            ))
            published.append(existing)
            continue

        display_id = contest_problem.post_contest_display_id or contest_problem._id
        if Problem.objects.filter(_id=display_id, contest_id__isnull=True).exists():
            # A later admin edit may have occupied the reserved display ID.
            # Keep this item queued instead of publishing under an unexpected ID.
            continue

        tags = list(contest_problem.tags.all())
        contest_problem.is_public = True
        contest_problem.publish_after_contest = False
        contest_problem.post_contest_display_id = None
        contest_problem.save(update_fields=(
            "is_public", "publish_after_contest", "post_contest_display_id"
        ))

        contest_problem.pk = None
        contest_problem.contest = None
        contest_problem._id = display_id
        contest_problem.visible = True
        contest_problem.is_public = False
        contest_problem.publish_after_contest = False
        contest_problem.post_contest_display_id = None
        contest_problem.submission_number = 0
        contest_problem.accepted_number = 0
        contest_problem.statistic_info = {}
        contest_problem.save()
        contest_problem.tags.set(tags)
        published.append(contest_problem)
    return published


__all__ = ["publish_due_contest_problems"]
