"""Import the trusted local Codabench manifest without silently overwriting content."""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils.timezone import now
from account.models import User, AdminType
from ai_studio.contracts import cells_input, judge_input, public_files_input
from ai_studio.models import AIContestProblem, AIProblem


class Command(BaseCommand):
    help = "Import five generated AI practice tasks (no contest or exam is created)"

    def add_arguments(self, parser):
        parser.add_argument("manifest", type=Path)
        parser.add_argument("--creator", required=True)
        parser.add_argument("--publish", action="store_true")
        parser.add_argument("--refresh-statement", action="store_true",
                            help="Refresh statement text only; require all code, files and judge settings to match")

    @transaction.atomic
    def handle(self, *args, **options):
        user = User.objects.filter(username=options["creator"], admin_type=AdminType.SUPER_ADMIN).first()
        if not user:
            raise CommandError("Creator must be an existing super administrator")
        problems = json.loads(options["manifest"].read_text())
        if len(problems) != 5 or {item["id"] for item in problems} != {"AI001", "AI002", "AI003", "AI004", "AI005"}:
            raise CommandError("Unexpected practice manifest")
        for item in problems:
            values = {"title": item["title"], "category": item["type"], "metric": item["metric"],
                      "points": item["points"], "statement": item["statement"], "cells": cells_input(item["cells"]),
                      "public_files": public_files_input(item["public_files"]), "judge": judge_input(item["judge"])}
            existing = AIProblem.objects.select_for_update().filter(code=item["id"]).first()
            if existing:
                fields = set(values) - ({"statement"} if options["refresh_statement"] else set())
                if any(getattr(existing, key) != values[key] for key in fields):
                    raise CommandError("Existing AI problem differs: " + item["id"])
                if options["refresh_statement"] and existing.statement != values["statement"]:
                    if AIContestProblem.objects.filter(problem=existing, contest__start_time__lte=now(),
                                                       contest__end_time__gte=now()).exists():
                        raise CommandError("Cannot refresh statement during a contest: " + item["id"])
                    # Documentation only: retain the judge version, scores and drafts.
                    existing.statement = values["statement"]
                    existing.save(update_fields=["statement", "updated_at"])
                if options["publish"] and not existing.visible:
                    existing.visible = True
                    existing.save(update_fields=["visible"])
            else:
                AIProblem.objects.create(code=item["id"], created_by=user, visible=options["publish"], **values)
        self.stdout.write("Five AI practice problems verified/imported")
