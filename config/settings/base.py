"""ChemEduTech — settings shared by every environment.

Secrets and environment-specific values come from environment variables
(see .env.example). Nothing secret is hardcoded here. Environment modules:
``config.settings.dev`` (default for manage.py) and ``config.settings.prod``.
"""

import os
from pathlib import Path

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
    },
    "compact": {  # question and answer text: formulas need sub/sup
        "toolbar": {"items": ["bold", "italic", "subscript", "superscript", *_CK_SPECIAL, "|", "undo", "redo"]},
    },
}

# --- Admin (django-unfold); full navigation/dashboard in STEP-14 ----------
UNFOLD = {
    "SITE_TITLE": "ChemEduTech",
    "SITE_HEADER": "ChemEduTech",
    "SITE_SYMBOL": "science",
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
