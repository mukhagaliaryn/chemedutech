"""Section 7 — the professional portfolio (guide @S7): the reflection (IV — the student's own words, the AI writes
none), the development map (V — goals, then results), the AI completeness check (only ✓ / ✕), «Assemble the
portfolio» (VI — the ten parts frozen as a version), «Submit to the teacher», the teacher's feedback (III — four
directions, strengths, improvements, recommendations, the status). Every step is logged."""

import hashlib
import json

from django.db import transaction
from django.db.models import Max
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext as _

from apps.ai import services as ai
from apps.feedback import services as feedback_services
from apps.pedagogy.models import Lesson, Review, Trial
from apps.progress.models import CourseResult, TopicResult

from .. import portfolio_selectors
from ..models import (
    DIRECTIONS,
    QUESTIONS,
    DevelopmentPlanItem,
    Portfolio,
    PortfolioEvent,
    PortfolioFeedback,
    PortfolioVersion,
    Reflection,
)
from ..providers.course import course_enrollment

E = PortfolioEvent.Action
MAX_TEXT = 6000


class PortfolioError(Exception):
    """The change is not allowed now (submitted or accepted, not complete …)."""


def portfolio_of(enrollment) -> Portfolio:
    """The student's portfolio (made on the first visit; the programme and the study year from the microlesson)."""
    portfolio = Portfolio.objects.filter(enrollment=enrollment).first()
    if portfolio:
        return portfolio
    micro = Lesson.objects.filter(owner_id=enrollment.student_id, kind=Lesson.Kind.MICROLESSON).first()
    details = micro.details if micro else {}
    portfolio, _created = Portfolio.objects.get_or_create(
        enrollment=enrollment,
        defaults={"programme_name": details.get("programme", ""), "study_year": details.get("study_year", "")},
    )
    return portfolio


def _editable(portfolio):
    if not portfolio.editable:
        raise PortfolioError("locked")


def _log(portfolio, action, actor=None, **data):
    PortfolioEvent.objects.create(portfolio=portfolio, action=action, actor=actor, data=data)


def _text(value) -> str:
    return str(value or "").strip()[:MAX_TEXT]


@transaction.atomic
def save_details(portfolio, *, programme_name: str, study_year: str) -> Portfolio:
    _editable(portfolio)
    portfolio.programme_name = _text(programme_name)[:255]
    portfolio.study_year = _text(study_year)[:64]
    portfolio.save(update_fields=["programme_name", "study_year", "updated_at"])
    return portfolio


@transaction.atomic
def save_reflection(enrollment, answers: dict) -> Reflection:
    """«Save the reflection»: the student's answers to the seven questions (plain text)."""
    portfolio = portfolio_of(enrollment)
    _editable(portfolio)
    clean = {key: _text(answers.get(key)) for key, _q in QUESTIONS}
    reflection, _created = Reflection.objects.update_or_create(enrollment=enrollment, defaults={"answers": clean})
    _log(portfolio, E.REFLECTION, chars={k: len(v) for k, v in clean.items()})
    return reflection


@transaction.atomic
def save_plan(enrollment, items: dict) -> list[DevelopmentPlanItem]:
    """«Set the professional development goal»: the planned action and the expected result of each direction."""
    portfolio = portfolio_of(enrollment)
    _editable(portfolio)
    rows = []
    for key, _label in DIRECTIONS:
        data = items.get(key) or {}
        item, _created = DevelopmentPlanItem.objects.update_or_create(
            enrollment=enrollment, direction=key,
            defaults={"action": _text(data.get("action")), "expected": _text(data.get("expected"))},
        )  # fmt: skip
        rows.append(item)
    _log(portfolio, E.PLAN)
    return rows


@transaction.atomic
def update_results(enrollment, items: dict) -> list[DevelopmentPlanItem]:
    """«Update the development result»: what was done in each direction of the plan."""
    portfolio = portfolio_of(enrollment)
    rows = []
    for item in DevelopmentPlanItem.objects.filter(enrollment=enrollment):
        data = items.get(item.direction) or {}
        item.done = bool(data.get("done"))
        item.result = _text(data.get("result"))
        item.save(update_fields=["done", "result", "updated_at"])
        rows.append(item)
    _log(portfolio, E.RESULTS, done=[i.direction for i in rows if i.done])
    return rows


def _number(value):
    return None if value is None else float(value)


