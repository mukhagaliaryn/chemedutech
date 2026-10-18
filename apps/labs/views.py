import json

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.core.permissions import ADMIN, TEACHER, has_role
from apps.courses.models import Stage
from apps.courses.selectors import topic_for_lab

from . import services
from .engine import get_lab
from .models import LabAttempt


def _get_spec(lab_key, experiment_key):
    lab = get_lab(lab_key)
    experiment = lab and lab.experiment(experiment_key)
    if not experiment:
        raise Http404
    return lab, experiment


def _ui_strings():
    """Interface strings used by the JS runner (translated server-side)."""
    return {
        "tools": _("Equipment and reagents"),
        "glass": _("Glassware"),
        "devices": _("Devices"),
        "reagents": _("Reagents"),
        "bench": _("Virtual bench"),
        "bench_empty": _("Drag equipment here or use the commands below."),
        "drop_here": _("Release to place on the bench"),
        "add": _("Add to bench"),
        "commands": _("Commands"),
        "messages": _("Warnings and observations"),
        "no_messages": _("Messages about your actions will appear here."),
        "journal": _("Lab journal"),
        "save_journal": _("Save journal"),
        "journal_saved": _("Journal saved."),
        "journal_required": _("Fill in all fields of the journal."),
        "journal_locked": _("The journal opens at the «%(step)s» step."),
        "hint": _("Hint"),
        "done": _("Done"),
        "running": _("In progress…"),
        "next": _("Next"),
        "order_error": _("Not yet. Next step: «%(step)s»."),
        "already_done": _("This step is already done."),
        "not_needed": _("This item is not needed in this experiment."),
        "already_on_bench": _("This item is already on the bench."),
        "choose": _("Choose"),
        "equation": _("Reaction equation"),
        "explanation": _("Scientific explanation"),
        "results": _("Measurements"),
        "time": _("Time"),
        "volume": _("Volume"),
        "min": _("min"),
        "s": _("s"),
        "ml": _("mL"),
        "rate": _("Rate"),
        "ml_min": _("mL/min"),
        "graph": _("Volume of gas against time"),
        "theoretical_max": _("Theoretical maximum"),
        "analysis": _("Analysis task"),
        "submit_analysis": _("Submit answers"),
        "answer_placeholder": _("Your answer"),
        "result_title": _("Experiment complete"),
        "result_errors": _("Order errors"),
        "result_warnings": _("Safety warnings"),
        "result_wrong": _("Wrong equipment or choices"),
        "result_time": _("Time spent"),
        "result_score": _("Analysis: correct answers"),
        "back_to_topic": _("Back to the topic"),
        "next_experiment": _("Next experiment"),
        "restart": _("Start again"),
        "restart_confirm": _(
            "Start the experiment again? The current progress will be saved as an unfinished attempt."
        ),
        "safety": _("Safety"),
        "observation": _("Observation"),
        "error": _("Mistake"),
        "info": _("Note"),
        "speed": _("Speed"),
        "no_catalyst": _("without catalyst"),
        "with_catalyst": _("with MnO₂"),
        "tube_a": _("A: without catalyst"),
        "tube_b": _("B: with MnO₂"),
        "cathode": _("Cathode (−)"),
        "anode": _("Anode (+)"),
        "ratio": _("Ratio"),
        "purity_test": _("Purity test: a quiet pop — the hydrogen is pure."),
        "splint_test": _("The glowing splint flares up: the gas is oxygen."),
        "mno2_only_b": _("Tube A is the control: it must stay without a catalyst."),
        # full-screen workspace (STEP-27): briefing → bench → result
        "experiment_n": _("Experiment %(n)s"),
        "goal": _("Goal"),
        "how_title": _("How it works"),
        "how_1": _("Drag the equipment onto the bench or press «+»."),
        "how_2": _("Carry out the commands in order: a command out of order is counted as a mistake."),
        "how_3": _("Fill in the lab journal, finish the experiment and answer the analysis questions."),
        "safety_generic": _(
            "The experiment runs on the screen only: it is not an instruction for working with real reagents."
        ),
        "steps_total": _("Steps: %(n)s"),
        "start": _("Start the experiment"),
        "steps": _("Steps"),
        "journal_tab": _("Journal"),
        "log": _("Messages"),
        "now": _("Now"),
        "run": _("Run"),
        "open_journal": _("Open the journal"),
        "finish_experiment": _("Finish the experiment"),
        "drag_or_add": _("Drag to the bench or press «+»:"),
        "choose_one": _("Choose:"),
        "all_done": _("All steps are done."),
        "tools_toggle": _("Equipment"),
        "collapse": _("Hide the panel"),
        "expand": _("Show the panel"),
        "close": _("Close"),
        "briefing": _("Briefing"),
        "show_explanation": _("Explanation"),
        "eq_ok": _("The equation is right."),
        "eq_species": _("Check the substances or ions."),
        "eq_coefficients": _("Check the coefficients."),
        "eq_unreadable": _("The equation cannot be read: check the formulas and the arrow."),
        "network_error": _("Connection problem. Your actions are kept and will be sent again."),
    }


