from decimal import Decimal

from apps.pedagogy.models import Lesson

from .base import Provider


class IndependentProvider(Provider):
    """Section 8 — the independent authorial lesson (guide @S8): the last section, so its percent is an indicator — one
    completed cycle (a lesson tried out and confirmed by the teacher) is 100 % (agreed with the user)."""

    def percent(self, enrollment, section) -> Decimal:
        done = Lesson.objects.filter(
            owner_id=enrollment.student_id, kind=Lesson.Kind.INDEPENDENT, status=Lesson.Status.FINAL
        ).exists()
        return Decimal(100 if done else 0)
