"""Score arithmetic (ARCHITECTURE §5). Pure functions over model instances, no queries."""

from collections import Counter
from decimal import ROUND_HALF_UP, Decimal

from apps.courses.models import DEFAULT_STAGE_KIND_WEIGHTS

HUNDRED = Decimal("100")


def q2(value) -> Decimal:
    return Decimal(value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def stage_weights(course, stages) -> dict[int, Decimal]:
    """Weights of the required stages of one topic (§5.2).

    A kind's share (course.stage_kind_weights, defaults for missing kinds) is split equally between the
    stages of that kind; Stage.weight set by the author wins. Kinds absent from the topic simply do not
    appear, so dividing by the total later normalises the rest.
    """
    shares = {**DEFAULT_STAGE_KIND_WEIGHTS, **(course.stage_kind_weights or {})}
    required = [s for s in stages if s.is_required]
    auto_count = Counter(s.kind for s in required if s.weight is None)
    weights = {}
    for s in required:
        if s.weight is not None:
            weights[s.pk] = Decimal(s.weight)
        else:
            weights[s.pk] = Decimal(str(shares.get(s.kind, 0))) / auto_count[s.kind]
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
