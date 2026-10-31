import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import utils.models


class Migration(migrations.Migration):

    dependencies = [
        ("contest", "0018_contestprepplanitem"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="contest",
            name="rank_freeze_time",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="contest",
            name="rank_unfrozen",
            field=models.BooleanField(default=False),
        ),
        migrations.CreateModel(
            name="ContestTeam",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.TextField()),
                ("members", utils.models.JSONField(default=list)),
                ("create_time", models.DateTimeField(auto_now_add=True)),
                ("contest", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE,
                                              related_name="teams", to="contest.contest")),
                ("user", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE,
                                              related_name="contest_team", to=settings.AUTH_USER_MODEL)),
            ],
            options={
                "db_table": "contest_team",
                "ordering": ("id",),
            },
        ),
    ]
