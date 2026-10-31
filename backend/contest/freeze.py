"""The frozen ACM board: what everyone but contest admins sees from the freeze time on.

Results known before the freeze keep counting exactly as on the live board.
Each attempt made later only shows as pending on its problem, until an admin
unfreezes the board after the contest.
"""
from collections import Counter

from django.db.models import Count

from judge.statistics import acm_attempts, finished_submissions, submission_facts
from submission.models import JudgeStatus, Submission


def frozen_facts(contest):
    """Finished official attempts made before the freeze, in ranking order."""
    return list(acm_attempts(submission_facts(finished_submissions(
        contest=contest, create_time__gte=contest.start_time, create_time__lt=contest.rank_freeze_time))))


def freeze_rows(contest, rows):
    """Recompute serialized ACM rank rows as of the freeze time, best first.

    Ties are broken by rank id so the live order cannot leak through them.
    """
    by_user = {row["user"]["id"]: row for row in rows}
    for row in rows:
        row.update(submission_number=0, accepted_number=0, total_time=0, submission_info={})
    solved = set()
    for fact in frozen_facts(contest):
        key = str(fact["problem_id"])
        accepted = fact["result"] == JudgeStatus.ACCEPTED
        first = accepted and key not in solved
        if accepted:
            solved.add(key)
        row = by_user.get(fact["user_id"])
        if row is None:
            continue
        info = row["submission_info"].setdefault(key, {
            "is_ac": False, "ac_time": 0, "error_number": 0, "is_first_ac": False})
        row["submission_number"] += 1
        if accepted:
            info.update(is_ac=True, ac_time=int((fact["create_time"] - contest.start_time).total_seconds()),
                        is_first_ac=first)
            row["accepted_number"] += 1
            row["total_time"] += info["ac_time"] + info["error_number"] * 1200
        elif fact["result"] not in (JudgeStatus.COMPILE_ERROR, JudgeStatus.SYSTEM_ERROR):
            info["error_number"] += 1

    later = Submission.objects.filter(contest=contest, create_time__gte=contest.rank_freeze_time,
                                      create_time__lte=contest.end_time) \
        .values("user_id", "problem_id").annotate(count=Count("id"))
    for item in later:
        row = by_user.get(item["user_id"])
        if row is None:
            continue
        info = row["submission_info"].setdefault(str(item["problem_id"]), {
            "is_ac": False, "ac_time": 0, "error_number": 0, "is_first_ac": False})
        if not info["is_ac"]:
            info["frozen_number"] = item["count"]
            row["submission_number"] += item["count"]
    rows.sort(key=lambda row: (-row["accepted_number"], row["total_time"], row["id"]))
    return rows


def frozen_problem_stats(contest):
    """Per-problem submission counters as they stood at the freeze time."""
    counts = {}
    for fact in frozen_facts(contest):
        counts.setdefault(fact["problem_id"], Counter())[str(fact["result"])] += 1
    return {problem_id: {"submission_number": sum(counter.values()),
                         "accepted_number": counter[str(JudgeStatus.ACCEPTED)],
                         "statistic_info": dict(counter)}
            for problem_id, counter in counts.items()}


def mask_problem_stats(contest, problems):
    """Replace live counters in serialized contest problems with the frozen ones."""
    stats = frozen_problem_stats(contest)
    for problem in problems:
        problem.update(stats.get(problem["id"], {"submission_number": 0, "accepted_number": 0,
                                                 "statistic_info": {}}))
