from django.db import models

from .models import PracticeSubmission

S = PracticeSubmission.Status


def finished_submissions(enrollment):
    """Graded or waiting-for-review submissions of one enrolment, newest first."""
    return (
        PracticeSubmission.objects.filter(enrollment=enrollment, status__in=(S.GRADED, S.NEEDS_REVIEW))
        .select_related("stage")
        .order_by("-graded_at", "-pk")
    )


def submission_counts(enrollment) -> dict[int, int]:
    """{stage_id: attempts used} — returned works are given back and do not count."""
    counts = {}
    qs = PracticeSubmission.objects.filter(enrollment=enrollment).exclude(status=S.RETURNED)
    for stage_id in qs.values_list("stage_id", flat=True):
        counts[stage_id] = counts.get(stage_id, 0) + 1
    return counts


def teacher_comments(enrollment, limit=3):
    """Latest submissions the teacher wrote a comment on."""
    return (
        PracticeSubmission.objects.filter(enrollment=enrollment)
        .exclude(teacher_comment="")
        .select_related("stage__topic__module__course", "graded_by")
        .order_by("-updated_at", "-pk")[:limit]
    )


def awaiting_review(enrollment_ids):
    """The teacher's queue: works the AI could not grade with confidence, oldest first."""
    return (
        PracticeSubmission.objects.filter(enrollment_id__in=enrollment_ids, status=S.NEEDS_REVIEW)
        .select_related("enrollment__student", "enrollment__group", "stage__topic__module__course")
        .order_by("submitted_at", "pk")
    )


def submissions_of(enrollment):
    return (
        PracticeSubmission.objects.filter(enrollment=enrollment)
        .select_related("stage__topic")
        .order_by("-submitted_at", "-pk")
    )


def last_submission_times(enrollment_ids) -> dict[int, object]:
    from django.db.models import Max

    rows = (
        PracticeSubmission.objects.filter(enrollment_id__in=enrollment_ids)
        .values("enrollment_id")
        .annotate(at=Max("submitted_at"))
    )
    return {r["enrollment_id"]: r["at"] for r in rows}


SAMPLE = "sample"
QUEUE_STATUSES = (S.NEEDS_REVIEW, SAMPLE, S.GRADED, S.RETURNED)


def grading_queue(enrollment_ids, status=S.NEEDS_REVIEW):
    """needs_review — the queue (oldest first); graded — AI-graded works not yet seen by a teacher (spot check);
    returned — works sent back."""
    if status == SAMPLE:  # drawn for the spot-check and not confirmed yet
        return (
            PracticeSubmission.objects.filter(enrollment_id__in=enrollment_ids, status=S.GRADED, teacher_override=False)
            .exclude(sampled_at=None)
            .select_related("enrollment__student", "enrollment__group", "stage__topic__module__course")
            .order_by("sampled_at", "pk")
        )
    qs = PracticeSubmission.objects.filter(enrollment_id__in=enrollment_ids, status=status).select_related(
        "enrollment__student", "enrollment__group", "stage__topic__module__course", "graded_by"
    )
    if status == S.GRADED:
        qs = qs.filter(teacher_override=False, answers__item__kind="open").distinct()
        return qs.order_by("-graded_at", "-pk")
    if status == S.RETURNED:
        return qs.order_by("-updated_at", "-pk")
    return qs.order_by("submitted_at", "pk")


def review_rows(submission) -> list[dict]:
    """Answers of a submission for the grading page; open answers carry the rubric, the AI grade and the last review."""
    from .models import AIGrade, TeacherReview

    rows = []
    answers = submission.answers.select_related("item__rubric").order_by("item__order", "item__pk")
    for answer in answers:
        row = {"answer": answer, "item": answer.item, "open": answer.item.kind == "open"}
        if row["open"]:
            grade = AIGrade.objects.filter(answer=answer).first()
            review = TeacherReview.objects.filter(answer=answer).order_by("-created_at", "-pk").first()
            ai = {c.get("criterion_id"): c for c in (grade.criteria_scores if grade else [])}
            given = {c.get("criterion_id"): c.get("points") for c in (review.criteria_scores if review else [])}
            rubric = getattr(answer.item, "rubric", None)
            criteria = []
            if rubric is not None:
                for c in rubric.criteria.order_by("order", "pk"):
                    suggestion = ai.get(c.pk, {})
                    value = given.get(c.pk, suggestion.get("points"))
                    criteria.append(
                        {"criterion": c, "ai_points": suggestion.get("points"), "reason": suggestion.get("reason", ""),
                         "value": value}
                    )  # fmt: skip
            row.update({"grade": grade, "review": review, "rubric": rubric, "criteria": criteria})
        rows.append(row)
    return rows


def submissions_by_day(enrollment_ids, days: int = 7) -> list[int]:
    """Works sent on each of the last ``days`` local days (oldest first) — the teacher's queue trend."""
    from datetime import timedelta

    from django.db.models.functions import TruncDate
    from django.utils import timezone

    today = timezone.localdate()
    start = today - timedelta(days=days - 1)
    counts = dict(
        PracticeSubmission.objects.filter(enrollment_id__in=enrollment_ids, submitted_at__date__gte=start)
        .annotate(day=TruncDate("submitted_at", tzinfo=timezone.get_current_timezone()))
        .values("day")
        .annotate(n=models.Count("pk"))
        .values_list("day", "n")
    )
    return [counts.get(start + timedelta(days=i), 0) for i in range(days)]
