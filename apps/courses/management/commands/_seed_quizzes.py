"""Quizzes of topic 1 (content in Kazakh). Questions are created only for an empty quiz, so re-running the
seed never touches questions that students have already answered."""

from decimal import Decimal

from apps.assessments.models import Choice, Question, Quiz

# (kind, text, options | answer, explanation); options: [(text, is_correct), ...]
THEORY_CHECKPOINT = [
    ("single", "<p>Неліктен сутегіні суды ығыстыру әдісімен жинауға болады?</p>",
     [("Ол суда іс жүзінде ерімейді", True), ("Ол судан ауыр", False), ("Ол сумен әрекеттеседі", False)],
     "Сутегі суда өте нашар ериді, сондықтан суды ығыстырып жинауға болады."),
    ("single", "<p>Оттегіні сутегі пероксидінен алғанда MnO<sub>2</sub> қандай рөл атқарады?</p>",
     [("Катализатор", True), ("Тотықтырғыш", False), ("Реакция өнімі", False)],
     "MnO₂ реакцияны жылдамдатады және реакция соңында өзгеріссіз қалады — бұл катализатор."),
    ("multiple", "<p>Сутегі туралы қай тұжырымдар дұрыс?</p>",
     [("Ең жеңіл газ", True), ("Ауамен қоспасы жарылғыш", True), ("Жануды қолдайды", False),
      ("Суда жақсы ериді", False)],
     "Сутегі — ең жеңіл газ, ауамен қоспасы жарылғыш; ол өзі жанады, бірақ жануды қолдамайды."),
    ("single", "<p>Судың электролизінде катодта қандай газ бөлінеді?</p>",
     [("Сутегі", True), ("Оттегі", False), ("Хлор", False)],
     "Катодта сутегі иондары тотықсызданады: катодта H₂, анодта O₂ бөлінеді."),
]  # fmt: skip

VIDEO_CHECKPOINT = [
    ("single", "<p>Сутегінің тазалығын қалай тексереді?</p>",
     [("Пробирканы жалынға жақындатады: тыныш «пах» дыбысы — таза сутегі", True),
      ("Бықсып тұрған шамшырақты енгізеді", False), ("Газды әк суы арқылы өткізеді", False)],
     "Таза сутегі тыныш «пах» дыбысымен жанады, ысқырық дыбыс — ауамен қоспа."),
    ("single", "<p>Оттегіні қалай анықтайды?</p>",
     [("Бықсып тұрған шамшырақ лап етіп жанады", True), ("Жалын сөнеді", False), ("Әк суы лайланады", False)],
     "Оттегі жануды қолдайды: бықсып тұрған шамшырақ лап етіп жанады."),
    ("numeric", "<p>Судың электролизінде V(H<sub>2</sub>) : V(O<sub>2</sub>) қатынасы неге тең? "
                "Сутегі көлемін оттегі көлеміне бөліп, санмен жазыңыз.</p>",
     (Decimal("2"), Decimal("0")),
     "2H₂O → 2H₂ + O₂: сутегі оттегіден екі есе көп, қатынас 2 : 1."),
]  # fmt: skip

