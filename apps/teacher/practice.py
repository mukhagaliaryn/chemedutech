"""Teacher: the digital research practices of section 5 (guide @S5 VII; STEP-35) — the finished practices of the
teacher's students and the 10-point grade (five criteria × 2), kept apart from the ICPAI component percents."""

from django.contrib import messages
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.translation import gettext as _

from apps.courses import selectors as course_selectors
from apps.pedagogy import frames
from apps.pedagogy import services as pedagogy
from apps.pedagogy.models import Lesson, Review, Trial

from .views import teacher_only


def _practices(request):
    return Lesson.objects.filter(
        kind=Lesson.Kind.RESEARCH_PRACTICE,
        status=Lesson.Status.FINAL,
        owner__in=course_selectors.teacher_students(request.user),
    ).select_related("owner__student_profile__group", "source_template", "review")


@teacher_only
def queue(request):
    """Finished practices: not graded first, then graded."""
    show = request.GET.get("show", "new")
    practices = _practices(request)
    counts = {
        "new": practices.filter(review__isnull=True).count(),
        "graded": practices.filter(review__isnull=False).count(),
    }
    rows = practices.filter(review__isnull=(show != "graded")).order_by("-updated_at")[:300]
    return render(request, "teacher/practice/queue.html", {"rows": rows, "show": show, "counts": counts})


@teacher_only
def detail(request, pk):
    """A practice: the sheet (I, II), the trial protocol and the analysis sheet (VI); the rubric form (VII)."""
    lesson = get_object_or_404(_practices(request), pk=pk)
    trial = lesson.trials.filter(mode=Trial.Mode.STEPWISE, finished_at__isnull=False).first()
    review = getattr(lesson, "review", None)
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
