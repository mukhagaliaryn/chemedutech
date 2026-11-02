"""The teacher's preview of the ICPAI sections (STEP-45), like the course pages of section 1 (learning.Place.preview):
the student's own pages with everything open and nothing recorded, from any section at any moment. The pages are the
student's context functions and templates running on samples.py; the actions a student would take lead on to the next
page without doing anything, the rest answer «not saved»; the AI is off. Reads only."""

import json

from django.contrib import messages
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import resolve, reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from apps.assessments.views import take_context
from apps.core.permissions import ADMIN, TEACHER, role_required
from apps.courses import selectors as course_selectors
from apps.courses.models import Stage
from apps.pedagogy import selectors as pedagogy_selectors
from apps.pedagogy import services as pedagogy
from apps.pedagogy.models import Lesson, LessonTemplate, Trial
from apps.programme.models import DiagnosticTest, Level, Programme, Section, SectionProgress, SectionVideo
from apps.programme.providers import provider_for
from apps.programme.services import diagnostics
from apps.student import designer as student_designer
from apps.student import independent as student_independent
from apps.student import micro as student_micro
from apps.student import portfolio as student_portfolio
from apps.student import practice as student_practice
from apps.student import sections as student_sections

from . import samples
from .samples import SAMPLE

NS = "student_preview"
NOT_SAVED = _("Preview: answers are not saved.")
TRIAL_CHOICE = "preview_trial"  # the session keeps the class and the level chosen for the sample trial

preview_only = role_required(TEACHER, ADMIN)


class Visit:
    """The teacher's programme with all its sections open, on a sample enrolment."""

    def __init__(self, request):
        self.user = request.user
        courses = course_selectors.teacher_courses(request.user)
        self.programme = Programme.objects.filter(course__in=courses, is_active=True).order_by("pk").first()
        if self.programme is None:
            raise Http404
        self.enrollment = samples.enrollment(self.programme, request.user)
        self.rows = [self._row(s) for s in self.programme.sections.order_by("number", "pk")]

    def _row(self, section) -> dict:
        return {
            "section": section, "progress": None, "status": SectionProgress.Status.AVAILABLE, "percent": 0,
            "ready": provider_for(section).ready, "url": reverse(f"{NS}:section", args=[section.number]),
        }  # fmt: skip

    def section(self, kind=None, number=None) -> Section:
        found = [r["section"] for r in self.rows if (number is None or r["section"].number == number)
                 and (kind is None or r["section"].kind == kind)]  # fmt: skip
        if not found:
            raise Http404
        return found[0]


def _here(url: str) -> str:
    """A student URL made by the shared code (reverse) as the same route of the preview."""
    match = resolve(url)
    return reverse(f"{NS}:{match.url_name}", kwargs=match.kwargs)


def _opts(opts: dict) -> dict:
    """The stage editor's options: its autosave goes to the preview, which stores nothing."""
    return {**opts, "saveUrl": _here(opts["saveUrl"]), "text": {**opts["text"], "saved": NOT_SAVED}}


def _page(request, visit, template, context, *, ai=False):
    """``ai`` keeps the steps open that a student passes through the AI; otherwise its panels say it is off here."""
    context = {**context, "preview": True, "preview_rows": visit.rows, "ai_enabled": ai}
    if "editor_opts" in context:
        context["editor_opts"] = _opts(context["editor_opts"])
    return render(request, template, context)


def _back(request) -> str:
    back = request.headers.get("referer", "")
    if url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}):
        return back
    return reverse(f"{NS}:dashboard")


def _not_saved(request):
    messages.info(request, NOT_SAVED)
    return redirect(_back(request))


@preview_only
def blocked(request, *args, **kwargs):
    """Every action without a page of its own: the autosave and the video report as JSON, HTMX with nothing to swap."""
    if request.content_type == "application/json":
        try:
            percent = int(json.loads(request.body or b"{}").get("percent", 0))
        except (ValueError, TypeError, AttributeError):
            percent = 0
        return JsonResponse({"preview": True, "percent": percent, "done": False})
    if request.headers.get("HX-Request"):
        return HttpResponse(status=204)
    return _not_saved(request)


