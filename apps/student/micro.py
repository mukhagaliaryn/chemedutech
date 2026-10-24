"""Section 6 — the microlesson and the professional trial ground (guide @S6; pictures image21–23; STEP-36):
«Choose the microlesson» (a part of a section 5 practice) → «Create the microlesson» (one) → the sheet (I: details;
II: four stages, each marked by the AI checker only ✓ CORRECT / ✕ WRONG — III) → «Try it out» (IV: the class and the
AI student's level; a 10-minute dialogue: explanation, question, the AI student's answer, the pedagogical action) →
the trial protocol → «Change the microlesson» / «Try it out again» (V) → «Assemble the microlesson» (VII)."""

import json

from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from apps.ai import services as ai
from apps.core.permissions import STUDENT, role_required
from apps.pedagogy import frames
from apps.pedagogy import selectors as pedagogy_selectors
from apps.pedagogy import services as pedagogy
from apps.pedagogy.models import Check, Lesson, LessonStage, Review, Trial, TrialMessage
from apps.programme import services as programme
from apps.programme.models import Section

from .designer import TRIAL_LEVELS

FRAME = "micro_4"


def _section(request, number):
    enrollment = programme.refresh(request.user)
    if enrollment is None:
        raise Http404
    section = get_object_or_404(Section, programme=enrollment.programme, number=number, kind=Section.Kind.MICROLESSON)
    if not programme.can_access(enrollment, section):
        raise Http404
    return enrollment, section


def _micro(request, number):
    enrollment, section = _section(request, number)
    lesson = get_object_or_404(
        Lesson.objects.select_related("source_lesson__source_template"),
        owner=request.user,
        kind=Lesson.Kind.MICROLESSON,
    )
    return enrollment, section, lesson


def _trials(lesson) -> list[dict]:
    """The microlesson's trials, numbered (1-сынақ …), with their dialogue counts and the teacher's grade."""
    reviews = {r.trial_id: r for r in Review.objects.filter(lesson=lesson, trial__isnull=False)}
    rows = []
    for n, trial in enumerate(lesson.trials.filter(mode=Trial.Mode.DIALOG).order_by("started_at", "pk"), start=1):
        kinds = list(trial.messages.values_list("answer_type", flat=True))
        rows.append({
            "number": n, "trial": trial, "review": reviews.get(trial.pk), "messages": len(kinds),
            "counts": {k: kinds.count(k) for k in ("correct", "partial", "wrong")},
            "seconds": pedagogy.elapsed_s(trial),
        })  # fmt: skip
    return rows


def micro_context(user) -> dict:
    """The section page's part: the microlesson, or the student's section 5 practices with their eight stages to
    choose a part from."""
    lesson = Lesson.objects.filter(owner=user, kind=Lesson.Kind.MICROLESSON).first()
    if lesson:
        return {"micro": lesson, "micro_trials": _trials(lesson)}
    practices = (
        Lesson.objects.filter(owner=user, kind=Lesson.Kind.RESEARCH_PRACTICE)
        .select_related("source_template")
        .prefetch_related("stages")
        .order_by("source_template__number")
    )
    return {"micro": None, "micro_sources": list(practices)}


@require_POST
@role_required(STUDENT)
def micro_start(request, number):
    """«Create the microlesson» from the chosen part of a practice; there is only one."""
    _enrollment, section = _section(request, number)
    practice = get_object_or_404(
        Lesson, pk=request.POST.get("practice") or 0, owner=request.user, kind=Lesson.Kind.RESEARCH_PRACTICE
    )
    try:
        pedagogy.start_micro(request.user, practice, int(request.POST.get("stage") or 0))
    except (pedagogy.LessonError, ValueError):
        messages.error(request, _("Choose a part of your lesson."))
        return redirect("student:section", section.number)
    return redirect("student:micro", section.number)


def _stage_opts(request, section, stage) -> dict:
    fields = pedagogy_selectors.stage_fields(stage)
    return {
        "saveUrl": reverse("student:micro_stage_save", args=[section.number, stage.order]),
        "csrf": get_token(request),
        "cleared": True,
        "title": stage.title,
        "minutes": stage.minutes,
        "fields": {f["key"]: f["html"] for f in fields},
        "total": 10,
        "edited": stage.edited,
        "first": fields[0]["key"],
        "text": {"saving": _("Saving…"), "saved": _("Saved"), "failed": _("Not saved — check the connection"),
                 "clearFirst": "", "inserted": ""},
    }  # fmt: skip


