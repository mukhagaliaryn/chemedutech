"""Section 4 — the pedagogical design constructor (guide @S4, @S4-L1…L3, @S4-AI; pictures image12–18; STEP-33):
the authorial templates → a template page → «Create my version» → the editor: the lesson structure, the chosen stage
(«Clear the content», the student's own fields), the AI assistant with the stage's quick requests. Then (guide
@S4-ASSEMBLE; STEP-34) «Assemble the lesson» → the plan (image17, PDF) → the trial with the AI student → «Trial results»
→ «Assemble the final version»."""

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
from apps.pedagogy import selectors as pedagogy_selectors
from apps.pedagogy import services as pedagogy
from apps.pedagogy.models import Lesson, LessonStage, LessonTemplate, Trial
from apps.programme import services as programme
from apps.programme.models import Section

# the AI student's levels with the guide's descriptions (@S4-ASSEMBLE 2)
TRIAL_LEVELS = [
    (Trial.Level.HIGH, _("Fully understands the task, gives scientific evidence and draws complex conclusions.")),
    (Trial.Level.MEDIUM, _("Knows the basic concepts but needs extra explanation in some tasks.")),
    (
        Trial.Level.LOW,
        _("May make mistakes in explaining chemical concepts, needs guiding questions and extra support."),
    ),
]

# the AI assistant's help on a stage (guide @S4-AI 3 and image18 «Көмек түрін таңдаңыз»; the author's note at
# @S4-L1: every numbered part is explained by the AI assistant, even how to choose its title)
STAGE_QUICK = [
    ("explain_stage", _("Explain the stage"), "help"),
    ("experiment_idea", _("Suggest a virtual experiment idea"), "lab"),
    ("research_questions", _("Develop research questions"), "search"),
    ("descriptors", _("Build assessment descriptors"), "check-square"),
    ("check_science", _("Check the scientific content"), "check"),
    ("student_answer", _("A virtual student's sample answer"), "user"),
    ("timing", _("Analyse the fit to the time"), "clock"),
    ("methods", _("Suggest alternative teaching methods"), "sparkle"),
]


def _section(request, number):
    """The open designer section of the student's programme."""
    enrollment = programme.refresh(request.user)
    if enrollment is None:
        raise Http404
    section = get_object_or_404(Section, programme=enrollment.programme, number=number, kind=Section.Kind.DESIGNER)
    if not programme.can_access(enrollment, section):
        raise Http404
    return enrollment, section


def _lesson(request, number, pk):
    enrollment, section = _section(request, number)
    lesson = get_object_or_404(Lesson.objects.select_related("source_template"), pk=pk, owner=request.user)
    return enrollment, section, lesson


def _stage(lesson, order) -> LessonStage:
    return get_object_or_404(LessonStage, lesson=lesson, order=order)


def designer_context(user) -> dict:
    """The section page's part: the template cards."""
    return {"designer": pedagogy_selectors.template_cards(user)}


@role_required(STUDENT)
def template(request, number, code):
    """An authorial template in full (image12): header, aim, the 45-minute bar, the six stages with their blocks,
    the expected results and the product; «Create my version» / «Open my version»."""
    enrollment, section = _section(request, number)
    template = get_object_or_404(pedagogy_selectors.templates(), code=code)
    stages = list(template.stages.all())
    return render(
        request,
        "student/designer/template.html",
        {
            "programme": enrollment.programme,
            "section": section,
            "template": template,
            "timeline": pedagogy_selectors.timeline(stages),
            "stage_blocks": [(s, pedagogy_selectors.template_blocks(s)) for s in stages],
            "lesson": pedagogy_selectors.lesson_of(request.user, template),
            "others": [t for t in pedagogy_selectors.templates() if t.pk != template.pk],
        },
    )


@require_POST
@role_required(STUDENT)
def lesson_start(request, number, code):
    """«Create my version»: the student's copy of the template, then the editor."""
    _enrollment, section = _section(request, number)
    template = get_object_or_404(LessonTemplate, code=code, is_active=True)
    lesson = pedagogy.start(request.user, template)
    return redirect("student:lesson_stage", section.number, lesson.pk, 1)


