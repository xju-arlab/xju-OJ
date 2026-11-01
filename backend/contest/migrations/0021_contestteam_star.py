from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contest", "0020_team_member_real_names"),
    ]

    operations = [
        migrations.AddField(
            model_name="contestteam",
            name="star",
            field=models.BooleanField(default=False),
        ),
    ]
