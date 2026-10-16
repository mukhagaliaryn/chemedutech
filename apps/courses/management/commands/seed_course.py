"""Create the course skeleton: 2 modules, 15 topics; topic 1 with its stages.

Course/module/topic texts are content (stored in the DB, in Kazakh) and are
placeholders until the author provides the final wording. Practice tasks are added in STEP-07a.
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.courses.models import Course, Module, Stage, Topic
from apps.courses.services import ensure_stage_content

from ._seed_quizzes import THEORY_CHECKPOINT, TOPIC_TEST, VIDEO_CHECKPOINT, checkpoint, topic_test

THEORY_T1 = """
<h2>Сутегі</h2>
<p>Сутегі — ең жеңіл газ, түссіз, иіссіз, суда нашар ериді. Зертханада сутегіні
белсенді металдарды (мырыш, темір) тұз қышқылымен немесе сұйылтылған күкірт
қышқылымен әрекеттестіріп алады.</p>
<span class="formula">Zn + 2HCl → ZnCl<sub>2</sub> + H<sub>2</sub>↑</span>
<p>Сутегі суда нашар еритіндіктен, оны суды ығыстыру әдісімен жинайды. Ауаны
ығыстыру арқылы жинағанда ыдысты төңкеріп ұстайды, себебі сутегі ауадан жеңіл.</p>
<h3>Қауіпсіздік</h3>
<ul>
  <li>Сутегінің ауамен қоспасы жарылғыш («күркіреуік газ»).</li>
  <li>Сутегіні тұтатпас бұрын міндетті түрде тазалығын тексереді: таза сутегі
  тыныш «пах» дыбысымен жанады.</li>
</ul>
<h2>Оттегі</h2>
<p>Зертханада оттегіні сутегі пероксидін марганец(IV) оксиді катализаторы
қатысында ыдыратып алады.</p>
<span class="formula">2H<sub>2</sub>O<sub>2</sub> → 2H<sub>2</sub>O + O<sub>2</sub>↑ (MnO<sub>2</sub>)</span>
<p>Катализатор реакция жылдамдығын арттырады, бірақ реакция соңында өзгеріссіз
қалады және түзілетін өнімнің жалпы мөлшерін өзгертпейді. Оттегіні бықсып
тұрған шамшырақпен анықтайды: шамшырақ лап етіп жанады.</p>
<h2>Судың электролизі</h2>
<p>Тұрақты ток әсерінен су сутегі мен оттегіге ыдырайды. Катодта сутегі,
анодта оттегі бөлінеді, олардың көлемдерінің қатынасы 2 : 1.</p>
<span class="formula">2H<sub>2</sub>O → 2H<sub>2</sub>↑ + O<sub>2</sub>↑</span>
"""


# Topic 1: a typical topic — the stage list is data, any length and mix of kinds is allowed.
T1_STAGES = [
    (Stage.Kind.THEORY, "Теория. Сутегі мен оттегінің алынуы және қасиеттері", {"body": THEORY_T1.strip()}),
    (Stage.Kind.VIDEO, "Видеосабақ. Сутегі мен оттегіні зертханада алу", {}),
    (Stage.Kind.LAB, "Зертханалық жұмыс. Сутегі және оттегі", {"lab_key": "t01"}),
    (Stage.Kind.PRACTICE, "Практикалық жұмыс 1. Сутегінің көлемін есептеу", {}),
    (Stage.Kind.PRACTICE, "Практикалық жұмыс 2. Оттегінің массасын есептеу", {}),
    (Stage.Kind.TEST, "Тақырып тесті", {}),
]


class Command(BaseCommand):
    help = "Create the ChemEduTech course skeleton (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        course, _ = Course.objects.update_or_create(
            slug="chemistry",
            defaults={
                "title": "Химия: виртуалды зертханалық практикум",
                "short_description": "Болашақ химия мұғалімдеріне арналған онлайн курс: теория және виртуалды зертханалық жұмыстар.",
                "status": Course.Status.PUBLISHED,
                "enrollment_mode": Course.EnrollmentMode.OPEN,
            },
        )
        m1, _ = Module.objects.update_or_create(course=course, order=1, defaults={"title": "1-модуль"})
        m2, _ = Module.objects.update_or_create(course=course, order=2, defaults={"title": "2-модуль"})

        for n in range(1, 16):
            module = m1 if n <= 8 else m2
            defaults = {
                "module": module,
                "order": n if n <= 8 else n - 8,
                "title": f"{n}-тақырып",
                "is_published": False,
            }
            if n == 1:
                defaults.update(
                    title="Сутегі және оттегі: алынуы және қасиеттері",
                    summary="Сутегі мен оттегіні зертханада алу, жинау, судың электролизі және катализатордың әсері.",
                    estimated_minutes=180,
                    is_published=True,
                )
            topic, _ = Topic.objects.update_or_create(module__course=course, number=n, defaults=defaults)
            if n == 1:
                for order, (kind, title, content) in enumerate(T1_STAGES, start=1):
                    stage, _ = Stage.objects.update_or_create(
                        topic=topic, order=order, defaults={"kind": kind, "title": title}
                    )
                    ensure_stage_content(stage, **content)
                self._seed_t1_quizzes(topic)

        self.stdout.write(
            self.style.SUCCESS(
                "Course skeleton is ready: 2 modules, 15 topics (topic 1 published, 6 stages, 3 quizzes)."
            )
        )

    def _seed_t1_quizzes(self, topic):
        stages = {}
        for s in topic.stages.order_by("order"):
            stages.setdefault(s.kind, s)  # the first stage of each kind
        for kind, title, questions in (
            (Stage.Kind.THEORY, "1-тақырып. Теорияның бекіту тесті", THEORY_CHECKPOINT),
            (Stage.Kind.VIDEO, "1-тақырып. Видеосабақтың бекіту тесті", VIDEO_CHECKPOINT),
        ):
            stage = stages[kind]
            if stage.checkpoint_quiz_id is None:
                stage.checkpoint_quiz = checkpoint(title, questions)
                stage.save(update_fields=["checkpoint_quiz", "updated_at"])
        test = stages[Stage.Kind.TEST].test_content
        if test.quiz_id is None:
            test.quiz = topic_test("1-тақырып тесті", TOPIC_TEST)
            test.save(update_fields=["quiz", "updated_at"])
