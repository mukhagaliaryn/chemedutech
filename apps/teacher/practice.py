"""Teacher: the works of sections 5 and 6 — the finished digital research practices (guide @S5 VII; STEP-35) and
the finished trials of the microlessons (@S6 VI; STEP-36, each trial graded apart) of the teacher's students, with the
10-point grade (five criteria × 2), kept apart from the ICPAI component percents."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.dateparse import parse_date
from django.utils.translation import gettext as _

from apps.courses import selectors as course_selectors
from apps.feedback.models import Notification
from apps.pedagogy import frames
from apps.pedagogy import selectors as pedagogy_selectors
from apps.pedagogy import services as pedagogy
from apps.pedagogy.models import ExpertReview, Lesson, Review, Trial
from apps.pedagogy.services import independent as ind
from apps.programme import services as programme_services
from apps.programme.models import FEEDBACK_DIRECTIONS, PARTS, Portfolio, PortfolioFeedback, Section, SectionSchedule
from apps.programme.services import portfolio as portfolio_services
from apps.programme.services import schedule as schedule_services

from .views import teacher_only


def _practices(request):
    return (
        Lesson.objects.filter(
            kind=Lesson.Kind.RESEARCH_PRACTICE,
            status=Lesson.Status.FINAL,
            owner__in=course_selectors.teacher_students(request.user),
        )
        .select_related("owner__student_profile__group", "source_template")
        .prefetch_related("reviews")
    )


def _portfolios(request):
    return Portfolio.objects.filter(
        enrollment__student__in=course_selectors.teacher_students(request.user), submitted_at__isnull=False
    ).select_related("enrollment__student__student_profile__group")


def _micro_trials(request):
    return Trial.objects.filter(
        mode=Trial.Mode.DIALOG,
        finished_at__isnull=False,
        lesson__kind=Lesson.Kind.MICROLESSON,
        lesson__owner__in=course_selectors.teacher_students(request.user),
    ).select_related("lesson__owner__student_profile__group", "version")


@teacher_only
def queue(request):
    """Section 5 practices or section 6 microlesson trials: «To grade» first, then «Graded»."""
    show = request.GET.get("show", "new")
    what = request.GET.get("what") if request.GET.get("what") in ("micro", "portfolio", "independent") else "practice"
    if what == "independent":
        return _independent_queue(request, show)
    practices, trials, portfolios = _practices(request), _micro_trials(request), _portfolios(request)
    waiting = portfolios.filter(status=Portfolio.Status.SUBMITTED)
    counts = {
        "practice": practices.filter(reviews__isnull=True).count(),
        "micro": trials.filter(reviews__isnull=True).count(),
        "portfolio": waiting.count(),
        "independent": _independent_waiting(request).count(),
    }
    if what == "portfolio":
        rows = (
            waiting
            if show != "graded"
            else portfolios.exclude(status=Portfolio.Status.SUBMITTED).filter(feedbacks__isnull=False).distinct()
        ).order_by("-submitted_at")[:300]
        graded = portfolios.filter(feedbacks__isnull=False).distinct().count()
        return render(request, "teacher/practice/queue.html", {
            "rows": rows, "show": show, "what": what, "counts": counts, "new": counts[what], "graded": graded,
        })  # fmt: skip
    items = trials if what == "micro" else practices
    graded = items.filter(reviews__isnull=False).count()
    if what == "micro":
        rows = trials.filter(reviews__isnull=(show != "graded")).prefetch_related("reviews").order_by("-finished_at")
        rows = [{"trial": t, "number": pedagogy.trial_number(t), "review": next(iter(t.reviews.all()), None)}
                for t in rows[:300]]  # fmt: skip
    else:
        rows = practices.filter(reviews__isnull=(show != "graded")).order_by("-updated_at")[:300]
    return render(request, "teacher/practice/queue.html", {
        "rows": rows, "show": show, "what": what, "counts": counts,
        "new": counts[what], "graded": graded,
    })  # fmt: skip


@teacher_only
def detail(request, pk):
    """A practice: the sheet (I, II), the trial protocol and the analysis sheet (VI); the rubric form (VII)."""
    lesson = get_object_or_404(_practices(request), pk=pk)
    trial = lesson.trials.filter(mode=Trial.Mode.STEPWISE, finished_at__isnull=False).first()
    review = lesson.review
    if request.method == "POST":
        scores = {str(n): request.POST.get(f"c{n}") for n, _label in Review.CRITERIA}
        try:
            pedagogy.grade(lesson, request.user, scores, request.POST.get("comment", ""))
        except pedagogy.LessonError:
            messages.error(request, _("Give every criterion 0, 1 or 2 points."))
        else:
            messages.success(request, _("The grade is saved."))
            return redirect("teacher:practice_queue")
        return redirect("teacher:practice", lesson.pk)
    version = lesson.versions.filter(reason="final").first()
    snapshot = version.snapshot if version else {"stages": []}
    turns = {t["stage_order"]: t for t in snapshot.get("trial", {}).get("turns", [])}
    rows = []
    for s in snapshot["stages"]:
        spec = frames.stage_spec("research_8", s.get("key", ""))
        labels = {f.key: f.label for f in spec.fields} if spec else {}
        rows.append({
            "stage": s, "spec": spec, "turn": turns.get(s["order"]),
            "fields": [{"label": labels.get(k, k), "html": v} for k, v in s["fields"].items() if v],
        })  # fmt: skip
    return render(request, "teacher/practice/detail.html", {
        "lesson": lesson, "plan": snapshot, "trial": trial, "rows": rows, "review": review,
        "criteria": [{"number": n, "label": label, "points": review.scores.get(str(n)) if review else None}
                     for n, label in Review.CRITERIA],
    })  # fmt: skip


@teacher_only
def micro(request, trial_pk):
    """A microlesson trial: the microlesson as tried (its version), the dialogue by stage, the rubric (@S6 VI)."""
    trial = get_object_or_404(_micro_trials(request), pk=trial_pk)
    lesson = trial.lesson
    review = Review.objects.filter(trial=trial).first()
    if request.method == "POST":
        scores = {str(n): request.POST.get(f"c{n}") for n, _label in Review.MICRO_CRITERIA}
        try:
            pedagogy.grade(lesson, request.user, scores, request.POST.get("comment", ""), trial=trial)
        except pedagogy.LessonError:
            messages.error(request, _("Give every criterion 0, 1 or 2 points."))
            return redirect("teacher:micro", trial.pk)
        messages.success(request, _("The grade is saved."))
        return redirect(f"{reverse('teacher:practice_queue')}?what=micro")
    stages = trial.version.snapshot["stages"]
    rows = []
    for s in stages:
        spec = frames.stage_spec("micro_4", s.get("key", ""))
        rows.append({
            "stage": s, "spec": spec,
            "fields": [{"label": f.label, "html": s["fields"].get(f.key, "")} for f in (spec.fields if spec else ())
                       if s["fields"].get(f.key)],
            "messages": [m for m in trial.messages.order_by("number") if m.stage_order == s["order"]],
        })  # fmt: skip
    return render(request, "teacher/practice/micro.html", {
        "trial": trial, "lesson": lesson, "plan": trial.version.snapshot, "rows": rows, "review": review,
        "number": pedagogy.trial_number(trial), "seconds": pedagogy.elapsed_s(trial),
        "criteria": [{"number": n, "label": label, "points": review.scores.get(str(n)) if review else None}
                     for n, label in Review.MICRO_CRITERIA],
    })  # fmt: skip


@teacher_only
def portfolio(request, pk):
    """A submitted portfolio (@S7 III): its latest version in ten parts and the teacher's professional feedback —
    four directions, strengths, parts to improve, recommendations, the status."""
    item = get_object_or_404(_portfolios(request), pk=pk)
    if request.method == "POST":
        try:
            portfolio_services.give_feedback(item, request.user, request.POST)
        except portfolio_services.PortfolioError as exc:
            messages.error(
                request,
                _("Choose the status of the work.")
                if str(exc) == "status"
                else _("The portfolio is not waiting for feedback."),
            )
            return redirect("teacher:portfolio", item.pk)
        programme_services.refresh(item.enrollment.student)
        messages.success(request, _("The feedback is saved and shown to the student."))
        return redirect(f"{reverse('teacher:practice_queue')}?what=portfolio")
    version = portfolio_services.latest_version(item)
    return render(request, "teacher/practice/portfolio.html", {
        "portfolio": item, "version": version, "data": version.snapshot if version else {}, "parts": PARTS,
        "feedback_directions": FEEDBACK_DIRECTIONS, "feedbacks": list(item.feedbacks.select_related("teacher")),
        "statuses": PortfolioFeedback.Status.choices, "waiting": item.status == Portfolio.Status.SUBMITTED,
    })  # fmt: skip


# --- section 8: the independent lessons, «Айгерім», the deadlines (guide @S8; STEP-38) -----------------------------


def _independent(request):
    return Lesson.objects.filter(
        kind=Lesson.Kind.INDEPENDENT, owner__in=course_selectors.teacher_students(request.user)
    ).select_related("owner__student_profile__group")


def _independent_waiting(request):
    """Independent lessons with an analysis after a trial the teacher has not confirmed yet."""
    return (
        _independent(request)
        .filter(expert_reviews__kind=ExpertReview.Kind.TRIAL, expert_reviews__confirmed_at__isnull=True)
        .distinct()
    )


def _independent_section(request):
    """The section 8 of the programmes on the teacher's courses."""
    return (
        Section.objects.filter(
            kind=Section.Kind.INDEPENDENT, programme__course__in=course_selectors.teacher_courses(request.user)
        )
        .select_related("programme")
        .first()
    )


