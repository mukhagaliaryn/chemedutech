"""Context builders for the student pages (product layer: reads only, writes go through services)."""

from dataclasses import dataclass, field

from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse
from django.utils.translation import gettext as _

from apps.core.permissions import ADMIN, STUDENT, TEACHER, has_role
from apps.courses.models import Course, Enrollment, Module, Stage, Topic
from apps.courses.selectors import courses_for
from apps.courses.services import sync_student_enrollments
from apps.progress import selectors as progress_selectors
from apps.progress.models import StageProgress

S = StageProgress.Status


@dataclass
class Place:
    """Where the user is: course (+ topic, stage). ``preview`` — a teacher/admin looks without progress."""

    course: Course
    enrollment: Enrollment | None
    preview: bool
    topic: Topic | None = None
    stage: Stage | None = None
    progress: dict = field(default_factory=dict)  # stage_id → StageProgress


def resolve(request, course_slug, topic_number=None, stage_pk=None) -> Place:
    user = request.user
    if has_role(user, STUDENT):
        sync_student_enrollments(user)
        enrollment = (
            Enrollment.objects.select_related("course")
            .filter(student=user, course__slug=course_slug)
            .exclude(status=Enrollment.Status.DROPPED)
            .exclude(course__status=Course.Status.DRAFT)
            .first()
        )
        if enrollment is None:
            raise Http404
        place = Place(enrollment.course, enrollment, preview=False)
    elif has_role(user, TEACHER, ADMIN):
        place = Place(get_object_or_404(courses_for(user), slug=course_slug), None, preview=True)
    else:
        raise Http404
    if topic_number is not None:
        topics = Topic.objects.filter(module__course=place.course, number=topic_number).select_related("module")
        if not place.preview:
            topics = topics.filter(is_published=True)
        place.topic = get_object_or_404(topics)
    if stage_pk is not None:
        place.stage = get_object_or_404(
            Stage.objects.select_related(
                "theory_content", "video_content", "lab_content", "test_content__quiz", "checkpoint_quiz", "topic"
            ),
            pk=stage_pk,
            topic=place.topic,
        )
    if place.enrollment:
        place.progress = progress_selectors.stage_progress_map(place.enrollment)
    return place


# --- URLs --------------------------------------------------------------------------


def topic_url(topic) -> str:
    return reverse("student:topic", args=[topic.module.course.slug, topic.number])


def stage_url(stage, name="student:stage") -> str:
    return reverse(name, args=[stage.topic.module.course.slug, stage.topic.number, stage.pk])


# --- statuses ----------------------------------------------------------------------


def stage_status(place: Place, stage) -> str:
    if place.preview:
        return S.AVAILABLE
    sp = place.progress.get(stage.pk)
    return sp.status if sp else S.LOCKED


def stage_meta(place: Place, stage) -> str:
    sp = place.progress.get(stage.pk)
    status = stage_status(place, stage)
    if status == S.PASSED and sp and sp.score_percent is not None:
        return _("Passed · %(score)s%%") % {"score": f"{sp.score_percent:.0f}"}
    if status == S.LOCKED:
        return _("Locked")
    if status == S.IN_PROGRESS:
        return _("In progress")
    if status == S.AWAITING_CHECK:
        return ""
    return stage.get_kind_display()


def stepper(place: Place, topic, stages, current=None) -> list[dict]:
    return [
        {
            "title": s.title,
            "kind": s.kind,
            "status": stage_status(place, s),
            "meta": stage_meta(place, s),
            "url": stage_url(s),
            "current": current is not None and s.pk == current.pk,
        }
        for s in stages
    ]


def ordered_stages(topic) -> list[Stage]:
    return list(topic.stages.order_by("order", "pk"))


def next_place(place: Place, stage) -> tuple[str, str] | None:
    """(url, title) of what comes after ``stage``: the next stage, else the next topic, else the course map."""
    stages = ordered_stages(stage.topic)
    index = [s.pk for s in stages].index(stage.pk)
    if index + 1 < len(stages):
        nxt = stages[index + 1]
        return stage_url(nxt), nxt.title
    topics = Topic.objects.filter(module__course=place.course, number__gt=stage.topic.number)
    if not place.preview:
        topics = topics.filter(is_published=True)
    nxt_topic = topics.order_by("number").select_related("module__course").first()
    if nxt_topic:
        return topic_url(nxt_topic), nxt_topic.title
    return reverse("student:course", args=[place.course.slug]), place.course.title


def continue_target(place: Place):
    """The first open, not finished stage in course order — «continue learning»."""
    topics = Topic.objects.filter(module__course=place.course, is_published=True).order_by("number")
    for topic in topics.prefetch_related("stages"):
        for stage in sorted(topic.stages.all(), key=lambda s: (s.order, s.pk)):
            if stage_status(place, stage) in (S.AVAILABLE, S.IN_PROGRESS):
                stage.topic = topic
                return stage
    return None


def course_map(place: Place) -> list[dict]:
    """Modules → topics → stages with statuses for the course map page."""
    results = progress_selectors.topic_results_map(place.enrollment) if place.enrollment else {}
    modules = []
    for module in Module.objects.filter(course=place.course).order_by("order", "pk"):
        topics = module.topics.order_by("number").prefetch_related("stages")
        if not place.preview:
            topics = topics.filter(is_published=True)
        rows = []
        for topic in topics:
            stages = sorted(topic.stages.all(), key=lambda s: (s.order, s.pk))
            required = [s for s in stages if s.is_required]
            result = results.get(topic.pk)
            rows.append(
                {
                    "topic": topic,
                    "result": result,
                    "status": result.status if result else ("available" if place.preview else "locked"),
                    "stages": [{"stage": s, "status": stage_status(place, s)} for s in stages],
                    "passed": sum(1 for s in required if stage_status(place, s) == S.PASSED),
                    "required": len(required),
                    "url": topic_url(topic),
                }
            )
        if rows:
            modules.append({"module": module, "topics": rows})
    return modules
