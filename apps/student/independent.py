"""Section 8 — the independent authorial lesson and professional improvement (guide @S8; picture image25; STEP-38):
«The next professional stage» (the four directions of development) → «Start developing an independent lesson» → the
sheet (details; stages of the student's own choosing, 45 minutes at most) with «Айгерім», the intelligent pedagogical
expert → «Submit for the trial» → the trial stage by stage with the AI student (or in a real audience — the teacher
enters the protocol) → Айгерім's analysis, confirmed by the teacher → the next cycle."""

import json

from django.contrib import messages
from django.http import Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from apps.ai import services as ai
from apps.core.permissions import STUDENT, role_required
from apps.feedback.models import Notification
from apps.pedagogy import frames
from apps.pedagogy import selectors as pedagogy_selectors
from apps.pedagogy import services as pedagogy
from apps.pedagogy.models import ExpertReview, Lesson, LessonStage, Review, Trial
from apps.pedagogy.services import independent as ind
from apps.programme import selectors as programme_selectors
from apps.programme import services as programme
from apps.programme.models import Section
from apps.programme.services import schedule as schedules

from .designer import TRIAL_LEVELS

# guide @S8 I — the personal directions of professional development by the ICPAI components
DIRECTIONS = {
    "motivational": _("developing independent creative and professional initiatives"),
    "cognitive": _("deepening chemistry subject and pedagogical knowledge"),
    "activity": _("designing authorial lessons on one's own and using them in practice"),
    "reflective": _("analysing, assessing and improving pedagogical decisions"),
}
STEPS = (
    _("Developing the lesson"),
    _("Айгерім's expert opinion"),
    _("Trying it out"),
    _("Analysing the results"),
    _("Improving"),
    _("The next lesson"),
)


def _section(request):
    enrollment = programme.refresh(request.user)
    if enrollment is None:
        raise Http404
    section = get_object_or_404(Section, programme=enrollment.programme, kind=Section.Kind.INDEPENDENT)
    if not programme.can_access(enrollment, section):
        raise Http404
    return enrollment, section


def _lesson(request, pk):
    enrollment, section = _section(request)
    lesson = get_object_or_404(Lesson, pk=pk, owner=request.user, kind=Lesson.Kind.INDEPENDENT)
    return enrollment, section, lesson


def _trial_rows(user) -> list[dict]:
    """Every finished trial of the student's independent lessons with the teacher's grade (the dynamics, image25)."""
    reviews = {r.trial_id: r for r in Review.objects.filter(lesson__owner=user, lesson__kind="independent")}
    rows = []
    trials = Trial.objects.filter(lesson__owner=user, lesson__kind="independent", finished_at__isnull=False)
    for n, t in enumerate(trials.select_related("lesson").order_by("finished_at", "pk"), start=1):
        rows.append({"number": n, "trial": t, "review": reviews.get(t.pk)})
    return rows


def independent_context(enrollment, section, user) -> dict:
    """The section page's part: the next professional stage, the deadlines, the lessons (cycles), the notifications,
    the trial results and their dynamics."""
    schedules.notify_task_once(user)
    dynamics = programme_selectors.component_dynamics(enrollment)
    latest = [r for r in dynamics if r["latest"] is not None]
    weakest = min(latest, key=lambda r: r["latest"])["component"] if latest else None
    schedule = schedules.schedule_for(enrollment, section)
    lessons = list(ind.lessons_of(user))
    current = next((x for x in reversed(lessons) if x.status in ind.OPEN), None)
    trials = _trial_rows(user)
    return {
        "directions": [{**r, "text": DIRECTIONS[r["component"]], "focus": r["component"] == weakest} for r in dynamics],
        "schedule": schedule,
        "countdown": schedules.countdown(schedule),
        "independent_lessons": lessons,
        "current_lesson": current,
        "trial_rows": trials,
        "max_score": max([t["review"].total for t in trials if t["review"]] or [0]),
        "icpai_notes": Notification.objects.filter(user=user, kind__startswith="icpai_").order_by("-created_at")[:5],
        "steps": STEPS,
    }