def _independent_queue(request, show):
    """Section 8: the groups' dates (hand-in and trial) and the independent lessons — those with an analysis after a
    trial waiting for the teacher's confirmation first."""
    section = _independent_section(request)
    groups = list(course_selectors.teacher_groups(request.user))
    if request.method == "POST" and section:
        group = next((g for g in groups if str(g.pk) == request.POST.get("group")), None)
        if group:
            schedule_services.set_schedule(
                section, group, request.user,
                hand_in_on=parse_date(request.POST.get("hand_in_on") or "") or None,
                trial_on=parse_date(request.POST.get("trial_on") or "") or None,
            )  # fmt: skip
            messages.success(request, _("The dates are saved; the students are notified."))
        return redirect(f"{reverse('teacher:practice_queue')}?what=independent")
    lessons = _independent(request)
    waiting = _independent_waiting(request)
    rows = (waiting if show != "graded" else lessons.exclude(pk__in=waiting)).order_by("-updated_at")[:300]
    schedules = {s.group_id: s for s in SectionSchedule.objects.filter(section=section)} if section else {}
    return render(request, "teacher/practice/queue.html", {
        "rows": rows, "show": show, "what": "independent", "new": waiting.count(),
        "graded": lessons.exclude(pk__in=waiting).count(),
        "counts": {"practice": _practices(request).filter(reviews__isnull=True).count(),
                   "micro": _micro_trials(request).filter(reviews__isnull=True).count(),
                   "portfolio": _portfolios(request).filter(status=Portfolio.Status.SUBMITTED).count(),
                   "independent": waiting.count()},
        "section8": section, "group_rows": [{"group": g, "schedule": schedules.get(g.pk)} for g in groups],
    })  # fmt: skip


