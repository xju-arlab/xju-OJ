import uuid

from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [("ai_studio", "0003_aiservicestate")]

    operations = [
        migrations.CreateModel(
            name="AIProblemImport",
            fields=[
                ("id", models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False, serialize=False)),
                ("source_sha256", models.CharField(max_length=64)),
                ("filename", models.CharField(max_length=128)),
                ("manifest", models.JSONField(default=list)),
                ("status", models.CharField(max_length=16, default="PREVIEW", db_index=True)),
                ("publish", models.BooleanField(default=False)),
                ("result", models.JSONField(default=list)),
                ("message", models.CharField(max_length=256, blank=True)),
                ("worker", models.CharField(max_length=64, blank=True)),
                ("lease", models.UUIDField(null=True)),
                ("lease_until", models.DateTimeField(null=True)),
                ("attempts", models.PositiveSmallIntegerField(default=0)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("created_by", models.ForeignKey(to=settings.AUTH_USER_MODEL, on_delete=django.db.models.deletion.PROTECT)),
            ],
            options={"ordering": ("-created_at", "-id")},
        ),
        migrations.AddConstraint(model_name="aiproblemimport", constraint=models.UniqueConstraint(
            fields=("created_by", "source_sha256"), name="ai_import_owner_digest_unique")),
        migrations.AddField(model_name="aiproblem", name="revision", field=models.PositiveIntegerField(default=1)),
        migrations.AddField(model_name="aiproblem", name="package_import", field=models.ForeignKey(
            to="ai_studio.aiproblemimport", null=True, on_delete=django.db.models.deletion.PROTECT, related_name="problems")),
        migrations.AddField(model_name="aiproblem", name="package_index", field=models.PositiveSmallIntegerField(null=True)),
    ]
