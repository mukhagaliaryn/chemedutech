from django.contrib.auth.decorators import login_required
from django.db.models import Prefetch
from django.http import Http404
from django.shortcuts import get_object_or_404, render

from apps.labs.engine import get_lab
from apps.labs.selectors import best_attempts_by_experiment

from .models import Course, Topic


@login_required
def dashboard(request):
    courses = Course.objects.filter(is_published=True).prefetch_related(
        "modules", Prefetch("modules__topics", queryset=Topic.objects.order_by("number"))
    )
    return render(request, "courses/dashboard.html", {"courses": courses})


@login_required
def topic_detail(request, course_slug, number):
    topic = get_object_or_404(
        Topic.objects.select_related("module__course"), module__course__slug=course_slug, number=number
    )
    if not topic.is_published and not request.user.is_teacher:
        raise Http404
    lab = get_lab(topic.lab_key) if topic.lab_key else None
    done = best_attempts_by_experiment(request.user, lab.key) if lab else {}
    experiments = [{"spec": e, "attempt": done.get(e.key)} for e in lab.experiments] if lab else []
    return render(
        request,
        "courses/topic.html",
        {"topic": topic, "course": topic.module.course, "lab": lab, "experiments": experiments},
    )
