from decimal import Decimal

from apps.pedagogy.models import Lesson, LessonTemplate

from .base import Provider, share


class DesignerProvider(Provider):
    """Section 4 — the lesson design constructor (guide @S4): the share of the authorial templates the student has
    taken to the end: at least one stage redesigned and the final version assembled (each template ≈ 33 %)."""

    def percent(self, enrollment, section) -> Decimal:
        templates = LessonTemplate.objects.filter(is_active=True)
        done = (
            Lesson.objects.filter(
                owner_id=enrollment.student_id,
                kind=Lesson.Kind.TEMPLATE_COPY,
                source_template__in=templates,
                status=Lesson.Status.FINAL,
                stages__edited=True,
            )
            .values("source_template")
            .distinct()
            .count()
        )
        return share(done, templates.count())
