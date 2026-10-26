"""Publish a private preparation contest as a new, independent normal contest.

The preparation contest itself never becomes public: publishing copies its
settings, announcements and problems in their current order.
Copies share test data directories by test_case_id, like AddContestProblemAPI;
uploading new data always allocates a new directory, so edits never leak back.
Once the published contest ends, its new problems join the public library.
"""
from django.db import transaction

from problem.contest_authoring import alphabetic_display_id, order_contest_problems
from problem.models import Problem
from problem.tasks import schedule_contest_problem_publication
from utils.api import APIError
from .models import Contest, ContestAnnouncement


@transaction.atomic
def publish_prep_contest(prep_contest, overrides):
    # The row lock serializes concurrent publish clicks.
    prep = Contest.objects.select_for_update().get(pk=prep_contest.pk)
    problems = list(order_contest_problems(Problem.objects.filter(contest=prep, visible=True)))
    if not problems:
        raise APIError("Upload the contest problems before publishing")
    if prep.prep_problem_count and len(problems) != prep.prep_problem_count:
        raise APIError(f"This contest takes {prep.prep_problem_count} problems, "
                       f"but {len(problems)} are uploaded")

    start_time = overrides.get("start_time", prep.start_time)
    end_time = overrides.get("end_time", prep.end_time)
    if end_time <= start_time:
        raise APIError("Start time must occur earlier than end time")
    password = overrides.get("password", prep.password) or None

    contest = Contest.objects.create(
        title=overrides.get("title", prep.title),
        description=prep.description,
        real_time_rank=overrides.get("real_time_rank", prep.real_time_rank),
        password=password,
        rule_type=prep.rule_type,
        start_time=start_time,
        end_time=end_time,
        created_by=prep.created_by,
        visible=True,
        allowed_ip_ranges=list(prep.allowed_ip_ranges),
        published_from=prep,
    )

    queued = False
    for index, problem in enumerate(problems):
        tags = list(problem.tags.all())
        # A problem copied in from the library is already public; only new
        # problems are queued, and they get a library display ID when they go out.
        already_public = problem.is_public
        problem.pk = None
        problem.contest = contest
        problem._id = alphabetic_display_id(index)
        problem.is_public = already_public
        problem.publish_after_contest = not already_public
        problem.post_contest_display_id = None
        problem.submission_number = problem.accepted_number = 0
        problem.statistic_info = {}
        problem.save()
        problem.tags.set(tags)
        queued = queued or not already_public

    for announcement in ContestAnnouncement.objects.filter(contest=prep).order_by("create_time", "id"):
        ContestAnnouncement.objects.create(
            contest=contest,
            title=announcement.title,
            content=announcement.content,
            created_by=announcement.created_by,
            visible=announcement.visible,
        )
    if queued:
        transaction.on_commit(lambda: schedule_contest_problem_publication(contest.id, contest.end_time))
    return contest
