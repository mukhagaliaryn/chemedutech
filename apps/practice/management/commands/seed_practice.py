"""Practice works of the seed (content in ``_practice/``, in Kazakh). Called by seed_course.

Without options a task is created when missing and its fields only when it has none. With ``--replace`` a task
nobody has submitted is brought in line with the content (title, statement, fields, rubrics); a task with
submissions (research data) is never touched.
"""

from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.courses.models import Stage
from apps.practice.models import GradingRubric, PracticeItem, PracticeTask, RubricCriterion

from ._practice import PRACTICES


def write_items(task: PracticeTask, spec: dict) -> None:
    rubrics = iter(spec.get("rubrics") or [])
    for order, (label, prompt, kind, points, answer_spec, hint) in enumerate(spec["items"], start=1):
        item = PracticeItem.objects.create(
            task=task, order=order, label=label, prompt=prompt, kind=kind, points=Decimal(str(points)),
            answer_spec=answer_spec or {}, hint=hint,
        )  # fmt: skip
        if kind == PracticeItem.Kind.OPEN:
            rubric_spec = next(rubrics)
            rubric = GradingRubric.objects.create(
                item=item, model_answer=rubric_spec["model_answer"], notes=rubric_spec.get("notes", "")
            )
            for i, (text, pts) in enumerate(rubric_spec["criteria"], start=1):
                RubricCriterion.objects.create(rubric=rubric, order=i, text=text, points=Decimal(str(pts)))


class Command(BaseCommand):
    help = "Create the practice works of the seed (idempotent; --replace rewrites unsubmitted works)."

    def add_arguments(self, parser):
        parser.add_argument("--replace", action="store_true")
        parser.add_argument("--topics", nargs="*", type=int, help="Only these topic numbers.")

    @transaction.atomic
    def handle(self, *args, replace=False, topics=None, **options):
        count = 0
        for number, specs in PRACTICES.items():
            if topics is not None and number not in topics:
                continue
            stages = Stage.objects.filter(
                topic__number=number, kind=Stage.Kind.PRACTICE, topic__module__course__slug="chemistry"
            ).order_by("order", "pk")
            for stage, spec in zip(stages, specs, strict=False):
                task, created = PracticeTask.objects.get_or_create(
                    stage=stage, defaults={"title": spec["title"], "instructions": spec["instructions"]}
                )
                count += 1
                if not task.items.exists():
                    write_items(task, spec)
                    continue
                if not replace or created:
                    continue
                if stage.practice_submissions.exists():
                    self.stdout.write(self.style.WARNING(f"«{stage.title}»: students have submitted it — kept."))
                    continue
                task.title, task.instructions = spec["title"], spec["instructions"]
                task.save(update_fields=["title", "instructions", "updated_at"])
                task.items.all().delete()
                write_items(task, spec)
        self.stdout.write(self.style.SUCCESS(f"Practice works ready: {count}"))
