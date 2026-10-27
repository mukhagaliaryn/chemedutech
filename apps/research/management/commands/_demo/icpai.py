"""One made-up student goes through the ICPAI sections 2–8 after the course, the way the section pages call the
services; every AI answer is scripted (tutor.py) and stored by the real AI layer. ``depth`` — the last section the
student gets to; ``waiting`` — the teacher has not reviewed the last work yet."""

from apps.ai import services as ai
from apps.assessments import services as quiz_services
from apps.assessments.models import Question
from apps.pedagogy import frames
from apps.pedagogy.models import ExpertReview, Lesson, LessonTemplate
from apps.pedagogy.services import assembly, independent, lessons, micro, practice
from apps.programme import services as programme
from apps.programme.models import DIRECTIONS, Portfolio, Section
from apps.programme.services import diagnostics
from apps.programme.services import portfolio as portfolio_services

from . import texts as T
from .answers import quiz_answers

LEVELS = ("high", "medium", "low")


class IcpaiWalk:
    def __init__(self, enrollment, student, clock, rng, tutor, teacher):
        self.pe = enrollment
        self.user = enrollment.student
        self.student = student
        self.quality = student.accuracy
        self.clock = clock
        self.rng = rng
        self.tutor = tutor
        self.teacher = teacher
        self.sections = {s.number: s for s in Section.objects.filter(programme=enrollment.programme)}

    def open(self, number) -> bool:
        programme.recalculate(self.pe)
        return programme.can_access(self.pe, self.sections[number])

    def level(self):
        """The AI student's level the future teacher picks for a trial."""
        return self.rng.choice(LEVELS)

    # --- the AI assistant -----------------------------------------------------------------------------------

    def explain_section(self, number):
        section = self.sections[number]
        purpose = section.purpose.split(". ")[0].rstrip(".") + "."
        self.tutor.next(T.SECTION_EXPLAIN.format(title=section.title, purpose=purpose))
        ai.ask(self.user, context_type="section", context_id=section.pk, context=section.purpose,
               intent="explain_section")  # fmt: skip
        self.clock.tick(2, 5)

    def stage_chat(self, stage, t, intents):
        for intent in intents:
            question, answer = T.STAGE_CHAT[intent]
            self.tutor.next(answer.format(stage=stage.title, **t))
            ai.ask(self.user, context_type="lesson_stage", context_id=stage.pk, context=stage.title, intent=intent)
            self.clock.tick(2, 6)
        if self.rng.random() < 0.5:  # a question of their own
            question, answer = self.rng.choice(T.FREE_QUESTIONS)
            self.tutor.next(answer.format(**t))
            ai.ask(self.user, context_type="lesson_stage", context_id=stage.pk, context=stage.title,
                   text=question.format(**t))  # fmt: skip
            self.clock.tick(2, 6)

    # --- 2. diagnostics, 3. the video ----------------------------------------------------------------------------

    def diagnostics(self):
        section = self.sections[2]
        if self.rng.random() < 0.6:
            self.explain_section(2)
        for index, test in enumerate(diagnostics.tests_of(section)):
            if index:
                self.clock.next_day(1, 2)
            attempt = diagnostics.start(self.pe, test)
            self.clock.tick(8, 16)
            questions = Question.objects.filter(pk__in=attempt.question_ids).prefetch_related("choices")
            growth = (-0.15, -0.05, 0.05)[min(index, 2)]  # the diagnostics show growth from I to III
            accuracy = max(0.2, min(1.0, self.quality + growth))
            attempt = quiz_services.submit_attempt(attempt, quiz_answers(questions, accuracy, self.rng))
            diagnostics.record(self.pe, test, attempt)

    def video(self):
        section = self.sections[3]
        programme.record_watch(self.pe, section, self.rng.randint(20, 45))
        self.clock.tick(4, 8)
        programme.record_watch(self.pe, section, 100)
        self.clock.tick(1, 3)

    # --- 4. the lesson design constructor -------------------------------------------------------------------------

    def designer(self, templates: int):
        if self.rng.random() < 0.7:
            self.explain_section(4)
        for template in LessonTemplate.objects.filter(is_active=True).order_by("number")[:templates]:
            t = T.TOPICS[template.code]
            lesson = lessons.start(self.user, template)
            stages = list(lesson.stages.order_by("order"))
            chosen = self.rng.sample(stages, k=2 if self.quality >= 0.7 else 1)
            for stage in chosen:
                self.stage_chat(stage, t, self.rng.sample(["explain_stage", "experiment_idea", "check_science"], k=2))
                lessons.clear(stage)
                self.clock.tick(10, 25)
                lessons.save(stage, title=stage.title, minutes=stage.minutes,
                             fields=T.redesign_fields(stage.original["fields"], t, self.quality))  # fmt: skip
            assembly.assemble(lesson)
            trial = assembly.start_trial(lesson, self.level())
            for order in range(1, len(stages) + 1):
                kind = self.answer_type(trial.level)
                self.tutor.next(T.sim(kind, t))
                assembly.run_turn(trial, order)
                self.clock.tick(2, 5)
            assembly.finalize(lesson)
            self.clock.next_day(0, 1)

    def answer_type(self, level):
        weights = practice.MIX[level]
        return self.rng.choices(practice.TYPES, weights=weights)[0]

    # --- 5. the digital research practice -------------------------------------------------------------------------

    def research(self, templates: int, graded: bool):
        if self.rng.random() < 0.5:
            self.explain_section(5)
        for template in LessonTemplate.objects.filter(is_active=True).order_by("number")[:templates]:
            t = T.TOPICS[template.code]
            lesson = practice.start_practice(self.user, template)
            practice.save_sheet_details(lesson, T.sheet_details(t, template.name.split(" – ")[0]))
            stages = list(lesson.stages.order_by("order"))
            for index, stage in enumerate(stages):
                if index in (2, 6):
                    self.stage_chat(stage, t, [self.rng.choice(["sheet_feedback", "sheet_time", "descriptors"])])
                fields = T.sheet_fields(stage.key, frames.keys_of(lesson.frame, stage.key), t, self.quality)
                lessons.save(stage, title=stage.title, minutes=stage.minutes, fields=fields)
                self.clock.tick(4, 10)
            trial = practice.start_stepwise(lesson, grade=lesson.grade, level=self.level())
            planned = practice.planned_types(trial)
            for stage in trial.version.snapshot["stages"]:
                given = practice.prefill(stage)
                kind = planned[stage["order"] - 1]
                self.tutor.next(T.sim(kind, t))
                turn = practice.give_task(trial, stage["order"], explanation=given["explanation"], task=given["task"],
                                          minutes=given["minutes"])  # fmt: skip
                self.clock.tick(3, 7)
                practice.analyse(
                    turn,
                    analysis=T.p(T.trim(T.ANALYSIS[kind].format(**t), self.quality)),
                    follow_up=T.p(T.FOLLOW_UP[kind]) if kind != "correct" or self.quality > 0.8 else "",
                    correction=T.p(T.CORRECTION.format(**t)) if kind == "wrong" else "",
                    improved_task=T.p(T.IMPROVED) if kind != "correct" and self.quality >= 0.7 else "",
                    duration_s=self.rng.randint(90, 300),
                )
            practice.finish(trial)
            if graded:
                self.teacher_grade(lesson)
            self.clock.next_day(0, 1)

    def scores(self):
        top = 2 if self.quality >= 0.85 else 1
        return {str(n): self.rng.randint(max(0, top - 1), 2 if self.quality >= 0.7 else top) for n in range(1, 6)}

    def teacher_grade(self, lesson, trial=None):
        lesson.refresh_from_db()  # the services save fresh rows
        practice.grade(lesson, self.teacher, self.scores(), self.rng.choice(T.TEACHER_COMMENTS), trial=trial)

    # --- 6. the microlesson ---------------------------------------------------------------------------------------

    def microlesson(self, graded: bool):
        if self.rng.random() < 0.5:
            self.explain_section(6)
        source = Lesson.objects.filter(owner=self.user, kind=Lesson.Kind.RESEARCH_PRACTICE).order_by("pk").first()
        t = T.TOPICS[source.source_template.code]
        lesson = micro.start_micro(self.user, source, self.rng.randint(2, 5))
        micro.save_micro_details(lesson, T.micro_details(t))
        stages = list(lesson.stages.order_by("order"))
        weak = self.rng.random() < (0.8 if self.quality < 0.85 else 0.25)  # the first check finds something
        for stage in stages:
            quality = 0.5 if weak and stage.order == 3 else self.quality
            fields = T.micro_fields(frames.keys_of(lesson.frame, stage.key), t, quality)
            lessons.save(stage, title=stage.title, minutes=stage.minutes, fields=fields)
            self.clock.tick(4, 9)
        self.check(lesson, wrong_stage=3 if weak else None)
        if weak:  # «Check again» after correcting the third stage
            stage = stages[2]
            lessons.save(stage, title=stage.title, minutes=stage.minutes,
                         fields=T.micro_fields(frames.keys_of(lesson.frame, stage.key), t, 1.0))  # fmt: skip
            self.clock.tick(5, 12)
            self.check(lesson)
        for number in range(2 if self.quality >= 0.85 else 1):
            if number:  # the second trial after a change: a fresh check of the new content
                stage = stages[1]
                fields = dict(stage.fields)
                fields["key_points"] = T.p(t["truth"] + " Бұл тұжырымды модельмен қайта көрсетемін.")
                lessons.save(stage, title=stage.title, minutes=stage.minutes, fields=fields)
                self.check(lesson)
                self.clock.next_day(0, 1)
            trial = micro.start_dialog(lesson, grade=t["grade"], level=self.level())
            self.dialog(trial, t)
            if graded:
                self.teacher_grade(lesson, trial)
        micro.assemble_micro(lesson)

    def check(self, lesson, wrong_stage=None):
        stages = {str(n): ("wrong" if n == wrong_stage else "ok") for n in range(1, 5)}
        criteria = {k: "ok" for k in ("aim", "explanation", "chemistry", "task_aim", "assessment", "time", "complete")}
        if wrong_stage:
            criteria["task_aim"] = "wrong"
        self.tutor.next({"stages": stages, "criteria": criteria})
        micro.check_micro(lesson)
        self.clock.tick(1, 3)

    def dialog(self, trial, t):
        level_types = {"high": ("correct", "correct", "partial"), "medium": ("correct", "partial", "wrong"),
                       "low": ("partial", "wrong", "wrong")}[trial.level]  # fmt: skip
        answered = 0
        for _stage, kind, text in T.DIALOG:
            if kind == "question":
                answer_type = level_types[min(answered, 2)] if answered < 2 else "correct"
                answered += 1
            elif kind == "action":
                answer_type = self.rng.choice(["correct", "partial"])
            else:
                answer_type = "none"
            reply = self.rng.choice(T.REPLY[answer_type]).format(**t)
            self.tutor.next({"reply": reply, "answer_type": answer_type})
            self.clock.tick(0.6, 1.0)  # about a minute a turn: the nine turns fit the ten minutes
            micro.send(trial, kind=kind, text=text.format(**t))
        micro.finish_dialog(trial)

    # --- 7. the portfolio -------------------------------------------------------------------------------------------

    def portfolio(self, outcome: str):
        """outcome: accepted | revised (needs more work, then accepted) | waiting (submitted, not reviewed yet)."""
        if self.rng.random() < 0.5:
            self.explain_section(7)
        folio = portfolio_services.portfolio_of(self.pe)
        portfolio_services.save_details(folio, programme_name="6B01504 Химия мұғалімін даярлау", study_year="3-курс")
        answers = {k: T.trim(v, self.quality) if k != "6" else v for k, v in T.REFLECTION.items()}
        portfolio_services.save_reflection(self.pe, answers)
        portfolio_services.save_plan(self.pe, {k: {"action": a, "expected": e} for k, (a, e) in T.PLAN.items()})
        self.clock.tick(15, 35)
        wrong = self.quality < 0.85 and self.rng.random() < 0.6
        items = {k: "ok" for k in (*[f"q{n}" for n in range(1, 8)], *(d for d, _label in DIRECTIONS))}
        if wrong:
            items["q3"] = "wrong"
        self.tutor.next({"items": items})
        portfolio_services.check(folio)
        if wrong:  # the student completes the third answer and checks again
            answers["3"] = T.REFLECTION["3"] + " Оны жеңу үшін қосымша әдебиет оқыдым."
            portfolio_services.save_reflection(self.pe, answers)
            self.tutor.next({"items": {k: "ok" for k in items}})
            portfolio_services.check(folio)
        portfolio_services.assemble(folio)
        portfolio_services.submit(folio)
        if outcome == "waiting":
            return
        self.clock.next_day(1, 2)
        if outcome == "revised":
            portfolio_services.give_feedback(folio, self.teacher, {**T.PORTFOLIO_FEEDBACK, "status": "needs_more"})
            folio.refresh_from_db()
            self.clock.tick(60, 240)
            answers["4"] = (
                T.REFLECTION["4"] + " Екінші сынақта ЖИ-оқушының қате түсінігін бағыттаушы сұрақпен түзеттім."
            )
            portfolio_services.save_reflection(self.pe, answers)
            portfolio_services.assemble(folio)
            portfolio_services.submit(folio)
            self.clock.next_day(1, 1)
        folio.refresh_from_db()
        portfolio_services.give_feedback(folio, self.teacher, {**T.PORTFOLIO_FEEDBACK, "status": "accepted"})
        if self.rng.random() < 0.6:  # later: what was done in the plan
            self.clock.next_day(1, 2)
            portfolio_services.update_results(self.pe, {d: {"done": self.rng.random() < 0.6, "result": "Орындалды."}
                                                        for d, _label in DIRECTIONS})  # fmt: skip

    # --- 8. the independent authorial lesson ------------------------------------------------------------------------

    def independent(self, confirmed: bool):
        if self.rng.random() < 0.6:
            self.explain_section(8)
        t = self.rng.choice(T.INDEPENDENT)
        lesson = independent.start_independent(self.user)
        independent.save_details(lesson, {
            "grade": t["grade"], "topic": t["topic"],
            "aim": f"Оқушылардың {t['concept']} туралы білімін виртуалды зерттеу арқылы қалыптастыру.",
            "outcomes": T.p(f"Оқушылар {t['concept']} ұғымын теңдеу ({t['equation']}) арқылы түсіндіреді."),
            "method": "Зерттеушілік оқыту, жұптық жұмыс", "digital_tools": "Виртуалды зертхана, интерактивті тест",
            "programme": "6B01504 Химия мұғалімін даярлау", "course_group": self.pe.group.name if self.pe.group else "",
            "idea": t["idea"], "lab_task": t["experiment"],
            "assessment": "Ғылыми дұрыстық, дәлелдің болуы, химиялық тілді қолдану.",
            "feedback_way": "«Екі жұлдыз, бір тілек» және ауызша кері байланыс.",
        })  # fmt: skip
        for title, minutes in T.FREE_STAGES:
            stage = independent.add_stage(lesson, title=title, minutes=minutes)
            fields = {
                "aim": T.p(f"{title}: {t['concept']} бойынша оқушының белсенді әрекетін ұйымдастыру."),
                "teacher": T.p(T.trim(f"{t['question']} Оқушылардың болжамын тыңдап, {t['truth']}", self.quality)),
                "task": T.p(T.trim(f"{t['experiment']} Нәтижені кестеге жазып, қорытынды жасаңыз.", self.quality)),
                "visual": T.p("Виртуалды модель, кесте"),
                "expected": T.p(f"Оқушы {t['concept']} ұғымын түсіндіреді."),
                "criterion": T.p("Жауап ғылыми дұрыс әрі дәлелді."),
            }
            lessons.save(stage, title=title, minutes=minutes, fields=fields)
            self.clock.tick(6, 14)
        self.tutor.next(T.expert(("accuracy", "fit", "sequence", "cognition", "assessment", "authorship"), t,
                                 min(self.quality, 0.75), self.rng))  # fmt: skip
        independent.expert_review(lesson)
        self.clock.tick(30, 120)
        self.tutor.next(T.expert(("accuracy", "fit", "sequence", "cognition", "assessment", "authorship"), t, 1.0,
                                 self.rng))  # fmt: skip
        independent.expert_review(lesson)  # «Check again» after the corrections
        independent.submit(lesson)
        lesson.refresh_from_db()
        self.clock.next_day(1, 2)
        trial = independent.start_trial(lesson, grade=t["grade"], level=self.level())
        planned = practice.planned_types(trial)
        for stage in trial.version.snapshot["stages"]:
            given = practice.prefill(stage)
            kind = planned[stage["order"] - 1]
            answers = {"right": t["truth"], "wrong": t["misconception"],
                       "partial": "Негізгі ойды түсіндім, бірақ себебін толық айта алмаймын."}  # fmt: skip
            self.tutor.next(T.sim(kind, {**t, **answers}))
            turn = practice.give_task(trial, stage["order"], explanation=given["explanation"], task=given["task"],
                                      minutes=given["minutes"])  # fmt: skip
            self.clock.tick(3, 7)
            practice.analyse(turn, analysis=T.p(T.ANALYSIS[kind].format(**t)), follow_up=T.p(T.FOLLOW_UP[kind]),
                             correction=T.p(t["truth"]) if kind == "wrong" else "", duration_s=self.rng.randint(90, 300))  # fmt: skip
        independent.finish_trial(trial)
        self.tutor.next(T.expert(("content", "aim", "time", "tasks", "feedback", "method", "reflection"), t,
                                 self.quality, self.rng))  # fmt: skip
        review = independent.trial_review(trial)
        if confirmed:
            self.clock.next_day(1, 2)
            score = 10 if self.quality >= 0.93 else 9 if self.quality >= 0.85 else 8 if self.quality >= 0.62 else 6
            independent.confirm(review, self.teacher, status=ExpertReview.Status.OK,
                                comment="Сабақ сынақтан сәтті өтті. Авторлық идея айқын көрінеді.", score=score)  # fmt: skip

    # --- the walk ---------------------------------------------------------------------------------------------------

    def run(self, plan: dict):
        """plan: {"depth": 2…8, "templates": n, "portfolio": outcome, "confirmed": bool, "graded": bool}."""
        depth = plan["depth"]
        steps = [
            (2, self.diagnostics),
            (3, self.video),
            (4, lambda: self.designer(plan.get("templates", 3))),
            (5, lambda: self.research(plan.get("templates", 3), plan.get("graded", True))),
            (6, lambda: self.microlesson(plan.get("graded", True))),
            (7, lambda: self.portfolio(plan.get("portfolio", "accepted"))),
            (8, lambda: self.independent(plan.get("confirmed", True))),
        ]
        for number, step in steps:
            if number > depth or not self.open(number):
                break
            self.clock.next_day(1, 2)
            step()
        programme.recalculate(self.pe)


def portfolio_status(enrollment) -> str:
    folio = Portfolio.objects.filter(enrollment=enrollment).first()
    return folio.get_status_display() if folio else ""
