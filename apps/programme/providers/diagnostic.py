from decimal import Decimal

from ..models import DiagnosticResult
from .base import Provider, share


class DiagnosticProvider(Provider):
    """Section 2 — the diagnostics: the share of its stages (I, II, III) taken. The scores do not count — a starting
    diagnostic with an 80 % score demanded would turn the experiment upside down; all stages must be taken (D71)."""

    def percent(self, enrollment, section) -> Decimal:
        phases = list(section.diagnostic_tests.values_list("phase", flat=True))
        done = DiagnosticResult.objects.filter(enrollment=enrollment, phase__in=phases).values("phase").distinct()
        return share(done.count(), len(phases))
