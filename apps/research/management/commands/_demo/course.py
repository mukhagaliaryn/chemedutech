"""One made-up student goes through the course stage by stage, the way the stage pages call the services."""

from datetime import timedelta
from unittest import mock

from django.test import override_settings

from apps.assessments import services as quiz_services
from apps.assessments.models import Question
from apps.courses.models import Stage, Topic
from apps.labs import services as lab_services
from apps.labs.engine import get_lab
from apps.practice.services import submissions as practice
from apps.progress import services as progress
from apps.progress.models import StageProgress

from .answers import DemoAI, lab_analysis, lab_journal, open_text, practice_raw, quiz_answers

RETRY_GAIN = 0.08  # a retake goes a little better


def course_stages(course) -> list[Stage]:
    topics = Topic.objects.filter(module__course=course, is_published=True).order_by("module__order", "order")
    return [s for t in topics for s in t.stages.order_by("order", "pk")]


class CourseWalk:
    def __init__(self, enrollment, student, clock, rng):
        self.enrollment = enrollment
        self.user = enrollment.student
        self.student = student
        self.clock = clock
        self.rng = rng
        self.ai = DemoAI(rng)

    # --- helpers ---------------------------------------------------------------------------------

    def spend(self, stage, minutes_from, minutes_to):
        seconds = self.clock.tick(minutes_from, minutes_to)
        progress.add_time(self.enrollment, stage, seconds)

    def quiz(self, stage, quiz, minutes=(3, 8)):
        """Attempts until the stage is passed or no attempt is left (the next stage needs it)."""
        accuracy = self.student.accuracy
        while True:
            attempt = quiz_services.start_attempt(self.user, quiz, self.enrollment, rng=self.rng)
            self.spend(stage, *minutes)
            questions = Question.objects.filter(pk__in=attempt.question_ids).prefetch_related("choices")
            quiz_services.submit_attempt(attempt, quiz_answers(questions, accuracy, self.rng))
            sp = progress.record_quiz_result(self.enrollment, stage, quiz)
            if sp.status == "passed" or quiz_services.attempts_left(self.user, quiz) == 0:
                return
            accuracy = min(1.0, accuracy + RETRY_GAIN)
            self.clock.tick(5, 40)

    # --- stage kinds -----------------------------------------------------------------------------

    def theory(self, stage, partial=False):
        progress.start_stage(self.enrollment, stage)
        if partial:
            self.spend(stage, 6, 15)
            return
        self.spend(stage, 14, 35)
        progress.complete_material(self.enrollment, stage)
        if stage.checkpoint_quiz:
            self.quiz(stage, stage.checkpoint_quiz)

    def video(self, stage, partial=False):
        content = stage.content
        progress.start_stage(self.enrollment, stage)
        self.spend(stage, 4, 9)
        if content and content.has_source:
            progress.record_watch(self.enrollment, stage, self.rng.randint(25, 55), content.min_watch_percent)
            if partial:
                return
            self.spend(stage, 6, 14)
            watched = self.rng.randint(content.min_watch_percent, 100)
            progress.record_watch(self.enrollment, stage, watched, content.min_watch_percent)
        elif partial:
            return
        else:
            progress.complete_material(self.enrollment, stage)
        if stage.checkpoint_quiz:
            self.quiz(stage, stage.checkpoint_quiz)

    def lab(self, stage, partial=False):
        lab = get_lab(stage.content.lab_key)
        progress.start_stage(self.enrollment, stage)
        rows = progress.lab_experiments(self.enrollment, stage)
        for index, row in enumerate(rows):
            if partial and index == max(1, len(rows) - 1):
                return  # the next experiment is waiting
            self.experiment(stage, lab, row["spec"], unfinished=partial and len(rows) == 1)
            if partial and len(rows) == 1:
                return
            progress.record_lab_result(self.enrollment, stage)

    def experiment(self, stage, lab, spec, unfinished=False):
        accuracy = self.student.accuracy
        attempt = lab_services.start_attempt(self.user, lab.key, spec, self.enrollment, stage)
        events, t, seq = [{"seq": 1, "t": 0, "type": "start"}], 0, 1
        steps = spec.steps[: len(spec.steps) // 2] if unfinished else spec.steps
        for step in steps:
            t += self.rng.randint(15, 90) * 1000
            if self.rng.random() > accuracy:  # a slip at this step
                kinds = ["order_error", "hint"]
                kinds += ["wrong_item"] if step.items else []
                kinds += ["wrong_choice"] if step.options else []
                kinds += ["safety_warning"] if step.safety else []
                seq += 1
                events.append({"seq": seq, "t": t, "type": self.rng.choice(kinds), "step": step.key})
                t += self.rng.randint(5, 30) * 1000
            seq += 1
            events.append({"seq": seq, "t": t, "type": "step_done", "step": step.key})
        lab_services.record_events(attempt, events)
        seconds = t // 1000 + self.rng.randint(60, 240)
        self.clock.now += timedelta(seconds=seconds)
        progress.add_time(self.enrollment, stage, seconds)
        if unfinished:
            return
        lab_services.save_journal(attempt, spec, lab_journal(spec, accuracy, self.rng))
        lab_services.record_events(attempt, [{"seq": seq + 1, "t": t + 60000, "type": "finish"}])
        lab_services.finish_attempt(attempt)
        self.spend(stage, 3, 8)
        lab_services.submit_analysis(attempt, spec, lab_analysis(spec, accuracy, self.rng))

    def practice(self, stage, partial=False):
        task = stage.practice_task
        progress.start_stage(self.enrollment, stage)
        if partial:
            self.spend(stage, 5, 15)
            return
        accuracy = self.student.accuracy
        while True:
            self.spend(stage, 18, 45)
            answers, fractions = {}, []
            for item in task.items.all().select_related("rubric"):
                if item.kind == "open":
                    fraction = min(1.0, max(0.0, accuracy + self.rng.uniform(-0.12, 0.08)))
                    fractions.append(fraction)
                    answers[item.pk] = open_text(item, fraction, self.rng)
                else:
                    answers[item.pk] = practice_raw(item, self.rng.random() < accuracy, self.rng)
            # the background AI task is replaced by the demo grader right here: no request leaves the machine
            with mock.patch("apps.practice.tasks.grade_submission"):
                submission = practice.submit(self.enrollment, task, answers)
            if submission.status == "grading":
                self.ai.fraction = sum(fractions) / len(fractions) if fractions else accuracy
                self.clock.tick(1, 3)
                with override_settings(AI_GRADING_ENABLED=True, AI_GRADING_MODEL="demo", AI_GRADING_FALLBACKS=False):
                    practice.grade_open_answers(submission, client=self.ai)
            sp = StageProgress.objects.get(enrollment=self.enrollment, stage=stage)
            if sp.status in ("passed", "awaiting_check") or practice.attempts_left(self.enrollment, task) == 0:
                return
            accuracy = min(1.0, accuracy + RETRY_GAIN)
            self.clock.tick(20, 120)

    def test(self, stage, partial=False):
        quiz = stage.content.quiz
        progress.start_stage(self.enrollment, stage)
        if partial:
            return
        limit = quiz.time_limit_min or 30
        self.quiz(stage, quiz, minutes=(min(8, limit - 2), limit - 2))

    # --- the walk --------------------------------------------------------------------------------

    def run(self, stop_at: int | None = None):
        """All stages in order; ``stop_at`` — the index of the stage the student is in the middle of."""
        progress.ensure_progress(self.enrollment)
        stages = course_stages(self.enrollment.course)
        previous_topic = None
        for index, stage in enumerate(stages):
            if previous_topic is not None and stage.topic_id != previous_topic:
                self.clock.next_day(0, 2)
            previous_topic = stage.topic_id
            partial = stop_at is not None and index == stop_at
            getattr(self, stage.kind)(stage, partial=partial)
            if partial:
                return
            self.clock.tick(2, 15)
