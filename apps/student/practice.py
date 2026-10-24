"""Section 5 — the digital research practice (guide @S5; picture image20; STEP-35): one practice per authorial
template → «The development sheet» (I: the lesson's details; II: eight stages, each with the AI assistant — III) →
«Try the lesson out» (IV: the class and the AI student's level; the stages one by one in six steps) → the analysis
sheet (VI) → «Finish the trial and gather the results» → the report with PDF; the teacher's 10-point grade (VII)."""

import json

from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from apps.ai import services as ai
from apps.ai.models import Mode
from apps.core.html import html_to_text
from apps.core.permissions import STUDENT, role_required
from apps.pedagogy import frames
from apps.pedagogy import selectors as pedagogy_selectors
from apps.pedagogy import services as pedagogy
from apps.pedagogy.models import Lesson, LessonStage, LessonTemplate, Review, Trial
from apps.programme import services as programme
from apps.programme.models import Section

from .designer import TRIAL_LEVELS

FRAME = "research_8"
# the AI assistant's services for the sheet (guide @S5 III, 1–7) and its four-part feedback
SHEET_QUICK = [
    ("explain_stage", _("Explain the stage"), "help"),
    ("sheet_feedback", _("The AI assistant's feedback"), "sparkle"),
    ("sheet_aim", _("Analyse whether the research aim fits the lesson topic"), "search"),
    ("sheet_order", _("Help put the tasks in order"), "list"),
    ("sheet_experiment", _("Remarks on the scientific correctness of the experiment"), "lab"),
    ("sheet_tools", _("Assess whether the digital tools fit the lesson aim"), "settings"),
    ("sheet_age", _("Methodical advice for the students' age and readiness"), "users"),
    ("sheet_time", _("Analyse whether the stage's time is enough"), "clock"),
    ("sheet_criteria", _("Make the assessment criteria and descriptors precise"), "check-square"),
]


def _section(request, number):
    enrollment = programme.refresh(request.user)
    if enrollment is None:
        raise Http404
    section = get_object_or_404(
        Section, programme=enrollment.programme, number=number, kind=Section.Kind.RESEARCH_PRACTICE
    )
    if not programme.can_access(enrollment, section):
        raise Http404
    return enrollment, section


def _practice(request, number, pk):
    enrollment, section = _section(request, number)
    lesson = get_object_or_404(
        Lesson.objects.select_related("source_template", "source_lesson"),
        pk=pk, owner=request.user, kind=Lesson.Kind.RESEARCH_PRACTICE,
    )  # fmt: skip
    return enrollment, section, lesson


def _base(enrollment, section, lesson) -> dict:
    stages = list(lesson.stages.all())
    return {
        "programme": enrollment.programme,
        "section": section,
        "lesson": lesson,
        "template": lesson.source_template,
        "stages": stages,
        "specs": dict(zip([s.order for s in stages], frames.RESEARCH_8, strict=False)),
        "filled": sum(1 for s in stages if any(s.fields.values())),
        "trial": lesson.trials.first(),
    }


def practice_context(user) -> dict:
    """The section page's part: one card per authorial template — its section 4 lesson, the practice and its grade."""
    practices = {
        p.source_template_id: p
        for p in Lesson.objects.filter(owner=user, kind=Lesson.Kind.RESEARCH_PRACTICE).prefetch_related("stages")
    }
    sources = {p.source_template_id: p for p in Lesson.objects.filter(owner=user, kind=Lesson.Kind.TEMPLATE_COPY)}
    reviews = {r.lesson_id: r for r in Review.objects.filter(lesson__in=practices.values())}
    cards = []
    for template in pedagogy_selectors.templates():
        practice = practices.get(template.pk)
        stages = list(practice.stages.all()) if practice else []
        cards.append({
            "template": template, "source": sources.get(template.pk), "practice": practice,
            "filled": sum(1 for s in stages if any(s.fields.values())), "stage_count": len(frames.RESEARCH_8),
            "review": reviews.get(practice.pk) if practice else None,
        })  # fmt: skip
    return {"practices": cards}


def practice_grades(user) -> list[dict]:
    """The finished section 5 practices with the teacher's 10-point grade («Results», kept apart from ICPAI)."""
    lessons = Lesson.objects.filter(owner=user, kind=Lesson.Kind.RESEARCH_PRACTICE, status=Lesson.Status.FINAL)
    return [
        {"lesson": lesson, "review": getattr(lesson, "review", None)}
        for lesson in lessons.select_related("source_template", "review").order_by("source_template__number")
    ]