@preview_only
def leave(request, **kwargs):
    return redirect(f"student:{request.resolver_match.url_name}", **kwargs)


@preview_only
def home(request):
    visit = Visit(request)
    return redirect(visit.rows[0]["url"])


def _diagnostic_rows(section) -> list[dict]:
    return [
        {"test": test, "state": diagnostics.OPEN, "results": [], "summary": None,
         "url": reverse(f"{NS}:diagnostic", args=[section.number, test.phase])}
        for test in diagnostics.tests_of(section)
    ]  # fmt: skip


def _course_block(programme) -> dict:
    course = programme.course
    stages = Stage.objects.filter(topic__module__course=course, topic__is_published=True, is_required=True)
    return {
        "course": course, "done": 0, "total": stages.count(), "card": None,
        "course_url": reverse("student:course", args=[course.slug]),
    }  # fmt: skip


def _portfolio_context(visit, portfolio) -> dict:
    context = student_portfolio.portfolio_context(visit.enrollment, visit.user, portfolio)
    for work in context["works"]:
        work["url"] = _here(work["url"]) if work["url"] else ""
    context["state"] = {**context["state"], "ready": True}  # the way to the assembled portfolio stays open
    return context


@preview_only
def section(request, number):
    visit = Visit(request)
    item = visit.section(number=number)
    row = next(r for r in visit.rows if r["section"].pk == item.pk)
    context = {"programme": visit.programme, "section": item, "row": row, "rows": visit.rows}
    context.update(student_sections._ai_panel(request, item))
    if item.kind == Section.Kind.COURSE:
        context["course_block"] = _course_block(visit.programme)
    elif item.kind == Section.Kind.DIAGNOSTIC:
        context["diagnostics"] = _diagnostic_rows(item)
    elif item.kind == Section.Kind.VIDEO:
        video = SectionVideo.objects.filter(section=item).first()
        context["video"] = video if video and video.youtube_id else None
        context["watched"] = 0
    elif item.kind == Section.Kind.DESIGNER:
        context.update(student_designer.designer_context(request.user))
    elif item.kind == Section.Kind.RESEARCH_PRACTICE:
        context.update(student_practice.practice_context(request.user))
    elif item.kind == Section.Kind.MICROLESSON:
        sources = [samples.practice_lesson(t, request.user) for t in pedagogy_selectors.templates()]
        context.update({"micro": None, "micro_sources": sources})
    elif item.kind == Section.Kind.PORTFOLIO:
        context.update(_portfolio_context(visit, samples.portfolio(visit.enrollment)))
    elif item.kind == Section.Kind.INDEPENDENT:
        context.update(student_independent.home_context(visit.enrollment, item, request.user))
    return _page(request, visit, "student/section.html", context)


@preview_only
def results(request):
    visit = Visit(request)
    item = visit.section(Section.Kind.DIAGNOSTIC)
    context = student_sections.results_context(visit.enrollment, request.user, _diagnostic_rows(item))
    return _page(request, visit, "student/icpai_results.html", context)


# --- section 2 --------------------------------------------------------------------------------------------------


def _test(visit, number, phase):
    item = visit.section(Section.Kind.DIAGNOSTIC, number)
    return item, get_object_or_404(DiagnosticTest.objects.select_related("quiz"), section=item, phase=phase)


@preview_only
def diagnostic(request, number, phase):
    """The stage's intro, with the guide's interpretation of the three levels a student sees after the test."""
    visit = Visit(request)
    item, test = _test(visit, number, phase)
    context = student_sections.diagnostic_context(visit.enrollment, item, test, _diagnostic_rows(item))
    context["level_texts"] = [
        {"label": label, "text": test.levels[value]} for value, label in Level.choices if test.levels.get(value)
    ]
    return _page(request, visit, "student/diagnostic.html", context)


@require_POST
@preview_only
def diagnostic_start(request, number, phase):
    return redirect(f"{NS}:diagnostic_take", number, phase)


@preview_only
def diagnostic_take(request, number, phase):
    """The test page as a student gets it, with the answer key and each question's component; no attempt is made."""
    visit = Visit(request)
    item, test = _test(visit, number, phase)
    attempt = samples.attempt(test, request.user)
    submit_url = reverse(f"{NS}:diagnostic_submit", args=[number, phase, attempt.pk])
    back_url = reverse(f"{NS}:diagnostic", args=[number, phase])
    context = take_context(test.quiz, attempt, submit_url, back_url, item.title)
    return _page(request, visit, "assessments/take.html", context)


