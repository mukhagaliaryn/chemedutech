from decimal import Decimal

from apps.pedagogy.models import Lesson

from .base import Provider


class MicrolessonProvider(Provider):
    """Section 6 — the microlesson (guide @S6): one microlesson; done when it is assembled («Assemble the microlesson»),
    which needs at least one finished trial. The teacher's 10-point grades of the trials do not count here (@S6 VI)."""

    def percent(self, enrollment, section) -> Decimal:
        done = Lesson.objects.filter(
            owner_id=enrollment.student_id, kind=Lesson.Kind.MICROLESSON, status=Lesson.Status.FINAL
        ).exists()
        return Decimal(100 if done else 0)
