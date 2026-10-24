"""The ICPAI programme: the programme on the seeded course, its 8 sections and the three diagnostic tests of
section 2 (docs/icpai/SPEC.md §0, §2.2).

Run after seed_course. Safe on every deploy: missing sections are added; existing ones keep the texts and
pass marks an administrator may have edited, unless --replace (then titles, kinds, texts and anchors come
from _icpai/ again). A diagnostic test somebody has taken keeps its questions (research data); only its texts
are rewritten by --replace. Student enrolments are made lazily when students open their cabinet.
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.assessments.models import Choice, Question, Quiz
from apps.courses.models import Course
from apps.programme.models import DiagnosticTest, Programme, Section

from ._icpai import COURSE_SLUG, PROGRAMME, SECTIONS
from ._icpai.diagnostics import DIAGNOSTICS


class Command(BaseCommand):
    help = "Create the ICPAI programme and its sections on the seeded course."

    def add_arguments(self, parser):
        parser.add_argument("--replace", action="store_true", help="Rewrite the section texts from the code.")

    @transaction.atomic
    def handle(self, *args, replace=False, verbosity=1, **options):
        course = Course.objects.filter(slug=COURSE_SLUG).first()
        if course is None:
            raise CommandError(f"Course «{COURSE_SLUG}» not found — run seed_course first.")
        programme, _created = Programme.objects.get_or_create(
            slug=PROGRAMME["slug"], defaults={"title": PROGRAMME["title"], "course": course}
        )
        added = 0
        for number, kind, title, purpose, anchor in SECTIONS:
            values = {"kind": kind, "title": title, "purpose": purpose, "guide_anchor": anchor}
            section, made = Section.objects.get_or_create(programme=programme, number=number, defaults=values)
            added += made
            if replace and not made:
                for field, value in values.items():
                    setattr(section, field, value)
                section.save()
        section = programme.sections.filter(kind=Section.Kind.DIAGNOSTIC).order_by("number").first()
        notes = self.seed_diagnostics(section, replace) if section else []
        for note in notes:
            self.stdout.write(self.style.WARNING(note))
        if verbosity:
            self.stdout.write(
                self.style.SUCCESS(f"Programme «{programme.title}» is ready: {len(SECTIONS)} sections ({added} new).")
            )

    def seed_diagnostics(self, section, replace) -> list[str]:
        """The tests I, II, III of the diagnostic section: quiz, 10 single-choice questions (1 point each, with the
        ICPAI component), options in the guide's order; the stage texts and level interpretations."""
        notes = []
        for phase, data in DIAGNOSTICS.items():
            texts = {
                "stage_name": data["stage"], "note": data["note"], "title": data["title"], "aim": data["aim"],
                "levels": data["levels"],
            }  # fmt: skip
            test = DiagnosticTest.objects.filter(section=section, phase=phase).select_related("quiz").first()
            if test is None:
                quiz = Quiz.objects.create(
                    title=data["stage"], kind=Quiz.Kind.DIAGNOSTIC, pass_percent=0, max_attempts=1,
                    shuffle_questions=False, shuffle_choices=False, show_answers_after=False, instant_feedback=False,
                )  # fmt: skip
                self.fill(quiz, data["questions"])
                DiagnosticTest.objects.create(section=section, phase=phase, quiz=quiz, **texts)
                continue
            if not replace:
                continue
            for field, value in texts.items():
                setattr(test, field, value)
            test.save()
            if test.quiz.attempts.exists():
                notes.append(f"Diagnostics {phase}: students have taken it — the questions are kept.")
            else:
                test.quiz.questions.all().delete()
                self.fill(test.quiz, data["questions"])
        return notes

    @staticmethod
    def fill(quiz, questions):
        for order, (text, component, options) in enumerate(questions, start=1):
            question = Question.objects.create(
                quiz=quiz, order=order, kind=Question.Kind.SINGLE, text=text, points=1, component=component
            )
            Choice.objects.bulk_create(
                Choice(question=question, order=i, text=option, is_correct=correct)
                for i, (option, correct) in enumerate(options, start=1)
            )