def snapshot(enrollment, portfolio) -> dict:
    """The ten parts of the final portfolio (@S7 VI), as they are now."""
    from ..selectors import component_dynamics

    student = enrollment.student
    profile = getattr(student, "student_profile", None)
    course_enr = course_enrollment(enrollment)
    result = CourseResult.objects.filter(enrollment=course_enr).first() if course_enr else None
    topics = TopicResult.objects.filter(enrollment=course_enr).select_related("topic") if course_enr else []
    lessons = list(Lesson.objects.filter(owner=student).prefetch_related("reviews", "stages", "versions"))
    micro = next((x for x in lessons if x.kind == Lesson.Kind.MICROLESSON), None)
    micro_reviews = {r.trial_id: r for r in Review.objects.filter(lesson=micro, trial__isnull=False)} if micro else {}
    answers = portfolio_selectors.reflection_answers(enrollment)
    plan = portfolio_selectors.plan_rows(enrollment)
    return {
        "student": {
            "name": student.get_full_name() or student.username, "programme": portfolio.programme_name,
            "group": str(profile.group) if profile and profile.group else "", "study_year": portfolio.study_year,
            "date": timezone.localdate().isoformat(),
        },
        "icpai": [
            {"component": r["component"], "label": str(r["label"]),
             "phases": {p: _number(v) for p, v in r["phases"].items()}}
            for r in component_dynamics(enrollment)
        ],
        "course": {
            "title": course_enr.course.title if course_enr else "",
            "score": _number(result.score_percent if result and result.score_percent is not None
                             else result.current_percent if result else None),
            "passed": bool(result and result.passed),
            "topics": [{"title": t.topic.title, "status": t.get_status_display(), "score": _number(t.score_percent)}
                       for t in topics],
        },
        "lessons": [
            {"title": x.title, "template": x.source_template.name if x.source_template else "",
             "status": x.get_status_display(), "redesigned": sum(1 for s in x.stages.all() if s.edited),
             "versions": len(x.versions.all())}
            for x in lessons if x.kind == Lesson.Kind.TEMPLATE_COPY
        ],
        "practices": [
            {"title": x.title, "template": x.source_template.name if x.source_template else "",
             "status": x.get_status_display(), "grade": x.review.total if x.review else None,
             "comment": x.review.comment if x.review else ""}
            for x in lessons if x.kind == Lesson.Kind.RESEARCH_PRACTICE
        ],
        "micro": {
            "topic": micro.topic, "status": micro.get_status_display(),
            "trials": [
                {"number": n, "level": t.get_level_display(), "grade": t.grade, "messages": t.messages.count(),
                 "review": micro_reviews[t.pk].total if t.pk in micro_reviews else None,
                 "comment": micro_reviews[t.pk].comment if t.pk in micro_reviews else ""}
                for n, t in enumerate(micro.trials.filter(mode=Trial.Mode.DIALOG).order_by("started_at", "pk"), start=1)
            ],
        } if micro else None,
        "trials": Trial.objects.filter(lesson__owner=student, finished_at__isnull=False).count(),
        "feedback": [
            {"teacher": f.teacher.get_full_name() or f.teacher.username, "status": f.get_status_display(),
             "date": f.created_at.date().isoformat(), "strengths": f.strengths, "improvements": f.improvements,
             "recommendations": f.recommendations,
             "directions": {k: getattr(f, k) for k in ("chemistry", "design", "digital", "practice")}}
            for f in portfolio.feedbacks.select_related("teacher")
        ],
        "reflection": [{"key": k, "question": str(q), "answer": answers.get(k, "")} for k, q in QUESTIONS],
        "plan": [
            {"direction": r["direction"], "label": str(r["label"]),
             "action": r["item"].action if r["item"] else "", "expected": r["item"].expected if r["item"] else "",
             "done": bool(r["item"] and r["item"].done), "result": r["item"].result if r["item"] else ""}
            for r in plan
        ],
    }  # fmt: skip


