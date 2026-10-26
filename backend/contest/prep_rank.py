"""Review leaderboard of a preparation contest.

Judge statistics skip preparation contests, so the board is derived from the
verification runs made since the current review round started, using the
normal ACM (solved, then penalty) or OI (latest score per problem) rules. Only
the selected problems count. Every member appears, and authors carry the
labels of the problems they wrote.
"""
from account.models import User
from problem.contest_authoring import order_contest_problems
from problem.models import Problem
from submission.models import JudgeStatus, Submission
from utils.constants import ContestPrepRole, ContestRuleType
from utils.shortcuts import datetime2str
from .models import ContestPrepMember

PENALTY_SECONDS = 20 * 60
NO_PENALTY = (JudgeStatus.COMPILE_ERROR, JudgeStatus.SYSTEM_ERROR)
UNFINISHED = (JudgeStatus.PENDING, JudgeStatus.JUDGING)


def review_runs(contest):
    runs = Submission.objects.filter(contest=contest).exclude(result__in=UNFINISHED)
    if contest.review_started_at:
        runs = runs.filter(create_time__gte=contest.review_started_at)
    return runs


def _member_roles(contest, user_ids):
    roles = dict(ContestPrepMember.objects.filter(contest=contest).values_list("user_id", "role"))
    roles[contest.created_by_id] = ContestPrepRole.CREATOR
    # Super admins act as the creator when they take part.
    for user in User.objects.filter(id__in=set(user_ids) - set(roles)):
        roles[user.id] = ContestPrepRole.CREATOR if user.is_super_admin() else None
    return roles


def review_rank(contest):
    problems = list(order_contest_problems(Problem.objects.filter(contest=contest, visible=True)))
    problem_ids = {problem.id for problem in problems}
    runs = list(review_runs(contest).filter(problem_id__in=problem_ids).order_by("create_time", "id")
                .values("user_id", "problem_id", "result", "create_time", "statistic_info"))
    start = contest.review_started_at or (runs[0]["create_time"] if runs else None)

    roles = _member_roles(contest, [run["user_id"] for run in runs])
    user_ids = {user_id for user_id, role in roles.items() if role} | {run["user_id"] for run in runs}
    users = {user.id: user for user in User.objects.filter(id__in=user_ids)}
    authored = {}
    for problem in problems:
        authored.setdefault(problem.created_by_id, []).append(problem._id)

    rows = {user_id: {"user": {"id": user_id, "username": users[user_id].username},
                      "role": roles.get(user_id), "authored": authored.get(user_id, []),
                      "accepted_number": 0, "submission_number": 0, "total_time": 0, "total_score": 0,
                      "submission_info": {}}
            for user_id in user_ids if user_id in users}

    if contest.rule_type == ContestRuleType.OI:
        for run in runs:
            row = rows[run["user_id"]]
            row["submission_number"] += 1
            # The latest attempt counts, as in an OI contest.
            row["submission_info"][str(run["problem_id"])] = run["statistic_info"].get("score", 0)
        for row in rows.values():
            row["total_score"] = sum(row["submission_info"].values())
            row["accepted_number"] = sum(
                1 for problem in problems
                if row["submission_info"].get(str(problem.id), 0) >= problem.total_score > 0)
        ordered = sorted(rows.values(), key=lambda row: (-row["total_score"], row["user"]["username"]))
    else:
        first_ac = {}
        for run in runs:
            row = rows[run["user_id"]]
            info = row["submission_info"].setdefault(str(run["problem_id"]), {
                "is_ac": False, "ac_time": 0, "error_number": 0, "is_first_ac": False})
            if info["is_ac"]:
                continue
            row["submission_number"] += 1
            if run["result"] == JudgeStatus.ACCEPTED:
                info["is_ac"] = True
                info["ac_time"] = max((run["create_time"] - start).total_seconds(), 0)
                first_ac.setdefault(run["problem_id"], run["user_id"])
                row["accepted_number"] += 1
                row["total_time"] += info["ac_time"] + info["error_number"] * PENALTY_SECONDS
            elif run["result"] not in NO_PENALTY:
                info["error_number"] += 1
        for problem_id, user_id in first_ac.items():
            rows[user_id]["submission_info"][str(problem_id)]["is_first_ac"] = True
        ordered = sorted(rows.values(), key=lambda row: (-row["accepted_number"], row["total_time"],
                                                         row["user"]["username"]))

    return {
        "rule_type": contest.rule_type,
        "review_started_at": datetime2str(contest.review_started_at) if contest.review_started_at else None,
        "problems": [{"id": problem.id, "_id": problem._id, "title": problem.title,
                      "total_score": problem.total_score} for problem in problems],
        "results": ordered,
    }
