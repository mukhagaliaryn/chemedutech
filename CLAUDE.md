# ChemEduTech — Claude Code notes

Doctoral dissertation (pedagogy) project: an LMS for future chemistry teachers with a 2D
virtual lab as the main product. The research log is the basis of the dissertation's
experimental chapter — never drop, rename or rewrite logged data (LabEvent, QuizAttempt,
AttemptAnswer) without an explicit migration plan agreed with the user.

**Read first:** `docs/ARCHITECTURE.md` (roles, models, gating, grading, technical decisions),
`docs/TASKS.md` (STEP plan). Work one STEP at a time.

**ICPAI programme (8 sections, STEP-28+):** `docs/icpai/SPEC.md` (models, 80% unlocking, AI modes, open questions)
and the author's guide `docs/icpai/source/guide.md` (text of `ICPAI_нұсқаулық.docx`; sections tagged `## [@S0-INTRO]`,
`## [@S1]` … `## [@S8]`; images in `docs/icpai/source/media/`). Content (texts, questions, answer keys, lesson templates,
field and button names) comes **verbatim from the guide** — never invent it. AI features go through `apps/ai` only;
the AI never writes a lesson stage, a reflection or a portfolio for the student (assistant → checker → expert roles).

**Design references** (ask the user for screenshots if you cannot open them):
- Design system (tokens, components): https://claude.ai/artifact/K8oYpbz6mGru4Z7E5Z11uj
- UI page mockups (student + teacher cabinets, lab, auth): https://claude.ai/artifact/R2Y3e5kNqsUNBn3Hnh9w5m

## Conventions
- Django 6, PostgreSQL, django-tailwind (`ui/` app, Tailwind 4), Alpine.js, HTMX, django-unfold, django-ckeditor-5.
- Font: Inter (Google Fonts). Colours/radii/shadows only from design tokens (`ui/static_src/src/styles.css` `@theme`).
- Layers: `core` → `accounts`, `organizations` → `courses`, `assessments`, `labs`, `ai` → `practice`, `progress`,
  `certificates`, `feedback`, `pedagogy` → `programme` → `student`, `teacher`, `research`. Lower layers never import higher ones.
- Each domain app: `models/` package (re-export in `__init__.py`), `services/` (writes), `selectors/` (reads),
  unfold `admin.py`. Views stay thin. Cross-app FKs as strings (`"courses.Topic"`).
- All source strings, `verbose_name`, `gettext_lazy` are **English**; kk (default) and ru via
  `makemessages -l kk -l ru` / `compilemessages`. Default language must be kk regardless of the browser's
  `Accept-Language` (see ARCHITECTURE §9.5).
- A topic's stages are an ordered list of any length and any mix of kinds (typically 1 theory, 1 video, 1 lab,
  several practice works, 1 test). Never assume a single stage of a kind; gating follows list order.
- Practice works are auto-graded: exact fields by checkers (`assessments/chem.py` for formulas/equations),
  open answers by AI (`practice/services/ai_grading.py`, Anthropic SDK) — the AI grade is final, a teacher may change it. Never compare answers 1:1 as raw strings.
  Tests must mock the Anthropic client — no network in tests.
- Reply to the user in Kazakh.

## Lab engine (code-based, keep as is unless asked)
- `apps/labs/engine/spec.py`: `LabSpec` → `ExperimentSpec` → `Item`, `Step`, `JournalField`, `Question`; registry in `engine/registry.py`.
- One experiment = `experiments/<lab>/<name>.py` + `ui/templates/labs/scenes/<scene>.html` + `ui/static/js/lab/experiments/<scene>.js`.
  Test-tube experiments use the shared scene `tubes` (no new JS): everything that happens is data in `params.ops` (see `tubes.js`).
- Journal fields: `text`, `number`, `choice`, `equation` (`answer=` checked on the server by `assessments.chem`, never sent to the browser).
- All templates live in `ui/templates/` (layouts/, components/, partials/, <app>/); components are documented in their
  header comments and shown at `/ui/styleguide/` (staff only). Icons: `{% include "components/icons.html#lock" %}`.
- `engine.js` (`Alpine.data("labRunner")`): step order, warnings, pointer drag & drop, journal, finish, analysis, batched event log.
- **Alpine `x-for`/`x-if` do not work inside `<svg>`** — use Django loops (`{% for i in 6|times %}`, `"0 10 20"|split`).
- Step kinds: `place`, `action`, `process` (scene calls `runner.processDone()`; may have items), `choice`, `journal`, `finish`;
  `Step.safety=True` logs a premature attempt as `safety_warning`.
- Score formula: `LabSpec.scoring = LabScoring(...)` → `apps/labs/scoring.py`; students run labs inside a course stage
  (`student:lab_run`, experiments open in order), `/labs/<lab>/<exp>/` is a teacher preview.

## Commands
`python manage.py test apps` · `python manage.py tailwind start|build` · `python manage.py seed_course` ·
`python manage.py makemessages -l kk -l ru --ignore=env --ignore="ui/static_src/*"` · `ruff check .`