@role_required(STUDENT)
def lesson(request, number, pk):
    _enrollment, section, lesson = _lesson(request, number, pk)
    return redirect("student:lesson_stage", section.number, lesson.pk, 1)


def _ai_panel(request, section, lesson, stage, error="") -> dict:
    return {
        "ai_enabled": ai.enabled(),
        "panel_id": f"ai-stage-{stage.pk}",
        "post_url": reverse("student:lesson_stage_ai", args=[section.number, lesson.pk, stage.order]),
        "thread": ai.thread(request.user, Mode.ASSISTANT, "lesson_stage", stage.pk),
        "remaining": ai.remaining_today(request.user),
        "error": error,
        "quick": STAGE_QUICK,
        "quick_list": True,
        "insert": True,
        "title": _("AI-assistant"),
        "subtitle": _("How can I help?"),
        "placeholder": _("Ask about this stage…"),
    }


@role_required(STUDENT)
def lesson_stage(request, number, pk, order):
    """The editor (image18): the lesson structure on the left, the chosen stage in the middle, the AI on the right."""
    enrollment, section, lesson = _lesson(request, number, pk)
    stage = _stage(lesson, order)
    stages = list(lesson.stages.all())
    fields = pedagogy_selectors.stage_fields(stage)
    context = {
        "programme": enrollment.programme,
        "section": section,
        "lesson": lesson,
        "template": lesson.source_template,
        "stage": stage,
        "stages": pedagogy_selectors.timeline(stages),
        "fields": fields,
        "edited_others": sum(1 for s in stages if s.edited and s.pk != stage.pk),
        "previous": next((s for s in reversed(stages) if s.order < stage.order), None),
        "following": next((s for s in stages if s.order > stage.order), None),
        "locked": lesson.status == Lesson.Status.FINAL,
        "editor_opts": {
            "saveUrl": reverse("student:lesson_stage_save", args=[section.number, lesson.pk, stage.order]),
            "csrf": get_token(request),
            "cleared": stage.cleared,
            "title": stage.title,
            "minutes": stage.minutes,
            "fields": {f["key"]: f["html"] for f in fields},
            "total": sum(s.minutes for s in stages),
            "edited": stage.edited,
            "first": fields[0]["key"],
            "text": {
                "saving": _("Saving…"),
                "saved": _("Saved"),
                "failed": _("Not saved — check the connection"),
                "clearFirst": _("To write the stage anew, first clear its content."),
                "inserted": _("The suggestion is in the editor — rework it in your own words."),
            },
        },
    }
    context.update(_ai_panel(request, section, lesson, stage))
    return render(request, "student/designer/editor.html", context)


@require_POST
@role_required(STUDENT)
def lesson_stage_clear(request, number, pk, order):
    """«Clear the content»: the original leaves the editor, an empty work area opens (guide @S4-AI)."""
    _enrollment, section, lesson = _lesson(request, number, pk)
    try:
        pedagogy.clear(_stage(lesson, order))
    except pedagogy.LessonError:
        messages.error(request, _("The final version cannot be changed."))
    return redirect("student:lesson_stage", section.number, lesson.pk, order)


@require_POST
@role_required(STUDENT)
def lesson_stage_restore(request, number, pk, order):
    _enrollment, section, lesson = _lesson(request, number, pk)
    try:
        pedagogy.restore(_stage(lesson, order))
    except pedagogy.LessonError:
        messages.error(request, _("The final version cannot be changed."))
    return redirect("student:lesson_stage", section.number, lesson.pk, order)


