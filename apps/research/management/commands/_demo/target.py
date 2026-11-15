"""A made-up student who reaches given topic scores (seed_control): every stage is taken through the real services
like CourseWalk does, but the answers are chosen so that the counted attempts give the planned stage scores.

How a topic score is reached (the platform's own formula, progress.services.scoring):
* theory / video / test — the quiz is answered right on exactly k questions (4 or 10 questions: 25 / 10 % steps);
  below the pass mark the student retakes until no attempt is left (the best attempt counts, «needs attention»);
* lab — the experiments run at the student's accuracy; the score is measured, not forced;
* practice works — exact items right or wrong and open answers graded by the scripted AI at a chosen share, so the
  last practice of a topic makes up what the lab and the quizzes left over.
Topics without a lab and practice (6–10: two 4-question quizzes and a 10-question test) can only take scores in steps
of 1.25; the five of them are chosen together so that the course score keeps the given letter grade."""

import itertools
import json
from datetime import timedelta
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.test import override_settings
from django.utils import timezone

from apps.assessments import services as quiz_services
from apps.assessments.models import Question
from apps.courses.selectors import stages_of
from apps.labs import services as lab_services
from apps.labs.engine import get_lab
from apps.practice.services import submissions as practice
from apps.progress import services as progress
from apps.progress.grading import grade_for
from apps.progress.models import ModuleResult, StageProgress, TopicResult
from apps.progress.services.scoring import q2, stage_weights

from .answers import (
    CRITERION,
    FEEDBACK,
    _wrong_equation,
    lab_analysis,
    lab_journal,
    open_text,
    option_key,
    practice_raw,
    quiz_answers_exact,
)
from .course import CourseWalk, course_stages

QUIZ_KINDS = ("theory", "video", "test")


class TargetAI:
    """The practice grader's scripted AI: every criterion at exactly ``fraction`` (half points), no jitter."""

    def __init__(self):
        self.fraction = 1.0
        self.messages = SimpleNamespace(create=self._create)
        self.beta = SimpleNamespace(messages=SimpleNamespace(create=self._create))

    def _create(self, **params):
        prompt = params["messages"][0]["content"]
        criteria = []
        for cid, top in CRITERION.findall(prompt):
            points = round(float(top) * self.fraction * 2) / 2
            reason = "Критерий орындалған." if points >= float(top) else "Критерий ішінара орындалған."
            criteria.append({"criterion_id": int(cid), "points": points, "reason": reason if points else "Жоқ."})
        level = "high" if self.fraction >= 0.85 else "medium" if self.fraction >= 0.55 else "low"
        text = json.dumps(
            {"criteria": criteria, "feedback_kk": FEEDBACK[level], "confidence": "high"}, ensure_ascii=False
        )
        return SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=text)],
            usage=SimpleNamespace(input_tokens=0, output_tokens=0),
            to_dict=lambda: {"demo": True, "text": text},
        )


def scored(field) -> bool:
    """A journal field the lab formula counts (labs.services.attempts._score_choices)."""
    if getattr(field, "kind", "") == "equation":
        return bool(field.answer)
    return any(o.correct for o in field.options)


def wrong_field(field, rng) -> str:
    if getattr(field, "kind", "") == "equation":
        return _wrong_equation(field.answer)
    return option_key(field.options, False, rng)


def whole(value) -> int:
    """A score rounded the way the gradebook rounds (half up)."""
    return int(Decimal(value).quantize(Decimal("1"), rounding="ROUND_HALF_UP"))


def quiz_of(stage):
    return stage.content.quiz if stage.kind == "test" else stage.checkpoint_quiz


def _plausible(values, target) -> float:
    """How far a plan of quiz percents is from a student working at ``target`` (failed quizzes cost more)."""
    return sum(abs(v - target) + (25 if v < 50 else 0) for v in values)


def quiz_only_options(weights, sizes, target, keep=3) -> list[tuple[Decimal, tuple]]:
    """Topics made of quizzes only: the reachable scores nearest to ``target`` with the most plausible plan of each."""
    steps = [[Decimal(100 * k) / n for k in range(n + 1)] for n in sizes]
    best: dict[Decimal, tuple] = {}
    for plan in itertools.product(*steps):
        score = q2(sum(w * v for w, v in zip(weights, plan, strict=True)) / sum(weights))
        cost = _plausible([float(v) for v in plan], target)
        if score not in best or cost < best[score][0]:
            best[score] = (cost, plan)
    nearest = sorted(best, key=lambda s: (abs(float(s) - target), best[s][0]))[:keep]
    return [(s, best[s][1]) for s in nearest]


