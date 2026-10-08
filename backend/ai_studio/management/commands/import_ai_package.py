"""The CLI shares the browser's package validation, queue and private storage."""
import json
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from account.models import User
from ai_studio.package_format import MAX_UPLOAD
from ai_studio.packages import adopt_existing, batch_summary, confirm_batch, preview_package
from utils.api import APIError


class Command(BaseCommand):
    help = "Validate and queue a portable AI ZIP package; default visibility is hidden"

    def add_arguments(self, parser):
        parser.add_argument("archive", type=Path)
        parser.add_argument("--creator", required=True)
        parser.add_argument("--publish", action="store_true")
        parser.add_argument("--preview", action="store_true")
        parser.add_argument("--adopt-existing", type=Path, metavar="BINDINGS_JSON",
                            help="Attach a trusted export from the existing judge without creating or changing problems")

    def handle(self, *args, **options):
        user = User.objects.filter(username=options["creator"]).first()
        if not user:
            raise CommandError("Creator does not exist")
        if options["adopt_existing"] and (options["publish"] or options["preview"]):
            raise CommandError("Adoption preserves all existing problem metadata and visibility")
        try:
            with options["archive"].open("rb") as stream:
                batch = preview_package(user, options["archive"].name, stream.read(MAX_UPLOAD + 1))
            if options["adopt_existing"]:
                bindings = json.loads(options["adopt_existing"].read_text())
                batch = adopt_existing(batch.pk, user, bindings)
            elif not options["preview"]:
                batch = confirm_batch(batch.pk, user, options["publish"])
        except (APIError, OSError, ValueError) as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(json.dumps(batch_summary(batch), ensure_ascii=False))
