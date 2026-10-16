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
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # project apps (layered: core → accounts/courses → labs → research)
    "apps.core",
    "apps.accounts",
    "apps.courses",
    "apps.labs",
    "apps.research",
]

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
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "builtins": ["apps.core.templatetags.lab_tags"],
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
LOGIN_URL = "accounts:login"
LOGIN_REDIRECT_URL = "courses:dashboard"
LOGOUT_REDIRECT_URL = "core:home"

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
STATICFILES_DIRS = [BASE_DIR / "static"]
STATIC_ROOT = BASE_DIR / "staticfiles"
MEDIA_URL = "media/"
MEDIA_ROOT = BASE_DIR / "media"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# --- AI grading of open practice answers (ARCHITECTURE §5.6) ---------------
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
AI_GRADING_MODEL = os.environ.get("AI_GRADING_MODEL", "claude-sonnet-5-5")
AI_GRADING_ENABLED = env_bool("AI_GRADING_ENABLED", False)
AI_GRADING_TIMEOUT_S = int(os.environ.get("AI_GRADING_TIMEOUT_S", "30"))
