"""Teacher: course content editor — structure, stages and their content, quizzes, practice fields (STEP-11).

Course authors (and the admin) edit; assistants see the structure read-only. Writes go through
courses / assessments / practice authoring services; objects students worked on are retired, not deleted.
"""

import json

from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST

from apps.assessments.models import Question, Quiz, QuizAttempt
from apps.assessments.services import authoring as quiz_authoring
from apps.courses import selectors as course_selectors
from apps.courses.models import Module, Stage, Topic
from apps.courses.services import authoring, ensure_stage_content
from apps.labs.engine import all_labs
from apps.practice.models import PracticeItem
from apps.practice.services import authoring as practice_authoring

from . import content_forms as forms
from .views import teacher_only

ERRORS = (authoring.AuthoringError, quiz_authoring.AuthoringError, practice_authoring.AuthoringError)


def _course(request, slug, edit=True):
    course = get_object_or_404(course_selectors.teacher_courses(request.user), slug=slug)
    can_edit = course_selectors.can_edit_course(request.user, course)
    if edit and not can_edit:
        raise PermissionDenied
    course.can_edit = can_edit
    return course


def _structure_url(course, anchor=""):
    return reverse("teacher:course_content", args=[course.slug]) + (f"#{anchor}" if anchor else "")


def _stage(course, pk):
    return get_object_or_404(Stage.objects.select_related("topic__module"), pk=pk, topic__module__course=course)


def _quiz(course, pk):
    """A quiz used by a stage of this course (checkpoint or topic test) or its pre/post test."""
    return get_object_or_404(
        Quiz.objects.filter(
            Q(checkpoint_for__topic__module__course=course)
            | Q(test_contents__stage__topic__module__course=course)
            | Q(benchmark_for=course)
        ).distinct(),
        pk=pk,
    )


def _stage_of_quiz(quiz):
    stage = getattr(quiz, "checkpoint_for", None)
    if stage is None:
        content = quiz.test_contents.select_related("stage").first()
        stage = content.stage if content else None
    return stage


# --- courses and structure -------------------------------------------------------------------


@teacher_only
def courses(request):
    rows = []
    for course in course_selectors.teacher_courses(request.user):
        topics = Topic.objects.filter(module__course=course)
        rows.append(
            {
                "course": course,
                "can_edit": course_selectors.can_edit_course(request.user, course),
                "modules": course.modules.count(),
                "topics": topics.count(),
                "published": topics.filter(is_published=True).count(),
                "stages": Stage.objects.filter(topic__module__course=course).count(),
            }
        )
    return render(request, "teacher/content/courses.html", {"rows": rows})


@teacher_only
def course_content(request, slug):
    course = _course(request, slug, edit=False)
    modules = []
    for module in course.modules.order_by("order", "pk"):
        topics = []
        for topic in module.topics.order_by("number"):
            stages = list(topic.stages.order_by("order", "pk"))
            for s in stages:
                s.ready = _stage_ready(s)
            topics.append({"topic": topic, "stages": stages})
        modules.append({"module": module, "topics": topics})
    return render(
        request,
        "teacher/content/course.html",
        {"course": course, "modules": modules, "benchmark": _benchmark_info(course)},
    )


def _benchmark_info(course) -> dict | None:
    quiz = course.benchmark_quiz
    if quiz is None:
        return None
    attempts = QuizAttempt.objects.filter(quiz=quiz, enrollment__course=course).exclude(finished_at=None)
    return {
        "quiz": quiz,
        "questions": quiz.questions.filter(is_active=True).count(),
        "pre": attempts.filter(phase=QuizAttempt.Phase.PRE).count(),
        "post": attempts.filter(phase=QuizAttempt.Phase.POST).count(),
    }


@require_POST
@teacher_only
def benchmark_create(request, slug):
    """Make the course's pre/post knowledge test (one per course) and open its editor."""
    course = _course(request, slug)
    if course.benchmark_quiz_id:
        return redirect("teacher:quiz", course.slug, course.benchmark_quiz_id)
    quiz = quiz_authoring.create_quiz(_("Knowledge test: %(course)s") % {"course": course.title}, Quiz.Kind.BENCHMARK)
    authoring.attach_benchmark(course, quiz)
    messages.success(request, _("The pre/post test is created. Add its questions."))
    return redirect("teacher:quiz", course.slug, quiz.pk)


def _stage_ready(stage) -> bool:
    content = stage.content
    if content is None:
        return False
    if stage.kind == Stage.Kind.THEORY:
        return bool(content.body)
    if stage.kind == Stage.Kind.VIDEO:
        return bool(content.url or content.file)
    if stage.kind == Stage.Kind.TEST:
        return content.quiz_id is not None
    if stage.kind == Stage.Kind.PRACTICE:
        return content.items.exists()
    return True


