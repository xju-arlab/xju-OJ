from django.db import migrations, models


def alphabetic_display_id(index):
    value = index + 1
    label = ""
    while value > 0:
        value -= 1
        label = chr(ord("A") + value % 26) + label
        value //= 26
    return label


def forward(apps, schema_editor):
    Contest = apps.get_model("contest", "Contest")
    ContestPrepMember = apps.get_model("contest", "ContestPrepMember")
    ContestPrepInvite = apps.get_model("contest", "ContestPrepInvite")
    Problem = apps.get_model("problem", "Problem")
    # Review is no longer a state: the workspace stays open while review rounds run.
    Contest.objects.filter(prep_state="Review").update(prep_state="Preparation")
    # Setters and verifiers become one organizer role.
    ContestPrepMember.objects.exclude(role="Organizer").update(role="Organizer")
    ContestPrepInvite.objects.exclude(role="Organizer").update(role="Organizer")
    # Visible problems are the selected ones; they now lead the order so review
    # and publish label them A, B, C... Two passes respect unique (_id, contest).
    for contest_id in Contest.objects.filter(prep_state__isnull=False).values_list("id", flat=True):
        problems = sorted(Problem.objects.filter(contest_id=contest_id).only("id", "_id", "visible"),
                          key=lambda problem: (not problem.visible, len(problem._id), problem._id))
        for problem in problems:
            Problem.objects.filter(pk=problem.pk).update(_id=f"~{problem.pk}")
        for index, problem in enumerate(problems):
            Problem.objects.filter(pk=problem.pk).update(_id=alphabetic_display_id(index))


def backward(apps, schema_editor):
    ContestPrepMember = apps.get_model("contest", "ContestPrepMember")
    ContestPrepInvite = apps.get_model("contest", "ContestPrepInvite")
    ContestPrepMember.objects.filter(role="Organizer").update(role="Setter")
    ContestPrepInvite.objects.filter(role="Organizer").update(role="Setter")


class Migration(migrations.Migration):

    dependencies = [
        ("contest", "0016_contestprepinvite_revoked_time"),
        ("problem", "0020_problem_favorite"),
    ]

    operations = [
        migrations.AddField(
            model_name="contest",
            name="prep_problem_count",
            field=models.PositiveIntegerField(blank=True, null=True),
        ),
        migrations.RunPython(forward, backward),
    ]