@role_required(STUDENT)
def micro(request, number):
    """The sheet: part I (POST saves it), the source part, the four stages with the checker's marks, the checker's
    seven criteria, the trials and the way on."""
    enrollment, section, lesson = _micro(request, number)
    if request.method == "POST":
        try:
            pedagogy.save_micro_details(lesson, request.POST)
        except pedagogy.LessonError:
            messages.error(request, _("The final version cannot be changed."))
        else:
            messages.success(request, _("Saved"))
        return redirect("student:micro", section.number)
    stages = list(lesson.stages.all())
    state = pedagogy.check_state(lesson)
    check = state["check"]
    source = lesson.source_lesson
    part = source.stages.filter(order=lesson.details.get("source_stage")).first() if source else None
    rows = []
    for stage in stages:
        spec = frames.stage_spec(FRAME, stage.key)
        rows.append({
            "stage": stage, "spec": spec, "fields": pedagogy_selectors.stage_fields(stage),
            "opts": _stage_opts(request, section, stage), "opts_id": f"opts-{stage.order}",
            "verdict": check.stages.get(str(stage.order)) if check else None,
        })  # fmt: skip
    return render(request, "student/micro/editor.html", {
        "programme": enrollment.programme, "section": section, "lesson": lesson, "rows": rows, "state": state,
        "criteria": [{"key": k, "label": label, "verdict": check.criteria.get(k) if check else None}
                     for k, label in Check.CRITERIA],
        "source": source, "part": part, "part_spec": frames.stage_spec("research_8", part.key) if part else None,
        "grades": pedagogy.practice.GRADES, "trials": _trials(lesson), "locked": lesson.status == Lesson.Status.FINAL,
        "open_trial": lesson.trials.filter(mode=Trial.Mode.DIALOG, finished_at__isnull=True).first(),
        "ai_enabled": ai.enabled(), "remaining": ai.remaining_today(request.user),
    })  # fmt: skip


@require_POST
@role_required(STUDENT)
def micro_stage_save(request, number, order):
    _enrollment, _section_obj, lesson = _micro(request, number)
    stage = get_object_or_404(LessonStage, lesson=lesson, order=order)
    try:
        data = json.loads(request.body or b"{}")
        fields = data.get("fields") or {}
        if not isinstance(fields, dict):
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({"error": "bad_request"}, status=400)
    try:
        stage = pedagogy.save(stage, title="", minutes=None, fields=fields)
    except pedagogy.LessonError as exc:
        return JsonResponse({"error": str(exc)}, status=409)
    return JsonResponse({"edited": stage.edited, "minutes_total": 10})


@require_POST
@role_required(STUDENT)
def micro_check(request, number):
    """«Send for checking» / «Check again»: the checker marks the stages and the criteria."""
    _enrollment, section, lesson = _micro(request, number)
    try:
        pedagogy.check_micro(lesson)
    except ai.LimitReached:
        messages.error(request, _("Today's AI requests are used up. They renew tomorrow."))
    except ai.AIUnavailable:
        messages.error(request, _("The AI assistant did not answer this time. Try again in a minute."))
    except pedagogy.LessonError:
        messages.error(request, _("The final version cannot be changed."))
    return redirect(f"{reverse('student:micro', args=[section.number])}#checker")


@role_required(STUDENT)
def micro_trial(request, number):
    """«Try it out»: the class and the AI student's level (GET), the trial starts (POST)."""
    enrollment, section, lesson = _micro(request, number)
    open_trial = lesson.trials.filter(mode=Trial.Mode.DIALOG, finished_at__isnull=True).first()
    if open_trial:
        return redirect("student:micro_dialog", section.number, open_trial.pk)
    if request.method == "POST":
        try:
            trial = pedagogy.start_dialog(
                lesson, grade=request.POST.get("grade", ""), level=request.POST.get("level", "")
            )
        except pedagogy.LessonError as exc:
            messages.error(
                request,
                _("Choose the class and the AI student's level.")
                if str(exc) == "level"
                else _("First every stage must be marked correct by the AI assistant's check."),
            )
            return redirect("student:micro_trial", section.number)
        return redirect("student:micro_dialog", section.number, trial.pk)
    return render(request, "student/micro/trial_start.html", {
        "programme": enrollment.programme, "section": section, "lesson": lesson, "levels": TRIAL_LEVELS,
        "grades": pedagogy.practice.GRADES, "state": pedagogy.check_state(lesson), "trials": _trials(lesson),
    })  # fmt: skip


def _dialog_context(request, section, lesson, trial, error="") -> dict:
    seconds = pedagogy.elapsed_s(trial)
    return {
        "section": section, "lesson": lesson, "trial": trial, "error": error,
        "messages_": list(trial.messages.order_by("number")), "seconds": seconds,
        "left": max(0, pedagogy.DURATION_S - seconds), "stage": pedagogy.stage_at(seconds),
        "kinds": TrialMessage.Kind.choices, "ai_enabled": ai.enabled(),
    }  # fmt: skip


@role_required(STUDENT)
def micro_dialog(request, number, trial_pk):
    """The microlesson with the AI student (image23): the 10-minute timer over the four stages, the dialogue, the
    message box (explanation / question / pedagogical action), the microlesson beside; when the time is up the trial
    is finished and its protocol opens."""
    enrollment, section, lesson = _micro(request, number)
    trial = get_object_or_404(lesson.trials, pk=trial_pk, mode=Trial.Mode.DIALOG)
    if trial.finished_at is None and pedagogy.elapsed_s(trial) >= pedagogy.DURATION_S:
        pedagogy.finish_dialog(trial)
    if trial.finished_at:
        return redirect("student:micro_protocol", section.number, trial.pk)
    context = _dialog_context(request, section, lesson, trial)
    context.update({
        "programme": enrollment.programme, "number": pedagogy.trial_number(trial),
        "rows": [{"stage": s, "spec": frames.stage_spec(FRAME, s["key"])} for s in trial.version.snapshot["stages"]],
    })  # fmt: skip
    return render(request, "student/micro/dialog.html", context)


