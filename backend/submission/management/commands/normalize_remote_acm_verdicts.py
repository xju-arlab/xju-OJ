import json
import os
from datetime import datetime, timezone
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from django.db import transaction

from account.models import User
from contest.models import Contest
from problem.models import Problem
from submission.models import JudgeStatus, Submission


class Command(BaseCommand):
    help = "Preview or repair legacy Luogu ACM 'partially accepted' labels; preserve all rank/AC counters."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true")
        parser.add_argument("--backup-dir")

    def handle(self, *args, **options):
        candidates = Submission.objects.filter(
            judge_mode="REMOTE", remote_oj="LUOGU", remote_status="FINISHED",
            result=JudgeStatus.PARTIALLY_ACCEPTED, problem__rule_type="ACM")
        self.stdout.write(f"Legacy ACM unaccepted submissions: {candidates.count()}")
        if not options["apply"]:
            self.stdout.write("Preview only. Use --apply to normalize these labels.")
            return
        directory = Path(options["backup_dir"] or Path(settings.DATA_DIR) / "backups")
        directory.mkdir(parents=True, exist_ok=True)
        changed = 0
        for problem_id in sorted(set(candidates.values_list("problem_id", flat=True))):
            with transaction.atomic():
                # Match remote finalization: submission, contest, problem,
                # then user. A repair must not invert the live worker locks.
                rows = list(candidates.filter(problem_id=problem_id)
                            .order_by("id").select_for_update(of=("self",)))
                if not rows:
                    continue
                contest_id = rows[0].contest_id
                if contest_id:
                    Contest.objects.select_for_update().get(pk=contest_id)
                problem = Problem.objects.select_for_update().get(id=problem_id)
                users = list(User.objects.select_for_update().filter(
                    id__in=[row.user_id for row in rows]).order_by("id"))
                profiles = [user.userprofile for user in users]
                snapshot = {
                    "problem_id": problem_id, "problem_statistic_info": problem.statistic_info,
                    "submissions": [{"id": row.id, "result": row.result, "remote_data": row.remote_data} for row in rows],
                    "profiles": [{"id": profile.id, "acm_problems_status": profile.acm_problems_status} for profile in profiles],
                }
                stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
                backup = directory / f"remote-acm-verdicts-{problem_id}-{stamp}.json"
                with os.fdopen(os.open(backup, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600), "w") as handle:
                    json.dump(snapshot, handle, ensure_ascii=False)
                for row in rows:
                    row.result = JudgeStatus.WRONG_ANSWER
                    row.remote_data = {**(row.remote_data or {}), "normalized_from": JudgeStatus.PARTIALLY_ACCEPTED}
                    row.save(update_fields=["result", "remote_data"])
                histogram = dict(problem.statistic_info or {})
                moved = min(int(histogram.get("8", 0)), len(rows))
                if moved:
                    histogram["8"] -= moved
                    if histogram["8"] == 0:
                        histogram.pop("8")
                    histogram["-1"] = histogram.get("-1", 0) + moved
                    problem.statistic_info = histogram
                    problem.save(update_fields=["statistic_info"])
                for profile in profiles:
                    status = profile.acm_problems_status or {}
                    for lane in ("problems", "contest_problems"):
                        entry = status.get(lane, {}).get(str(problem_id))
                        if entry and entry.get("status") == JudgeStatus.PARTIALLY_ACCEPTED:
                            entry["status"] = JudgeStatus.WRONG_ANSWER
                    profile.acm_problems_status = status
                    profile.save(update_fields=["acm_problems_status"])
                changed += len(rows)
                self.stdout.write(f"Problem {problem_id}: normalized {len(rows)} labels; backup: {backup}")
        self.stdout.write(f"Normalized {changed} labels. Accepted counts, ranks and submission timestamps preserved.")