@teacher_only
def independent(request, pk):
    """An independent lesson: the details and stages, the trials (protocols), «Айгерім»'s opinions with the
    teacher's confirmation (status, comment; for an analysis after a trial the final grade 0–10), a real-audience
    trial protocol."""
    lesson = get_object_or_404(_independent(request), pk=pk)
    if request.method == "POST":
        action = request.POST.get("action")
        try:
            if action == "confirm":
                review = get_object_or_404(lesson.expert_reviews, pk=request.POST.get("review"))
                ind.confirm(review, request.user, status=request.POST.get("status", ""),
                            comment=request.POST.get("comment", ""), score=request.POST.get("score"))  # fmt: skip
                if review.kind == ExpertReview.Kind.TRIAL and review.teacher_status != ExpertReview.Status.OK:
                    schedule_services.notify(lesson.owner, Notification.Kind.ICPAI_RETRIAL)
                programme_services.refresh(lesson.owner)
                messages.success(request, _("Confirmed."))
            elif action == "real":
                ind.record_real_trial(lesson, request.user, grade=request.POST.get("grade", ""),
                                      notes=request.POST.get("notes", ""))  # fmt: skip
                messages.success(request, _("The real-audience trial protocol is saved."))
        except pedagogy.LessonError as exc:
            messages.error(request, {
                "score": _("Give a grade from 0 to 10."), "status": _("Choose the status."),
                "empty": _("Write the protocol."),
            }.get(str(exc), _("The final version cannot be changed.")))  # fmt: skip
        return redirect("teacher:independent", lesson.pk)
    grades = {r.trial_id: r for r in Review.objects.filter(lesson=lesson, trial__isnull=False)}
    trials = [{"trial": t, "turns": list(t.turns.order_by("stage_order")), "grade": grades.get(t.pk),
               "reviews": list(t.expert_reviews.all())}
              for t in lesson.trials.select_related("recorded_by").order_by("started_at")]  # fmt: skip
    return render(request, "teacher/practice/independent.html", {
        "lesson": lesson, "stages": pedagogy_selectors.timeline(list(lesson.stages.all())),
        "fields": frames.FREE, "trials": trials,
        "drafts": list(lesson.expert_reviews.filter(kind=ExpertReview.Kind.DRAFT)[:3]),
        "dimensions": ExpertReview.DIMENSIONS, "directions": ExpertReview.TRIAL_DIRECTIONS,
        "statuses": ExpertReview.Status.choices, "grade_choices": pedagogy.practice.GRADES,
        "editable": lesson.status != Lesson.Status.FINAL,
    })  # fmt: skip