@require_POST
@preview_only
def diagnostic_submit(request, number, phase, attempt_id):
    messages.info(request, NOT_SAVED)
    return redirect(f"{NS}:diagnostic", number, phase)


# --- section 4 --------------------------------------------------------------------------------------------------


def _template(pk) -> LessonTemplate:
    return get_object_or_404(LessonTemplate, number=pk - SAMPLE, is_active=True)


def _designer_lesson(visit, number, pk):
    return visit.section(Section.Kind.DESIGNER, number), samples.template_lesson(_template(pk), visit.user)


def _chosen(request) -> dict:
    return request.session.get(TRIAL_CHOICE, {})


def _choose(request):
    """The class and the level chosen on a trial's start page, kept for the sample trial's pages."""
    level, grade = request.POST.get("level"), request.POST.get("grade", "")
    if level in Trial.Level.values:
        request.session[TRIAL_CHOICE] = {"level": level, "grade": grade}


def _sample_trial(request, lesson, mode, **kwargs):
    trial = samples.trial(lesson, mode, **_chosen(request), **kwargs)
    samples.with_trial(lesson, trial)
    return trial


@preview_only
def lesson_template(request, number, code):
    visit = Visit(request)
    item = visit.section(Section.Kind.DESIGNER, number)
    template = get_object_or_404(pedagogy_selectors.templates(), code=code)
    context = student_designer.template_context(visit.enrollment, item, template, request.user)
    return _page(request, visit, "student/designer/template.html", context)


@require_POST
@preview_only
def lesson_start(request, number, code):
    template = get_object_or_404(LessonTemplate, code=code, is_active=True)
    return redirect(f"{NS}:lesson_stage", number, SAMPLE + template.number, 1)


@preview_only
def lesson(request, number, pk):
    return redirect(f"{NS}:lesson_stage", number, pk, 1)


@preview_only
def lesson_stage(request, number, pk, order):
    visit = Visit(request)
    item, sample = _designer_lesson(visit, number, pk)
    _sample_trial(request, sample, Trial.Mode.ASSEMBLED)
    stage = sample.stages.filter(order=order).first()
    if stage is None:
        raise Http404
    if "cleared" in request.GET:
        samples.clear(stage)
    context = student_designer.editor_context(request, visit.enrollment, item, sample, stage)
    return _page(request, visit, "student/designer/editor.html", context)


@require_POST
@preview_only
def lesson_stage_clear(request, number, pk, order):
    return redirect(f"{reverse(f'{NS}:lesson_stage', args=[number, pk, order])}?cleared=1")


@require_POST
@preview_only
def lesson_stage_restore(request, number, pk, order):
    return redirect(f"{NS}:lesson_stage", number, pk, order)


@preview_only
def lesson_assemble(request, number, pk):
    if request.method == "POST":
        if request.POST.get("action") == "assemble":
            return redirect(f"{NS}:lesson_plan", number, pk)
        return _not_saved(request)
    visit = Visit(request)
    item, sample = _designer_lesson(visit, number, pk)
    context = student_designer.assemble_context(visit.enrollment, item, sample)
    return _page(request, visit, "student/designer/assemble.html", context)


@preview_only
def lesson_plan(request, number, pk):
    visit = Visit(request)
    item, sample = _designer_lesson(visit, number, pk)
    context = student_designer.plan_page_context(visit.enrollment, item, sample, sample.versions.first())
    return _page(request, visit, "student/designer/plan.html", context)


@preview_only
def lesson_trial(request, number, pk):
    """The level comes first, as for a student; after «Start the trial» the sample trial's stages."""
    visit = Visit(request)
    item, sample = _designer_lesson(visit, number, pk)
    trial = _sample_trial(request, sample, Trial.Mode.ASSEMBLED)
    context = student_designer.trial_context(
        request, visit.enrollment, item, sample, trial if "trial" in request.GET else None
    )
    return _page(request, visit, "student/designer/trial.html", context)


