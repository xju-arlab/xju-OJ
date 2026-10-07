"""Import the trusted local Codabench manifest without silently overwriting content."""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from account.models import User, AdminType
from ai_studio.contracts import cells_input, judge_input, public_files_input
from ai_studio.models import AIProblem


class Command(BaseCommand):
    help = "Import five generated AI practice tasks (no contest or exam is created)"

    def add_arguments(self, parser):
        parser.add_argument("manifest", type=Path)
        parser.add_argument("--creator", required=True)
        parser.add_argument("--publish", action="store_true")

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
            existing = AIProblem.objects.filter(code=item["id"]).first()
            if existing:
                if any(getattr(existing, key) != value for key, value in values.items()):
                    raise CommandError("Existing AI problem differs: " + item["id"])
                if options["publish"] and not existing.visible:
                    existing.visible = True
                    existing.save(update_fields=["visible"])
            else:
                AIProblem.objects.create(code=item["id"], created_by=user, visible=options["publish"], **values)
        self.stdout.write("Five AI practice problems verified/imported")
