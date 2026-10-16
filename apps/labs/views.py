import json

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

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
        "network_error": _("Connection problem. Your actions are kept and will be sent again."),
    }


@login_required
def run_experiment(request, lab_key, experiment_key):
    lab, experiment = _get_spec(lab_key, experiment_key)
    topic = topic_for_lab(lab.key)
    attempt = services.start_attempt(request.user, lab.key, experiment)

    experiments = list(lab.experiments)
    idx = experiments.index(experiment)
    next_exp = experiments[idx + 1] if idx + 1 < len(experiments) else None

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
            "topic": topic.get_absolute_url() if topic else reverse("student:courses"),
            "next": reverse("labs:run", args=[lab.key, next_exp.key]) if next_exp else "",
            "restart": request.path,
        },
    }
    return render(
        request,
        "labs/run.html",
        {
            "lab": lab,
            "experiment": experiment,
            "experiments": experiments,
            "topic": topic,
            "config": config,
        },
    )


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
    services.save_journal(attempt, experiment, data)
    return JsonResponse({"ok": True})


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
    return JsonResponse({"correct": attempt.analysis_correct, "total": attempt.analysis_total})