TOPIC_TEST = [
    ("single", "<p>Мырыш тұз қышқылымен әрекеттескенде қандай газ бөлінеді?</p>",
     [("H<sub>2</sub>", True), ("O<sub>2</sub>", False), ("Cl<sub>2</sub>", False), ("CO<sub>2</sub>", False)],
     "Zn + 2HCl → ZnCl₂ + H₂↑"),
    ("numeric", "<p>Zn + 2HCl → ZnCl<sub>2</sub> + H<sub>2</sub> бойынша 0,1 моль мырыштан қалыпты жағдайда "
                "неше литр сутегі түзіледі?</p>",
     (Decimal("2.24"), Decimal("0.02")),
     "n(H₂) = n(Zn) = 0,1 моль; V = 0,1 · 22,4 = 2,24 л."),
    ("numeric", "<p>2H<sub>2</sub>O<sub>2</sub> → 2H<sub>2</sub>O + O<sub>2</sub> бойынша 0,2 моль сутегі "
                "пероксидінен неше моль оттегі түзіледі?</p>",
     (Decimal("0.1"), Decimal("0")),
     "Оттегі пероксидтен екі есе аз: 0,2 / 2 = 0,1 моль."),
    ("short_text", "<p>Реакцияны жылдамдататын, бірақ өзі өзгеріссіз қалатын зат қалай аталады? (бір сөз)</p>",
     ["катализатор"],
     "Катализатор — реакцияны жылдамдататын, бірақ реакция соңында өзгеріссіз қалатын зат."),
    ("multiple", "<p>Оттегіні зертханада алу үшін қай заттарды пайдалануға болады?</p>",
     [("H<sub>2</sub>O<sub>2</sub> (MnO<sub>2</sub> қатысында)", True),
      ("KMnO<sub>4</sub> (қыздырғанда)", True), ("NaCl", False), ("Zn", False)],
     "Оттегіні сутегі пероксидін ыдыратып немесе калий перманганатын қыздырып алады."),
    ("single", "<p>Ауаны ығыстыру әдісімен сутегіні жинағанда ыдысты қалай ұстайды?</p>",
     [("Төңкеріп, түбін жоғары қаратып", True), ("Ауызын жоғары қаратып", False), ("Көлденең", False)],
     "Сутегі ауадан жеңіл, сондықтан төңкерілген ыдыстың жоғарғы бөлігіне жиналады."),
    ("short_text", "<p>Сутегінің ауамен (оттегімен) жарылғыш қоспасы қалай аталады?</p>",
     ["күркіреуік газ", "күркіреуік"],
     "Сутегі мен оттегінің 2 : 1 көлемдік қатынастағы қоспасы — күркіреуік газ."),
    ("single", "<p>Судың электролизі кезінде суға неліктен аздаған электролит (мысалы, Na<sub>2</sub>SO<sub>4</sub>) "
               "қосады?</p>",
     [("Ерітіндінің электр өткізгіштігін арттыру үшін", True), ("Сутегі көлемін көбейту үшін", False),
      ("Оттегінің еруін азайту үшін", False)],
     "Таза су электр тогын нашар өткізеді; электролит иондары өткізгіштікті арттырады."),
    ("formula", "<p>Мырыш тұз қышқылымен әрекеттескенде түзілетін тұздың формуласын жазыңыз.</p>",
     ["ZnCl2"],
     "Мырыш хлориді — ZnCl₂."),
    ("equation", "<p>Сутегі пероксидінің MnO<sub>2</sub> қатысында ыдырау теңдеуін коэффициенттерімен жазыңыз.</p>",
     ["2H2O2 -> 2H2O + O2"],
     "2H₂O₂ → 2H₂O + O₂↑ (катализатор MnO₂)."),
]  # fmt: skip


def fill_quiz(quiz: Quiz, questions) -> None:
    if quiz.questions.exists():
        return
    for order, (kind, text, spec, explanation) in enumerate(questions, start=1):
        q = Question.objects.create(quiz=quiz, order=order, kind=kind, text=text, explanation=explanation)
        if kind in ("single", "multiple"):
            Choice.objects.bulk_create(
                Choice(question=q, order=i, text=t, is_correct=ok) for i, (t, ok) in enumerate(spec, start=1)
            )
        elif kind == "numeric":
            q.numeric_answer, q.numeric_tolerance = spec
            q.save(update_fields=["numeric_answer", "numeric_tolerance"])
        else:
            q.accepted_answers = spec
            q.save(update_fields=["accepted_answers"])


def checkpoint(title, questions, pass_percent=75) -> Quiz:
    quiz, _ = Quiz.objects.get_or_create(
        title=title,
        kind=Quiz.Kind.CHECKPOINT,
        defaults={"pass_percent": pass_percent, "max_attempts": 3, "show_answers_after": True, "instant_feedback": True},
    )
    fill_quiz(quiz, questions)
    return quiz


def topic_test(title, questions) -> Quiz:
    quiz, _ = Quiz.objects.get_or_create(
        title=title,
        kind=Quiz.Kind.TOPIC_TEST,
        defaults={"pass_percent": 60, "max_attempts": 2, "time_limit_min": 15, "shuffle_questions": True},
    )
    fill_quiz(quiz, questions)
    return quiz
