"""Context builders for the teacher cabinet (reads only). Scope always comes from courses.selectors.teaching."""

from dataclasses import dataclass, field
from datetime import timedelta
from decimal import Decimal

from django.utils import timezone
from django.utils.translation import gettext as _
from django.utils.translation import ngettext

from apps.assessments import selectors as quiz_selectors
from apps.courses import selectors as course_selectors
from apps.courses.models import Stage
from apps.labs import selectors as lab_selectors
from apps.labs.engine import get_lab
from apps.practice import selectors as practice_selectors
from apps.progress import selectors as progress_selectors
from apps.progress.models import StageProgress
from apps.progress.services import lab_experiments

S = StageProgress.Status
INACTIVE_DAYS = 7


@dataclass
class Plan:
    """A course's stages of published topics in learning order; ``position`` is the place inside the topic."""

    stages: list = field(default_factory=list)
    required: list = field(default_factory=list)


def plan_of(course) -> Plan:
    plan = Plan()
    stages = (
        Stage.objects.filter(topic__module__course=course, topic__is_published=True)
        .select_related("topic", "lab_content")
        .order_by("topic__number", "order", "pk")
    )
    position, topic_id = 0, None
    for s in stages:
        position = position + 1 if s.topic_id == topic_id else 1
        topic_id = s.topic_id
        s.position = position
        plan.stages.append(s)
        if s.is_required:
            plan.required.append(s)
    return plan


def mean(values) -> Decimal | None:
    values = [Decimal(v) for v in values if v is not None]
    return sum(values) / len(values) if values else None


def _last_activity(ids) -> dict:
    last = {}
    for source in (
        progress_selectors.last_progress_times(ids),
        lab_selectors.last_attempt_times(ids),
        quiz_selectors.last_attempt_times(ids),
        practice_selectors.last_submission_times(ids),
    ):
        for pk, at in source.items():
            if at and (pk not in last or at > last[pk]):
                last[pk] = at
    return last


def lab_title(attempt) -> str:
    lab = get_lab(attempt.lab_key)
    spec = lab.experiment(attempt.experiment_key) if lab else None
    return f"{spec.number}. {spec.title}" if spec else attempt.experiment_key


def _attention(ids, progress, plans_by_enrollment, inactive) -> dict[int, list[str]]:
    """{enrollment_id: [reason, …]} — what the teacher should look at (ARCHITECTURE §8 «struggling students»)."""
    reasons = {pk: [] for pk in ids}
    for pk, by_stage in progress.items():
        for stage in plans_by_enrollment[pk].stages:
            sp = by_stage.get(stage.pk)
            if sp and sp.needs_attention:
                reasons[pk].append(_("«%(stage)s»: passed only because the attempts ran out") % {"stage": stage.title})
    for row in quiz_selectors.repeated_failures(ids):
        reasons[row["enrollment_id"]].append(
            ngettext("Failed «%(quiz)s» %(n)s time", "Failed «%(quiz)s» %(n)s times", row["n"])
            % {"quiz": row["quiz__title"], "n": row["n"]}
        )
    for attempt in lab_selectors.risky_attempts(ids):
        reasons[attempt.enrollment_id].append(
            ngettext("%(n)s safety warning in «%(exp)s»", "%(n)s safety warnings in «%(exp)s»", attempt.safety_warnings)
            % {"n": attempt.safety_warnings, "exp": lab_title(attempt)}
        )
    for pk, days in inactive.items():
        if days is not None and days >= INACTIVE_DAYS:
            reasons[pk].append(ngettext("%(n)s day inactive", "%(n)s days inactive", days) % {"n": days})
    return reasons


def _position(enrollment, plan, by_stage) -> dict:
    """«1.3 Lab work · experiment 3», plus a flag when a practice waits for the teacher."""
    if not by_stage:  # progress rows appear on the student's first visit
        return {"text": _("Not started yet"), "stage": None, "awaiting": False}
    awaiting = any(by_stage.get(s.pk) and by_stage[s.pk].status == S.AWAITING_CHECK for s in plan.stages)
    current = next(
        (s for s in plan.stages if by_stage.get(s.pk) and by_stage[s.pk].status in (S.AVAILABLE, S.IN_PROGRESS)),
        None,
    )
    if current is None:
        done = plan.required and all(by_stage.get(s.pk) and by_stage[s.pk].status == S.PASSED for s in plan.required)
        return {"text": _("Course completed") if done else "", "stage": None, "awaiting": awaiting}
    text = f"{current.topic.number}.{current.position} {current.get_kind_display()}"
    if current.kind == "lab" and by_stage[current.pk].status == S.IN_PROGRESS:
        rows = lab_experiments(enrollment, current)
        done = sum(1 for r in rows if r["done"])
        if done < len(rows):
            text += " · " + _("experiment %(n)s") % {"n": done + 1}
    return {"text": text, "stage": current, "awaiting": awaiting}


