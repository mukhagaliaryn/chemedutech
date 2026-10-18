"""ChemEduTech — settings shared by every environment.

Secrets and environment-specific values come from environment variables
(see .env.example). Nothing secret is hardcoded here. Environment modules:
``config.settings.dev`` (default for manage.py) and ``config.settings.prod``.
"""

import os
from pathlib import Path

from django.urls import reverse_lazy
from django.utils.translation import gettext_lazy as _

BASE_DIR = Path(__file__).resolve().parent.parent.parent

try:  # optional .env support
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:  # pragma: no cover
    pass


def env_bool(name, default=False):
    return os.environ.get(name, str(default)).lower() in {"1", "true", "yes", "on"}


def env_list(name, default=""):
    return [v.strip() for v in os.environ.get(name, default).split(",") if v.strip()]


SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "")
DEBUG = False
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS")
CSRF_TRUSTED_ORIGINS = env_list("DJANGO_CSRF_TRUSTED_ORIGINS")

INSTALLED_APPS = [
    # django-unfold must come before django.contrib.admin
    "unfold",
    "unfold.contrib.filters",
    "unfold.contrib.forms",
    "unfold.contrib.inlines",
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # third-party
    "tailwind",
    "django_htmx",
    "django_ckeditor_5",
    "django_tasks_db",
    # project apps (layered: core → accounts/courses → labs → research)
    "apps.core",
    "apps.accounts",
    "apps.organizations",
    "apps.courses",
    "apps.assessments",
    "apps.labs",
    "apps.progress",
    "apps.practice",
    "apps.feedback",
    "apps.certificates",
    # product layer: views and URLs only
    "apps.student",
    "apps.teacher",
    "apps.research",
    # presentation: every template and static file lives here (django-tailwind theme app)
    "ui",
]

TAILWIND_APP_NAME = "ui"

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    # Replaces django.middleware.locale.LocaleMiddleware: needs request.user,
    # ignores Accept-Language (ARCHITECTURE §9.5).
    "apps.core.middleware.KazakhFirstLocaleMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django_htmx.middleware.HtmxMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

# Django's default «same-origin» sends no Referer to other sites; embedded YouTube players then refuse to
# play («Video unavailable», error 153). The browser default sends only the origin cross-site — no paths.
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "builtins": ["apps.core.templatetags.lab_tags", "ui.templatetags.ui_tags"],
            "context_processors": [
                "django.template.context_processors.request",
                "django.template.context_processors.i18n",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "chemedutech"),
        "USER": os.environ.get("POSTGRES_USER", "chem"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", "chem"),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

AUTH_USER_MODEL = "accounts.User"
AUTHENTICATION_BACKENDS = ["apps.accounts.backends.UsernameOrEmailBackend"]
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "core:home"  # core:home sends a signed-in user to the cabinet of their role
LOGOUT_REDIRECT_URL = "core:home"

EMAIL_BACKEND = os.environ.get("DJANGO_EMAIL_BACKEND", "django.core.mail.backends.smtp.EmailBackend")
EMAIL_HOST = os.environ.get("DJANGO_EMAIL_HOST", "localhost")
EMAIL_PORT = int(os.environ.get("DJANGO_EMAIL_PORT", "25"))
EMAIL_HOST_USER = os.environ.get("DJANGO_EMAIL_HOST_USER", "")
EMAIL_HOST_PASSWORD = os.environ.get("DJANGO_EMAIL_HOST_PASSWORD", "")
EMAIL_USE_TLS = env_bool("DJANGO_EMAIL_USE_TLS", False)
DEFAULT_FROM_EMAIL = os.environ.get("DJANGO_DEFAULT_FROM_EMAIL", "ChemEduTech <noreply@localhost>")

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
]