@require_POST
@role_required(STUDENT)
def micro_send(request, number, trial_pk):
    """HTMX: the teacher's message → the AI student's reply; answers the dialogue (and the time left)."""
    _enrollment, section, lesson = _micro(request, number)
    trial = get_object_or_404(lesson.trials, pk=trial_pk, mode=Trial.Mode.DIALOG)
    error = ""
    try:
        pedagogy.send(trial, kind=request.POST.get("kind", ""), text=request.POST.get("text", ""))
    except pedagogy.LessonError as exc:
        error = str(exc)
        if error in ("time_up", "finished"):
            response = HttpResponse(status=204)
            response["HX-Redirect"] = reverse("student:micro_protocol", args=[section.number, trial.pk])
            return response
    except ai.LimitReached:
        error = "limit"
    except ai.AIUnavailable:
        error = "failed"
    return render(
        request, "student/micro/partials/messages.html", _dialog_context(request, section, lesson, trial, error)
    )


@require_POST
@role_required(STUDENT)
def micro_finish(request, number, trial_pk):
    _enrollment, section, lesson = _micro(request, number)
    trial = get_object_or_404(lesson.trials, pk=trial_pk, mode=Trial.Mode.DIALOG)
    pedagogy.finish_dialog(trial)
    programme.refresh(request.user)
    return redirect("student:micro_protocol", section.number, trial.pk)


@role_required(STUDENT)
def micro_protocol(request, number, trial_pk):
    """The trial protocol (@S6 IV 6): the explanations, questions, the AI student's answers and the student's
    pedagogical actions by stage; the teacher's grade; «Change the microlesson» / «Try it out again»; the trials."""
    enrollment, section, lesson = _micro(request, number)
    trial = get_object_or_404(lesson.trials, pk=trial_pk, mode=Trial.Mode.DIALOG)
    if trial.finished_at is None:
        return redirect("student:micro_dialog", section.number, trial.pk)
    review = Review.objects.filter(trial=trial).first()
    trials = _trials(lesson)
    return render(request, "student/micro/protocol.html", {
        "programme": enrollment.programme, "section": section, "lesson": lesson, "trial": trial,
        "number": next((t["number"] for t in trials if t["trial"].pk == trial.pk), 1),
        "messages_": list(trial.messages.order_by("number")), "seconds": pedagogy.elapsed_s(trial),
        "stages": trial.version.snapshot["stages"], "review": review, "trials": trials,
        "score_rows": [{"number": n, "label": label, "points": review.scores.get(str(n)) if review else None}
                       for n, label in Review.MICRO_CRITERIA],
    })  # fmt: skip


@require_POST
@role_required(STUDENT)
def micro_assemble(request, number):
    """«Assemble the microlesson» — closes it with the history of its trials."""
    _enrollment, section, lesson = _micro(request, number)
    try:
        pedagogy.assemble_micro(lesson)
    except pedagogy.LessonError:
        messages.error(request, _("First try the microlesson out with the AI student."))
        return redirect("student:micro", section.number)
    programme.refresh(request.user)
    messages.success(request, _("The microlesson is assembled into your professional trial portfolio."))
    return redirect("student:micro", section.number)


@role_required(STUDENT)
def micro_pdf(request, number):
    from weasyprint import HTML

    _enrollment, _section_obj, lesson = _micro(request, number)
    version = lesson.versions.filter(reason="final").first()
    if version is None:
        raise Http404
    rows = [{"stage": s, "spec": frames.stage_spec(FRAME, s["key"]),
             "fields": [{"label": f.label, "html": s["fields"].get(f.key, "")}
                        for f in frames.fields_of(FRAME, s["key"]) if s["fields"].get(f.key)]}
            for s in version.snapshot["stages"]]  # fmt: skip
    reviews = {r.trial_id: r for r in Review.objects.filter(lesson=lesson, trial__isnull=False)}
    trials = [{**t, "review": reviews.get(t["pk"])} for t in version.snapshot.get("trials", [])]
    html = render(request, "student/micro/report_pdf.html", {
        "lesson": lesson, "plan": version.snapshot, "rows": rows, "trials": trials,
        "kinds": dict(TrialMessage.Kind.choices), "types": dict(TrialMessage.AnswerType.choices),
        "levels": dict(Trial.Level.choices),
    })  # fmt: skip
    data = HTML(string=html.content.decode(), base_url=request.build_absolute_uri("/")).write_pdf()
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="microlesson-{lesson.pk}.pdf"'
    return response


def micro_grades(user) -> list[dict]:
    """The section 6 trials with the teacher's grades («Results», kept apart from ICPAI)."""
    lesson = Lesson.objects.filter(owner=user, kind=Lesson.Kind.MICROLESSON).first()
    return [t for t in _trials(lesson) if t["trial"].finished_at] if lesson else []
