from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("ai_studio", "0006_aicontestconfig_ranking")]

    operations = [
        migrations.AlterField(
            model_name="aicontestconfig",
            name="ranking",
            field=models.CharField(default="score", max_length=8, choices=[("score", "score"), ("acm", "acm"), ("oi", "oi")]),
        ),
    ]