@require_POST
@preview_only
def lesson_trial_start(request, number, pk):
    _choose(request)
    return redirect(f"{reverse(f'{NS}:lesson_trial', args=[number, pk])}?trial=1")


@preview_only
def lesson_trial_turn(request, number, pk, trial_pk, order):
    """The window «See the AI student's answer»."""
    visit = Visit(request)
    item, sample = _designer_lesson(visit, number, pk)
    trial = _sample_trial(request, sample, Trial.Mode.ASSEMBLED)
    stage = pedagogy.stage_of(trial, order)
    turn = trial.turns.filter(stage_order=order).first()
    context = {"section": item, "lesson": sample, "trial": trial, "stage": stage, "turn": turn, "task": turn.task}
    return _page(request, visit, "student/designer/partials/turn.html", context)


@preview_only
def lesson_results(request, number, pk):
    visit = Visit(request)
    item, sample = _designer_lesson(visit, number, pk)
    trial = _sample_trial(request, sample, Trial.Mode.ASSEMBLED)
    context = student_designer.results_context(visit.enrollment, item, sample, trial)
    return _page(request, visit, "student/designer/results.html", context)


# --- section 5 --------------------------------------------------------------------------------------------------


def _practice_lesson(visit, number, pk):
    return visit.section(Section.Kind.RESEARCH_PRACTICE, number), samples.practice_lesson(_template(pk), visit.user)


def _ready_sheet(context) -> dict:
    """The sample sheet is empty; what a student would have to fill in does not stop the way on."""
    return {**context, "problems": []}


@require_POST
@preview_only
def practice_start(request, number, code):
    template = get_object_or_404(LessonTemplate, code=code, is_active=True)
    return redirect(f"{NS}:practice", number, SAMPLE + template.number)


@preview_only
def practice(request, number, pk):
    if request.method == "POST":
        return _not_saved(request)
    visit = Visit(request)
    item, sample = _practice_lesson(visit, number, pk)
    context = _ready_sheet(student_practice.sheet_context(visit.enrollment, item, sample))
    return _page(request, visit, "student/practice/sheet.html", context)


@preview_only
def practice_stage(request, number, pk, order):
    visit = Visit(request)
    item, sample = _practice_lesson(visit, number, pk)
    stage = sample.stages.filter(order=order).first()
    if stage is None:
        raise Http404
    context = student_practice.stage_page_context(request, visit.enrollment, item, sample, stage)
    return _page(request, visit, "student/practice/stage.html", context)


@preview_only
def practice_trial(request, number, pk):
    if request.method == "POST":
        _choose(request)
        return redirect(f"{NS}:practice_step", number, pk, SAMPLE + 1, 1)
    visit = Visit(request)
    item, sample = _practice_lesson(visit, number, pk)
    context = _ready_sheet(student_practice.trial_start_context(visit.enrollment, item, sample))
    return _page(request, visit, "student/practice/trial_start.html", context)


def _next_after(request, trial, order, step_name, step_args, results_url):
    """The step's forms: «give the task» shows the place of the AI student's answer, the analysis leads to the next
    stage or the results."""
    if request.POST.get("action") == "give":
        return redirect(f"{request.path}?answered=1#answer")
    following = next((s["order"] for s in trial.version.snapshot["stages"] if s["order"] > order), None)
    return redirect(f"{NS}:{step_name}", *step_args, following) if following else redirect(results_url)


def _step_page(request, visit, context):
    """Every stage stays open and none counts as done: the teacher moves between them freely."""
    context["trial_stages"] = [{**s, "done": False} for s in context["trial_stages"]]
    return _page(request, visit, "student/practice/step.html", context, ai=True)


def _step(request, trial, order) -> tuple:
    stage = next((s for s in trial.version.snapshot["stages"] if s["order"] == order), None)
    if stage is None:
        raise Http404
    return stage, samples.turn(trial, stage, analysed=False) if "answered" in request.GET else None


