# ChemEduTech

Химиядан онлайн білім беру платформасы (LMS) және 2D виртуалды зертхана. Докторлық диссертациялық
жоба: болашақ химия мұғалімдеріне арналған курс, интерактивті зертханалық жұмыстар, AI бағалайтын
практикалық жұмыстар және педагогикалық экспериментке (бақылау / эксперименттік топ) арналған
зерттеу деректерін жинау.

**Стек:** Django 6, PostgreSQL, Tailwind CSS 4 (django-tailwind, `ui/` апп), Alpine.js, HTMX,
django-unfold (әкімші), django-ckeditor-5, django.tasks (фондық тапсырмалар), Anthropic Python SDK
(ашық жауаптарды бағалау), WeasyPrint (сертификат PDF). Интерфейс тілдері: қазақ (әдепкі), орыс, ағылшын.

Толық сипаттама — [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) (модельдер, оқу ағыны, бағалау,
шешімдер журналы D1–D50), жұмыс жоспары — [`docs/TASKS.md`](docs/TASKS.md).

## Рөлдер және беттер

| Рөл | Кабинет | Негізгі беттер |
|---|---|---|
| Студент (өзі тіркеледі) | `/me/` | басты бет, курс картасы, кезең ойнатқышы `/learn/…` (теория, видео, зертхана, практика, тест), бағалар кітапшасы, сертификаттар, профиль |
| Мұғалім (әкімші қосады) | `/teacher/` | басты бет, топтар мен студенттер, жұмыстарды тексеру, бағалар журналы (CSV/XLSX), курс мазмұнының редакторы, статистика, зерттеу деректері |
| Әкімші | `/admin/` | барлық модельдер (unfold), жалпы көрсеткіштер |
| Барлығы | — | хабарламалар `/notifications/`, сертификатты тексеру `/certificates/verify/<uuid>/` (логинсіз) |

Оқу ретпен жүреді: кезең → тақырып → модуль → курс (`apps/progress`). Ұпай — ҚР кредиттік
шкаласы бойынша (A … F, GPA). Курс өту ұпайымен аяқталса — сертификат (PDF + QR) автоматты беріледі.

## Әзірлеу ортасында іске қосу

```bash
python -m venv env && . env/bin/activate
pip install -r requirements/dev.txt                  # prod: requirements/base.txt
cp .env.example .env                                  # PostgreSQL параметрлері (немесе USE_SQLITE=1)
python manage.py migrate
python manage.py tailwind install && python manage.py tailwind build   # Node.js керек (ui/static_src)
python manage.py compilemessages --ignore=env --ignore=node_modules
python manage.py seed_course                          # курс қаңқасы: 1-тақырып, тесттер, практикалар
python manage.py createsuperuser                      # role=admin
python manage.py runserver
```

- CSS-ті әзірлеу кезінде: `python manage.py tailwind start`. Компоненттер үлгісі: `/ui/styleguide/` (тек әкімші).
- Alpine мен HTMX `ui/static/vendor/`-да (CDN-сіз); жаңарту: `cd ui/static_src && npm run vendor`.
- Dev-те фондық тапсырмалар (AI бағалау, PDF) бірден орындалады, email консольге шығады.

**Алғашқы деректер.** `seed_course` пайдаланушы жасамайды. Әкімшіде: Университет → Факультет →
Кафедра; мұғалімдерді «Пайдаланушылар → Қосу» арқылы қосып, курсқа «Курс мұғалімдері» ретінде
бекітіңіз (`author` — мазмұнды өңдейді, `assistant` — тек оқытады). Мұғалім өз кабинетінде топ
жасайды, оған зерттеу тобын (`control` / `experimental`) тағайындайды және курсқа бекітеді.
Студенттер `/accounts/signup/` бетінде тіркеледі (топты тізімнен таңдайды немесе қосылу кодын енгізеді).

## Production

`.env` (`config.settings.prod`):

