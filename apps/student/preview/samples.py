"""The sample work of the teacher's preview: real model instances that are never saved, so the student's page code and
templates run on them unchanged. ``SAMPLE`` lies above every real id, which makes the pages' own reads (a lesson's
reviews, an enrolment's results) find nothing of anybody's. Nothing here is written; the texts are the frames' and the
templates' own, and the AI's answers are a placeholder — the preview never calls the AI."""

from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from apps.assessments.models import QuizAttempt
from apps.pedagogy import frames
from apps.pedagogy import services as pedagogy
from apps.pedagogy.models import Lesson, LessonStage, LessonVersion, Trial, TrialTurn
from apps.pedagogy.services.practice import GRADES
from apps.programme.models import Portfolio, PortfolioVersion, ProgrammeEnrollment
from apps.programme.services import portfolio as portfolio_services

SAMPLE = 2_000_000_000
PLACEHOLDER = _("Preview: the AI does not answer here; the AI student's answer appears in this place.")


class Rows(list):
    """Rows held in memory, answering like the querysets the pages use."""

    def all(self):
        return self

    def order_by(self, *fields):
        return self

    def select_related(self, *fields):
        return self

    def prefetch_related(self, *lookups):
        return self

    def exists(self):
        return bool(self)

    def first(self):
        return self[0] if self else None

    def count(self):
        return len(self)

    def aggregate(self, **expressions):
        return dict.fromkeys(expressions)

    def filter(self, **conditions):
        return Rows(row for row in self if all(_holds(row, *c) for c in conditions.items()))

    def values_list(self, field, flat=False):
        return [getattr(row, field) if flat else (getattr(row, field),) for row in self]


def _holds(row, condition, wanted) -> bool:
    field, _sep, lookup = condition.partition("__")
    value = getattr(row, field, None)
    if lookup == "isnull":
        return (value is None) == wanted
    if lookup == "lte":
        return value is not None and value <= wanted
    return value == wanted


def _related(instance, **rows):
    """Fills the instance's reverse relations: a related manager answers from this cache, not from the database."""
    instance._prefetched_objects_cache = {name: Rows(value) for name, value in rows.items()}
    return instance


def enrollment(programme, user) -> ProgrammeEnrollment:
    return ProgrammeEnrollment(pk=SAMPLE, programme=programme, student=user)


def _stage(lesson, order, **fields) -> LessonStage:
    return LessonStage(pk=SAMPLE + order, lesson=lesson, order=order, **fields)


def _blank_stages(lesson, specs) -> list[LessonStage]:
    return [
        _stage(lesson, order, key=spec.key, title=str(spec.title), minutes=spec.minutes,
               fields={f.key: "" for f in spec.fields})
        for order, spec in enumerate(specs, start=1)
    ]  # fmt: skip


def _ready(lesson, stages) -> Lesson:
    """The lesson with its stages and one assembled version (its plan and trial pages stand on a version)."""
    _related(lesson, stages=stages, versions=[], trials=[], reviews=[], checks=[], expert_reviews=[])
    lesson._prefetched_objects_cache["versions"].append(LessonVersion(
        pk=SAMPLE + 1, lesson=lesson, number=1, reason=LessonVersion.Reason.ASSEMBLE,
        snapshot=pedagogy.snapshot(lesson), created_at=timezone.now(),
    ))  # fmt: skip
    return lesson


def template_lesson(template, user) -> Lesson:
    """Section 4: the copy of a template as pedagogy.start makes it."""
    lesson = Lesson(
        pk=SAMPLE + template.number, owner=user, kind=Lesson.Kind.TEMPLATE_COPY, frame="template",
        source_template=template, title=template.name, topic=template.topic, grade=template.grade,
        duration_min=template.duration_min, aim=template.aim, outcomes=template.outcomes,
    )  # fmt: skip
    stages = [
        _stage(
            lesson, s.order, title=s.title, minutes=s.minutes, fields=pedagogy.template_fields(s.blocks, lesson.frame)
        )
        for s in template.stages.all()
    ]
    return _ready(lesson, stages)


def clear(stage) -> LessonStage:
    """«Clear the content» for this page only: the empty fields open."""
    stage.fields = dict.fromkeys(frames.keys_of(stage.lesson.frame, stage.key), "")
    stage.cleared_at = timezone.now()
    return stage


