import utils.models
from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ("problem", "0020_problem_favorite"),
    ]

    operations = [
        migrations.AddField(
            model_name="problem",
            name="data_range",
            field=utils.models.RichTextField(blank=True, default=""),
        ),
    ]