# --- Internationalisation -------------------------------------------------
# Source strings are written in English; kk (default) and ru come from
# locale/*.po via `compilemessages`. The interface language is chosen by
# apps.core.middleware.KazakhFirstLocaleMiddleware, never by Accept-Language.
LANGUAGE_CODE = "kk"
LANGUAGES = [
    ("kk", _("Kazakh")),
    ("ru", _("Russian")),
    ("en", _("English")),
]
LOCALE_PATHS = [BASE_DIR / "locale"]
USE_I18N = True
TIME_ZONE = "Asia/Almaty"
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- Rich text: django-ckeditor-5 (ARCHITECTURE §9.2) ----------------------
# Uploads go through apps.core.uploads.ckeditor_upload (teachers and admins); the package's own URL
# is not included. Output is sanitised with apps.core.html.clean_html (|sanitize filter).
CK_EDITOR_5_UPLOAD_FILE_VIEW_NAME = "ckeditor_upload"
CKEDITOR_5_FILE_UPLOAD_PERMISSION = "any"  # checked by our view
CKEDITOR_5_FILE_STORAGE = "apps.core.uploads.CKEditorStorage"
CKEDITOR_5_UPLOAD_FILE_TYPES = ["jpeg", "png", "gif", "webp"]
CKEDITOR_5_MAX_FILE_SIZE = 5  # MB
_CK_SPECIAL = ["specialCharacters"]
CKEDITOR_5_CONFIGS = {
    "default": {  # theory, descriptions
        "toolbar": {
            "items": [
                "heading",
                "style",
                "|",
                "bold",
                "italic",
                "link",
                "subscript",
                "superscript",
                *_CK_SPECIAL,
                "|",
                "bulletedList",
                "numberedList",
                "blockQuote",
                "|",
                "imageUpload",
                "mediaEmbed",
                "insertTable",
                "|",
                "undo",
                "redo",
                "sourceEditing",
            ],  # fmt: skip
            "shouldNotGroupWhenFull": True,
        },
        "heading": {
            "options": [
                {"model": "paragraph", "title": "Paragraph", "class": "ck-heading_paragraph"},
                {"model": "heading2", "view": "h2", "title": "Heading 2", "class": "ck-heading_heading2"},
                {"model": "heading3", "view": "h3", "title": "Heading 3", "class": "ck-heading_heading3"},
            ]
        },
        "image": {"toolbar": ["imageTextAlternative", "|", "imageStyle:alignLeft", "imageStyle:alignCenter"]},
        "table": {"contentToolbar": ["tableColumn", "tableRow", "mergeTableCells"]},
        "mediaEmbed": {"previewsInData": False},
        # Theory markup (ARCHITECTURE §9.2): formula lines, note boxes, figures and cards keep their classes
        # when a teacher edits the text; the classes are styled by .prose-theory in styles.css.
        "htmlSupport": {
            "allow": [{"name": "/^(p|div|span|figure|figcaption|img|table)$/", "classes": True}],
        },
        "style": {
            "definitions": [
                {"name": "Formula", "element": "p", "classes": ["formula"]},
                {"name": "Note", "element": "p", "classes": ["note"]},
                {"name": "Task", "element": "p", "classes": ["note", "note-task"]},
            ]
        },
    },
    "compact": {  # teacher's short texts: question, option, explanation, prompt, hint — formulas need sub/sup
        "toolbar": {"items": ["bold", "italic", "subscript", "superscript", *_CK_SPECIAL, "|", "undo", "redo"]},
    },
    "answer": {  # student's free-text answers (practice, lab journal and analysis)
        "toolbar": {
            "items": [
                "bold", "italic", "subscript", "superscript", *_CK_SPECIAL, "|", "bulletedList", "numberedList",
                "|", "undo", "redo",
            ],  # fmt: skip
        },
    },
}
# Configs the pages create editors from in JS (ui/static/js/richtext.js, {% rich_text_assets %}).
RICH_TEXT_CONFIGS = ("compact", "answer")

