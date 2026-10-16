"""Create the course skeleton: 2 modules, 15 topics, topic 1 with its lab.

Course/module/topic texts are content (stored in the DB, in Kazakh) and are
placeholders until the author provides the final wording.
"""
from django.core.management.base import BaseCommand
from django.db import transaction

from apps.courses.models import Course, Module, Topic

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


class Command(BaseCommand):
    help = "Create the ChemEduTech course skeleton (idempotent)."

    @transaction.atomic
    def handle(self, *args, **options):
        course, _ = Course.objects.update_or_create(
            slug="chemistry",
            defaults={
                "title": "Химия: виртуалды зертханалық практикум",
                "description": "Болашақ химия мұғалімдеріне арналған онлайн курс: теория және виртуалды зертханалық жұмыстар.",
            },
        )
        m1, _ = Module.objects.update_or_create(course=course, number=1, defaults={"title": "1-модуль"})
        m2, _ = Module.objects.update_or_create(course=course, number=2, defaults={"title": "2-модуль"})

        for n in range(1, 16):
            module = m1 if n <= 8 else m2
            defaults = {"module": module, "title": f"{n}-тақырып", "is_published": False}
            if n == 1:
                defaults.update(
                    title="Сутегі және оттегі: алынуы және қасиеттері",
                    summary="Сутегі мен оттегіні зертханада алу, жинау, судың электролизі және катализатордың әсері.",
                    theory=THEORY_T1.strip(),
                    lab_key="t01",
                    is_published=True,
                )
            Topic.objects.update_or_create(module__course=course, number=n, defaults=defaults)

        self.stdout.write(self.style.SUCCESS("Course skeleton is ready: 2 modules, 15 topics (topic 1 published)."))
