from django.db.models import Prefetch, QuerySet
from django.urls import reverse

from ..models import Course, Module, Stage, Topic


def stages_of(topic: Topic) -> QuerySet[Stage]:
    """All stages of a topic in order, with their content — never assume one stage per kind."""
    return topic.stages.select_related(
        "theory_content", "video_content", "lab_content", "test_content__quiz", "checkpoint_quiz"
    )


def course_tree(courses: QuerySet[Course]) -> QuerySet[Course]:
    """Courses with modules → topics → stages prefetched (course map, dashboards)."""
    return courses.prefetch_related(
        Prefetch("modules", queryset=Module.objects.order_by("order", "pk")),
        Prefetch("modules__topics", queryset=Topic.objects.order_by("number")),
        Prefetch("modules__topics__stages", queryset=Stage.objects.order_by("order", "pk")),
    )


def stage_url(stage) -> str:
    """The student's page of a stage (by url name — the student app sits above this layer)."""
    return reverse("student:stage", args=[stage.topic.module.course.slug, stage.topic.number, stage.pk])