@preview_only
def practice_step(request, number, pk, trial_pk, order):
    visit = Visit(request)
    item, sample = _practice_lesson(visit, number, pk)
    trial = _sample_trial(request, sample, Trial.Mode.STEPWISE)
    stage, turn = _step(request, trial, order)
    if request.method == "POST":
        results_url = reverse(f"{NS}:practice_results", args=[number, pk])
        return _next_after(request, trial, order, "practice_step", (number, pk, trial_pk), results_url)
    return _step_page(
        request, visit, student_practice.step_context(request, visit.enrollment, item, sample, trial, stage, turn)
    )


@preview_only
def practice_results(request, number, pk):
    visit = Visit(request)
    item, sample = _practice_lesson(visit, number, pk)
    trial = _sample_trial(request, sample, Trial.Mode.STEPWISE)
    context = student_practice.results_context(visit.enrollment, item, sample, trial)
    return _page(request, visit, "student/practice/results.html", context)


# --- section 6 --------------------------------------------------------------------------------------------------


def _micro_lesson(request, visit, number):
    """The microlesson of the part chosen on the section page (?practice, ?stage), else the first one."""
    item = visit.section(Section.Kind.MICROLESSON, number)
    templates = list(pedagogy_selectors.templates())
    if not templates:
        raise Http404
    chosen = request.GET.get("practice", "")
    template = next((t for t in templates if chosen == str(SAMPLE + t.number)), templates[0])
    source = samples.practice_lesson(template, visit.user)
    order = request.GET.get("stage", "")
    return item, samples.micro_lesson(source, int(order) if source.stages.filter(order=_int(order)) else 1, visit.user)


def _int(value) -> int | None:
    return int(value) if value.isdigit() else None


def _micro_state(context) -> dict:
    """The AI checker's ✓ is what opens the trial; here the way is open without it."""
    return {**context, "state": {**context["state"], "passed": True}}


@require_POST
@preview_only
def micro_start(request, number):
    part = {"practice": request.POST.get("practice", ""), "stage": request.POST.get("stage", "")}
    query = "&".join(f"{k}={v}" for k, v in part.items() if v.isdigit())
    return redirect(f"{reverse(f'{NS}:micro', args=[number])}?{query}")


@preview_only
def micro(request, number):
    if request.method == "POST":
        return _not_saved(request)
    visit = Visit(request)
    item, sample = _micro_lesson(request, visit, number)
    _sample_trial(request, sample, Trial.Mode.DIALOG)
    context = _micro_state(student_micro.editor_context(request, visit.enrollment, item, sample))
    for row in context["rows"]:
        row["opts"] = _opts(row["opts"])
    return _page(request, visit, "student/micro/editor.html", context)


@preview_only
def micro_trial(request, number):
    if request.method == "POST":
        _choose(request)
        return redirect(f"{NS}:micro_dialog", number, SAMPLE + 1)
    visit = Visit(request)
    item, sample = _micro_lesson(request, visit, number)
    context = _micro_state(student_micro.trial_start_context(visit.enrollment, item, sample))
    return _page(request, visit, "student/micro/trial_start.html", context)


@preview_only
def micro_dialog(request, number, trial_pk):
    visit = Visit(request)
    item, sample = _micro_lesson(request, visit, number)
    trial = _sample_trial(request, sample, Trial.Mode.DIALOG, finished=False)
    context = student_micro.dialog_page_context(request, visit.enrollment, item, sample, trial)
    return _page(request, visit, "student/micro/dialog.html", context, ai=True)


@require_POST
@preview_only
def micro_send(request, number, trial_pk):
    """HTMX: the dialogue answers that nothing goes to the AI student here."""
    visit = Visit(request)
    item, sample = _micro_lesson(request, visit, number)
    trial = _sample_trial(request, sample, Trial.Mode.DIALOG, finished=False)
    context = student_micro._dialog_context(request, item, sample, trial, "preview")
    return _page(request, visit, "student/micro/partials/messages.html", context)


@require_POST
@preview_only
def micro_finish(request, number, trial_pk):
    return redirect(f"{NS}:micro_protocol", number, trial_pk)


@preview_only
def micro_protocol(request, number, trial_pk):
    visit = Visit(request)
    item, sample = _micro_lesson(request, visit, number)
    trial = _sample_trial(request, sample, Trial.Mode.DIALOG)
    context = student_micro.protocol_context(visit.enrollment, item, sample, trial)
    return _page(request, visit, "student/micro/protocol.html", context)


