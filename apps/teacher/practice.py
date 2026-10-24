"""Teacher: the works of sections 5 and 6 — the finished digital research practices (guide @S5 VII; STEP-35) and
the finished trials of the microlessons (@S6 VI; STEP-36, each trial graded apart) of the teacher's students, with the
10-point grade (five criteria × 2), kept apart from the ICPAI component percents."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.courses import selectors as course_selectors
from apps.pedagogy import frames
from apps.pedagogy import services as pedagogy
from apps.pedagogy.models import Lesson, Review, Trial

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
    what = "micro" if request.GET.get("what") == "micro" else "practice"
    practices, trials = _practices(request), _micro_trials(request)
    counts = {
        "practice": practices.filter(reviews__isnull=True).count(),
        "micro": trials.filter(reviews__isnull=True).count(),
    }
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
