"""Local development settings (default for manage.py)."""

from .base import *  # noqa: F403
from .base import env_bool, env_list

SECRET_KEY = SECRET_KEY or "dev-insecure-change-me"  # noqa: F405
DEBUG = env_bool("DJANGO_DEBUG", True)
ALLOWED_HOSTS = env_list("DJANGO_ALLOWED_HOSTS", "localhost,127.0.0.1")
INTERNAL_IPS = ["127.0.0.1"]
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
TASKS = {"default": {"BACKEND": "django.tasks.backends.immediate.ImmediateBackend"}}

INSTALLED_APPS = [*INSTALLED_APPS, "django_browser_reload"]  # noqa: F405
MIDDLEWARE = [*MIDDLEWARE, "django_browser_reload.middleware.BrowserReloadMiddleware"]  # noqa: F405

if env_bool("USE_SQLITE", False):
    DATABASES = {"default": {"ENGINE": "django.db.backends.sqlite3", "NAME": BASE_DIR / "db.sqlite3"}}  # noqa: F405

# Dev only: lets a page be framed by the same site, so layouts can be checked at phone width
# in an iframe (production keeps Django's default DENY).
X_FRAME_OPTIONS = "SAMEORIGIN"