# --- section 7 --------------------------------------------------------------------------------------------------


@preview_only
def portfolio(request):
    visit = Visit(request)
    return redirect(f"{NS}:section", visit.section(Section.Kind.PORTFOLIO).number)


@preview_only
def portfolio_reflection(request):
    if request.method == "POST":
        return _not_saved(request)
    visit = Visit(request)
    item = visit.section(Section.Kind.PORTFOLIO)
    context = student_portfolio.reflection_context(visit.enrollment, item, samples.portfolio(visit.enrollment))
    return _page(request, visit, "student/portfolio/reflection.html", context)


@preview_only
def portfolio_plan(request):
    if request.method == "POST":
        return _not_saved(request)
    visit = Visit(request)
    item = visit.section(Section.Kind.PORTFOLIO)
    context = student_portfolio.plan_context(visit.enrollment, item, samples.portfolio(visit.enrollment))
    return _page(request, visit, "student/portfolio/plan.html", context)


@require_POST
@preview_only
def portfolio_assemble(request):
    return redirect(f"{NS}:portfolio_view")


@preview_only
def portfolio_view(request):
    visit = Visit(request)
    item = visit.section(Section.Kind.PORTFOLIO)
    sample = samples.portfolio(visit.enrollment)
    version = samples.portfolio_version(sample)
    context = student_portfolio.view_context(visit.enrollment, item, sample, version)
    return _page(request, visit, "student/portfolio/view.html", context)


# --- section 8 --------------------------------------------------------------------------------------------------


@preview_only
def independent_home(request):
    visit = Visit(request)
    return redirect(f"{NS}:section", visit.section(Section.Kind.INDEPENDENT).number)


@require_POST
@preview_only
def independent_start(request):
    return redirect(f"{NS}:independent", SAMPLE + 1)


@preview_only
def independent(request, pk, order=None):
    """The sheet with no stages, or — once a stage is added — one blank stage; ?submitted — after «Submit for the
    trial»."""
    if request.method == "POST":
        return _not_saved(request)
    visit = Visit(request)
    item = visit.section(Section.Kind.INDEPENDENT)
    status = Lesson.Status.SUBMITTED if "submitted" in request.GET else Lesson.Status.DRAFT
    sample = samples.independent_lesson(request.user, with_stage=order is not None, status=status)
    stage = sample.stages.filter(order=order).first() if order is not None else None
    if order is not None and stage is None:
        raise Http404
    context = student_independent.editor_context(request, visit.enrollment, item, sample, stage)
    return _page(request, visit, "student/independent/editor.html", _ready_sheet(context))


@require_POST
@preview_only
def independent_stage_add(request, pk):
    return redirect(f"{NS}:independent_stage", pk, 1)


@require_POST
@preview_only
def independent_submit(request, pk):
    return redirect(f"{reverse(f'{NS}:independent', args=[pk])}?submitted=1#trial")


@require_POST
@preview_only
def independent_trial_start(request, pk):
    _choose(request)
    return redirect(f"{NS}:independent_step", pk, SAMPLE + 1, 1)


def _independent_lesson(visit):
    return visit.section(Section.Kind.INDEPENDENT), samples.independent_lesson(visit.user, with_stage=True)


@preview_only
def independent_step(request, pk, trial_pk, order):
    visit = Visit(request)
    item, sample = _independent_lesson(visit)
    trial = _sample_trial(request, sample, Trial.Mode.STEPWISE)
    stage, turn = _step(request, trial, order)
    if request.method == "POST":
        results_url = reverse(f"{NS}:independent_trial", args=[pk, trial_pk])
        return _next_after(request, trial, order, "independent_step", (pk, trial_pk), results_url)
    context = student_independent.step_context(request, visit.enrollment, item, sample, trial, stage, turn)
    context["results_url"] = _here(context["results_url"])
    return _step_page(request, visit, context)


@preview_only
def independent_trial(request, pk, trial_pk):
    visit = Visit(request)
    item, sample = _independent_lesson(visit)
    trial = _sample_trial(request, sample, Trial.Mode.STEPWISE)
    context = student_independent.trial_context(visit.enrollment, item, sample, trial)
    return _page(request, visit, "student/independent/trial.html", context)