@require_POST
@role_required(STUDENT)
def lesson_stage_save(request, number, pk, order):
    """The editor's autosave: {title, minutes, fields: {key: html}, inserted} → {edited, minutes, minutes_total}."""
    _enrollment, _section_obj, lesson = _lesson(request, number, pk)
    stage = _stage(lesson, order)
    try:
        data = json.loads(request.body or b"{}")
        fields = data.get("fields") or {}
        if not isinstance(fields, dict):
            raise ValueError
        inserted = int(data["inserted"]) if data.get("inserted") else None
    except (ValueError, TypeError, AttributeError):
        return JsonResponse({"error": "bad_request"}, status=400)
    try:
        stage = pedagogy.save(
            stage, title=data.get("title", ""), minutes=data.get("minutes"), fields=fields, inserted=inserted
        )
    except pedagogy.LessonError as exc:
        return JsonResponse({"error": str(exc)}, status=409)
    total = sum(lesson.stages.values_list("minutes", flat=True))
    return JsonResponse(
        {"edited": stage.edited, "title": stage.title, "minutes": stage.minutes, "minutes_total": total}
    )


def _stage_context(lesson, stage) -> str:
    """What the AI assistant knows about the stage: the template, the lesson, the stage and the student's draft."""
    stages = list(lesson.stages.all())
    start = sum(s.minutes for s in stages if s.order < stage.order)
    outline = "\n".join(f"{s.order}. «{s.title}» – {s.minutes} min" for s in stages)
    if stage.cleared:
        draft = "\n\n".join(
            f"{f['label']}:\n{html_to_text(f['html'])}" for f in pedagogy_selectors.stage_fields(stage) if f["html"]
        )
        state = (
            "The student cleared the template's content of this stage and is writing it anew. Their draft so far:\n"
            + (ai.quote(draft) if draft else "(empty)")
        )
    else:
        original = "\n\n".join(
            f"{f['label']}:\n{html_to_text(f['html'])}" for f in pedagogy_selectors.stage_fields(stage) if f["html"]
        )
        state = (
            "The stage still has the template's content (the author's text). To change it the student clicks "
            f"«Clear the content» and writes the stage anew.\nThe template's content:\n{original}"
        )
    template = lesson.source_template
    return (
        "Section 4 «Pedagogical design constructor»: the student studies an authorial 45-minute chemistry lesson "
        "template, redesigns its stages with the AI assistant, then assembles the lesson and tries it out with an AI "
        "student.\n"
        f"Authorial template: «{template.name if template else lesson.title}»; lesson topic: {lesson.topic}; "
        f"{lesson.grade}.\nLesson aim: {lesson.aim}\nStages:\n{outline}\n\n"
        f"The student is on stage {stage.order} «{stage.title}» ({start}–{start + stage.minutes} min).\n{state}"
    )


@require_POST
@role_required(STUDENT)
def lesson_stage_ai(request, number, pk, order):
    """HTMX: a question or a quick request to the AI assistant about the stage; answers the thread."""
    _enrollment, section, lesson = _lesson(request, number, pk)
    stage = _stage(lesson, order)
    error = ""
    try:
        ai.ask(
            request.user,
            context_type="lesson_stage",
            context_id=stage.pk,
            context=_stage_context(lesson, stage),
            text=request.POST.get("text", ""),
            intent=request.POST.get("intent", ""),
        )
    except ai.LimitReached:
        error = "limit"
    except ai.AIUnavailable as exc:
        error = "" if str(exc) == "empty" else "failed"
    return render(request, "ai/partials/thread.html", _ai_panel(request, section, lesson, stage, error))


# --- «Assemble the lesson», the AI student, «Assemble the final version» (guide @S4-ASSEMBLE; STEP-34) ----------


def _lesson_context(enrollment, section, lesson) -> dict:
    return {"programme": enrollment.programme, "section": section, "lesson": lesson, "template": lesson.source_template}