@require_POST
@role_required(STUDENT)
def practice_start(request, number, code):
    _enrollment, section = _section(request, number)
    template = get_object_or_404(LessonTemplate, code=code, is_active=True)
    lesson = pedagogy.start_practice(request.user, template)
    return redirect("student:practice", section.number, lesson.pk)


@role_required(STUDENT)
def practice(request, number, pk):
    """Part I of the sheet: the lesson's details; the structure of the eight stages; the section 4 lesson as source."""
    enrollment, section, lesson = _practice(request, number, pk)
    if request.method == "POST":
        try:
            pedagogy.save_sheet_details(lesson, request.POST)
        except pedagogy.LessonError:
            messages.error(request, _("The final version cannot be changed."))
        else:
            messages.success(request, _("Saved"))
        return redirect("student:practice", section.number, lesson.pk)
    context = _base(enrollment, section, lesson)
    context.update({"grades": pedagogy.practice.GRADES, "problems": pedagogy.sheet_problems(lesson)})
    if lesson.source_lesson:
        version = lesson.source_lesson.versions.order_by("-number").first()
        context["source_rows"] = pedagogy_selectors.timeline(list(lesson.source_lesson.stages.all()))
        context["source_version"] = version
        designer = Section.objects.filter(programme=enrollment.programme, kind=Section.Kind.DESIGNER).first()
        context["designer_number"] = designer.number if designer else None
    return render(request, "student/practice/sheet.html", context)


def _ai_panel(request, section, lesson, stage, error="") -> dict:
    return {
        "ai_enabled": ai.enabled(),
        "panel_id": f"ai-stage-{stage.pk}",
        "post_url": reverse("student:practice_stage_ai", args=[section.number, lesson.pk, stage.order]),
        "thread": ai.thread(request.user, Mode.ASSISTANT, "lesson_stage", stage.pk),
        "remaining": ai.remaining_today(request.user),
        "error": error,
        "quick": SHEET_QUICK,
        "quick_list": True,
        "insert": True,
        "title": _("AI-assistant"),
        "subtitle": _("I analyse your task and help to improve it."),
        "placeholder": _("Ask about this stage…"),
    }


@role_required(STUDENT)
def practice_stage(request, number, pk, order):
    """Part II: one of the eight stages — its minutes and aim, its fields (saved by themselves), the AI assistant."""
    enrollment, section, lesson = _practice(request, number, pk)
    stage = get_object_or_404(LessonStage, lesson=lesson, order=order)
    spec = frames.stage_spec(FRAME, stage.key)
    fields = pedagogy_selectors.stage_fields(stage)
    context = _base(enrollment, section, lesson)
    context.update({
        "stage": stage,
        "spec": spec,
        "fields": fields,
        "locked": lesson.status == Lesson.Status.FINAL,
        "editor_opts": {
            "saveUrl": reverse("student:practice_stage_save", args=[section.number, lesson.pk, stage.order]),
            "csrf": get_token(request),
            "cleared": True,
            "title": stage.title,
            "minutes": stage.minutes,
            "fields": {f["key"]: f["html"] for f in fields},
            "total": lesson.duration_min,
            "edited": stage.edited,
            "first": fields[0]["key"],
            "text": {
                "saving": _("Saving…"),
                "saved": _("Saved"),
                "failed": _("Not saved — check the connection"),
                "clearFirst": "",
                "inserted": _("The suggestion is in the editor — rework it in your own words."),
            },
        },
    })  # fmt: skip
    context.update(_ai_panel(request, section, lesson, stage))
    return render(request, "student/practice/stage.html", context)


@require_POST
@role_required(STUDENT)
def practice_stage_save(request, number, pk, order):
    _enrollment, _section_obj, lesson = _practice(request, number, pk)
    stage = get_object_or_404(LessonStage, lesson=lesson, order=order)
    try:
        data = json.loads(request.body or b"{}")
        fields = data.get("fields") or {}
        if not isinstance(fields, dict):
            raise ValueError
        inserted = int(data["inserted"]) if data.get("inserted") else None
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({"error": "bad_request"}, status=400)
    try:
        stage = pedagogy.save(stage, title="", minutes=None, fields=fields, inserted=inserted)
    except pedagogy.LessonError as exc:
        return JsonResponse({"error": str(exc)}, status=409)
    return JsonResponse({"edited": stage.edited, "minutes_total": lesson.duration_min})


