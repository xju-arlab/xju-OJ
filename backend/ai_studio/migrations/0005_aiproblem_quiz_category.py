from django.db import migrations, models


class Migration(migrations.Migration):
    """Allow quiz problems; choices are state only, so no database DDL runs."""
    dependencies = [("ai_studio", "0004_problem_packages")]

    operations = [
        migrations.AlterField(
            model_name="aiproblem",
            name="category",
            field=models.CharField(max_length=16, choices=[("logic", "logic"), ("model", "model"),
                                                          ("challenge", "challenge"), ("quiz", "quiz")]),
        ),
    ]