@teacher_only
def course_settings(request, slug):
    course = _course(request, slug)
    form = forms.CourseForm(request.POST or None, request.FILES or None, instance=course)
    if request.method == "POST" and form.is_valid():
        course = form.save(commit=False)
        course.stage_kind_weights = form.cleaned_data["stage_kind_weights"]
        course.save()
        messages.success(request, _("The course settings are saved."))
        return redirect("teacher:course_content", course.slug)
    return render(request, "teacher/content/course_form.html", {"course": course, "form": form})


@require_POST
@teacher_only
def reorder(request, slug):
    """Drag & drop / arrow buttons: {"what": modules|topics|stages|questions|items, "parent": id, "ids": [...]}."""
    course = _course(request, slug)
    try:
        data = json.loads(request.body or "{}")
        ids = [int(i) for i in data.get("ids", [])]
        what, parent = data.get("what"), data.get("parent")
    except (ValueError, TypeError):
        return JsonResponse({"ok": False}, status=400)
    try:
        if what == "modules":
            authoring.reorder_modules(course, ids)
        elif what == "topics":
            authoring.reorder_topics(get_object_or_404(Module, pk=parent, course=course), ids)
        elif what == "stages":
            authoring.reorder_stages(get_object_or_404(Topic, pk=parent, module__course=course), ids)
        elif what == "questions":
            quiz_authoring.reorder_questions(_quiz(course, parent), ids)
        elif what == "items":
            stage = _stage(course, parent)
            practice_authoring.reorder_items(practice_authoring.ensure_task(stage), ids)
        else:
            return JsonResponse({"ok": False}, status=400)
    except ERRORS as exc:
        return JsonResponse({"ok": False, "error": str(exc)}, status=409)
    return JsonResponse({"ok": True})


# --- modules and topics ----------------------------------------------------------------------


@teacher_only
def module_edit(request, slug, pk=None):
    course = _course(request, slug)
    module = get_object_or_404(Module, pk=pk, course=course) if pk else None
    form = forms.ModuleForm(request.POST or None, instance=module)
    if request.method == "POST" and form.is_valid():
        module = authoring.save_module(course, form.cleaned_data, module)
        messages.success(request, _("The module is saved."))
        return redirect(_structure_url(course, f"m{module.pk}"))
    return render(request, "teacher/content/simple_form.html", _form_context(course, form, module, _("Module")))


@teacher_only
def topic_edit(request, slug, pk=None):
    course = _course(request, slug)
    topic = get_object_or_404(Topic, pk=pk, module__course=course) if pk else None
    initial = {}
    if topic is None and request.GET.get("module"):
        initial["module"] = request.GET["module"]
    form = forms.TopicForm(course, request.POST or None, request.FILES or None, instance=topic, initial=initial)
    if request.method == "POST" and form.is_valid():
        topic = authoring.save_topic(form.cleaned_data["module"], form.cleaned_data, topic)
        messages.success(request, _("The topic is saved."))
        return redirect(_structure_url(course, f"t{topic.pk}"))
    return render(request, "teacher/content/simple_form.html", _form_context(course, form, topic, _("Topic")))


def _form_context(course, form, obj, noun):
    return {"course": course, "form": form, "object": obj, "noun": noun, "multipart": bool(form.is_multipart())}


@require_POST
@teacher_only
def topic_publish(request, slug, pk):
    course = _course(request, slug)
    topic = get_object_or_404(Topic, pk=pk, module__course=course)
    authoring.set_published(topic, request.POST.get("published") == "1")
    return redirect(_structure_url(course, f"t{topic.pk}"))


@require_POST
@teacher_only
def delete(request, slug, what, pk):
    """Delete a module / topic / stage / question / practice field — refused when students used it."""
    course = _course(request, slug)
    back = _structure_url(course)
    try:
        if what == "module":
            authoring.delete_module(get_object_or_404(Module, pk=pk, course=course))
        elif what == "topic":
            authoring.delete_topic(get_object_or_404(Topic, pk=pk, module__course=course))
        elif what == "stage":
            stage = _stage(course, pk)
            back = _structure_url(course, f"t{stage.topic_id}")
            authoring.delete_stage(stage)
        elif what == "question":
            question = get_object_or_404(Question, pk=pk)
            quiz = _quiz(course, question.quiz_id)
            back = reverse("teacher:quiz", args=[course.slug, quiz.pk])
            if not quiz_authoring.delete_question(question):
                messages.info(request, _("Students have answered this question: it is retired, not deleted."))
                return redirect(back)
        elif what == "item":
            item = get_object_or_404(PracticeItem, pk=pk, task__stage__topic__module__course=course)
            back = reverse("teacher:stage", args=[course.slug, item.task.stage_id]) + "#items"
            practice_authoring.delete_item(item)
        else:
            raise Http404
    except ERRORS as exc:
        messages.error(request, str(exc))
        return redirect(request.POST.get("back") or back)
    messages.success(request, _("Deleted."))
    return redirect(back)


