"""Fixed practice works for tests, so tests do not depend on the course content of the seed.

``use_test_practices()`` replaces the fields of the first two practice works of topic 1 (after ``seed_course``)
with the two works below: every field kind and one open field with a two-criterion rubric.
"""

from apps.courses.models import Stage

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


def use_test_practices(course_slug="chemistry"):
    from .management.commands.seed_practice import write_items

    stages = Stage.objects.filter(
        topic__number=1, kind=Stage.Kind.PRACTICE, topic__module__course__slug=course_slug
    ).order_by("order", "pk")[:2]
    for stage, spec in zip(stages, (PRACTICE_1, PRACTICE_2), strict=True):
        task = stage.practice_task
        task.title, task.instructions = spec["title"], spec["instructions"]
        task.save(update_fields=["title", "instructions"])
        task.items.all().delete()
        write_items(task, {**spec, "rubrics": [spec["rubric"]] if spec.get("rubric") else []})
