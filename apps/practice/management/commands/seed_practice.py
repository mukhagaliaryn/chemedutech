"""Practice works of topic 1 (content in Kazakh). Called by seed_course; idempotent — fields are created
only for a task without fields, so re-running never touches answers students have already given."""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.courses.models import Stage
from apps.practice.models import GradingRubric, PracticeItem, PracticeTask, RubricCriterion

PRACTICE_1 = {
    "title": "Сутегінің көлемін есептеу",
    "instructions": (
        "<p>6,5 г мырыш тұз қышқылының артық мөлшерімен толық әрекеттесті. Реакция теңдеуін жазып, "
        "қалыпты жағдайда (қ.ж.) бөлінген сутегінің көлемін есептеңіз. M(Zn) = 65 г/моль, V<sub>m</sub> = 22,4 л/моль.</p>"
    ),
    "items": [
        ("Реакция теңдеуі", "Мырыш пен тұз қышқылының әрекеттесу теңдеуін коэффициенттерімен жазыңыз.", "equation", 2,
         {"equation": "Zn + 2HCl -> ZnCl2 + H2", "require_balanced": True}, "Сутегі молекуласы — H₂."),
        ("n(Zn)", "Мырыштың зат мөлшері", "numeric", 1,
         {"value": 0.1, "tolerance_pct": 1, "unit": "mol", "units": ["mol", "mmol"]}, "n = m / M"),
        ("V(H₂)", "Бөлінген сутегінің көлемі (қ.ж.)", "numeric", 2,
         {"value": 2.24, "tolerance_pct": 1, "unit": "L", "units": ["mL", "L"]}, "V = n · Vm"),
        ("Тұздың формуласы", "Реакцияда түзілген тұздың формуласы", "formula", 1, {"formula": "ZnCl2"}, ""),
        ("Тотықсыздандырғыш", "Бұл реакцияда мырыш қандай рөл атқарады? (бір сөз)", "text_short", 1,
         {"accepted": ["тотықсыздандырғыш", "тотықсыздағыш"], "typos": 1}, ""),
        ("Түсіндіру", "Неліктен сутегіні суды ығыстыру әдісімен жинауға болады және оны тұтатпас бұрын не істеу керек?",
         "open", 2, None, ""),
    ],
    "rubric": {
        "model_answer": "Сутегі суда нашар ериді, сондықтан суды ығыстырып жинауға болады. Тұтатпас бұрын "
        "сутегінің тазалығын тексеру керек: ауамен қоспасы жарылғыш (күркіреуік газ).",
        "criteria": [("Сутегінің суда нашар еритінін түсіндіреді", 1),
                     ("Тұтатпас бұрын тазалығын тексеру қажеттігін (жарылыс қаупін) атайды", 1)],
    },
}  # fmt: skip

PRACTICE_2 = {
    "title": "Оттегінің массасын есептеу",
    "instructions": (
        "<p>3,4 г сутегі пероксиді MnO<sub>2</sub> қатысында толық ыдырады. Реакция теңдеуін жазып, бөлінген "
        "оттегінің массасын есептеңіз. M(H<sub>2</sub>O<sub>2</sub>) = 34 г/моль, M(O<sub>2</sub>) = 32 г/моль.</p>"
    ),
    "items": [
        ("Реакция теңдеуі", "Сутегі пероксидінің ыдырау теңдеуі", "equation", 2,
         {"equation": "2H2O2 -> 2H2O + O2", "require_balanced": True}, ""),
        ("n(H₂O₂)", "Сутегі пероксидінің зат мөлшері", "numeric", 1,
         {"value": 0.1, "tolerance_pct": 1, "unit": "mol", "units": ["mol", "mmol"]}, ""),
        ("m(O₂)", "Бөлінген оттегінің массасы", "numeric", 2,
         {"value": 1.6, "tolerance_pct": 1, "unit": "g", "units": ["mg", "g"]}, "n(O₂) = n(H₂O₂) / 2"),
        ("MnO₂ рөлі", "Бұл реакцияда MnO₂ не болып табылады?", "choice", 1,
         {"options": ["катализатор", "тотықтырғыш", "реагент"], "correct": ["катализатор"]}, ""),
        ("Тәжірибе реті", "Тәжірибенің қадамдарын дұрыс ретке келтіріңіз", "ordering", 1,
         {"order": ["Пробиркаға H₂O₂ ерітіндісін құю", "MnO₂ ұнтағын қосу", "Бықсып тұрған шамшырақты енгізу"]}, ""),
        ("Газды анықтау", "Газ бен оны анықтау тәсілін сәйкестендіріңіз", "matching", 1,
         {"pairs": {"H₂": "тыныш «пах» дыбысымен жанады", "O₂": "бықсыған шамшырақ лап етіп жанады"}}, ""),
    ],
}  # fmt: skip


class Command(BaseCommand):
    help = "Create the practice works of topic 1 (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        stages = list(Stage.objects.filter(topic__number=1, kind="practice", topic__module__course__slug="chemistry")
                      .order_by("order"))  # fmt: skip
        for stage, spec in zip(stages, (PRACTICE_1, PRACTICE_2), strict=False):
            task, _ = PracticeTask.objects.get_or_create(
                stage=stage, defaults={"title": spec["title"], "instructions": spec["instructions"]}
            )
            if task.items.exists():
                continue
            for order, (label, prompt, kind, points, answer_spec, hint) in enumerate(spec["items"], start=1):
                item = PracticeItem.objects.create(
                    task=task, order=order, label=label, prompt=prompt, kind=kind, points=points,
                    answer_spec=answer_spec or {}, hint=hint,
                )  # fmt: skip
                if kind == "open":
                    rubric = GradingRubric.objects.create(item=item, model_answer=spec["rubric"]["model_answer"])
                    for i, (text, pts) in enumerate(spec["rubric"]["criteria"], start=1):
                        RubricCriterion.objects.create(rubric=rubric, order=i, text=text, points=pts)
        self.stdout.write(self.style.SUCCESS(f"Practice works ready: {len(stages)}"))
