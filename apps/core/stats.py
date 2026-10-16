"""Descriptive statistics for the research pages — standard library only.

Significance tests (t-test, Mann–Whitney) are left to the exported CSV and a statistics package;
here: n, mean, median, Pearson r and Cohen's kappa.
"""

import statistics
from collections import Counter
from decimal import Decimal


def _floats(values):
    return [float(v) for v in values if v is not None]


def describe(values) -> dict:
    """{"n", "mean", "median"} (None when there is no value)."""
    xs = _floats(values)
    if not xs:
        return {"n": 0, "mean": None, "median": None}
    return {"n": len(xs), "mean": statistics.fmean(xs), "median": statistics.median(xs)}


def share(flags) -> dict:
    """{"n", "yes", "rate" (0..100)} of booleans."""
    flags = [bool(f) for f in flags]
    if not flags:
        return {"n": 0, "yes": 0, "rate": None}
    yes = sum(flags)
    return {"n": len(flags), "yes": yes, "rate": yes / len(flags) * 100}


def pearson(xs, ys) -> float | None:
    """Pearson r of paired values; None for fewer than 3 pairs or no variance."""
    pairs = [(float(x), float(y)) for x, y in zip(xs, ys, strict=True) if x is not None and y is not None]
    if len(pairs) < 3:
        return None
    a, b = zip(*pairs, strict=True)
    try:
        return statistics.correlation(a, b)
    except statistics.StatisticsError:
        return None


def cohen_kappa(pairs) -> float | None:
    """Unweighted Cohen's kappa for two raters: pairs of category labels (rater A, rater B).

    κ = (p_o − p_e) / (1 − p_e). Returns 1.0 when both raters always agree on one category, None without pairs.
    """
    pairs = [(str(a), str(b)) for a, b in pairs]
    n = len(pairs)
    if not n:
        return None
    observed = sum(1 for a, b in pairs if a == b) / n
    left, right = Counter(a for a, _ in pairs), Counter(b for _, b in pairs)
    expected = sum(left[c] * right[c] for c in set(left) | set(right)) / (n * n)
    if expected == 1:
        return 1.0
    return (observed - expected) / (1 - expected)


def label(points) -> str:
    """A category label for a criterion score: 0, 0.5, 1 … (stable text for kappa)."""
    return format(Decimal(str(points)).normalize(), "f")
