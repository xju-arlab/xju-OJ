from django.db import migrations
from django.db.models import Q


def teams_in_chinese(apps, schema_editor):
    """Team accounts without a language pick open in Chinese, like new ones."""
    UserProfile = apps.get_model("account", "UserProfile")
    UserProfile.objects.filter(Q(language__isnull=True) | Q(language=""), user__contest_team__isnull=False) \
        .update(language="zh-CN")


class Migration(migrations.Migration):

    dependencies = [
        ("account", "0017_user_admin_role_manual_override"),
        ("contest", "0021_contestteam_star"),
    ]

    operations = [
        migrations.RunPython(teams_in_chinese, migrations.RunPython.noop),
    ]
