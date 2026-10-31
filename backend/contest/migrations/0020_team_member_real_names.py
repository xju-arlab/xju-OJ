from django.db import migrations


def members_as_real_names(apps, schema_editor):
    """Team accounts now carry their member list as the real name."""
    ContestTeam = apps.get_model("contest", "ContestTeam")
    UserProfile = apps.get_model("account", "UserProfile")
    for team in ContestTeam.objects.all():
        UserProfile.objects.filter(user_id=team.user_id).update(real_name=",".join(team.members) or team.name)


def team_names_as_real_names(apps, schema_editor):
    ContestTeam = apps.get_model("contest", "ContestTeam")
    UserProfile = apps.get_model("account", "UserProfile")
    for team in ContestTeam.objects.all():
        UserProfile.objects.filter(user_id=team.user_id).update(real_name=team.name)


class Migration(migrations.Migration):

    dependencies = [
        ("contest", "0019_rank_freeze_and_teams"),
        ("account", "0017_user_admin_role_manual_override"),
    ]

    operations = [
        migrations.RunPython(members_as_real_names, team_names_as_real_names),
    ]
