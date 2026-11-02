"""Every route of the student cabinet again under the same names (``app_name = "student"``), mounted with the instance
namespace ``student_preview``: on a page rendered here {% url 'student:…' %} resolves to this instance by itself, so
the student's templates stay as they are. A route without a preview page answers «not saved»; those of ``OUTSIDE``
lead out to the real pages a teacher may open (the course preview of section 1, the profile)."""

from django.urls import path

from apps.student.urls import urlpatterns as student_urls

from . import views

app_name = "student"

PAGES = {
    "dashboard": views.home,
    "section": views.section,
    "icpai": views.results,
    "diagnostic": views.diagnostic,
    "diagnostic_start": views.diagnostic_start,
    "diagnostic_submit": views.diagnostic_submit,
    "lesson_template": views.lesson_template,
    "lesson_start": views.lesson_start,
    "lesson": views.lesson,
    "lesson_stage": views.lesson_stage,
    "lesson_stage_clear": views.lesson_stage_clear,
    "lesson_stage_restore": views.lesson_stage_restore,
    "lesson_assemble": views.lesson_assemble,
    "lesson_plan": views.lesson_plan,
    "lesson_trial": views.lesson_trial,
    "lesson_trial_start": views.lesson_trial_start,
    "lesson_trial_turn": views.lesson_trial_turn,
    "lesson_results": views.lesson_results,
    "practice_start": views.practice_start,
    "practice": views.practice,
    "practice_stage": views.practice_stage,
    "practice_trial": views.practice_trial,
    "practice_step": views.practice_step,
    "practice_results": views.practice_results,
    "micro_start": views.micro_start,
    "micro": views.micro,
    "micro_trial": views.micro_trial,
    "micro_dialog": views.micro_dialog,
    "micro_send": views.micro_send,
    "micro_finish": views.micro_finish,
    "micro_protocol": views.micro_protocol,
    "portfolio": views.portfolio,
    "portfolio_reflection": views.portfolio_reflection,
    "portfolio_plan": views.portfolio_plan,
    "portfolio_assemble": views.portfolio_assemble,
    "portfolio_view": views.portfolio_view,
    "independent_home": views.independent_home,
    "independent_start": views.independent_start,
    "independent": views.independent,
    "independent_stage": views.independent,
    "independent_stage_add": views.independent_stage_add,
    "independent_submit": views.independent_submit,
    "independent_trial_start": views.independent_trial_start,
    "independent_step": views.independent_step,
    "independent_trial": views.independent_trial,
}
OUTSIDE = ("profile", "course", "topic", "stage")


def _route(pattern):
    view = PAGES.get(pattern.name) or (views.leave if pattern.name in OUTSIDE else views.blocked)
    return path(str(pattern.pattern).removeprefix("me/"), view, name=pattern.name)


urlpatterns = [
    path("sections/<int:number>/diagnostic/<str:phase>/take/", views.diagnostic_take, name="diagnostic_take"),
    *[_route(p) for p in student_urls],
]