@role_required(STUDENT)
def home(request):
    _enrollment, section = _section(request)
    return redirect("student:section", section.number)


@require_POST
@role_required(STUDENT)
def start(request):
    """«Start developing an independent lesson» (or the next lesson after a completed cycle)."""
    _section(request)
    lesson = ind.start_independent(request.user)
    return redirect("student:independent", lesson.pk)


def _editor_context(request, enrollment, section, lesson, stage) -> dict:
    stages = pedagogy_selectors.timeline(list(lesson.stages.all()))
    reviews = list(lesson.expert_reviews.filter(kind=ExpertReview.Kind.DRAFT)[:5])
    context = {
        "programme": enrollment.programme, "section": section, "lesson": lesson, "stages": stages, "stage": stage,
        "total": sum(r["stage"].minutes for r in stages), "problems": ind.problems(lesson), "grades": pedagogy.practice.GRADES,
        "review": reviews[0] if reviews else None, "earlier_reviews": reviews[1:],
        "dimensions": ExpertReview.DIMENSIONS, "locked": lesson.status == Lesson.Status.FINAL,
        "levels": TRIAL_LEVELS, "open_trial": ind.open_trial(lesson), "trials": list(lesson.trials.order_by("-started_at")),
        "ai_enabled": ai.enabled(), "remaining": ai.remaining_today(request.user), "steps": STEPS,
        "schedule": schedules.schedule_for(enrollment, section),
    }  # fmt: skip
    if stage:
        fields = pedagogy_selectors.stage_fields(stage)
        context["fields"] = fields
        context["editor_opts"] = {
            "saveUrl": reverse("student:independent_stage_save", args=[lesson.pk, stage.order]),
            "csrf": get_token(request), "cleared": True, "title": stage.title, "minutes": stage.minutes,
            "fields": {f["key"]: f["html"] for f in fields}, "total": context["total"], "edited": stage.edited,
            "first": fields[0]["key"],
            "text": {"saving": _("Saving…"), "saved": _("Saved"),
                     "failed": _("Not saved — the stages take more than 45 minutes, or check the connection"),
                     "clearFirst": "", "inserted": ""},
        }  # fmt: skip
    return context


@role_required(STUDENT)
def lesson(request, pk, order=None):
    """The sheet (image25): the details, the stages (add, change, delete; 45 minutes at most), the chosen stage's
    content, «Айгерім» — her latest opinion by six dimensions and «See Айгерім's opinion» / «Check again» —,
    «Save the project», «Submit for the trial»; the trial and its results."""
    enrollment, section, lesson = _lesson(request, pk)
    if request.method == "POST":
        try:
            ind.save_details(lesson, request.POST)
        except pedagogy.LessonError:
            messages.error(request, _("The final version cannot be changed."))
        else:
            messages.success(request, _("The project is saved."))
        return redirect("student:independent", lesson.pk)
    stage = None
    if order is not None:
        stage = get_object_or_404(LessonStage, lesson=lesson, order=order)
    elif lesson.stages.exists():
        stage = lesson.stages.order_by("order").first()
    return render(
        request, "student/independent/editor.html", _editor_context(request, enrollment, section, lesson, stage)
    )


@require_POST
@role_required(STUDENT)
def stage_add(request, pk):
    _enrollment, _section_obj, lesson = _lesson(request, pk)
    try:
        stage = ind.add_stage(lesson, title=request.POST.get("title", ""), minutes=request.POST.get("minutes"))
    except pedagogy.LessonError as exc:
        messages.error(request, _("The stages take 45 minutes at most in all.") if str(exc) == "too_long"
                       else _("Give the stage a name and its minutes."))  # fmt: skip
        return redirect("student:independent", lesson.pk)
    return redirect("student:independent_stage", lesson.pk, stage.order)