def student_rows(enrollments, now=None) -> list[dict]:
    """One row per enrolment: where the student is, progress, score, lab errors, last activity, attention."""
    enrollments = list(enrollments)
    if not enrollments:
        return []
    now = now or timezone.now()
    ids = [e.pk for e in enrollments]
    plans = {}
    for e in enrollments:
        if e.course_id not in plans:
            plans[e.course_id] = plan_of(e.course)
    by_enrollment = {e.pk: plans[e.course_id] for e in enrollments}
    progress = progress_selectors.stage_progress_by_enrollment(ids)
    results = progress_selectors.course_results_by_enrollment(ids)
    errors = lab_selectors.error_totals(ids)
    last = _last_activity(ids)
    inactive = {}
    for e in enrollments:
        result = results.get(e.pk)
        if result and result.passed:
            inactive[e.pk] = None
        else:
            inactive[e.pk] = (now - (last.get(e.pk) or e.created_at)).days
    attention = _attention(ids, progress, by_enrollment, inactive)
    rows = []
    for e in enrollments:
        plan, by_stage = plans[e.course_id], progress[e.pk]
        result = results.get(e.pk)
        passed = sum(1 for s in plan.required if by_stage.get(s.pk) and by_stage[s.pk].status == S.PASSED)
        rows.append(
            {
                "enrollment": e,
                "student": e.student,
                "position": _position(e, plan, by_stage),
                "passed": passed,
                "total": len(plan.required),
                "share": Decimal(passed) / len(plan.required) * 100 if plan.required else None,
                "score": result.current_percent if result else None,
                "errors": errors.get(e.pk),
                "last": last.get(e.pk),
                "inactive_days": inactive[e.pk],
                "attention": attention[e.pk],
            }
        )
    return rows


def filter_rows(rows, q="", show=""):
    q = (q or "").strip().lower()
    if q:
        rows = [
            r
            for r in rows
            if q in r["student"].full_name.lower()
            or q in r["student"].username.lower()
            or q in (r["student"].email or "").lower()
        ]
    if show == "attention":
        rows = [r for r in rows if r["attention"] or r["position"]["awaiting"]]
    elif show == "inactive":
        rows = [r for r in rows if r["inactive_days"] is not None and r["inactive_days"] >= INACTIVE_DAYS]
    return rows


# --- dashboard -------------------------------------------------------------------------


def group_summaries(groups, rows) -> list[dict]:
    """Per group: members, average progress and score over the members' enrolments in the teacher's courses."""
    by_group = {}
    for r in rows:
        profile = getattr(r["student"], "student_profile", None)
        if profile and profile.group_id:
            by_group.setdefault(profile.group_id, []).append(r)
    summaries = []
    for g in groups:
        members = by_group.get(g.pk, [])
        summaries.append(
            {
                "group": g,
                "students": g.students.count(),
                "progress": mean(r["share"] for r in members),
                "score": mean(r["score"] for r in members),
            }
        )
    return summaries


def dashboard(user) -> dict:
    enrollments = list(course_selectors.teacher_enrollments(user).select_related("student__student_profile__group"))
    rows = student_rows(enrollments)
    ids = [e.pk for e in enrollments]
    now = timezone.now()
    week_ago = now - timedelta(days=7)
    queue = list(practice_selectors.awaiting_review(ids))
    first_topic, first_topic_share = None, None
    if enrollments:
        main_course = max({e.course for e in enrollments}, key=lambda c: sum(1 for e in enrollments if e.course == c))
        plan = plan_of(main_course)
        if plan.stages:
            first_topic = plan.stages[0].topic
            same = [e.pk for e in enrollments if e.course_id == main_course.pk]
            first_topic_share = Decimal(progress_selectors.completed_topic_counts(same, first_topic)) / len(same) * 100
    attention = [(r, reason) for r in rows for reason in r["attention"]]
    groups = course_selectors.teacher_groups(user).filter(is_active=True).order_by("name")
    active_series = progress_selectors.active_students_by_day(ids, 7)
    return {
        "active_series": active_series,
        "active_today": active_series[-1] if active_series else 0,
        "queue_series": practice_selectors.submissions_by_day(ids, 7),
        "courses": course_selectors.teacher_courses(user),
        "students": len({e.student_id for e in enrollments}),
        "active_week": len({r["student"].pk for r in rows if r["last"] and r["last"] >= week_ago}),
        "avg_progress": mean(r["share"] for r in rows),
        "first_topic": first_topic,
        "first_topic_share": first_topic_share,
        "avg_score": mean(r["score"] for r in rows),
        "queue": queue[:5],
        "queue_count": len(queue),
        "queue_oldest_days": (now - queue[0].submitted_at).days if queue else None,
        "attention": attention[:6],
        "attention_count": len(attention),
        "groups": group_summaries(groups, rows),
    }


