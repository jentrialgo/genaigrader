import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("genaigrader", "0010_evaluation_notes"),
    ]

    operations = [
        migrations.AlterField(
            model_name="questionevaluation",
            name="question_option",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="genaigrader.questionoption",
            ),
        ),
    ]
