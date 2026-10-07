"""Reconcile affected projections from verdict facts, including repeated jobs.

ACM contests count attempts through the first AC; CE and system errors do not
add penalty. OI contests use the latest submitted attempt, even when workers
finish out of order. Practice changes personal marks only.
"""
from collections import Counter

from django.db import transaction

from account.models import User
from contest.models import ACMContestRank, Contest, ContestRuleType, ContestStatus, OIContestRank
from problem.models import Problem
from submission.models import JudgeStatus, Submission
from utils.cache import cache
from utils.constants import CacheKey


def finished_submissions(**filters):
    return Submission.objects.filter(**filters).exclude(
        result__in=(JudgeStatus.PENDING, JudgeStatus.JUDGING)).order_by("create_time", "id")


def submission_facts(query):
    return list(query.values("id", "problem_id", "user_id", "result", "create_time", "statistic_info"))


def acm_attempts(facts):
    """Keep the existing contest rule: attempts after an AC are unranked."""
    accepted = set()
    for fact in facts:
        key = (fact["user_id"], fact["problem_id"])
        if key in accepted:
            continue
        yield fact
        if fact["result"] == JudgeStatus.ACCEPTED:
            accepted.add(key)


def update_personal_mark(profile, problem, facts):
    if not facts:
        return
    field = "acm_problems_status" if problem.rule_type == ContestRuleType.ACM else "oi_problems_status"
    section = "contest_problems" if problem.contest_id else "problems"
    statuses = getattr(profile, field)
    problems = statuses.setdefault(section, {})
    # Public solved marks are sticky while any AC still exists. Contest OI
    # marks retain their existing latest-attempt behavior, including practice.
    chosen = facts[-1]
    if not problem.contest_id or problem.rule_type == ContestRuleType.ACM:
        chosen = next((fact for fact in facts if fact["result"] == JudgeStatus.ACCEPTED), chosen)
    mark = {"_id": problem._id, "status": chosen["result"]}
    if problem.rule_type == ContestRuleType.OI:
        mark["score"] = chosen["statistic_info"].get("score", 0)
    problems[str(problem.pk)] = mark
    profile.save(update_fields=[field])
    if not problem.contest_id:
        public_marks = [*profile.acm_problems_status.get("problems", {}).values(),
                        *profile.oi_problems_status.get("problems", {}).values()]
        profile.accepted_number = sum(mark["status"] == JudgeStatus.ACCEPTED for mark in public_marks)
        profile.total_score = sum(mark.get("score", 0)
                                  for mark in profile.oi_problems_status.get("problems", {}).values())
        profile.submission_number = finished_submissions(user_id=profile.user_id, contest_id=None).count()
        profile.save(update_fields=["accepted_number", "total_score", "submission_number"])


def update_contest_rank(contest, problem, user_id, official):
    facts = submission_facts(official.filter(user_id=user_id))
    if contest.rule_type == ContestRuleType.OI:
        rank, _ = OIContestRank.objects.get_or_create(contest=contest, user_id=user_id)
        rank.submission_info = {str(fact["problem_id"]): fact["statistic_info"].get("score", 0)
                                for fact in facts}
        rank.total_score = sum(rank.submission_info.values())
        rank.save(update_fields=["submission_info", "total_score"])
        return

    first_ac_ids = set(official.filter(result=JudgeStatus.ACCEPTED)
                       .order_by("problem_id", "create_time", "id").distinct("problem_id")
                       .values_list("id", flat=True))
    rank, _ = ACMContestRank.objects.select_for_update().get_or_create(contest=contest, user_id=user_id)
    previous = rank.submission_info
    rank.submission_info = {}
    rank.submission_number = rank.accepted_number = rank.total_time = 0
    for fact in acm_attempts(facts):
        key = str(fact["problem_id"])
        info = rank.submission_info.setdefault(key, {
            "is_ac": False, "ac_time": 0, "error_number": 0, "is_first_ac": False})
        rank.submission_number += 1
        if fact["result"] == JudgeStatus.ACCEPTED:
            info.update(is_ac=True, ac_time=(fact["create_time"] - contest.start_time).total_seconds(),
                        is_first_ac=fact["id"] in first_ac_ids)
            if previous.get(key, {}).get("checked"):
                info["checked"] = True
            rank.accepted_number += 1
            rank.total_time += info["ac_time"] + info["error_number"] * 1200
        elif fact["result"] not in (JudgeStatus.COMPILE_ERROR, JudgeStatus.SYSTEM_ERROR):
            info["error_number"] += 1
    rank.save(update_fields=["submission_info", "submission_number", "accepted_number", "total_time"])

    # A rejudge or a late result can transfer first AC to another participant.
    first = official.filter(problem=problem, result=JudgeStatus.ACCEPTED).first()
    for other in ACMContestRank.objects.filter(contest=contest).exclude(pk=rank.pk):
        info = other.submission_info.get(str(problem.pk))
        if info:
            expected = bool(first and first.user_id == other.user_id and info.get("is_ac"))
            if info.get("is_first_ac") != expected:
                info["is_first_ac"] = expected
                other.save(update_fields=["submission_info"])


@transaction.atomic
def refresh_submission_statistics(submission):
    contest = None
    if submission.contest_id:
        # Serialize contest projections and first-AC changes across workers.
        contest = Contest.objects.select_for_update().get(pk=submission.contest_id)
        if submission.create_time < contest.start_time:
            return
    problem = Problem.objects.select_for_update().get(pk=submission.problem_id)
    user = User.objects.select_for_update().get(pk=submission.user_id)
    problem_query = finished_submissions(problem=problem, contest_id=submission.contest_id)
    personal_query = problem_query.filter(user_id=user.pk)
    if contest:
        personal_query = personal_query.filter(create_time__gte=contest.start_time)
    update_personal_mark(user.userprofile, problem, submission_facts(personal_query))
    if contest and submission.create_time > contest.end_time:
        return

    if contest:
        official = finished_submissions(contest=contest, create_time__gte=contest.start_time,
                                        create_time__lte=contest.end_time)
        facts = submission_facts(official.filter(problem=problem))
    else:
        facts = submission_facts(problem_query)
    if contest and contest.rule_type == ContestRuleType.ACM:
        facts = list(acm_attempts(facts))
    counts = Counter(str(fact["result"]) for fact in facts)
    problem.submission_number = len(facts)
    problem.accepted_number = counts[str(JudgeStatus.ACCEPTED)]
    problem.statistic_info = dict(counts)
    problem.save(update_fields=["submission_number", "accepted_number", "statistic_info"])
    if contest:
        update_contest_rank(contest, problem, user.pk, official)
        if (contest.rule_type == ContestRuleType.OI or contest.real_time_rank
                or contest.status == ContestStatus.CONTEST_ENDED):
            cache.delete(f"{CacheKey.contest_rank_cache}:{contest.pk}")
