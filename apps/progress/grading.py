"""Kazakhstan credit grading scale (ARCHITECTURE §3.7). A code constant on purpose: the scale is
normative and must not change while the pedagogical experiment runs (decision D4)."""

from dataclasses import dataclass
from decimal import Decimal

from django.utils.functional import Promise
from django.utils.translation import gettext_lazy as _


@dataclass(frozen=True)
class Grade:
    min_percent: int
    letter: str
    gpa: Decimal
    traditional: str | Promise


EXCELLENT, GOOD, SATISFACTORY, FAIL = _("Excellent"), _("Good"), _("Satisfactory"), _("Unsatisfactory")

SCALE = (
    Grade(95, "A", Decimal("4.00"), EXCELLENT),
    Grade(90, "A-", Decimal("3.67"), EXCELLENT),
    Grade(85, "B+", Decimal("3.33"), GOOD),
    Grade(80, "B", Decimal("3.00"), GOOD),
    Grade(75, "B-", Decimal("2.67"), GOOD),
    Grade(70, "C+", Decimal("2.33"), SATISFACTORY),
    Grade(65, "C", Decimal("2.00"), SATISFACTORY),
    Grade(60, "C-", Decimal("1.67"), SATISFACTORY),
    Grade(55, "D+", Decimal("1.33"), SATISFACTORY),
    Grade(50, "D", Decimal("1.00"), SATISFACTORY),
    Grade(0, "F", Decimal("0.00"), FAIL),
)


def grade_for(percent) -> Grade:
    """Band of a 0–100 score. Scores are compared after rounding to a whole percent (94.6 → 95 → A)."""
    value = Decimal(str(percent)).quantize(Decimal("1"), rounding="ROUND_HALF_UP")
    for grade in SCALE:
        if value >= grade.min_percent:
            return grade
    return SCALE[-1]
