from decimal import Decimal

from ..models import Portfolio
from ..portfolio_selectors import completeness
from .base import Provider


class PortfolioProvider(Provider):
    """Section 7 — the professional portfolio (guide @S7; SPEC §3): a quarter each for the reflection (seven answers),
    the development map (five directions), the portfolio assembled and submitted to the teacher, and the teacher's
    status «Accepted». Without «Accepted» the section stays at 75 % and does not pass."""

    def percent(self, enrollment, section) -> Decimal:
        state = completeness(enrollment)
        portfolio = Portfolio.objects.filter(enrollment=enrollment).first()
        parts = [
            state["reflection"],
            state["plan"],
            bool(portfolio and portfolio.submitted_at),
            bool(portfolio and portfolio.status == Portfolio.Status.ACCEPTED),
        ]
        return Decimal(25 * sum(parts))
