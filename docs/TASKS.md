# ChemEduTech — жұмыс жоспары (STEP-тер)

Әр STEP — бөлек сессия/коммит. Бастамас бұрын `docs/ARCHITECTURE.md` және `CLAUDE.md` оқылады.
Әр STEP соңында: `python manage.py check`, тесттер, `makemigrations --check`, `ruff`, қысқа есеп
(не жасалды, қандай шешім қабылданды, не қалды). Келісілмеген архитектуралық өзгеріс болса —
алдымен сұра.

> **Маңызды:** прототипте өндірістік дерек жоқ. Модельдер түбегейлі өзгергендіктен
> миграцияларды нөлден қайта жасауға болады (STEP-03-те).

---

## STEP-00 · Бастапқы күй
- [x] `git init`, `.gitignore` тексеру, бастапқы коммит («prototype»).
- [x] Қазіргі тесттерді іске қосу (`python manage.py test apps`) — 6 тест өтуі керек.
- [x] `docs/` құжаттарын оқып, түсініксіз жерлерді тізіп шық (код жазбай).

## STEP-01 · Тәуелділіктер, settings, тіл
- [x] `requirements/` (`base.txt`, `dev.txt`): `Django>=6.0,<6.1`, `psycopg[binary]`, `django-unfold`, `django-ckeditor-5`,
      `django-tailwind`, `django-browser-reload` (dev), `django-htmx`, `nh3`, `python-dotenv`, `weasyprint`, `qrcode`,
      `anthropic`, `django-tasks`, `pytest-django`, `ruff`. `.env.example`-ге `ANTHROPIC_API_KEY`, `AI_GRADING_MODEL`, `AI_GRADING_ENABLED` қосу.
- [x] `config/settings/{base,dev,prod}.py`; `DJANGO_SETTINGS_MODULE` default — `config.settings.dev`.
- [x] `apps/core/middleware.py` → `KazakhFirstLocaleMiddleware` (ARCHITECTURE §9.5); `LocaleMiddleware`-ді алмастыру.
- [x] Тест: `Accept-Language: ru,en` + cookie жоқ → `<html lang="kk">` және қазақша мәтін; cookie `ru` → орысша.
- **Қабылдау шарты:** браузер тілі қандай болса да, бірінші кіргенде платформа қазақша.

## STEP-02 · `ui/` апп (django-tailwind) және дизайн жүйесі
- [x] `python manage.py tailwind init` → `ui` (Tailwind v4). `TAILWIND_APP_NAME="ui"`.
- [x] Түбірдегі `templates/` → `ui/templates/`, `static/` → `ui/static/`, апптардағы шаблондар → `ui/templates/<app>/`.
      `static/src/app.css` токендері → `ui/static_src/src/styles.css`. Түбірдегі `package.json`, `node_modules` жойылады.
- [x] Шрифт: Golos (self-hosted) → **Inter (Google Fonts)**. `static/fonts/` жойылады.
- [x] Дизайн токендері: ARCHITECTURE §10 + «ChemEduTech Design System» артефакты (түстер, радиус, көлеңке, типография шкаласы).
- [x] Layout-тар: `layouts/public.html`, `layouts/student.html` (сол жақ навигация + жоғарғы панель), `layouts/teacher.html`.
- [x] Компоненттер: `components/` (button, input, select, card, badge, progress_bar, stat_card, table, empty_state, modal, toast, avatar, stage_stepper, lock_state).
- [x] Зертхана беті жаңа токендерге көшеді, бірақ **симулятор логикасы мен сахналар өзгермейді** (тек түстер/шрифт).
- **Қабылдау шарты:** `python manage.py tailwind build` жұмыс істейді; 4 тәжірибе бұрынғыдай өтеді; барлық беттер Inter-мен.

## STEP-03 · accounts + organizations
- [x] `User`: `role` (admin/teacher/student), unique email (case-insensitive), `middle_name`, `phone`, `avatar`, `language`.
      Ескі `researcher` рөлі және `User.cohort` жойылады (cohort → AcademicGroup/Enrollment).
- [x] `UsernameOrEmailBackend`; логин формасында бір өріс «Логин немесе email».
- [x] `organizations`: University, Faculty, Department, Specialty, AcademicGroup (`join_code`, `research_cohort`, `curator`), StudentProfile, TeacherProfile.
- [x] Тіркелу (тек студент): HTMX каскадты select (университет → факультет → кафедра → топ) немесе топ коды.
- [x] Логиннен кейін рөл бойынша бағыттау; `core/permissions.py` mixin-дері.
- [x] Unfold админ: User (мұғалім қосу формасы — role=teacher, TeacherProfile inline), ұйымдар (иерархиялық inlines, сүзгілер).
- [x] Миграцияларды нөлден қайта жасау.
- [x] Тесттер: email/username логин, тіркелу тек student жасайды, teacher-ді өздігінен тіркеу мүмкін емес, каскадты select.