@role_required(STUDENT)
def lesson_assemble(request, number, pk):
    """Before «Assemble the lesson»: the lesson's name, topic, aim and expected results (editable), what is still
    missing (empty stages, the minutes), the stages at a glance; the button assembles a version."""
    enrollment, section, lesson = _lesson(request, number, pk)
    if request.method == "POST":
        if lesson.status == Lesson.Status.FINAL:
            messages.error(request, _("The final version cannot be changed."))
            return redirect("student:lesson_plan", section.number, lesson.pk)
        post = request.POST
        pedagogy.save_details(
            lesson, title=post.get("title", ""), topic=post.get("topic", ""), aim=post.get("aim", ""),
            outcomes=post.get("outcomes", ""),
        )  # fmt: skip
        if post.get("action") == "assemble":
            try:
                pedagogy.assemble(lesson)
            except pedagogy.LessonError:
                messages.error(request, _("The lesson cannot be assembled yet — see what is missing."))
            else:
                messages.success(request, _("The lesson is assembled."))
                return redirect("student:lesson_plan", section.number, lesson.pk)
        else:
            messages.success(request, _("Saved"))
        return redirect("student:lesson_assemble", section.number, lesson.pk)
    stages = list(lesson.stages.all())
    problems = pedagogy.problems(lesson)
    codes = {p["code"] for p in problems}
    context = _lesson_context(enrollment, section, lesson)
    context.update({
        "problems": problems,
        "details_problem": "details" in codes,
        "empty_stages": "empty_stage" in codes,
        "minutes_problem": "minutes" in codes,
        "blocked": bool(codes - {"details"}),  # the details are saved by the same button
        "stages": pedagogy_selectors.timeline(stages),
        "edited_count": sum(1 for s in stages if s.edited),
        "minutes_total": sum(s.minutes for s in stages),
        "version": pedagogy.assembled_version(lesson),
    })  # fmt: skip
    return render(request, "student/designer/assemble.html", context)


def _plan_version(lesson, request):
    """The version shown: ?v=N, else the final one, else the latest assembled one."""
    versions = lesson.versions.order_by("-number")
    if request.GET.get("v", "").isdigit():
        return get_object_or_404(versions, number=int(request.GET["v"]))
    return versions.filter(reason="final").first() or versions.first()


def _plan_context(lesson, version) -> dict:
    return {
        "version": version,
        "plan": version.snapshot,
        "rows": pedagogy_selectors.plan_rows(version.snapshot),
        "columns": pedagogy_selectors.PLAN_COLUMNS,
    }


@role_required(STUDENT)
def lesson_plan(request, number, pk):
    """The assembled lesson as the short-term lesson plan (image17), with PDF, print and the way to the trial."""
    enrollment, section, lesson = _lesson(request, number, pk)
    version = _plan_version(lesson, request)
    if version is None:
        return redirect("student:lesson_assemble", section.number, lesson.pk)
    context = _lesson_context(enrollment, section, lesson)
    context.update(_plan_context(lesson, version))
    context.update({"versions": list(lesson.versions.order_by("-number")), "trial": lesson.trials.first()})
    return render(request, "student/designer/plan.html", context)


@role_required(STUDENT)
def lesson_plan_pdf(request, number, pk):
    from weasyprint import HTML

    _enrollment, _section_obj, lesson = _lesson(request, number, pk)
    version = _plan_version(lesson, request)
    if version is None:
        raise Http404
    html = render(request, "student/designer/plan_pdf.html", {"lesson": lesson, **_plan_context(lesson, version)})
    data = HTML(string=html.content.decode(), base_url=request.build_absolute_uri("/")).write_pdf()
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="lesson-{lesson.pk}-v{version.number}.pdf"'
    return response


def _trial(lesson, request, trial_pk=None):
    trials = lesson.trials.select_related("version")
    if trial_pk:
        return get_object_or_404(trials, pk=trial_pk)
    pick = request.GET.get("trial", "")
    return get_object_or_404(trials, pk=int(pick)) if pick.isdigit() else trials.first()


@role_required(STUDENT)
def lesson_trial(request, number, pk):
    """«Try it out with the AI student»: the level (high / medium / low), then every stage of the assembled lesson
    with «See the AI student's answer»; the guide's warning that this is a simulation."""
    enrollment, section, lesson = _lesson(request, number, pk)
    if pedagogy.assembled_version(lesson) is None:
        return redirect("student:lesson_assemble", section.number, lesson.pk)
    trial = _trial(lesson, request)
    stages = trial.version.snapshot["stages"] if trial else []
    made = {t.stage_order: t for t in trial.turns.all()} if trial else {}
    turns = {s["order"]: made.get(s["order"]) for s in stages}  # None where not made: the template filter «get»
    context = _lesson_context(enrollment, section, lesson)
    context.update({
        "trial": trial,
        "trials": list(lesson.trials.all()),
        "turns": turns,
        "stages": stages,
        "done": len(made),
        "progress": round(len(made) * 100 / len(stages)) if stages else 0,
        "levels": TRIAL_LEVELS,
        "ai_enabled": ai.enabled(),
        "remaining": ai.remaining_today(request.user),
    })  # fmt: skip
    return render(request, "student/designer/trial.html", context)


