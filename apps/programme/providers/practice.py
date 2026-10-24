from decimal import Decimal

from apps.pedagogy.models import Lesson, LessonTemplate

from .base import Provider, share


class ResearchPracticeProvider(Provider):
    """Section 5 — the digital research practice (guide @S5): one practice per authorial template; a practice counts
    when its sheet is filled, its trial with the AI student finished and its results gathered (each ≈ 33 %).
    The teacher's 10-point grade does not count here (@S5 VII)."""

    def percent(self, enrollment, section) -> Decimal:
        templates = LessonTemplate.objects.filter(is_active=True)
        done = (
            Lesson.objects.filter(
                owner_id=enrollment.student_id,
                kind=Lesson.Kind.RESEARCH_PRACTICE,
                source_template__in=templates,
                status=Lesson.Status.FINAL,
            )
            .values("source_template")
            .distinct()
            .count()
        )
        return share(done, templates.count())