## STEP-04 · courses: курс құрылымы және контент
- [x] Course (+ `stage_kind_weights`), CourseTeacher, CourseGroup, Enrollment, Module, Topic, Stage + TheoryContent, VideoContent, LabContent, TestContent (ARCHITECTURE §3.3).
      Практика контенті (PracticeTask/Item) — STEP-07a-да.
- [x] **Икемділік:** тақырыпта кез келген түрдің кез келген саны (бірнеше практика, 2 теория т.б.) — кодта «жалғыз теория» деген болжам болмасын (§3.3 Икемділік ережесі).
- [x] `django-ckeditor-5` баптау (`default`, `compact` конфигтері, sub/sup), жүктеу рұқсаты мұғалімге; `nh3` санитизация фильтрі.
- [x] Unfold админ: Course → Module (inline) → Topic → Stage (inline, сұрыптау), контент модельдері.
- [x] Жазылу сервисі: `enroll(student, course, source)`; CourseGroup жасалғанда топ студенттері жазылады.
- [x] `seed_course` командасын жаңа құрылымға көшіру: 1-тақырып → кезеңдер: Теория (+бекіту тесті), Видео (+бекіту тесті), Зертхана (t01),
      Практикалық жұмыс 1, Практикалық жұмыс 2, Тақырып тесті (практикалардың мазмұны STEP-07a-да толтырылады).

## STEP-05 · assessments: тесттер
- [x] Quiz, Question, Choice, QuizAttempt, AttemptAnswer (§3.4).
- [x] Сервистер: `start_attempt` (сұрақ пулынан таңдау, араластыру), `submit_attempt` (автобағалау: single/multiple/numeric/short_text), `max_attempts`, `grading=best|last|first`.
- [x] Тест тапсыру UI (Alpine): бір бетте немесе сұрақ-сұрақпен, таймер (`time_limit_min`), нәтиже + түсіндірмелер.
- [x] Тесттер: әр сұрақ түрін бағалау, талпыныс шегі, пул таңдау.

## STEP-05a · `assessments/chem.py`: химиялық формула мен теңдеу талдағышы
- [x] Формуланы талдау (жақшалар, гидраттар `·`, иондар мен заряд, unicode `₂ ⁺`), теңдеуді талдау (`=`, `->`, `→`, `⇌`, `↑↓`), теңестірілуін тексеру.
- [x] Салыстыру: заттар жиыны + коэффициенттер (рет маңызды емес), көбейтілген коэффициенттер (`4H2 + 2O2 → 4H2O`) — бөлек белгі «теңестірілген, бірақ қысқартылмаған».
- [x] Кемінде 40 юнит-тест (1-тақырыптың барлық теңдеулері кіреді).
- [x] `Question.kind`-ке `formula`, `equation` қосу.

## STEP-06 · progress: gating және бағалау қозғалтқышы  ⭐ ең маңызды
- [x] StageProgress, TopicResult, ModuleResult, CourseResult, GradeScale (§3.7).
- [x] `progress.services` (§4): `ensure_progress`, `can_access`, `start_stage`, `complete_stage`, `recalculate`, `unlock_stage`.
- [x] Ұпай есептеу (§5): кезең → тақырып → модуль → курс, салмақтармен; түр үлесін бір түрдегі кезеңдер арасында бөлу және жоқ түрлерді нормалау (§5.2); ағымдағы vs қорытынды.
- [x] Тесттер (кемінде 15): ретпен ашылу, URL арқылы айналып өту мүмкін еместігі, бекіту тестінен өтпесе кезең жабық қалуы,
      практиканы мұғалім қайтарғанда күйдің өзгеруі, салмақты орташа, әріптік баға, курс аяқталғанда CourseResult,
      **бір тақырыпта 3 практика** (әрқайсысы ретпен ашылуы, салмақ бөлінуі), видеосыз тақырып (нормалау),
      `needs_review` практикадан кейін келесі кезең ашылып, тақырып аяқталмауы.

## STEP-07 · Студенттің оқу ойнатқышы
- [x] `/me/courses/<slug>/` курс картасы (құлып/ашық/аяқталды, ұпайлар).
- [x] `/learn/<course>/<topic>/` кезеңдер степпері; `/learn/.../<stage>/` — kind бойынша шаблон:
      теория (оқыдым → бекіту тесті), видео (YouTube/файл, көру пайызын бақылау → бекіту тесті), тест;
      практика беті — STEP-07a.
- [x] Степпер кезеңдер санына тәуелсіз (5-тен 10-ға дейін; көп болса көлденең айналдыру/мобильде тізім).
- [x] Құлыпталған кезеңге кірсе — «алдымен … аяқтаңыз» беті (келесі әрекетке сілтемемен).