@require_POST
@role_required(STUDENT)
def lesson_trial_start(request, number, pk):
    _enrollment, section, lesson = _lesson(request, number, pk)
    try:
        trial = pedagogy.start_trial(lesson, request.POST.get("level", ""))
    except pedagogy.LessonError:
        messages.error(request, _("Choose the AI student's level."))
        return redirect("student:lesson_trial", section.number, lesson.pk)
    return redirect(f"{reverse('student:lesson_trial', args=[section.number, lesson.pk])}?trial={trial.pk}")


@role_required(STUDENT)
def lesson_trial_turn(request, number, pk, trial_pk, order):
    """HTMX: the window «See the AI student's answer» of one stage — made by the AI on the first POST, then shown."""
    _enrollment, section, lesson = _lesson(request, number, pk)
    trial = _trial(lesson, request, trial_pk)
    try:
        stage = pedagogy.stage_of(trial, order)
    except pedagogy.LessonError:
        raise Http404 from None
    turn, error = trial.turns.filter(stage_order=order).first(), ""
    if turn is None and request.method == "POST":
        try:
            turn = pedagogy.run_turn(trial, order)
        except ai.LimitReached:
            error = "limit"
        except ai.AIUnavailable as exc:
            error = "off" if str(exc) == "disabled" else "failed"
    fresh = request.method == "POST" and turn is not None and not error
    context = {"section": section, "lesson": lesson, "trial": trial, "stage": stage, "turn": turn, "error": error}
    context["fresh"] = fresh
    context["task"] = turn.task if turn else pedagogy.task_html(stage)
    return render(request, "student/designer/partials/turn.html", context)


@role_required(STUDENT)
def lesson_results(request, number, pk):
    """«Trial results»: by stage — the difficulties, the possible errors, the methodical suggestions and the stages
    revised since; «Assemble the final version» once a trial is finished."""
    enrollment, section, lesson = _lesson(request, number, pk)
    trial = _trial(lesson, request)
    if trial is None:
        return redirect("student:lesson_trial", section.number, lesson.pk)
    turns = {t.stage_order: t for t in trial.turns.all()}
    kinds = [t.answer_type for t in turns.values()]
    revised = pedagogy_selectors.changed_since(lesson, trial.version.snapshot)
    context = _lesson_context(enrollment, section, lesson)
    context.update({
        "trial": trial,
        "rows": [{"stage": s, "turn": turns.get(s["order"]), "revised": s["order"] in revised}
                 for s in trial.version.snapshot["stages"]],
        "revised_count": len(revised),
        "counts": {k: kinds.count(k) for k in ("correct", "partial", "wrong")},
        "overall": round((kinds.count("correct") + kinds.count("partial") / 2) * 100 / len(kinds)) if kinds else None,
        "finished": pedagogy.finished_trial(lesson),
        "problems": pedagogy.problems(lesson),
    })  # fmt: skip
    return render(request, "student/designer/results.html", context)


@require_POST
@role_required(STUDENT)
def lesson_finalize(request, number, pk):
    """«Assemble the final version»: the lesson is frozen, closed and counts for section 4."""
    _enrollment, section, lesson = _lesson(request, number, pk)
    try:
        pedagogy.finalize(lesson)
    except pedagogy.LessonError as exc:
        messages.error(
            request,
            _("First try the lesson out with the AI student.")
            if str(exc) == "no_trial"
            else _("The lesson cannot be assembled yet — see what is missing."),
        )
        return redirect("student:lesson_results", section.number, lesson.pk)
    programme.refresh(request.user)
    messages.success(request, _("The final version is assembled and saved to your portfolio."))
    return redirect("student:lesson_plan", section.number, lesson.pk)
