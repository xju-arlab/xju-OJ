from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contest", "0022_team_language"),
    ]

    operations = [
        migrations.AddField(
            model_name="contestteam",
            name="campus",
            field=models.CharField(blank=True, default="", max_length=16),
        ),
    ]
