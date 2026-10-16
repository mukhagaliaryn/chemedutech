"""Context builders for the cabinet pages: dashboard, gradebook, certificates (reads only, ARCHITECTURE §8)."""

from decimal import Decimal

from django.db.models import F, Max
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from apps.assessments import selectors as quiz_selectors
from apps.courses.models import Course, Enrollment
from apps.courses.selectors import stages_of
from apps.feedback import selectors as notification_selectors
from apps.labs import selectors as lab_selectors
from apps.labs.engine import get_lab
from apps.practice import selectors as practice_selectors
from apps.progress import selectors as progress_selectors
from apps.progress.grading import SCALE, grade_for
from apps.progress.services import lab_experiments
from apps.progress.services.scoring import stage_weights

from . import learning
from .learning import S

RECENT = 5


def enrollments_of(user) -> list[Enrollment]:
    """The student's courses, the one worked on most recently first."""
    return list(
        Enrollment.objects.filter(student=user)
        .exclude(status=Enrollment.Status.DROPPED)
        .exclude(course__status=Course.Status.DRAFT)
        .select_related("course", "group")
        .annotate(last_activity=Max("stage_progress__updated_at"))
        .order_by(F("last_activity").desc(nulls_last=True), "-created_at")
    )


def pick(enrollments, course_slug=None) -> Enrollment | None:
    """?course=<slug> or the most recent course."""
    return next((e for e in enrollments if e.course.slug == course_slug), enrollments[0] if enrollments else None)


def place_of(enrollment) -> learning.Place:
    place = learning.Place(enrollment.course, enrollment, preview=False)
    place.progress = progress_selectors.stage_progress_map(enrollment)
    return place


