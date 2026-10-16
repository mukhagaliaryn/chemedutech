from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.core.permissions import STUDENT, has_role, role_required
from apps.labs.selectors import best_attempts_by_experiment

from . import selectors, services
from .models import Course, Stage


@login_required
def dashboard(request):
    user = request.user
    services.sync_student_enrollments(user)
    courses = selectors.course_tree(selectors.courses_for(user))
    show_open = has_role(user, STUDENT) and not courses.exists()
    return render(
        request,
        "courses/dashboard.html",
        {"courses": courses, "open_courses": selectors.open_courses() if show_open else []},
    )


@require_POST
@role_required(STUDENT)
def enroll(request, course_slug):
    course = get_object_or_404(Course, slug=course_slug)
    try:
        services.self_enroll(request.user, course)
    except services.EnrollmentError as exc:
        messages.error(request, str(exc))
    return redirect("courses:dashboard")


@login_required
def topic_detail(request, course_slug, number):
    topic = selectors.topic_by_number(request.user, course_slug, number)
    if topic is None:
        raise Http404
    stages = list(selectors.stages_of(topic))
    labs = []
    for stage in stages:
        if stage.kind == Stage.Kind.LAB and stage.content:
            done = best_attempts_by_experiment(request.user, stage.content.lab_key)
            specs = stage.content.experiment_specs()
            labs.append({"stage": stage, "experiments": [{"spec": e, "attempt": done.get(e.key)} for e in specs]})
    return render(
        request,
        "courses/topic.html",
        {
            "topic": topic,
            "course": topic.module.course,
            # progress statuses arrive with STEP-06; until then every stage is shown as available
            "stepper": [
                {"title": s.title, "kind": s.kind, "status": "available", "meta": s.get_kind_display()} for s in stages
            ],
            "theory_stages": [s for s in stages if s.kind == Stage.Kind.THEORY and s.content],
            "labs": labs,
            "quizzes": [
                {"stage": s, "quiz": q}
                for s in stages
                if (q := s.checkpoint_quiz or (s.content.quiz if s.kind == Stage.Kind.TEST and s.content else None))
            ],
        },
    )