def best_subset(points: list[Decimal], goal: Decimal, rng) -> set[int]:
    """Indexes of items whose points add up nearest to ``goal`` (half-point DP; ties at random)."""
    order = list(range(len(points)))
    rng.shuffle(order)
    reach = {0: frozenset()}
    for i in order:
        step = int(points[i] * 2)
        for total, chosen in list(reach.items()):
            reach.setdefault(total + step, chosen | {i})
    target = int(goal * 2)
    total = min(reach, key=lambda t: (abs(t - target), rng.random()))
    return set(reach[total])


class TargetCourseWalk(CourseWalk):
    """``targets`` — {topic number: score}; ``final`` — the course score and letter to keep; ``days`` — the
    datetime each topic starts (the last one is the completion date)."""

    def __init__(self, enrollment, student, clock, rng, targets, final, days):
        super().__init__(enrollment, student, clock, rng)
        self.targets = targets
        self.final_score, self.letter = final
        self.days = days
        self.grader = TargetAI()
        self.course = enrollment.course
        self.planned: dict[int, tuple] = {}  # topic number → planned quiz percents (quiz-only topics)

    # --- quizzes ---------------------------------------------------------------------------------

    def take(self, stage, quiz, percent: Decimal, minutes):
        """Attempts that end with exactly ``percent`` counted: one attempt when it passes, else retakes (no better)."""
        attempt = quiz_services.start_attempt(self.user, quiz, self.enrollment, rng=self.rng)
        n = len(attempt.question_ids)
        right = round(float(percent) * n / 100)
        passes = right * 100 >= quiz.pass_percent * n
        tries = 1 if passes else (quiz.max_attempts or 1)
        plan = [self.rng.randint(max(0, right - 2), right) for _ in range(tries - 1)] + [right]
        if not passes:
            self.rng.shuffle(plan)
        for index, k in enumerate(plan):
            if index:
                self.clock.tick(5, 40)
                attempt = quiz_services.start_attempt(self.user, quiz, self.enrollment, rng=self.rng)
            self.spend(stage, *minutes)
            questions = list(Question.objects.filter(pk__in=attempt.question_ids).prefetch_related("choices"))
            ids = {q.pk for q in self.rng.sample(questions, k)}
            quiz_services.submit_attempt(attempt, quiz_answers_exact(questions, ids, self.rng))
            progress.record_quiz_result(self.enrollment, stage, quiz)

    def material(self, stage):
        progress.start_stage(self.enrollment, stage)
        if stage.kind == "video":
            content = stage.content
            self.spend(stage, 4, 9)
            if content and content.has_source:
                progress.record_watch(self.enrollment, stage, self.rng.randint(25, 55), content.min_watch_percent)
                self.spend(stage, 6, 14)
                watched = self.rng.randint(content.min_watch_percent, 100)
                progress.record_watch(self.enrollment, stage, watched, content.min_watch_percent)
                return
        else:
            self.spend(stage, 14, 35)
        progress.complete_material(self.enrollment, stage)

    # --- practice ----------------------------------------------------------------------------------

    def practice_to(self, stage, percent: float):
        """One work aimed at ``percent``; below the pass mark a weaker first attempt and a second one at it."""
        task = stage.practice_task
        progress.start_stage(self.enrollment, stage)
        passes = percent >= float(stage.pass_percent)
        tries = 1 if passes else max(1, task.max_attempts or 1)
        goals = [max(0.0, percent - self.rng.uniform(6, 15)) for _ in range(tries - 1)] + [percent]
        for index, goal in enumerate(goals):
            if index:
                self.clock.tick(20, 120)
            self.spend(stage, 18, 45)
            self.submit_practice(task, goal)
        # the points came out just under the pass mark: another try at the same goal while attempts are left
        while (
            StageProgress.objects.get(enrollment=self.enrollment, stage=stage).status
            not in ("passed", "awaiting_check")
            and practice.attempts_left(self.enrollment, task) > 0
        ):
            self.clock.tick(20, 120)
            self.spend(stage, 18, 45)
            self.submit_practice(task, percent)

    def submit_practice(self, task, percent: float):
        items = list(task.items.all().select_related("rubric"))
        exact = [i for i in items if i.kind != "open"]
        opened = [i for i in items if i.kind == "open"]
        total = sum((Decimal(i.points) for i in items), Decimal(0))
        goal = Decimal(str(percent)) * total / 100
        open_total = sum((Decimal(i.points) for i in opened), Decimal(0))
        share = Decimal(str(min(1.0, max(0.0, percent / 100))))
        right = best_subset([Decimal(i.points) for i in exact], goal - share * open_total, self.rng)
        exact_points = sum((Decimal(exact[i].points) for i in right), Decimal(0))
        fraction = float((goal - exact_points) / open_total) if open_total else 0.0
        self.grader.fraction = min(1.0, max(0.0, fraction))
        answers = {}
        for index, item in enumerate(exact):
            answers[item.pk] = practice_raw(item, index in right, self.rng)
        for item in opened:
            answers[item.pk] = open_text(item, self.grader.fraction, self.rng)
        with mock.patch("apps.practice.tasks.grade_submission"):
            submission = practice.submit(self.enrollment, task, answers)
        if submission.status == "grading":
            self.clock.tick(1, 3)
            with override_settings(AI_GRADING_ENABLED=True, AI_GRADING_MODEL="demo", AI_GRADING_FALLBACKS=False):
                practice.grade_open_answers(submission, client=self.grader)

    # --- a topic ---------------------------------------------------------------------------------

    def scores(self, stages) -> dict[int, Decimal]:
        rows = StageProgress.objects.filter(enrollment=self.enrollment, stage__in=stages).exclude(score_percent=None)
        return {r.stage_id: r.score_percent for r in rows}

    def topic(self, topic, stages):
        target = float(self.targets[topic.number])
        weights = stage_weights(self.course, stages)
        total = sum(weights.values())
        w = {s.pk: weights[s.pk] / total for s in stages}
        quizzes = [s for s in stages if s.kind in QUIZ_KINDS]
        if all(s.kind in QUIZ_KINDS for s in stages):
            plan = dict(zip([s.pk for s in quizzes], self.planned[topic.number], strict=True))
            for stage in stages:
                if stage.kind != "test":
                    self.material(stage)
                else:
                    progress.start_stage(self.enrollment, stage)
                self.take(stage, quiz_of(stage), plan[stage.pk], self.quiz_minutes(stage))
                self.clock.tick(2, 15)
            return
        test = next((s for s in stages if s.kind == "test"), None)
        test_n = len(quiz_of(test).questions.filter(is_active=True)) if test else 10
        step = 100 / max(1, test_n)
        planned_test = min(100.0, max(30.0, round(target / step) * step + self.rng.choice((-step, 0, 0, step))))
        for stage in stages:
            done = self.scores(stages)
            if stage.kind in ("theory", "video"):
                self.material(stage)
                n = quiz_of(stage).questions.count()
                self.take(stage, quiz_of(stage), self.material_quiz_percent(target, n), (3, 8))
            elif stage.kind == "lab":
                self.lab(stage, target=target)
            elif stage.kind == "practice":
                practices = [s for s in stages if s.kind == "practice" and s.pk not in done]
                left = sum(w[s.pk] for s in practices)
                fixed = sum(w[pk] * v for pk, v in done.items())
                need = (Decimal(str(target)) - fixed - (w[test.pk] * Decimal(str(planned_test)) if test else 0)) / left
                need = float(need)
                if test and len(practices) == len([s for s in stages if s.kind == "practice"]):
                    planned_test = self.balance_test(target, fixed, w[test.pk], left, step)
                    need = float((Decimal(str(target)) - fixed - w[test.pk] * Decimal(str(planned_test))) / left)
                if len(practices) > 1:
                    need += self.rng.uniform(-8, 8)
                self.practice_to(stage, min(100.0, max(0.0, need)))
            elif stage.kind == "test":
                progress.start_stage(self.enrollment, stage)
                fixed = sum(w[pk] * v for pk, v in done.items() if pk != stage.pk)
                options = [planned_test + d for d in (-step, 0, step) if 0 <= planned_test + d <= 100]
                best = min(
                    options,
                    key=lambda v: (abs(float(fixed + w[stage.pk] * Decimal(str(v))) - target), v != planned_test),
                )
                self.take(stage, quiz_of(stage), Decimal(str(best)), self.quiz_minutes(stage))
            self.clock.tick(2, 15)

    def balance_test(self, target, fixed, w_test, left, step) -> float:
        """After the lab: the test score (within ±25 of the target) that leaves the practices nearest to the target
        themselves, so that what the lab missed is shared by the test and the practices, not by the practices alone."""
        low, high = max(0.0, target - 20), min(100.0, target + 20)
        options = [k * step for k in range(int(100 / step) + 1) if low <= k * step <= high] or [
            round(target / step) * step
        ]

        def practice_need(v):
            return float((Decimal(str(target)) - fixed - w_test * Decimal(str(v))) / left)

        def cost(v):
            need = practice_need(v)
            return (
                abs(need - target) + abs(v - target) * 0.6 + (1000 if not 0 <= need <= 100 else 0) + self.rng.random()
            )

        return min(options, key=cost)

    def material_quiz_percent(self, target, n) -> Decimal:
        quarter = 100 / n
        if target >= 80:
            choices = (75, 100, 100)
        elif target >= 68:
            choices = (75, 75, 100)
        elif target >= 58:
            choices = (50, 75, 75, 75)
        else:
            choices = (50, 50, 75)
        return Decimal(round(self.rng.choice(choices) / quarter) * quarter)

    def quiz_minutes(self, stage):
        if stage.kind != "test":
            return (3, 8)
        limit = quiz_of(stage).time_limit_min or 30
        return (min(8, limit - 2), limit - 2)

    def lab(self, stage, partial=False, target=None):
        """Every experiment aimed at the target (a little spread, the last one makes up the mean)."""
        lab = get_lab(stage.content.lab_key)
        progress.start_stage(self.enrollment, stage)
        goal = target if target is not None else self.student.accuracy * 100
        rows = progress.lab_experiments(self.enrollment, stage)
        scores = []
        for index, row in enumerate(rows):
            aim = goal * (len(scores) + 1) - sum(scores) if index == len(rows) - 1 else goal + self.rng.uniform(-6, 6)
            scores.append(self.experiment_to(stage, lab, row["spec"], min(100.0, max(0.0, aim))))
            progress.record_lab_result(self.enrollment, stage)

    def lab_plan(self, spec, scoring, goal):
        """(order errors, wrong item/choice slips, right journal fields, right analysis answers) nearest to ``goal``
        by the lab's formula, the parts themselves near the goal too."""
        journal = [f for f in spec.journal if scored(f)]
        closed = [q for q in spec.questions if any(o.correct for o in q.options)]
        can_wrong = any(st.items or st.options for st in spec.steps)
        best = None
        for orders in range(0, min(len(spec.steps), 6) + 1):
            for wrongs in range(0, (4 if can_wrong else 0) + 1):
                process = max(0.0, 100 - scoring.order_error_penalty * orders - scoring.wrong_penalty * wrongs)
                for j in range(len(journal) + 1):
                    for a in range(len(closed) + 1):
                        parts = [(scoring.weight_process, process)]
                        if journal:
                            parts.append((scoring.weight_journal, 100 * j / len(journal)))
                        if closed:
                            parts.append((scoring.weight_analysis, 100 * a / len(closed)))
                        score = sum(w * v for w, v in parts) / sum(w for w, _ in parts)
                        cost = (
                            abs(score - goal) * 10
                            + sum(abs(v - goal) for _, v in parts) * 0.05
                            + self.rng.random() * 0.1
                        )
                        if best is None or cost < best[0]:
                            best = (cost, orders, wrongs, j, a)
        return best[1:]

    def experiment_to(self, stage, lab, spec, goal) -> float:
        orders, wrongs, j, a = self.lab_plan(spec, lab.scoring, goal)
        attempt = lab_services.start_attempt(self.user, lab.key, spec, self.enrollment, stage)
        slips = ["order_error"] * orders + ["wrong"] * wrongs
        self.rng.shuffle(slips)
        steps = list(spec.steps)
        where = {}
        for kind in slips:
            if kind == "wrong":
                options = [k for k, st in enumerate(steps) if st.items or st.options]
                k = self.rng.choice(options)
                kind = "wrong_item" if steps[k].items else "wrong_choice"
            else:
                k = self.rng.randrange(len(steps))
            where.setdefault(k, []).append(kind)
        events, t, seq = [{"seq": 1, "t": 0, "type": "start"}], 0, 1
        for k, step in enumerate(steps):
            t += self.rng.randint(15, 90) * 1000
            for kind in where.get(k, []):
                seq += 1
                events.append({"seq": seq, "t": t, "type": kind, "step": step.key})
                t += self.rng.randint(5, 30) * 1000
            seq += 1
            events.append({"seq": seq, "t": t, "type": "step_done", "step": step.key})
        lab_services.record_events(attempt, events)
        seconds = t // 1000 + self.rng.randint(60, 240)
        self.clock.now += timedelta(seconds=seconds)
        progress.add_time(self.enrollment, stage, seconds)
        journal = lab_journal(spec, 1.0, self.rng)
        scored_fields = [f for f in spec.journal if scored(f)]
        right = set(self.rng.sample(range(len(scored_fields)), j))
        for index, f in enumerate(scored_fields):
            if index not in right:
                journal[f.key] = wrong_field(f, self.rng)
        lab_services.save_journal(attempt, spec, journal)
        lab_services.record_events(attempt, [{"seq": seq + 1, "t": t + 60000, "type": "finish"}])
        lab_services.finish_attempt(attempt)
        self.spend(stage, 3, 8)
        closed = [q for q in spec.questions if any(o.correct for o in q.options)]
        good = set(self.rng.sample(range(len(closed)), a))
        analysis = lab_analysis(spec, 1.0, self.rng)
        for index, q in enumerate(closed):
            analysis[q.key] = option_key(q.options, index in good, self.rng)
        attempt = lab_services.submit_analysis(attempt, spec, analysis)
        return float(attempt.score_percent or 0)

    # --- quiz-only topics: chosen together for the letter ------------------------------------------

    def plan_quiz_topics(self, topics):
        """The scores of the quiz-only topics nearest to their targets that keep the course letter grade."""
        modules: dict[int, list] = {}
        for t in topics:
            modules.setdefault(t.module_id, []).append(t)
        options = {}
        for t in topics:
            stages = list(stages_of(t).order_by("order", "pk"))
            if not all(s.kind in QUIZ_KINDS for s in stages):
                continue
            weights = stage_weights(self.course, stages)
            sizes = [quiz_of(s).questions.count() for s in stages]
            options[t.number] = quiz_only_options([weights[s.pk] for s in stages], sizes, float(self.targets[t.number]))
        if not options:
            return
        done = {r.topic.number: r.score_percent for r in TopicResult.objects.filter(enrollment=self.enrollment)
                .select_related("topic") if r.score_percent is not None}  # fmt: skip
        numbers = sorted(options)
        best = None
        for choice in itertools.product(*(options[n] for n in numbers)):
            scores = {**done, **{n: c[0] for n, c in zip(numbers, choice, strict=True)}}
            module_scores = [q2(sum(Decimal(scores.get(t.number, self.targets[t.number])) for t in ts) / len(ts))
                             for ts in modules.values()]  # fmt: skip
            final = q2(sum(module_scores) / len(module_scores))
            cost = abs(float(final) - self.final_score) * 3 + sum(
                abs(float(c[0]) - float(self.targets[n])) + (0.3 if whole(c[0]) != int(self.targets[n]) else 0)
                for n, c in zip(numbers, choice, strict=True)
            )
            if grade_for(final).letter != self.letter:
                cost += 1000
            if best is None or cost < best[0]:
                best = (cost, choice)
        for n, c in zip(numbers, best[1], strict=True):
            self.planned[n] = c[1]

    # --- the walk --------------------------------------------------------------------------------

    def run(self, stop_at=None):
        progress.ensure_progress(self.enrollment)
        stages = course_stages(self.course)
        topics = []
        for s in stages:
            if s.topic not in topics:
                topics.append(s.topic)
        for topic in topics:
            day = self.days[topic.number]
            if day > self.clock.now:
                self.clock.now = day
            if not self.planned and all(s.kind in QUIZ_KINDS for s in stages_of(topic)):
                self.plan_quiz_topics(topics)
            self.topic(topic, [s for s in stages if s.topic_id == topic.pk])

    def module_scores(self) -> list[Decimal]:
        return list(ModuleResult.objects.filter(enrollment=self.enrollment).order_by("module__order")
                    .values_list("current_percent", flat=True))  # fmt: skip


def topic_days(start, end, count, rng) -> dict[int, object]:
    """When each topic starts: spread from ``start`` to ``end`` (the completion day, early enough to finish)."""
    span = (end - start).total_seconds()
    days = {}
    for index in range(count):
        moment = start + timedelta(seconds=span * index / max(1, count - 1))
        local = timezone.localtime(moment)
        hour = rng.randint(9, 13) if index == count - 1 else rng.randint(9, 19)
        days[index + 1] = local.replace(hour=hour, minute=rng.randint(0, 59), second=0, microsecond=0)
    return days