# --- stages -------------------------------------------------------------------------------------


@teacher_only
def stage_new(request, slug):
    course = _course(request, slug)
    topic = get_object_or_404(Topic, pk=request.GET.get("topic") or request.POST.get("topic"), module__course=course)
    form = forms.NewStageForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        kind = form.cleaned_data["kind"]
        stage = authoring.create_stage(topic, kind, form.cleaned_data)
        if kind == Stage.Kind.PRACTICE:
            practice_authoring.ensure_task(stage)
        messages.success(request, _("The stage is added. Now fill in its content."))
        return redirect("teacher:stage", course.slug, stage.pk)
    return render(request, "teacher/content/stage_new.html", {"course": course, "topic": topic, "form": form})


def _content_of(stage):
    if stage.kind == Stage.Kind.PRACTICE:
        return practice_authoring.ensure_task(stage)
    return stage.content or ensure_stage_content(stage)


@teacher_only
def stage_edit(request, slug, pk):
    course = _course(request, slug)
    stage = _stage(course, pk)
    content = _content_of(stage)
    content_form_class = forms.CONTENT_FORMS[stage.kind]
    data, files = (request.POST, request.FILES) if request.method == "POST" else (None, None)
    form = forms.StageForm(data, instance=stage, prefix="stage")
    content_form = content_form_class(data, files, instance=content, prefix="content")
    if request.method == "POST" and form.is_valid() and content_form.is_valid():
        authoring.update_stage(stage, form.cleaned_data)
        content_form.save()
        messages.success(request, _("The stage is saved."))
        return redirect("teacher:stage", course.slug, stage.pk)
    context = {
        "course": course,
        "stage": stage,
        "form": form,
        "content_form": content_form,
        "has_work": authoring.stage_has_work(stage),
        "labs": all_labs(),
    }
    if stage.kind in (Stage.Kind.THEORY, Stage.Kind.VIDEO):
        context["quiz"] = stage.checkpoint_quiz
    elif stage.kind == Stage.Kind.TEST:
        context["quiz"] = content.quiz
    elif stage.kind == Stage.Kind.PRACTICE:
        context["items"] = content.items.order_by("order", "pk")
    return render(request, "teacher/content/stage.html", context)


@require_POST
@teacher_only
def stage_quiz_create(request, slug, pk):
    """Make the checkpoint quiz of a theory / video stage, or the quiz of a topic test stage."""
    course = _course(request, slug)
    stage = _stage(course, pk)
    if stage.kind in (Stage.Kind.THEORY, Stage.Kind.VIDEO) and stage.checkpoint_quiz is None:
        quiz = quiz_authoring.create_quiz(_("Checkpoint: %(stage)s") % {"stage": stage.title}, Quiz.Kind.CHECKPOINT)
        authoring.attach_checkpoint(stage, quiz)
    elif stage.kind == Stage.Kind.TEST and (stage.content is None or stage.content.quiz_id is None):
        quiz = quiz_authoring.create_quiz(stage.title, Quiz.Kind.TOPIC_TEST)
        authoring.attach_test(stage, quiz)
    else:
        raise Http404
    return redirect("teacher:quiz", course.slug, quiz.pk)


# --- quizzes ----------------------------------------------------------------------------------


@teacher_only
def quiz_edit(request, slug, pk):
    course = _course(request, slug)
    quiz = _quiz(course, pk)
    form_class = forms.BenchmarkQuizForm if quiz.kind == Quiz.Kind.BENCHMARK else forms.QuizForm
    form = form_class(request.POST or None, instance=quiz)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, _("The quiz settings are saved."))
        return redirect("teacher:quiz", course.slug, quiz.pk)
    return render(
        request,
        "teacher/content/quiz.html",
        {
            "course": course,
            "quiz": quiz,
            "stage": _stage_of_quiz(quiz),
            "form": form,
            "questions": quiz.questions.order_by("order", "pk").prefetch_related("choices"),
        },
    )


def _choice_rows(request, question) -> list[dict]:
    existing = {c.pk: c for c in question.choices.all()} if question.pk else {}
    rows = []
    for i in range(int(request.POST.get("choices-count", 0) or 0)):
        pk = request.POST.get(f"choices-{i}-id")
        rows.append(
            {
                "choice": existing.get(int(pk)) if pk and pk.isdigit() else None,
                "text": request.POST.get(f"choices-{i}-text", ""),
                "is_correct": request.POST.get(f"choices-{i}-correct") == "on",
                "delete": request.POST.get(f"choices-{i}-delete") == "on",
            }
        )
    return rows


