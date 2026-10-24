from decimal import ROUND_HALF_UP, Decimal


def share(done: int, total: int) -> Decimal:
    """done / total as a percent with 2 decimals (0 for an empty section)."""
    if total <= 0:
        return Decimal(0)
    value = Decimal(min(done, total) * 100) / Decimal(total)
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


class Provider:
    ready = True

    def percent(self, enrollment, section) -> Decimal:
        """How much of ``section`` the programme enrolment has done, 0–100."""
        raise NotImplementedError


class Upcoming(Provider):
    """A section kind that is not built yet: nothing to do, nothing done."""

    ready = False

    def percent(self, enrollment, section) -> Decimal:
        return Decimal(0)