@require_POST
@role_required(STUDENT)
def stage_delete(request, pk, order):
    _enrollment, _section_obj, lesson = _lesson(request, pk)
    try:
        ind.delete_stage(get_object_or_404(LessonStage, lesson=lesson, order=order))
    except pedagogy.LessonError:
        messages.error(request, _("The final version cannot be changed."))
    return redirect("student:independent", lesson.pk)


@require_POST
@role_required(STUDENT)
def stage_save(request, pk, order):
    _enrollment, _section_obj, lesson = _lesson(request, pk)
    stage = get_object_or_404(LessonStage, lesson=lesson, order=order)
    try:
        data = json.loads(request.body or b"{}")
        fields = data.get("fields") or {}
        if not isinstance(fields, dict):
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({"error": "bad_request"}, status=400)
    try:
        stage = pedagogy.save(stage, title=data.get("title", ""), minutes=data.get("minutes"), fields=fields)
    except pedagogy.LessonError as exc:
        return JsonResponse({"error": str(exc)}, status=409)
    return JsonResponse({"edited": stage.edited, "minutes_total": ind.total_minutes(lesson)})


@require_POST
@role_required(STUDENT)
def expert(request, pk):
    """«See Айгерім's opinion» / «Check again» (compares with the previous opinion)."""
    _enrollment, _section_obj, lesson = _lesson(request, pk)
    try:
        ind.expert_review(lesson)
    except ai.LimitReached:
        messages.error(request, _("Today's AI requests are used up. They renew tomorrow."))
    except ai.AIUnavailable:
        messages.error(request, _("Айгерім did not answer this time. Try again in a minute."))
    except pedagogy.LessonError:
        messages.error(request, _("The final version cannot be changed."))
    else:
        schedules.notify(request.user, Notification.Kind.ICPAI_EXPERT)
    return redirect(f"{reverse('student:independent', args=[lesson.pk])}#expert")


@require_POST
@role_required(STUDENT)
def submit(request, pk):
    """«Submit for the trial»: the structure is checked."""
    _enrollment, _section_obj, lesson = _lesson(request, pk)
    try:
        ind.submit(lesson)
    except pedagogy.LessonError:
        messages.error(request, _("Fill in the details and every stage first; the stages take 45 minutes at most."))
    else:
        messages.success(request, _("The lesson is submitted for the trial."))
    return redirect(f"{reverse('student:independent', args=[lesson.pk])}#trial")


@require_POST
@role_required(STUDENT)
def trial_start(request, pk):
    enrollment, section, lesson = _lesson(request, pk)
    schedule = schedules.schedule_for(enrollment, section)
    if schedule and schedule.trial_on and schedule.trial_on > timezone.localdate():
        messages.error(request, _("The trial opens on its date set by the teacher."))
        return redirect(f"{reverse('student:independent', args=[lesson.pk])}#trial")
    try:
        trial = ind.start_trial(lesson, grade=request.POST.get("grade", ""), level=request.POST.get("level", ""))
    except pedagogy.LessonError as exc:
        messages.error(request, {
            "level": _("Choose the class and the AI student's level."),
            "not_submitted": _("Submit the lesson for the trial first."),
            "open_trial": _("Finish the trial that is going on first."),
        }.get(str(exc), _("Fill in the details and every stage first; the stages take 45 minutes at most.")))  # fmt: skip
        return redirect(f"{reverse('student:independent', args=[lesson.pk])}#trial")
    return redirect("student:independent_step", lesson.pk, trial.pk, 1)


