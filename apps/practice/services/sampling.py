"""Random spot-check of AI grades (ARCHITECTURE §5.6): the teacher re-grades a share of AI-graded works."""

import math
import random

from django.db import transaction
from django.utils import timezone

from ..models import PracticeSubmission

S = PracticeSubmission.Status


def ai_graded(enrollment_ids):
    """Works graded with an AI part (an open answer with an AI grade), whatever the teacher did later."""
    return PracticeSubmission.objects.filter(
        enrollment_id__in=enrollment_ids, status=S.GRADED, answers__ai_grade__isnull=False
    ).distinct()


@transaction.atomic
def draw_review_sample(enrollment_ids, percent: int, rng: random.Random | None = None) -> int:
    """Mark works for a check until ``percent`` of the AI-graded ones are in the sample. Returns how many were added.

    Works a teacher already confirmed are not drawn (their grade is already checked).
    """
    population = ai_graded(enrollment_ids)
    target = math.ceil(population.count() * max(0, min(percent, 100)) / 100)
    already = population.exclude(sampled_at=None).count()
    pool = list(population.filter(sampled_at=None, teacher_override=False).values_list("pk", flat=True))
    need = max(0, min(target - already, len(pool)))
    chosen = (rng or random.SystemRandom()).sample(sorted(pool), need)
    PracticeSubmission.objects.filter(pk__in=chosen).update(sampled_at=timezone.now())
    return need
