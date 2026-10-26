import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import utils.models


def every_problem_belongs_to_the_contest(apps, schema_editor):
    """Preparation contests no longer pick a subset: all their problems take part."""
    Problem = apps.get_model("problem", "Problem")
    Problem.objects.filter(contest__prep_state__isnull=False, visible=False).update(visible=True)


class Migration(migrations.Migration):

    dependencies = [
        ("contest", "0017_prep_organizers_and_selection"),
        ("problem", "0020_problem_favorite"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name="ContestPrepPlanItem",
            fields=[
                ("id", models.AutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("difficulty", models.TextField()),
                ("tags", utils.models.JSONField(default=list)),
                ("create_time", models.DateTimeField(auto_now_add=True)),
                ("assignee", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL,
                                               related_name="+", to=settings.AUTH_USER_MODEL)),
                ("contest", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="prep_plan",
                                              to="contest.contest")),
            ],
            options={
                "db_table": "contest_prep_plan_item",
                "ordering": ("create_time", "id"),
            },
        ),
        migrations.AddField(
            model_name="contest",
            name="review_ended_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(every_problem_belongs_to_the_contest, migrations.RunPython.noop),
    ]
