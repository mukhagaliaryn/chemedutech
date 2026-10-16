"""Score of one lab attempt by the lab's formula (LabSpec.scoring, ARCHITECTURE §5.4)."""

from decimal import ROUND_HALF_UP, Decimal

from .engine.spec import LabScoring


def attempt_score(attempt, scoring: LabScoring) -> Decimal:
    process = max(
        0.0,
        100
        - scoring.order_error_penalty * attempt.order_errors
        - scoring.safety_warning_penalty * attempt.safety_warnings
        - scoring.wrong_penalty * (attempt.wrong_items + attempt.wrong_choices),
    )
    parts = [(scoring.weight_process, process)]
    if attempt.journal_total:
        parts.append((scoring.weight_journal, 100 * attempt.journal_correct / attempt.journal_total))
    if attempt.analysis_total:
        parts.append((scoring.weight_analysis, 100 * attempt.analysis_correct / attempt.analysis_total))
    total_weight = sum(w for w, _ in parts) or 1
    score = sum(w * s for w, s in parts) / total_weight
    return Decimal(str(score)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
