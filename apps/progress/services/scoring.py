"""Score arithmetic (ARCHITECTURE §5). Pure functions over model instances, no queries."""

from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal

from apps.courses.models import DEFAULT_STAGE_KIND_WEIGHTS

HUNDRED = Decimal("100")


def q2(value) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def stage_weights(course, stages) -> dict[int, Decimal]:
    """Weights of the required stages of one topic (§5.2).

    A kind's share (course.stage_kind_weights, defaults for missing kinds) is split between the stages of that
    kind in proportion to Stage.weight — the stage's relative weight within its kind (default 1: equal parts).
    Kinds absent from the topic simply do not appear, so dividing by the total later normalises the rest.
    """
    shares = {**DEFAULT_STAGE_KIND_WEIGHTS, **(course.stage_kind_weights or {})}
    required = [s for s in stages if s.is_required]
    kind_total = defaultdict(Decimal)
    for s in required:
        kind_total[s.kind] += Decimal(s.weight)
    weights = {}
    for s in required:
        total = kind_total[s.kind]
        share = Decimal(str(shares.get(s.kind, 0)))
        weights[s.pk] = share * Decimal(s.weight) / total if total else Decimal(0)
    return weights


def weighted_average(pairs) -> Decimal | None:
    """pairs: [(weight, score)]. Equal weights when every weight is 0; None when there is nothing to average."""
    pairs = [(Decimal(w), Decimal(s)) for w, s in pairs]
    if not pairs:
        return None
    total = sum(w for w, _ in pairs)
    if total == 0:
        return q2(sum(s for _, s in pairs) / len(pairs))
    return q2(sum(w * s for w, s in pairs) / total)