def practice_lesson(template, user) -> Lesson:
    """Section 5: the empty sheet of eight stages beside the template's section 4 lesson."""
    source = template_lesson(template, user)
    lesson = Lesson(
        pk=SAMPLE + template.number, owner=user, kind=Lesson.Kind.RESEARCH_PRACTICE, frame="research_8",
        source_template=template, source_lesson=source, title=source.title, topic=source.topic,
    )  # fmt: skip
    return _ready(lesson, _blank_stages(lesson, frames.RESEARCH_8))


def micro_lesson(practice, order, user) -> Lesson:
    """Section 6: the empty microlesson made from a part of a practice."""
    part = practice.stages.filter(order=order).first()
    lesson = Lesson(
        pk=SAMPLE + 1, owner=user, kind=Lesson.Kind.MICROLESSON, frame="micro_4",
        source_template=practice.source_template, source_lesson=practice, title=practice.topic or practice.title,
        topic=practice.topic, duration_min=10, details={"source_stage": part.order, "source_title": part.title},
    )  # fmt: skip
    return _ready(lesson, _blank_stages(lesson, frames.MICRO_4))


def independent_lesson(user, *, with_stage=False, status=Lesson.Status.DRAFT) -> Lesson:
    """Section 8: the empty lesson; its stages are the student's own, so at most one blank stage is shown."""
    lesson = Lesson(
        pk=SAMPLE + 1, owner=user, kind=Lesson.Kind.INDEPENDENT, frame="free", cycle=1, title="", duration_min=45,
        status=status,
    )  # fmt: skip
    title = str(_("Stage %(n)s") % {"n": 1})
    fields = dict.fromkeys(frames.keys_of(lesson.frame), "")
    return _ready(lesson, [_stage(lesson, 1, title=title, minutes=5, fields=fields)] if with_stage else [])


def turn(trial, stage, *, analysed=True) -> TrialTurn:
    now = timezone.now()
    return TrialTurn(
        pk=SAMPLE + stage["order"], trial=trial, stage_order=stage["order"], stage_title=stage["title"],
        task=pedagogy.task_html(stage), answer=str(PLACEHOLDER), answer_type=TrialTurn.AnswerType.PARTIAL,
        time_minutes=stage["minutes"], analysed_at=now if analysed else None, created_at=now,
    )  # fmt: skip


def trial(lesson, mode, *, level=Trial.Level.MEDIUM, grade="", finished=True) -> Trial:
    """A trial of the lesson's version: every stage answered by the placeholder; the dialogue of section 6 is empty."""
    version = lesson.versions.first()
    now = timezone.now()
    sample = Trial(
        pk=SAMPLE + 1, lesson=lesson, version=version, mode=mode, level=level,
        grade=grade or lesson.grade or GRADES[0],
        started_at=now, finished_at=now if finished else None,
    )  # fmt: skip
    turns = [] if mode == Trial.Mode.DIALOG else [turn(sample, s) for s in version.snapshot["stages"]]
    return _related(sample, turns=turns, messages=[], expert_reviews=[])


def with_trial(lesson, sample) -> Lesson:
    lesson._prefetched_objects_cache["trials"][:] = [sample]
    return lesson


def portfolio(enrollment) -> Portfolio:
    return _related(Portfolio(pk=SAMPLE, enrollment=enrollment), feedbacks=[], versions=[])


def portfolio_version(sample) -> PortfolioVersion:
    version = PortfolioVersion(
        pk=SAMPLE, portfolio=sample, number=1, created_at=timezone.now(),
        snapshot=portfolio_services.snapshot(sample.enrollment, sample),
    )  # fmt: skip
    sample._prefetched_objects_cache["versions"].append(version)
    return version


def attempt(test, user) -> QuizAttempt:
    """The diagnostic test's single attempt as a student would open it, the questions in their order."""
    questions = test.quiz.questions.filter(is_active=True).values_list("pk", flat=True)
    return QuizAttempt(
        pk=SAMPLE, quiz=test.quiz, user=user, phase=test.phase, attempt_no=1, question_ids=list(questions),
        choice_order={}, started_at=timezone.now(),
    )  # fmt: skip