@teacher_only
def question_edit(request, slug, quiz_pk, pk=None):
    course = _course(request, slug)
    quiz = _quiz(course, quiz_pk)
    question = get_object_or_404(Question, pk=pk, quiz=quiz) if pk else Question(quiz=quiz)
    form = forms.QuestionForm(request.POST or None, instance=question)
    choices = [{"choice": c, "text": c.text, "is_correct": c.is_correct, "in_use": quiz_authoring.choice_in_use(c)}
               for c in question.choices.order_by("order", "pk")] if question.pk else []  # fmt: skip
    if request.method == "POST":
        choices = _choice_rows(request, question)
        if form.is_valid():
            try:
                quiz_authoring.save_question(quiz, form.instance, choices)
            except quiz_authoring.AuthoringError as exc:
                form.add_error(None, str(exc))
            else:
                messages.success(request, _("The question is saved."))
                if request.POST.get("then") == "new":
                    return redirect("teacher:question_new", course.slug, quiz.pk)
                return redirect(reverse("teacher:quiz", args=[course.slug, quiz.pk]) + "#questions")
    rows = [
        {
            "id": c["choice"].pk if c.get("choice") else "",
            "text": c["text"],
            "correct": c["is_correct"],
            "delete": c.get("delete", False),
            "in_use": c.get("in_use") or bool(c.get("choice") and quiz_authoring.choice_in_use(c["choice"])),
        }
        for c in choices
    ]
    rows += [{"id": "", "text": "", "correct": False, "delete": False, "in_use": False}] * max(0, 4 - len(rows))
    return render(
        request,
        "teacher/content/question.html",
        {
            "course": course,
            "quiz": quiz,
            "question": question if question.pk else None,
            "form": form,
            "choice_rows": rows,
            "in_use": quiz_authoring.question_in_use(question),
        },
    )


# --- practice fields ------------------------------------------------------------------------------


def _criterion_rows(request, rubric) -> list[dict]:
    existing = {c.pk: c for c in rubric.criteria.all()} if rubric else {}
    rows = []
    for i in range(int(request.POST.get("criteria-count", 0) or 0)):
        pk = request.POST.get(f"criteria-{i}-id")
        try:
            points = max(0, float(request.POST.get(f"criteria-{i}-points", "0").replace(",", ".") or 0))
        except ValueError:
            points = 0
        rows.append(
            {
                "criterion": existing.get(int(pk)) if pk and pk.isdigit() else None,
                "text": request.POST.get(f"criteria-{i}-text", ""),
                "points": points,
                "delete": request.POST.get(f"criteria-{i}-delete") == "on",
            }
        )
    return rows


@teacher_only
def item_edit(request, slug, stage_pk, pk=None):
    course = _course(request, slug)
    stage = _stage(course, stage_pk)
    if stage.kind != Stage.Kind.PRACTICE:
        raise Http404
    task = practice_authoring.ensure_task(stage)
    item = get_object_or_404(PracticeItem, pk=pk, task=task) if pk else PracticeItem(task=task)
    rubric = getattr(item, "rubric", None) if item.pk else None
    action = request.POST.get("action", "save") if request.method == "POST" else None
    form = forms.PracticeItemForm(request.POST if action == "save" else None, instance=item)
    trial = None
    if request.method == "POST" and action == "try" and item.pk:
        trial = practice_authoring.try_answer(item, request.POST.get("answer", ""))
        trial["answer"] = request.POST.get("answer", "")
    elif request.method == "POST" and form.is_valid():
        try:
            item = practice_authoring.save_item(task, form.instance)
            if item.kind == PracticeItem.Kind.OPEN:
                practice_authoring.save_rubric(
                    item,
                    request.POST.get("model_answer", "").strip(),
                    request.POST.get("notes", "").strip(),
                    _criterion_rows(request, getattr(item, "rubric", None)),
                )
        except practice_authoring.AuthoringError as exc:
            form.add_error(None, str(exc))
        else:
            messages.success(request, _("The answer field is saved."))
            return redirect("teacher:item", course.slug, stage.pk, item.pk)
    criteria = [
        {"id": c.pk, "text": c.text, "points": float(c.points), "delete": False}
        for c in (rubric.criteria.order_by("order", "pk") if rubric else [])
    ] or [{"id": "", "text": "", "points": 1, "delete": False}]
    return render(
        request,
        "teacher/content/item.html",
        {
            "course": course,
            "stage": stage,
            "item": item if item.pk else None,
            "form": form,
            "rubric": rubric,
            "criteria": criteria,
            "in_use": practice_authoring.item_in_use(item),
            "trial": trial,
        },
    )
