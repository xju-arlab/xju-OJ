"""Contest problem authoring shared by the admin console and contest preparation.

Contest problem order is carried by the A, B, ... Z, AA display IDs. Order by
length first so AA sorts after Z; a plain text sort would put AA before B.
"""
from django.db import transaction
from django.db.models.functions import Length

from utils.api import APIError
from utils.constants import ContestPrepState
from .models import Problem, ProblemTag


def alphabetic_display_id(index):
    value = index + 1
    label = ""
    while value > 0:
        value -= 1
        label = chr(ord("A") + value % 26) + label
        value //= 26
    return label


def next_contest_display_id(contest):
    used = set(Problem.objects.filter(contest=contest).values_list("_id", flat=True))
    index = 0
    while True:
        candidate = alphabetic_display_id(index)
        if candidate not in used:
            return candidate
        index += 1


def order_contest_problems(queryset):
    return queryset.order_by(Length("_id"), "_id")


def set_problem_tags(problem, tag_names):
    for name in tag_names:
        try:
            tag = ProblemTag.objects.get(name=name)
        except ProblemTag.DoesNotExist:
            tag = ProblemTag.objects.create(name=name)
        problem.tags.add(tag)


def create_contest_problem(contest, data, user):
    """Create a contest problem from a validated payload that passed ProblemBase.common_checks."""
    tags = data.pop("tags")
    data["contest"] = contest
    data["created_by"] = user
    problem = Problem.objects.create(**data)
    set_problem_tags(problem, tags)
    return problem


def update_contest_problem(problem, data):
    """Apply a validated edit payload; the contest display ID never changes here."""
    data["_id"] = problem._id
    tags = data.pop("tags")
    data["languages"] = list(data["languages"])
    for key, value in data.items():
        setattr(problem, key, value)
    problem.save()
    problem.tags.remove(*problem.tags.all())
    set_problem_tags(problem, tags)


@transaction.atomic
def reorder_contest_problems(contest, problem_ids):
    """Relabel every problem of the contest A, B, C... in the given order."""
    problems = {item.id: item for item in Problem.objects.select_for_update().filter(contest=contest)}
    if len(problem_ids) != len(set(problem_ids)) or set(problem_ids) != set(problems):
        raise APIError("The order must list every problem of the contest exactly once")
    # unique_together(_id, contest) is checked per row, so move every label to
    # a unique temporary value before assigning the final ones.
    for problem_id in problems:
        Problem.objects.filter(pk=problem_id).update(_id=f"~{problem_id}")
    for index, problem_id in enumerate(problem_ids):
        Problem.objects.filter(pk=problem_id).update(_id=alphabetic_display_id(index))


def ensure_contest_problems_editable(contest):
    """Problems of a preparation contest are frozen while it is in Review."""
    if contest.prep_state == ContestPrepState.REVIEW:
        raise APIError("Switch the contest back to preparation before editing problems")