| Айнымалы | Мәні |
|---|---|
| `DJANGO_SETTINGS_MODULE` | `config.settings.prod` |
| `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` | міндетті |
| `SITE_URL` | сайттың толық адресі — сертификат QR-коды осыған сілтейді |
| `POSTGRES_*` | дерекқор |
| `ANTHROPIC_API_KEY`, `AI_GRADING_ENABLED=1`, `AI_GRADING_MODEL` | ашық жауаптарды AI бағалауы (өшірулі болса — бірден мұғалім кезегіне) |
| `DJANGO_EMAIL_*` | құпиясөзді қалпына келтіру хаттары |
| `DJANGO_SECURE_HSTS_SECONDS` | HTTPS тұрақты жұмыс істейтіні расталғаннан кейін ғана қойыңыз (мыс. `31536000`) |

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py compilemessages --ignore=env --ignore=node_modules
python manage.py check --deploy
gunicorn config.wsgi                 # Nginx артында, HTTPS
python manage.py db_worker           # фондық тапсырмалар: AI бағалау, сертификат PDF (systemd қызметі)
```

- Сертификат PDF-і үшін серверде WeasyPrint жүйелік кітапханалары (Pango) және **қазақ әріптері бар
  қаріп** керек: `apt install fonts-dejavu-core` (немесе Inter қарпі).
- `media/` (CKEditor суреттері, практика файлдары, сертификаттар) — Nginx арқылы; `media/certificates/pdf/`
  тікелей берілмейді, PDF рұқсатпен `/certificates/<uuid>/pdf/` арқылы жүктеледі.

## Зерттеу деректері

- Зертхана: әр әрекет `LabEvent`-ке (seq, уақыт, түр, қадам, payload), талпыныс метрикалары `LabAttempt`-те.
  Зерттеу тобы жазылу сәтінде `Enrollment.research_cohort`-қа, талпыныс басталғанда `LabAttempt`-ке көшіріледі.
- Тест жауаптары, практика жауаптары, AI бағалары (`AIGrade`, толық жауабымен) және мұғалім тексерістері
  (`TeacherReview`) жойылмайды (PROTECT, әкімшіде тек оқу).
- `/teacher/analytics/<course>/` — бақылау және эксперименттік топтарды салыстыру (орташа, медиана, n),
  воронка, зертханадағы жиі қателер, қадамдағы уақыт, AI ↔ мұғалім сәйкестігі (Cohen's kappa, Pearson r),
  кездейсоқ іріктеп тексеру; студенттер бойынша CSV.
- `/teacher/research/` — CSV экспорттар (UTF-8 BOM): `attempts`, `events`, `quiz_answers`, `ai_reviews`.
  Мұғалім өз курстарының деректерін, әкімші — бәрін көреді.

Маңыздылық тесттерін (t-тест, Манн–Уитни) экспортталған деректер бойынша статистикалық бағдарламада есептеңіз.

## Архитектура қысқаша

```
apps/
  core          — middleware (тіл: әрқашан алдымен қазақша), рұқсаттар, HTML санитизация, xlsx, статистика
  accounts      — User (role: admin / teacher / student), тіркелу, профиль
  organizations — университет → факультет → кафедра → топ, студент/мұғалім профилі
  courses       — курс → модуль → тақырып → кезең, контент, жазылу, топ сервистері, авторлық сервистер
  assessments   — тесттер, chem.py (формула мен теңдеу талдағышы)
  labs          — зертхана қозғалтқышы (кодпен жазылған тәжірибелер), талпыныстар мен оқиғалар логы
  practice      — практикалық жұмыстар: тексергіштер, AI бағалау, мұғалім тексерісі, іріктеме
  progress      — кезең ашылуы және бағалау қозғалтқышы, ҚР шкаласы
  feedback      — хабарламалар, пікірлер
  certificates  — сертификат, PDF, тексеру беті
  student / teacher / research — өнім қабаты: беттер мен экспорттар
ui/             — барлық шаблондар, статика, Tailwind (дизайн токендері)
```

Ереже: жазу — `services/`, оқу — `selectors/`, views жұқа; төменгі қабат жоғарғыны импорттамайды.

## Жаңа тәжірибе қосу

Әр тәжірибе — үш файл:

| Файл | Мазмұны |
|---|---|
| `apps/labs/experiments/<lab>/<name>.py` | `ExperimentSpec`: құралдар, командалар реті, ескертулер, журнал, талдау сұрақтары, физикалық параметрлер |
| `ui/templates/labs/scenes/<name>.html` | 2D SVG жұмыс үстелі |
| `ui/static/js/lab/experiments/<name>.js` | Анимация және физикалық модель (`ChemLab.scene(...)`) |

Жалпы логика (рет, ескертулер, журнал, логтау) — `ui/static/js/lab/engine.js`. Ұпай формуласы —
`LabSpec.scoring` (`apps/labs/scoring.py`). Мұғалім курс редакторында кезеңге зертхана мен оның
тәжірибелерін таңдайды.

## Аудармалар

Барлық мәтін кодта ағылшынша (`gettext_lazy`, `{% translate %}`); курс мазмұны дерекқорда қазақша.

```bash
python manage.py makemessages -l kk -l ru --ignore=env --ignore="ui/static_src/*" --ignore=node_modules
# locale/*/LC_MESSAGES/django.po аудару
python manage.py compilemessages --ignore=env --ignore=node_modules
```

## Тексерулер

```bash
python manage.py test apps ui          # Anthropic клиенті тесттерде әрқашан fake — желіге шықпайды
python manage.py makemigrations --check --dry-run
ruff check . && ruff format --check .  # зертхана симуляторы файлдары formatter-ден шығарылған
```
