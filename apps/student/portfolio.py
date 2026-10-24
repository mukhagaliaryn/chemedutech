"""Section 7 — feedback and the professional portfolio (guide @S7; picture image24; STEP-37): «My professional works»
(gathered automatically), «ICPAI — professional readiness results», «The teacher's professional feedback», «My
professional reflection», «My professional development trajectory», «Assemble my professional portfolio» (PDF, view,
submit to the teacher)."""

from django.contrib import messages
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext_lazy as _
from django.views.decorators.http import require_POST

from apps.ai import services as ai
from apps.core.permissions import STUDENT, role_required
from apps.programme import portfolio_selectors
from apps.programme import selectors as programme_selectors
from apps.programme import services as programme
from apps.programme.models import DIRECTIONS, FEEDBACK_DIRECTIONS, PARTS, QUESTIONS, Section
from apps.programme.services import portfolio as portfolio_services

from . import micro, practice


def _section(request):
    enrollment = programme.refresh(request.user)
    if enrollment is None:
        raise Http404
    section = get_object_or_404(Section, programme=enrollment.programme, kind=Section.Kind.PORTFOLIO)
    if not programme.can_access(enrollment, section):
        raise Http404
    return enrollment, section


def _check_rows(portfolio) -> dict:
    """The AI check's marks, only when it is for the reflection and the plan as they are now."""
    data = portfolio.ai_check or {}
    current = bool(data) and data.get("fingerprint") == portfolio_services.fingerprint(portfolio.enrollment)
    return {"items": data.get("items", {}) if current else {}, "current": current, "at": data.get("at")}


def feedback_rows(feedback) -> list[dict]:
    """The four directions of the teacher's feedback with what the teacher wrote."""
    if feedback is None:
        return []
    return [
        {"key": k, "label": label, "help": help_, "text": getattr(feedback, k)}
        for k, label, help_ in FEEDBACK_DIRECTIONS
    ]


def portfolio_context(enrollment, user) -> dict:
    """The section page's part (image24)."""
    portfolio = portfolio_services.portfolio_of(enrollment)
    answers = portfolio_selectors.reflection_answers(enrollment)
    feedback = portfolio.feedbacks.select_related("teacher").first()
    return {
        "portfolio": portfolio,
        "feedback_rows": feedback_rows(feedback),
        "works": portfolio_selectors.works(enrollment),
        "dynamics": programme_selectors.component_dynamics(enrollment),
        "phases": ("I", "II", "III"),
        "feedback": feedback,
        "reflection": [{"key": k, "question": q, "answer": answers.get(k, "")} for k, q in QUESTIONS],
        "plan": portfolio_selectors.plan_rows(enrollment),
        "state": portfolio_selectors.completeness(enrollment),
        "check": _check_rows(portfolio),
        "version": portfolio_services.latest_version(portfolio),
        "current": portfolio_services.is_current(portfolio),
        "practice_grades": practice.practice_grades(user),
        "micro_grades": micro.micro_grades(user),
        "parts": PARTS,
        "ai_enabled": ai.enabled(),
    }


@role_required(STUDENT)
def portfolio(request):
    """The portfolio lives on its section page."""
    _enrollment, section = _section(request)
    return redirect("student:section", section.number)


@role_required(STUDENT)
def reflection(request):
    """«My professional reflection» (@S7 IV): seven questions, «Save the reflection»; the AI writes none."""
    enrollment, section = _section(request)
    portfolio = portfolio_services.portfolio_of(enrollment)
    if request.method == "POST":
        try:
            portfolio_services.save_reflection(enrollment, {k: request.POST.get(f"q{k}", "") for k, _q in QUESTIONS})
        except portfolio_services.PortfolioError:
            messages.error(request, _("The portfolio is with the teacher now and cannot be changed."))
        else:
            messages.success(request, _("The reflection is saved to your portfolio."))
            return redirect("student:section", section.number)
        return redirect("student:portfolio_reflection")
    answers = portfolio_selectors.reflection_answers(enrollment)
    return render(request, "student/portfolio/reflection.html", {
        "programme": enrollment.programme, "section": section, "portfolio": portfolio,
        "rows": [{"key": k, "question": q, "answer": answers.get(k, ""),
                  "mark": _check_rows(portfolio)["items"].get(f"q{k}")} for k, q in QUESTIONS],
        "feedback": portfolio.feedbacks.first(),
    })  # fmt: skip