def _stage_context(lesson, stage) -> str:
    spec = frames.stage_spec(FRAME, stage.key)
    draft = "\n\n".join(
        f"{f['label']}:\n{html_to_text(f['html'])}" for f in pedagogy_selectors.stage_fields(stage) if f["html"]
    )
    outline = "\n".join(f"{n}. {s.title} ({s.start}–{s.end} min)" for n, s in enumerate(frames.RESEARCH_8, start=1))
    return (
        "Section 5 «Digital research practice»: the student fills «The development sheet of the digital research "
        "practice» — eight stages of a 45-minute chemistry lesson — then conducts it stage by stage with an AI student.\n"
        f"Lesson: «{lesson.title}»; chemistry topic: {lesson.topic}; grade: {lesson.grade or '—'}.\n"
        f"Aim: {lesson.aim}\nAuthorial method: {lesson.method or '—'}\nDigital tools: {lesson.digital_tools or '—'}\n"
        f"Stages:\n{outline}\n\nThe student is on stage {stage.order} «{stage.title}» "
        f"({spec.start}–{spec.end} min). Its aim (the author's): {spec.aim}\n"
        f"The fields of the stage: {', '.join(str(f.label) for f in spec.fields)}.\n"
        f"The student's draft so far:\n{ai.quote(draft) if draft else '(empty)'}"
    )


@require_POST
@role_required(STUDENT)
def practice_stage_ai(request, number, pk, order):
    _enrollment, section, lesson = _practice(request, number, pk)
    stage = get_object_or_404(LessonStage, lesson=lesson, order=order)
    error = ""
    try:
        ai.ask(
            request.user, context_type="lesson_stage", context_id=stage.pk, context=_stage_context(lesson, stage),
            text=request.POST.get("text", ""), intent=request.POST.get("intent", ""),
        )  # fmt: skip
    except ai.LimitReached:
        error = "limit"
    except ai.AIUnavailable as exc:
        error = "" if str(exc) == "empty" else "failed"
    return render(request, "ai/partials/thread.html", _ai_panel(request, section, lesson, stage, error))


# --- IV «Try the lesson out» — stage by stage --------------------------------------------------------------------


@role_required(STUDENT)
def practice_trial(request, number, pk):
    """The class and the AI student's level (GET), then the trial starts (POST); an unfinished trial goes on."""
    enrollment, section, lesson = _practice(request, number, pk)
    if request.method == "POST":
        try:
            trial = pedagogy.start_stepwise(
                lesson, grade=request.POST.get("grade", ""), level=request.POST.get("level", "")
            )
        except pedagogy.LessonError as exc:
            messages.error(
                request,
                _("Choose the class and the AI student's level.")
                if str(exc) == "level"
                else _("Fill in the sheet first — see what is missing."),
            )
            return redirect("student:practice_trial", section.number, lesson.pk)
        return redirect("student:practice_step", section.number, lesson.pk, trial.pk, 1)
    trial = lesson.trials.filter(finished_at__isnull=True).first()
    if trial and lesson.status != Lesson.Status.FINAL and request.GET.get("new") is None:
        order = pedagogy.current_order(trial)
        if order:
            return redirect("student:practice_step", section.number, lesson.pk, trial.pk, order)
    context = _base(enrollment, section, lesson)
    context.update({
        "levels": TRIAL_LEVELS,
        "grades": pedagogy.practice.GRADES,
        "problems": pedagogy.sheet_problems(lesson),
    })  # fmt: skip
    return render(request, "student/practice/trial_start.html", context)


def _trial(lesson, trial_pk) -> Trial:
    return get_object_or_404(lesson.trials.select_related("version"), pk=trial_pk, mode=Trial.Mode.STEPWISE)


