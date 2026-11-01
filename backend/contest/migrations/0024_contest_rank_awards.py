from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("contest", "0023_contestteam_campus"),
    ]

    operations = [
        migrations.AddField(
            model_name="contest",
            name="rank_awards",
            field=models.JSONField(blank=True, default=dict),
        ),
    ]