@role_required(STUDENT)
def plan(request):
    """«My professional development trajectory» (@S7 V): «Set the professional development goal» (actions and
    expected results) and «Update the development result» (done, result)."""
    enrollment, section = _section(request)
    portfolio = portfolio_services.portfolio_of(enrollment)
    if request.method == "POST":
        post = request.POST
        try:
            if post.get("action") == "results":
                portfolio_services.update_results(enrollment, {
                    k: {"done": post.get(f"{k}_done") == "on", "result": post.get(f"{k}_result", "")}
                    for k, _label in DIRECTIONS
                })  # fmt: skip
                messages.success(request, _("The development results are updated."))
            else:
                portfolio_services.save_plan(enrollment, {
                    k: {"action": post.get(f"{k}_action", ""), "expected": post.get(f"{k}_expected", "")}
                    for k, _label in DIRECTIONS
                })  # fmt: skip
                messages.success(request, _("The professional development goals are set."))
        except portfolio_services.PortfolioError:
            messages.error(request, _("The portfolio is with the teacher now and cannot be changed."))
        return redirect("student:portfolio_plan")
    marks = _check_rows(portfolio)["items"]
    return render(request, "student/portfolio/plan.html", {
        "programme": enrollment.programme, "section": section, "portfolio": portfolio,
        "rows": [{**r, "mark": marks.get(r["direction"])} for r in portfolio_selectors.plan_rows(enrollment)],
        "works": portfolio_selectors.works(enrollment),
    })  # fmt: skip


@require_POST
@role_required(STUDENT)
def details(request):
    enrollment, section = _section(request)
    try:
        portfolio_services.save_details(
            portfolio_services.portfolio_of(enrollment),
            programme_name=request.POST.get("programme_name", ""), study_year=request.POST.get("study_year", ""),
        )  # fmt: skip
    except portfolio_services.PortfolioError:
        messages.error(request, _("The portfolio is with the teacher now and cannot be changed."))
    return redirect(f"{reverse('student:section', args=[section.number])}#assemble")


@require_POST
@role_required(STUDENT)
def check(request):
    """The AI assistant checks the completeness of the reflection and the plan (✓ / ✕ only)."""
    enrollment, section = _section(request)
    try:
        portfolio_services.check(portfolio_services.portfolio_of(enrollment))
    except ai.LimitReached:
        messages.error(request, _("Today's AI requests are used up. They renew tomorrow."))
    except ai.AIUnavailable:
        messages.error(request, _("The AI assistant did not answer this time. Try again in a minute."))
    except portfolio_services.PortfolioError:
        messages.error(request, _("The portfolio is with the teacher now and cannot be changed."))
    return redirect(f"{reverse('student:section', args=[section.number])}#assemble")


@require_POST
@role_required(STUDENT)
def assemble(request):
    enrollment, section = _section(request)
    try:
        portfolio_services.assemble(portfolio_services.portfolio_of(enrollment))
    except portfolio_services.PortfolioError as exc:
        messages.error(
            request,
            _("The portfolio is with the teacher now and cannot be changed.")
            if str(exc) == "locked"
            else _("Fill in the reflection and the development map first; the final diagnostics must be taken."),
        )
        return redirect(f"{reverse('student:section', args=[section.number])}#assemble")
    messages.success(request, _("The portfolio is assembled."))
    return redirect("student:portfolio_view")


@require_POST
@role_required(STUDENT)
def submit(request):
    """«Submit to the teacher» the latest assembled version."""
    enrollment, section = _section(request)
    try:
        portfolio_services.submit(portfolio_services.portfolio_of(enrollment))
    except portfolio_services.PortfolioError as exc:
        messages.error(
            request,
            _("Assemble the portfolio again — it has changed since.")
            if str(exc) == "assemble_first"
            else _("The portfolio is with the teacher now and cannot be changed."),
        )
    else:
        programme.refresh(request.user)
        messages.success(request, _("The portfolio is submitted to the teacher."))
    return redirect(f"{reverse('student:section', args=[section.number])}#assemble")


def _version(portfolio, request):
    versions = portfolio.versions.order_by("-number")
    if request.GET.get("v", "").isdigit():
        return get_object_or_404(versions, number=int(request.GET["v"]))
    return versions.first()


def sheet_context(version) -> dict:
    return {"version": version, "data": version.snapshot, "parts": PARTS, "feedback_directions": FEEDBACK_DIRECTIONS}


@role_required(STUDENT)
def view(request):
    """«View the portfolio»: the assembled version in its ten parts."""
    enrollment, section = _section(request)
    portfolio = portfolio_services.portfolio_of(enrollment)
    version = _version(portfolio, request)
    if version is None:
        return redirect("student:section", section.number)
    return render(request, "student/portfolio/view.html", {
        "programme": enrollment.programme, "section": section, "portfolio": portfolio,
        "versions": list(portfolio.versions.order_by("-number")), "current": portfolio_services.is_current(portfolio),
        **sheet_context(version),
    })  # fmt: skip


@role_required(STUDENT)
def pdf(request):
    """«Save as PDF» (WeasyPrint)."""
    from weasyprint import HTML

    enrollment, _section_obj = _section(request)
    portfolio = portfolio_services.portfolio_of(enrollment)
    version = _version(portfolio, request)
    if version is None:
        raise Http404
    html = render(request, "student/portfolio/pdf.html", sheet_context(version))
    data = HTML(string=html.content.decode(), base_url=request.build_absolute_uri("/")).write_pdf()
    response = HttpResponse(data, content_type="application/pdf")
    response["Content-Disposition"] = f'attachment; filename="icpai-portfolio-v{version.number}.pdf"'
    return response
