from django.db import migrations, models


class Migration(migrations.Migration):
    """Existing AI contests keep weighted-score ranking."""
    dependencies = [("ai_studio", "0005_aiproblem_quiz_category")]

    operations = [
        migrations.AddField(
            model_name="aicontestconfig",
            name="ranking",
            field=models.CharField(default="score", max_length=8, choices=[("score", "score"), ("acm", "acm")]),
        ),
    ]