@role_required(STUDENT)
def practice_step(request, number, pk, trial_pk, order):
    """One stage of the trial in six steps (@S5 IV): the teacher's explanation, the task, the time → the AI student's
    answer (V) → the analysis (VI) → the next stage. Stages open one by one."""
    enrollment, section, lesson = _practice(request, number, pk)
    trial = _trial(lesson, trial_pk)
    stages = trial.version.snapshot["stages"]
    stage = next((s for s in stages if s["order"] == order), None)
    if stage is None:
        raise Http404
    current = pedagogy.current_order(trial)
    if current is not None and order > current:
        return redirect("student:practice_step", section.number, lesson.pk, trial.pk, current)
    turn = trial.turns.filter(stage_order=order).first()
    error = ""
    if request.method == "POST":
        post = request.POST
        try:
            if post.get("action") == "give":
                pedagogy.give_task(
                    trial, order, explanation=post.get("explanation", ""), task=post.get("task", ""),
                    minutes=post.get("minutes"),
                )  # fmt: skip
                return redirect(f"{request.path}#answer")
            if post.get("action") == "analyse" and turn:
                pedagogy.analyse(
                    turn, analysis=post.get("analysis", ""), follow_up=post.get("follow_up", ""),
                    correction=post.get("correction", ""), improved_task=post.get("improved_task", ""),
                    duration_s=post.get("duration_s"),
                )  # fmt: skip
                following = pedagogy.current_order(trial)
                if following:
                    return redirect("student:practice_step", section.number, lesson.pk, trial.pk, following)
                return redirect("student:practice_results", section.number, lesson.pk)
        except ai.LimitReached:
            error = "limit"
        except ai.AIUnavailable as exc:
            error = "off" if str(exc) == "disabled" else "failed"
        except pedagogy.LessonError as exc:
            error = str(exc)
        turn = trial.turns.filter(stage_order=order).first()
    done = {t.stage_order: t for t in trial.turns.filter(analysed_at__isnull=False)}
    context = _base(enrollment, section, lesson)
    context.update({
        "trial": trial,
        "stage": stage,
        "spec": frames.stage_spec(FRAME, stage.get("key", "")),
        "trial_stages": [{**s, "done": s["order"] in done, "open": current is None or s["order"] <= current}
                         for s in stages],
        "turn": turn,
        "prefill": pedagogy.prefill(stage),
        "error": error,
        "ai_enabled": ai.enabled(),
        "remaining": ai.remaining_today(request.user),
        "is_last": order == stages[-1]["order"],
    })  # fmt: skip
    return render(request, "student/practice/step.html", context)


@role_required(STUDENT)
def practice_results(request, number, pk):
    """The analysis sheet after the trial (VI) for every stage → «Finish the trial and gather the results»; after
    that — the report: the sheet, the AI student's answers, the corrections, the teacher's grade."""
    enrollment, section, lesson = _practice(request, number, pk)
    trial = lesson.trials.filter(mode=Trial.Mode.STEPWISE).select_related("version").first()
    if trial is None:
        return redirect("student:practice_trial", section.number, lesson.pk)
    context = _base(enrollment, section, lesson)
    context.update(_report(lesson, trial))
    context["open_stage"] = pedagogy.current_order(trial)
    return render(request, "student/practice/results.html", context)


def _report(lesson, trial) -> dict:
    version = lesson.versions.filter(reason="final").first() or trial.version
    turns = {t.stage_order: t for t in trial.turns.all()}
    rows = []
    for s in version.snapshot["stages"]:
        spec = frames.stage_spec(FRAME, s.get("key", ""))
        labels = {f.key: f.label for f in spec.fields} if spec else {}
        rows.append({
            "stage": s, "spec": spec, "turn": turns.get(s["order"]),
            "fields": [{"label": labels.get(k, k), "html": v} for k, v in s["fields"].items() if v],
        })  # fmt: skip
    kinds = [t.answer_type for t in turns.values()]
    review = getattr(lesson, "review", None) if lesson.status == Lesson.Status.FINAL else None
    return {
        "trial": trial,
        "version": version,
        "plan": version.snapshot,
        "rows": rows,
        "counts": {k: kinds.count(k) for k in ("correct", "partial", "wrong")},
        "review": review,
        "score_rows": [
            {"number": n, "label": label, "points": review.scores.get(str(n)) if review else None}
            for n, label in Review.CRITERIA
        ],
    }


@require_POST
@role_required(STUDENT)
def practice_finish(request, number, pk):
    _enrollment, section, lesson = _practice(request, number, pk)
    trial = lesson.trials.filter(mode=Trial.Mode.STEPWISE, finished_at__isnull=True).first()
    if trial is None:
        return redirect("student:practice_results", section.number, lesson.pk)
    try:
        pedagogy.finish(trial)
    except pedagogy.LessonError:
        messages.error(request, _("First analyse the AI student's answer at every stage."))
    else:
        programme.refresh(request.user)
        messages.success(request, _("The trial is finished; the results are gathered into your research portfolio."))
    return redirect("student:practice_results", section.number, lesson.pk)


@role_required(STUDENT)
def practice_pdf(request, number, pk):
    from weasyprint import HTML

    _enrollment, _section_obj, lesson = _practice(request, number, pk)
    trial = lesson.trials.filter(mode=Trial.Mode.STEPWISE).select_related("version").first()
    if trial is None:
        raise Http404
    html = render(request, "student/practice/report_pdf.html", {"lesson": lesson, **_report(lesson, trial)})
    data = HTML(string=html.content.decode(), base_url=request.build_absolute_uri("/")).write_pdf()
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="practice-{lesson.pk}.pdf"'
    return response
