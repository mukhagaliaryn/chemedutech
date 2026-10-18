"""Create or update the course from the content in ``_content/`` (the author's materials, in Kazakh).

Without options the command only adds what is missing (idempotent, safe on every deploy). With ``--replace`` it
also brings existing objects in line with the content: course/topic/stage texts, theory bodies and the questions
of quizzes nobody has attempted. Quizzes with attempts and stages are never deleted; practice works:
apps.practice seed_practice (called with the same option).
"""

from django.apps import apps
from django.core.management import call_command
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.assessments.models import Quiz
from apps.courses.models import Course, Module, Stage, Topic
from apps.courses.services import ensure_stage_content

from ._content import CONTENT, COURSE, MODULE_1_TOPICS, MODULES, TOPIC_COUNT, TOPICS
from ._seed_quizzes import sync_quiz


class Command(BaseCommand):
    help = "Create the ChemEduTech course from the seed content (idempotent; --replace updates existing content)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--replace",
            action="store_true",
            help="Update existing texts and rewrite quizzes and practice works that no student has answered yet.",
        )
        parser.add_argument(
            "--topics", nargs="*", type=int, help="Build the content of these topic numbers only (tests use 1)."
        )

    @transaction.atomic
    def handle(self, *args, replace=False, topics=None, **options):
        self.replace = replace
        self.content = {n: c for n, c in CONTENT.items() if not topics or n in topics}
        self.notes = []
        course, created = Course.objects.get_or_create(
            slug=COURSE["slug"],
            defaults={
                **{k: v for k, v in COURSE.items() if k != "slug"},
                "status": Course.Status.PUBLISHED,
                "enrollment_mode": Course.EnrollmentMode.OPEN,
            },
        )
        if replace and not created:
            Course.objects.filter(pk=course.pk).update(
                title=COURSE["title"], short_description=COURSE["short_description"]
            )
        modules = {}
        for order, title in MODULES:
            module, made = Module.objects.get_or_create(course=course, order=order, defaults={"title": title})
            if replace and not made and module.title != title:
                module.title = title
                module.save(update_fields=["title", "updated_at"])
            modules[order] = module

        for n in range(1, max(TOPIC_COUNT, max(TOPICS)) + 1):
            self._topic(course, modules, n)

        if apps.is_installed("apps.practice"):  # a higher layer: called by name, not imported
            call_command("seed_practice", replace=replace, topics=list(self.content), verbosity=options["verbosity"])
        for note in self.notes:
            self.stdout.write(self.style.WARNING(note))
        published = Topic.objects.filter(module__course=course, is_published=True).count()
        self.stdout.write(self.style.SUCCESS(f"Course «{course.slug}» is ready: {published} published topics."))

    # --- topics and stages ----------------------------------------------------------------

    def _topic(self, course, modules, n):
        module_order, title, summary = TOPICS.get(n, (1 if n <= MODULE_1_TOPICS else 2, f"{n}-тақырып", ""))
        content = self.content.get(n)
        module = modules[module_order]
        order = n if module_order == 1 else n - MODULE_1_TOPICS
        topic = Topic.objects.filter(module__course=course, number=n).first()
        fresh = topic is None
        if fresh:
            topic = Topic.objects.create(
                module=module, number=n, order=order, title=title, summary=summary, is_published=False
            )
        elif self.replace:
            topic.title, topic.summary = title, summary
            topic.save(update_fields=["title", "summary", "updated_at"])
        if content is None:
            return
        if fresh or self.replace:  # a topic the teacher unpublished stays unpublished on a plain run
            topic.estimated_minutes = content.MINUTES
            topic.is_published = True
            topic.save(update_fields=["estimated_minutes", "is_published", "updated_at"])
        self._stages(topic, content.STAGES)

    def _stages(self, topic, specs):
        """Stages are matched by kind and position within the kind (the 2nd practice spec ↔ the 2nd practice stage),
        so re-ordering never changes the kind of a stage students have worked on. Extra stages are kept."""
        existing = {}
        for stage in topic.stages.order_by("order", "pk"):
            existing.setdefault(stage.kind, []).append(stage)
        seen = {}
        ordered = []
        for spec in specs:
            kind = spec["kind"]
            index = seen.get(kind, 0)
            seen[kind] = index + 1
            pool = existing.get(kind, [])
            stage = pool[index] if index < len(pool) else None
            if stage is None:
                stage = Stage.objects.create(topic=topic, kind=kind, title=spec["title"], order=1000 + len(ordered))
                fresh = True
            else:
                fresh = False
            if fresh or self.replace:
                stage.title = spec["title"]
                stage.pass_percent = spec.get("pass_percent", 60)
                stage.save(update_fields=["title", "pass_percent", "updated_at"])
            self._content(stage, spec, fresh)
            ordered.append(stage)
        if self.replace or any(s.order >= 1000 for s in ordered):
            extras = [s for kind, pool in existing.items() for s in pool[seen.get(kind, 0) :]]
            for order, stage in enumerate([*ordered, *extras], start=1):
                if stage.order != order:
                    Stage.objects.filter(pk=stage.pk).update(order=order)
            for stage in extras:
                self.notes.append(
                    f"Topic {topic.number}: stage «{stage.title}» is not in the content; kept at the end."
                )

    def _content(self, stage, spec, fresh):
        fields = dict(spec.get("content") or {})
        current = getattr(stage, "content", None)
        if not (fresh or self.replace) and current is not None:
            fields = {k: v for k, v in fields.items() if not getattr(current, k, None)}  # fill blanks only
        ensure_stage_content(stage, **fields)
        if spec.get("checkpoint"):
            title, questions = spec["checkpoint"]
            quiz, result = sync_quiz(
                stage.checkpoint_quiz, Quiz.Kind.CHECKPOINT, title, questions, replace=self.replace
            )
            self._note(stage, result)
            if stage.checkpoint_quiz_id != quiz.pk:
                stage.checkpoint_quiz = quiz
                stage.save(update_fields=["checkpoint_quiz", "updated_at"])
        if spec.get("test"):
            title, questions = spec["test"]
            test = stage.test_content
            quiz, result = sync_quiz(
                test.quiz, Quiz.Kind.TOPIC_TEST, title, questions, spec.get("test_settings"), replace=self.replace
            )
            self._note(stage, result)
            if test.quiz_id != quiz.pk:
                test.quiz = quiz
                test.save(update_fields=["quiz", "updated_at"])

    def _note(self, stage, result):
        if result == "attempted":
            self.notes.append(f"Stage «{stage.title}»: students have attempted its quiz — the questions are kept.")
