# Stage.weight: from «absolute override, empty = kind share» to «relative weight within the kind, default 1».
# Old explicit values meant something else (a share of the topic), so every stage starts from equal parts.

import django.core.validators
from django.db import migrations, models


def reset_weights(apps, schema_editor):
    apps.get_model("courses", "Stage").objects.update(weight=1)


class Migration(migrations.Migration):
    dependencies = [
        ("courses", "0006_course_benchmark_quiz_coursegroup_posttest_opened_at"),
    ]

    operations = [
        migrations.RunPython(reset_weights, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="stage",
            name="weight",
            field=models.DecimalField(
                decimal_places=2,
                default=1,
                help_text="Relative weight among the stages of the same kind: the course share of the kind is split in this proportion",
                max_digits=6,
                validators=[django.core.validators.MinValueValidator(0)],
                verbose_name="weight",
            ),
        ),
    ]