@role_required(STUDENT)
def step(request, pk, trial_pk, order):
    """One stage of the trial — the same six steps as section 5 (student/practice/step.html)."""
    enrollment, section, lesson = _lesson(request, pk)
    trial = get_object_or_404(lesson.trials.select_related("version"), pk=trial_pk, mode=Trial.Mode.STEPWISE)
    stages = trial.version.snapshot["stages"]
    stage = next((s for s in stages if s["order"] == order), None)
    if stage is None:
        raise Http404
    current = pedagogy.current_order(trial)
    if trial.finished_at is None and current is not None and order > current:
        return redirect("student:independent_step", lesson.pk, trial.pk, current)
    turn = trial.turns.filter(stage_order=order).first()
    error = ""
    if request.method == "POST" and trial.finished_at is None:
        post = request.POST
        try:
            if post.get("action") == "give":
                pedagogy.give_task(trial, order, explanation=post.get("explanation", ""), task=post.get("task", ""),
                                   minutes=post.get("minutes"))  # fmt: skip
                return redirect(f"{request.path}#answer")
            if post.get("action") == "analyse" and turn:
                pedagogy.analyse(
                    turn, analysis=post.get("analysis", ""), follow_up=post.get("follow_up", ""),
                    correction=post.get("correction", ""), improved_task=post.get("improved_task", ""),
                    duration_s=post.get("duration_s"),
                )  # fmt: skip
                following = pedagogy.current_order(trial)
                if following:
                    return redirect("student:independent_step", lesson.pk, trial.pk, following)
                ind.finish_trial(trial)
                return redirect("student:independent_trial", lesson.pk, trial.pk)
        except ai.LimitReached:
            error = "limit"
        except ai.AIUnavailable as exc:
            error = "off" if str(exc) == "disabled" else "failed"
        except pedagogy.LessonError as exc:
            error = str(exc)
        turn = trial.turns.filter(stage_order=order).first()
    done = {t.stage_order for t in trial.turns.filter(analysed_at__isnull=False)}
    return render(request, "student/practice/step.html", {
        "programme": enrollment.programme, "section": section, "lesson": lesson, "trial": trial, "stage": stage,
        "spec": None, "stage_fields": frames.FREE,
        "trial_stages": [{**s, "done": s["order"] in done, "open": current is None or s["order"] <= current} for s in stages],
        "turn": turn, "prefill": pedagogy.prefill(stage), "error": error, "ai_enabled": ai.enabled(),
        "remaining": ai.remaining_today(request.user), "is_last": order == stages[-1]["order"],
        "step_url": "student:independent_step", "results_url": reverse("student:independent_trial", args=[lesson.pk, trial.pk]),
    })  # fmt: skip


@role_required(STUDENT)
def trial(request, pk, trial_pk):
    """A trial's results (VI): the protocol (the AI student's answers and the analyses, or the real audience's
    protocol), Айгерім's analysis by seven directions, the teacher's confirmation and grade; «Improve» / the next
    lesson."""
    enrollment, section, lesson = _lesson(request, pk)
    trial = get_object_or_404(lesson.trials.select_related("version", "recorded_by"), pk=trial_pk)
    review = trial.expert_reviews.first()
    grade = Review.objects.filter(trial=trial).first()
    return render(request, "student/independent/trial.html", {
        "programme": enrollment.programme, "section": section, "lesson": lesson, "trial": trial,
        "turns": list(trial.turns.order_by("stage_order")), "review": review, "grade": grade,
        "directions": ExpertReview.TRIAL_DIRECTIONS, "open_stage": pedagogy.current_order(trial) if not trial.finished_at else None,
        "ai_enabled": ai.enabled(), "steps": STEPS,
    })  # fmt: skip


@require_POST
@role_required(STUDENT)
def trial_review(request, pk, trial_pk):
    """Айгерім's expert analysis after the trial."""
    _enrollment, _section_obj, lesson = _lesson(request, pk)
    trial = get_object_or_404(lesson.trials, pk=trial_pk)
    try:
        ind.trial_review(trial)
    except ai.LimitReached:
        messages.error(request, _("Today's AI requests are used up. They renew tomorrow."))
    except ai.AIUnavailable:
        messages.error(request, _("Айгерім did not answer this time. Try again in a minute."))
    except pedagogy.LessonError:
        messages.error(request, _("Finish the trial first."))
    else:
        schedules.notify(request.user, Notification.Kind.ICPAI_EXPERT)
    return redirect("student:independent_trial", lesson.pk, trial.pk)