## STEP-07a · Практикалық жұмыстар: автоматты және AI бағалау
- [ ] Модельдер: PracticeTask, PracticeItem, PracticeSubmission, PracticeAnswer, GradingRubric, RubricCriterion, AIGrade, TeacherReview (§3.6, §5.5, §5.6).
- [ ] Тексергіштер: `numeric` (ауытқу, бірлік түрлендіру), `formula`/`equation` (STEP-05a), `text_short` (қалыпқа келтіру + Левенштейн), `choice`/`blank`, `matching`/`ordering` (жартылай ұпай).
- [ ] AI бағалау: `practice/services/ai_grading.py` — Anthropic SDK, structured output (JSON schema), промпт нұсқасы, студент жауабын бөлек блокта беру (prompt injection-ға қарсы), 2 рет қайталау, `needs_review`.
      Фондық тапсырма: `django.tasks` (`django-tasks` DatabaseBackend; dev — ImmediateBackend).
- [ ] Студент беті: есептің шарты + өрістер, химиялық пернетақта (`₂ ₃ ⁺ ⁻ → ↑ ↓ ⇌`) + жанды көрініс, «Бағалануда…» күйі (HTMX polling), нәтиже: әр өріс бойынша ✓/✗, AI кері байланысы, қайта жіберу (`max_attempts`).
- [ ] Unfold админ + мұғалім редакторы: өрістер мен критерийлерді қосу (inline), «Тексеріп көру» батырмасы — автор үлгі жауапты енгізіп, бағалауды сынайды.
- [ ] Тесттер: әр тексергіш, AI клиенті mock-пен (сәтті, тайм-аут, low confidence, жарамсыз JSON), injection мәтіні ұпайды өзгертпейтіні.

## STEP-08 · Зертхананы оқу ағынына қосу
- [ ] `LabContent` кезеңінен зертхана ашылады; `LabAttempt.enrollment/stage` толтырылады; `research_cohort` Enrollment-тен.
- [ ] Зертхана ішіндегі тәжірибелер де ретпен ашылады.
- [ ] Зертхана ұпайы (§5.4) → барлық тәжірибе аяқталса `complete_stage`.
- [ ] Зертхана бетіндегі «Тақырыпқа оралу»/«Келесі тәжірибе» сілтемелері жаңа маршруттарға.
- [ ] Бар тесттер өтуі + жаңа: зертхана кезеңін аяқтау.

## STEP-09 · Студент кабинеті
- [ ] `/me/` dashboard, `/me/results/` бағалар кітапшасы, `/me/certificates/`, `/me/profile/` (дизайн — артефакттағы макеттер).
- [ ] Хабарламалар (Notification) навбарда.

## STEP-10 · Мұғалім кабинеті: топтар мен студенттер
- [ ] `/teacher/` dashboard, `/teacher/groups/` (CRUD, қосылу коды, студенттерді қосу/шығару, курсқа бекіту, research_cohort),
      `/teacher/students/<id>/` (уақыт сызығы, ұпайлар, зертхана логы, тест талпыныстары, кезеңді қолмен ашу).
- [ ] Мұғалім тек өз курстары мен топтарын көреді (selectors-та сүзу + тест).

## STEP-11 · Мұғалім: мазмұн басқару, тексеру, кері байланыс
- [ ] `/teacher/courses/<slug>/`: модуль/тақырып/кезең CRUD, сұрыптау (drag), CKEditor 5, тест редакторы, зертханаға `lab_key` таңдау.
- [ ] `/teacher/grading/` — `needs_review` кезегі, AI ұсынған бағаны критерийлер бойынша **растау/өзгерту** (TeacherReview), қайтару; Comment (тред) және Notification.
- [ ] `/teacher/gradebook/<course>/` матрица + CSV/XLSX экспорт.

## STEP-12 · Статистика және зерттеу
- [ ] `/teacher/analytics/<course>/`: аяқтау воронкасы, тақырып бойынша орташа ұпай, зертханадағы жиі қателер (қадам бойынша), қадамдағы орташа уақыт,
      **control vs experimental** салыстыру (орташа, медиана, n);
      **AI ↔ мұғалім бағасының сәйкестігі** (Cohen's kappa, корреляция, орташа айырма) және кездейсоқ 10–15% жұмысты тексеруге белгілеу.
- [ ] `/teacher/research/` — қазіргі research апп осында көшеді; экспорт: attempts, events, quiz answers (CSV, UTF-8 BOM).

## STEP-13 · Сертификаттар
- [ ] CertificateTemplate, Certificate (§7), WeasyPrint PDF, QR, `/certificates/verify/<uuid>/`.
- [ ] CourseResult.passed → автоматты шығару + Notification.

## STEP-14 · Админ және жылтырату
- [ ] Unfold: `UNFOLD` баптаулары (түстер — дизайн жүйесінен), бүйір навигация, `DASHBOARD_CALLBACK` (жалпы сандар).
- [ ] i18n: `makemessages -l kk -l ru`, барлық жаңа жолдарды аудару, `compilemessages`.
- [ ] Қауіпсіздік: рұқсат тесттері (студент `/teacher/`-ге кіре алмайды т.б.), CKEditor HTML санитизациясы.
- [ ] README жаңарту.