# --- Admin (django-unfold); full navigation/dashboard in STEP-14 ----------
UNFOLD = {
    "SITE_TITLE": "ChemEduTech",
    "SITE_HEADER": "ChemEduTech",
    "SITE_SYMBOL": "science",
    "SITE_URL": "/",
    "DASHBOARD_CALLBACK": "apps.research.admin_dashboard.dashboard_callback",
    "SIDEBAR": {
        "show_search": True,
        "show_all_applications": True,
        "navigation": [
            {
                "title": _("Users"),
                "separator": True,
                "items": [
                    {"title": _("Users"), "icon": "person", "link": reverse_lazy("admin:accounts_user_changelist")},
                    {
                        "title": _("Student profiles"),
                        "icon": "school",
                        "link": reverse_lazy("admin:organizations_studentprofile_changelist"),
                    },
                    {
                        "title": _("Teacher profiles"),
                        "icon": "badge",
                        "link": reverse_lazy("admin:organizations_teacherprofile_changelist"),
                    },
                ],
            },
            {
                "title": _("Organisations"),
                "separator": True,
                "items": [
                    {
                        "title": _("Universities"),
                        "icon": "account_balance",
                        "link": reverse_lazy("admin:organizations_university_changelist"),
                    },
                    {
                        "title": _("Faculties"),
                        "icon": "domain",
                        "link": reverse_lazy("admin:organizations_faculty_changelist"),
                    },
                    {
                        "title": _("Departments"),
                        "icon": "apartment",
                        "link": reverse_lazy("admin:organizations_department_changelist"),
                    },
                    {
                        "title": _("Specialties"),
                        "icon": "menu_book",
                        "link": reverse_lazy("admin:organizations_specialty_changelist"),
                    },
                    {
                        "title": _("Academic groups"),
                        "icon": "groups",
                        "link": reverse_lazy("admin:organizations_academicgroup_changelist"),
                    },
                ],
            },
            {
                "title": _("Courses"),
                "separator": True,
                "items": [
                    {
                        "title": _("Courses"),
                        "icon": "library_books",
                        "link": reverse_lazy("admin:courses_course_changelist"),
                    },
                    {
                        "title": _("Modules"),
                        "icon": "view_module",
                        "link": reverse_lazy("admin:courses_module_changelist"),
                    },
                    {"title": _("Topics"), "icon": "topic", "link": reverse_lazy("admin:courses_topic_changelist")},
                    {
                        "title": _("Stages"),
                        "icon": "format_list_numbered",
                        "link": reverse_lazy("admin:courses_stage_changelist"),
                    },
                    {
                        "title": _("Enrolments"),
                        "icon": "how_to_reg",
                        "link": reverse_lazy("admin:courses_enrollment_changelist"),
                    },
                    {
                        "title": _("Course groups"),
                        "icon": "group_work",
                        "link": reverse_lazy("admin:courses_coursegroup_changelist"),
                    },
                ],
            },
            {
                "title": _("Assessment"),
                "separator": True,
                "items": [
                    {"title": _("Quizzes"), "icon": "quiz", "link": reverse_lazy("admin:assessments_quiz_changelist")},
                    {
                        "title": _("Quiz attempts"),
                        "icon": "fact_check",
                        "link": reverse_lazy("admin:assessments_quizattempt_changelist"),
                    },
                    {
                        "title": _("Practice tasks"),
                        "icon": "edit_note",
                        "link": reverse_lazy("admin:practice_practicetask_changelist"),
                    },
                    {
                        "title": _("Practice submissions"),
                        "icon": "assignment_turned_in",
                        "link": reverse_lazy("admin:practice_practicesubmission_changelist"),
                    },
                    {
                        "title": _("AI grades"),
                        "icon": "smart_toy",
                        "link": reverse_lazy("admin:practice_aigrade_changelist"),
                    },
                    {
                        "title": _("Teacher reviews"),
                        "icon": "rate_review",
                        "link": reverse_lazy("admin:practice_teacherreview_changelist"),
                    },
                    {
                        "title": _("Stage progress"),
                        "icon": "timeline",
                        "link": reverse_lazy("admin:progress_stageprogress_changelist"),
                    },
                    {
                        "title": _("Course results"),
                        "icon": "grade",
                        "link": reverse_lazy("admin:progress_courseresult_changelist"),
                    },
                ],
            },
            {
                "title": _("Lab"),
                "separator": True,
                "items": [
                    {
                        "title": _("Lab attempts"),
                        "icon": "science",
                        "link": reverse_lazy("admin:labs_labattempt_changelist"),
                    },
                ],
            },
            {
                "title": _("Certificates and feedback"),
                "separator": True,
                "items": [
                    {
                        "title": _("Certificates"),
                        "icon": "workspace_premium",
                        "link": reverse_lazy("admin:certificates_certificate_changelist"),
                    },
                    {
                        "title": _("Certificate templates"),
                        "icon": "design_services",
                        "link": reverse_lazy("admin:certificates_certificatetemplate_changelist"),
                    },
                    {
                        "title": _("Comments"),
                        "icon": "forum",
                        "link": reverse_lazy("admin:feedback_comment_changelist"),
                    },
                    {
                        "title": _("Notifications"),
                        "icon": "notifications",
                        "link": reverse_lazy("admin:feedback_notification_changelist"),
                    },
                ],
            },
        ],
    },
    "COLORS": {
        "primary": {  # Reagent Blue — the design system primary scale
            "50": "#eef4ff",
            "100": "#d9e6ff",
            "200": "#b7ceff",
            "300": "#8aaef7",
            "400": "#5b88ec",
            "500": "#3570df",
            "600": "#1f5fd1",
            "700": "#1a4dab",
            "800": "#183f87",
            "900": "#15336b",
            "950": "#0d2149",
        },
    },
}

# --- AI grading of open practice answers (ARCHITECTURE §5.6) ---------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
AI_GRADING_MODEL = os.environ.get("AI_GRADING_MODEL", "claude-sonnet-5-5")
AI_GRADING_ENABLED = env_bool("AI_GRADING_ENABLED", False)
AI_GRADING_TIMEOUT_S = int(os.environ.get("AI_GRADING_TIMEOUT_S", "30"))
AI_GRADING_EFFORT = os.environ.get("AI_GRADING_EFFORT", "medium")  # low | medium | high
# Server-side refusal fallback (beta) on models that support it; turn off if the API rejects it.
AI_GRADING_FALLBACKS = env_bool("AI_GRADING_FALLBACKS", True)

# --- Background tasks (Django 6 django.tasks; ARCHITECTURE §9.6) -----------------
# Production: the database backend + `python manage.py db_worker` (systemd). Dev/tests run inline.
TASKS = {"default": {"BACKEND": "django_tasks_db.DatabaseBackend"}}

# Absolute address of the site — the QR code of a certificate points to its verification page.
SITE_URL = os.environ.get("SITE_URL", "http://localhost:8000").rstrip("/")