# --- one student -----------------------------------------------------------------------


def time_spent(enrollment) -> str:
    from apps.student import cabinet

    return cabinet.duration(progress_selectors.time_spent_s(enrollment))


def recent_events(enrollment, limit=6):
    return progress_selectors.events_of(enrollment, limit)


def student_page(enrollment) -> dict:
    """Everything a teacher needs about one student in one course."""
    from apps.student import cabinet, learning  # the student's own gradebook builders, reused read-only

    place = cabinet.place_of(enrollment)
    quiz_counts = quiz_selectors.attempt_counts(enrollment)
    practice_counts = practice_selectors.submission_counts(enrollment)
    topics = []
    for m in learning.course_map(place):
        for t in m["topics"]:
            t["module"] = m["module"]
            t["table"] = cabinet.topic_table(place, t["topic"], quiz_counts, practice_counts)
            topics.append(t)
    row = student_rows([enrollment])[0]
    lab_attempts = list(lab_selectors.attempts_of(enrollment))
    for a in lab_attempts:
        a.title = lab_title(a)
    result = progress_selectors.course_result(enrollment)
    return {
        "row": row,
        "result": result,
        "topics": topics,
        "time_spent": cabinet.duration(progress_selectors.time_spent_s(enrollment)),
        "events": progress_selectors.events_of(enrollment),
        "lab_attempts": lab_attempts,
        "quiz_attempts": quiz_selectors.finished_attempts(enrollment),
        "submissions": practice_selectors.submissions_of(enrollment),
    }


# --- gradebook ---------------------------------------------------------------------------


def gradebook(course, enrollments) -> dict:
    """Students × topics matrix: topic score and status, module and course scores, letter (ARCHITECTURE §8)."""
    from apps.courses.models import Module, Topic
    from apps.progress.grading import grade_for

    enrollments = sorted(enrollments, key=lambda e: (e.student.last_name, e.student.first_name, e.student.username))
    ids = [e.pk for e in enrollments]
    modules = list(Module.objects.filter(course=course).order_by("order", "pk"))
    topics = list(
        Topic.objects.filter(module__course=course, is_published=True).select_related("module").order_by("number")
    )
    modules = [m for m in modules if any(t.module_id == m.pk for t in topics)]
    topic_results = progress_selectors.topic_results_by_enrollment(ids)
    module_results = progress_selectors.module_results_by_enrollment(ids)
    course_results = progress_selectors.course_results_by_enrollment(ids)
    rows = []
    for e in enrollments:
        result = course_results.get(e.pk)
        current = result.current_percent if result else None
        rows.append(
            {
                "enrollment": e,
                "student": e.student,
                "topics": [{"topic": t, "result": topic_results[e.pk].get(t.pk)} for t in topics],
                "modules": [module_results[e.pk].get(m.pk) for m in modules],
                "result": result,
                "current": current,
                "grade": grade_for(current) if current is not None else None,
            }
        )
    return {"modules": modules, "topics": topics, "rows": rows}


def gradebook_table(book, labels) -> list[list]:
    """The matrix as plain rows for CSV / XLSX (numbers stay numbers)."""
    header = [labels["student"], labels["username"], labels["group"], labels["cohort"]]
    header += [f"{labels['topic']} {t.number}" for t in book["topics"]]
    header += [f"{labels['module']} {m.order}" for m in book["modules"]]
    header += [labels["current"], labels["final"], labels["letter"], labels["topics_completed"]]
    table = [header]
    for r in book["rows"]:
        e = r["enrollment"]
        line = [r["student"].full_name, r["student"].username, e.group.name if e.group else "", e.research_cohort]
        for cell in r["topics"]:
            res = cell["result"]
            line.append(res.score_percent if res and res.status == "completed" else "")
        line += [m.current_percent if m and m.current_percent is not None else "" for m in r["modules"]]
        result = r["result"]
        line += [
            r["current"] if r["current"] is not None else "",
            result.score_percent if result and result.score_percent is not None else "",
            r["grade"].letter if r["grade"] else "",
            f"{result.topics_completed}/{result.topics_total}" if result else "",
        ]
        table.append(line)
    return table