def fingerprint(enrollment) -> str:
    """The student's own parts (the reflection and the plan) — a change after assembling asks to assemble again."""
    data = {"reflection": portfolio_selectors.reflection_answers(enrollment),
            "plan": [(r["direction"], r["item"].action, r["item"].expected) if r["item"] else (r["direction"],)
                     for r in portfolio_selectors.plan_rows(enrollment)]}  # fmt: skip
    return hashlib.sha256(json.dumps(data, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


def check(portfolio, *, client=None) -> dict:
    """The AI assistant checks only the completeness and the consistency of the reflection and the plan (✓ / ✕)."""
    _editable(portfolio)
    enrollment = portfolio.enrollment
    data = snapshot(enrollment, portfolio)
    reflection = "\n".join(f"q{r['key']}. {r['question']}\n{r['answer'] or '(empty)'}" for r in data["reflection"])
    plan = "\n".join(f"{r['direction']}. {r['label']}: action — {r['action'] or '(empty)'}; expected — "
                     f"{r['expected'] or '(empty)'}" for r in data["plan"])  # fmt: skip
    works = "\n".join(
        f"- {c['title']}: {c['status']['label']}{' · ' + c['grade'] if c['grade'] else ''}"
        for c in portfolio_selectors.works(enrollment)
    )
    own = f"Reflection:\n{reflection}\n\nDevelopment map:\n{plan}"
    context = f"The student's works and results:\n{works}\n\n{ai.quote(own)}"
    message = ai.check_portfolio(
        enrollment.student, context_type="portfolio", context_id=portfolio.pk, context=context, client=client
    )
    portfolio.ai_check = {
        "items": message.structured["items"], "fingerprint": fingerprint(enrollment),
        "at": timezone.now().isoformat(), "message": message.pk,
    }  # fmt: skip
    portfolio.save(update_fields=["ai_check", "updated_at"])
    _log(portfolio, E.CHECKED, wrong=[k for k, v in message.structured["items"].items() if v != "ok"])
    return portfolio.ai_check


@transaction.atomic
def assemble(portfolio) -> PortfolioVersion:
    """«Assemble the portfolio»: needs the reflection, the development map and the final diagnostics."""
    portfolio = Portfolio.objects.select_for_update().get(pk=portfolio.pk)
    _editable(portfolio)
    enrollment = portfolio.enrollment
    if not portfolio_selectors.completeness(enrollment)["ready"]:
        raise PortfolioError("not_ready")
    number = (portfolio.versions.aggregate(n=Max("number"))["n"] or 0) + 1
    data = snapshot(enrollment, portfolio)
    data["meta"] = {
        "number": number,
        "assembled_at": timezone.now().isoformat(),
        "fingerprint": fingerprint(enrollment),
    }
    version = PortfolioVersion.objects.create(portfolio=portfolio, number=number, snapshot=data)
    _log(portfolio, E.ASSEMBLED, version=number)
    return version


def latest_version(portfolio) -> PortfolioVersion | None:
    return portfolio.versions.order_by("-number").first()


def is_current(portfolio) -> bool:
    """The latest version holds the reflection and the plan as they are now."""
    version = latest_version(portfolio)
    return bool(version) and version.snapshot.get("meta", {}).get("fingerprint") == fingerprint(portfolio.enrollment)


@transaction.atomic
def submit(portfolio) -> Portfolio:
    """«Submit to the teacher»: the latest assembled version (made after the last change) goes to the teacher."""
    portfolio = Portfolio.objects.select_for_update().get(pk=portfolio.pk)
    _editable(portfolio)
    if not is_current(portfolio):
        raise PortfolioError("assemble_first")
    portfolio.status = Portfolio.Status.SUBMITTED
    portfolio.submitted_at = timezone.now()
    portfolio.save(update_fields=["status", "submitted_at", "updated_at"])
    _log(portfolio, E.SUBMITTED, version=latest_version(portfolio).number)
    return portfolio


@transaction.atomic
def give_feedback(portfolio, teacher, data: dict) -> PortfolioFeedback:
    """The teacher's professional feedback on the submitted portfolio; its status becomes the portfolio's status
    («Accepted» closes it; «Needs more work» / «Needs revising» opens it for the student again)."""
    portfolio = Portfolio.objects.select_for_update().get(pk=portfolio.pk)
    if portfolio.status != Portfolio.Status.SUBMITTED:
        raise PortfolioError("not_submitted")
    status = data.get("status")
    if status not in PortfolioFeedback.Status.values:
        raise PortfolioError("status")
    fields = ("chemistry", "design", "digital", "practice", "strengths", "improvements", "recommendations")
    feedback = PortfolioFeedback.objects.create(
        portfolio=portfolio, version=latest_version(portfolio), teacher=teacher, status=status,
        **{f: _text(data.get(f)) for f in fields},
    )  # fmt: skip
    portfolio.status = status
    portfolio.save(update_fields=["status", "updated_at"])
    _log(portfolio, E.FEEDBACK, actor=teacher, status=status)
    feedback_services.notify(
        portfolio.enrollment.student, feedback_services.Kind.COMMENT,
        _("Portfolio: %(status)s") % {"status": feedback.get_status_display()}, reverse("student:portfolio"),
    )  # fmt: skip
    return feedback