def lab_page(request, *, lab, experiment, attempt, urls: dict, nav: list[dict], topic=None, back_url=""):
    """Render the simulator. ``urls`` override the API/navigation endpoints the runner (engine.js) calls;
    ``nav`` — [{number, title, url (None = locked), current, done}] for the experiment switcher."""
    config = {
        "attempt": attempt.pk,
        "lab": lab.key,
        "experiment": experiment.as_json(),
        "ui": _ui_strings(),
        "urls": {
            "events": reverse("labs:api_events", args=[attempt.pk]),
            "journal": reverse("labs:api_journal", args=[attempt.pk]),
            "finish": reverse("labs:api_finish", args=[attempt.pk]),
            "analysis": reverse("labs:api_analysis", args=[attempt.pk]),
            "restart": request.path,
            "next": "",
            **urls,
        },
    }
    return render(
        request,
        "labs/run.html",
        {
            "lab": lab,
            "experiment": experiment,
            "nav": nav,
            "topic": topic,
            "back_url": back_url or config["urls"].get("topic", ""),
            "config": config,
        },
    )


@login_required
def run_experiment(request, lab_key, experiment_key):
    """Outside a course stage: a teacher's or admin's preview. Students are sent to their lab stage."""
    lab, experiment = _get_spec(lab_key, experiment_key)
    if not has_role(request.user, TEACHER, ADMIN):
        stage = (
            Stage.objects.filter(
                kind=Stage.Kind.LAB,
                lab_content__lab_key=lab.key,
                topic__module__course__enrollments__student=request.user,
                topic__is_published=True,
            )
            .select_related("topic__module__course")
            .first()
        )
        if stage is None:
            raise Http404
        course = stage.topic.module.course
        return redirect("student:lab_run", course.slug, stage.topic.number, stage.pk, experiment.key)
    topic = topic_for_lab(lab.key)
    attempt = services.start_attempt(request.user, lab.key, experiment)
    experiments = list(lab.experiments)
    idx = experiments.index(experiment)
    next_exp = experiments[idx + 1] if idx + 1 < len(experiments) else None
    nav = [
        {
            "number": e.number,
            "title": e.title,
            "url": reverse("labs:run", args=[lab.key, e.key]),
            "current": e == experiment,
        }
        for e in experiments
    ]
    urls = {
        "topic": topic.get_absolute_url() if topic else reverse("student:courses"),
        "next": reverse("labs:run", args=[lab.key, next_exp.key]) if next_exp else "",
    }
    return lab_page(request, lab=lab, experiment=experiment, attempt=attempt, urls=urls, nav=nav, topic=topic)


def _attempt_for(request, pk):
    return get_object_or_404(LabAttempt, pk=pk, user=request.user)


def _json_body(request):
    try:
        return json.loads(request.body or b"{}")
    except json.JSONDecodeError:
        return None


@login_required
@require_POST
def api_events(request, pk):
    attempt = _attempt_for(request, pk)
    data = _json_body(request)
    if not isinstance(data, dict) or not isinstance(data.get("events"), list):
        return HttpResponseBadRequest("events list expected")
    saved = services.record_events(attempt, data["events"])
    return JsonResponse({"saved": saved})


@login_required
@require_POST
def api_journal(request, pk):
    attempt = _attempt_for(request, pk)
    _, experiment = _get_spec(attempt.lab_key, attempt.experiment_key)
    data = _json_body(request)
    if not isinstance(data, dict):
        return HttpResponseBadRequest("object expected")
    checks = services.save_journal(attempt, experiment, data)
    return JsonResponse({"ok": True, "checks": checks})


@login_required
@require_POST
def api_finish(request, pk):
    attempt = _attempt_for(request, pk)
    data = _json_body(request) or {}
    if isinstance(data.get("events"), list):
        services.record_events(attempt, data["events"])
    attempt = services.finish_attempt(attempt)
    return JsonResponse(
        {
            "duration_s": attempt.duration_s,
            "order_errors": attempt.order_errors,
            "safety_warnings": attempt.safety_warnings,
            "wrong": attempt.wrong_items + attempt.wrong_choices,
        }
    )


@login_required
@require_POST
def api_analysis(request, pk):
    attempt = _attempt_for(request, pk)
    _, experiment = _get_spec(attempt.lab_key, attempt.experiment_key)
    data = _json_body(request)
    if not isinstance(data, dict):
        return HttpResponseBadRequest("object expected")
    attempt = services.submit_analysis(attempt, experiment, data)
    return JsonResponse(analysis_payload(attempt))


def analysis_payload(attempt):
    return {
        "correct": attempt.analysis_correct,
        "total": attempt.analysis_total,
        "score": float(attempt.score_percent) if attempt.score_percent is not None else None,
    }