def duration(seconds: int) -> str:
    hours, minutes = divmod(int(seconds) // 60, 60)
    if hours:
        return _("%(h)s h %(m)s min") % {"h": hours, "m": minutes}
    return _("%(m)s min") % {"m": minutes}


# --- stages ---------------------------------------------------------------------------


def _quiz_of(stage):
    if stage.kind == "test":
        content = getattr(stage, "test_content", None)
        return content.quiz if content else None
    return stage.checkpoint_quiz


def _lab_rows(place, stage):
    return lab_experiments(place.enrollment, stage) if stage.kind == "lab" else []


def stage_meta(place, stage, status) -> str:
    """Short state line under a stage tile: «Passed · 100%», «2 / 4 experiments», «Locked» …"""
    sp = place.progress.get(stage.pk)
    if status == S.PASSED:
        if sp and sp.score_percent is not None:
            return _("Passed · %(score)s%%") % {"score": f"{sp.score_percent:.0f}"}
        return _("Passed")
    if status == S.LOCKED:
        return _("Locked")
    if status == S.AWAITING_CHECK:
        return _("Awaiting check")
    if stage.kind == "lab":
        rows = _lab_rows(place, stage)
        if rows:
            done = sum(1 for r in rows if r["done"])
            return ngettext("%(a)s / %(b)s experiment", "%(a)s / %(b)s experiments", len(rows)) % {
                "a": done,
                "b": len(rows),
            }
    if status == S.IN_PROGRESS:
        return _("In progress")
    return _("Open")


def grading_method(stage) -> str:
    if stage.kind in ("theory", "video"):
        quiz = stage.checkpoint_quiz
        if quiz is None:
            return _("Reading the material") if stage.kind == "theory" else _("Watching the video")
        n = quiz.questions_per_attempt or quiz.questions.count()
        return ngettext("Checkpoint quiz (%(n)s question)", "Checkpoint quiz (%(n)s questions)", n) % {"n": n}
    if stage.kind == "lab":
        content = stage.content
        lab = get_lab(content.lab_key) if content else None
        if lab is None:
            return _("Automatic")
        sc = lab.scoring
        return _("Automatic: process %(p)s%% · journal %(j)s%% · analysis %(a)s%%") % {
            "p": f"{sc.weight_process * 100:.0f}",
            "j": f"{sc.weight_journal * 100:.0f}",
            "a": f"{sc.weight_analysis * 100:.0f}",
        }
    if stage.kind == "practice":
        return _("Automatic checks and AI, confirmed by the teacher")
    return _("Automatic")


# --- dashboard ------------------------------------------------------------------------


def continue_card(place) -> dict | None:
    stage = learning.continue_target(place)
    if stage is None:
        return None
    topic = stage.topic
    tiles = []
    for s in learning.ordered_stages(topic):
        status = learning.stage_status(place, s)
        tiles.append({"stage": s, "status": status, "meta": stage_meta(place, s, status), "current": s.pk == stage.pk})
    return {"stage": stage, "topic": topic, "module": topic.module, "tiles": tiles, "url": learning.stage_url(stage)}


def module_rows(place, course_map) -> list[dict]:
    results = progress_selectors.module_results_map(place.enrollment)
    rows, previous = [], None
    for m in course_map:
        topics = m["topics"]
        numbers = [t["topic"].number for t in topics]
        rows.append(
            {
                "module": m["module"],
                "result": results.get(m["module"].pk),
                "passed": sum(t["passed"] for t in topics),
                "required": sum(t["required"] for t in topics),
                "first": min(numbers),
                "last": max(numbers),
                "locked": all(t["status"] == "locked" for t in topics),
                "topics": len(topics),
                "started": sum(1 for t in topics if t["status"] != "locked"),
                "previous": previous,
            }
        )
        previous = m["module"]
    return rows


def lab_totals(place, course_map) -> tuple[int, int]:
    total = 0
    for m in course_map:
        for t in m["topics"]:
            for s in t["stages"]:
                if s["stage"].kind == "lab" and s["stage"].content:
                    total += len(s["stage"].content.experiment_specs())
    return lab_selectors.analysed_experiment_count(place.enrollment), total


def recent_results(enrollment, limit=RECENT) -> list[dict]:
    """Quizzes, lab experiments and practice works of the course, newest first."""
    items = []
    for a in quiz_selectors.finished_attempts(enrollment)[:limit]:
        items.append(
            {
                "icon": "test",
                "title": a.quiz.title,
                "meta": _("Quiz · attempt %(n)s") % {"n": a.attempt_no},
                "at": a.finished_at,
                "percent": a.percent,
                "variant": "success" if a.passed else "warning",
            }
        )
    for a in lab_selectors.recent_analysed(enrollment)[:limit]:
        lab = get_lab(a.lab_key)
        spec = lab.experiment(a.experiment_key) if lab else None
        meta = _("Lab")
        if a.safety_warnings:
            meta += " · " + ngettext("%(n)s safety warning", "%(n)s safety warnings", a.safety_warnings) % {
                "n": a.safety_warnings
            }
        items.append(
            {
                "icon": "lab",
                "title": f"{spec.number}. {spec.title}" if spec else a.experiment_key,
                "meta": meta,
                "at": a.finished_at,
                "percent": a.score_percent,
                "variant": "success" if (a.score_percent or 0) >= 50 else "warning",
            }
        )
    for sub in practice_selectors.finished_submissions(enrollment)[:limit]:
        waiting = sub.status == sub.Status.NEEDS_REVIEW
        items.append(
            {
                "icon": "practice",
                "title": sub.stage.title,
                "meta": _("Practice · attempt %(n)s") % {"n": sub.attempt_no},
                "at": sub.graded_at or sub.submitted_at,
                "percent": sub.percent,
                "variant": "info" if waiting else ("success" if sub.percent >= sub.stage.pass_percent else "warning"),
                "note": _("Awaiting check") if waiting else "",
            }
        )
    items.sort(key=lambda i: i["at"], reverse=True)
    return items[:limit]


def teacher_comments(enrollment, limit=3) -> list[dict]:
    """Comments of teachers on the student's works and the comments written with a grade, newest first."""
    items = [
        {"author": c.author, "stage": c.stage, "body": c.body, "at": c.created_at}
        for c in notification_selectors.latest_for_student(enrollment, limit)
    ]
    items += [
        {"author": s.graded_by, "stage": s.stage, "body": s.teacher_comment, "at": s.updated_at}
        for s in practice_selectors.teacher_comments(enrollment, limit)
    ]
    items.sort(key=lambda i: i["at"], reverse=True)
    return items[:limit]


def dashboard(user, enrollment) -> dict:
    place = place_of(enrollment)
    course_map = learning.course_map(place)
    result = progress_selectors.course_result(enrollment)
    card = continue_card(place)
    current_topic = None
    if card:
        current_topic = next((t for m in course_map for t in m["topics"] if t["topic"].pk == card["topic"].pk), None)
    labs_done, labs_total = lab_totals(place, course_map)
    return {
        "enrollment": enrollment,
        "course": enrollment.course,
        "result": result,
        "grade": grade_for(result.current_percent) if result and result.current_percent is not None else None,
        "card": card,
        "current_topic": current_topic,
        "modules": module_rows(place, course_map),
        "labs_done": labs_done,
        "labs_total": labs_total,
        "time_spent": duration(progress_selectors.time_spent_s(enrollment)),
        "recent": recent_results(enrollment),
        "comments": teacher_comments(enrollment),
        "notifications": notification_selectors.recent(user, 3, unread_only=True),
    }


# --- gradebook ------------------------------------------------------------------------


def _attempts(place, stage, quiz_counts, practice_counts) -> str:
    if stage.kind == "lab":
        rows = _lab_rows(place, stage)
        if rows:
            return ngettext("%(a)s / %(b)s experiment", "%(a)s / %(b)s experiments", len(rows)) % {
                "a": sum(1 for r in rows if r["done"]),
                "b": len(rows),
            }
        return "—"
    if stage.kind == "practice":
        n = practice_counts.get(stage.pk, 0)
    else:
        quiz = _quiz_of(stage)
        n = quiz_counts.get(quiz.pk, 0) if quiz else 0
    return str(n) if n else "—"


def topic_table(place, topic, quiz_counts, practice_counts) -> list[dict]:
    stages = list(stages_of(topic).order_by("order", "pk"))
    weights = stage_weights(place.course, stages)
    total = sum(weights.values())
    rows = []
    for s in stages:
        status = learning.stage_status(place, s)
        sp = place.progress.get(s.pk)
        weight = weights.get(s.pk)
        rows.append(
            {
                "stage": s,
                "status": status,
                "method": grading_method(s),
                "weight": (weight / total * 100) if weight is not None and total else None,
                "attempts": _attempts(place, s, quiz_counts, practice_counts),
                "score": sp.score_percent if sp else None,
                "needs_attention": bool(sp and sp.needs_attention),
            }
        )
    return rows


def scale(current_letter=None) -> list[dict]:
    rows, upper = [], 100
    for grade in SCALE:
        tone = {"A": "success", "B": "info", "C": "neutral", "D": "warning", "F": "danger"}[grade.letter[0]]
        rows.append(
            {
                "letter": grade.letter,
                "range": f"{grade.min_percent}–{upper}",
                "tone": tone,
                "current": grade.letter == current_letter,
            }
        )
        upper = grade.min_percent - 1
    return rows


def gradebook(enrollment) -> dict:
    place = place_of(enrollment)
    course_map = learning.course_map(place)
    result = progress_selectors.course_result(enrollment)
    grade = grade_for(result.current_percent) if result and result.current_percent is not None else None
    quiz_counts = quiz_selectors.attempt_counts(enrollment)
    practice_counts = practice_selectors.submission_counts(enrollment)
    topics, closed = [], []
    for m in course_map:
        for t in m["topics"]:
            if t["status"] == "locked":
                closed.append(t["topic"])
            else:
                t["table"] = topic_table(place, t["topic"], quiz_counts, practice_counts)
                topics.append(t)
    return {
        "enrollment": enrollment,
        "course": enrollment.course,
        "result": result,
        "grade": grade,
        "modules": module_rows(place, course_map),
        "topics": topics,
        "closed": closed,
        "scale": scale(grade.letter if grade else None),
    }


# --- certificates -----------------------------------------------------------------------


def certificate_rows(enrollments) -> list[dict]:
    """Every course with a certificate: issued (PDF, verification link) or how far the student is from it."""
    from apps.certificates.models import Certificate
    from apps.certificates.services import verification_url

    issued = {c.enrollment_id: c for c in Certificate.objects.filter(enrollment__in=enrollments)}
    rows = []
    for e in enrollments:
        if not e.course.certificate_enabled:
            continue
        result = progress_selectors.course_result(e)
        current = result.current_percent if result else None
        rows.append(
            {
                "enrollment": e,
                "course": e.course,
                "result": result,
                "passed": bool(result and result.passed),
                "topics_completed": result.topics_completed if result else 0,
                "topics_total": result.topics_total if result else 0,
                "current": current,
                "grade": grade_for(result.score_percent) if result and result.score_percent is not None else None,
                "below_pass": current is not None and current < Decimal(e.course.passing_score),
                "certificate": issued.get(e.pk),
                "verify_url": verification_url(issued[e.pk]) if e.pk in issued else "",
            }
        )
    return rows
