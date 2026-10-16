"""Production settings (default for wsgi/asgi). Served behind Nginx over HTTPS."""

import os

from django.core.exceptions import ImproperlyConfigured

from .base import *  # noqa: F403
from .base import env_bool

if not SECRET_KEY:  # noqa: F405
    raise ImproperlyConfigured("DJANGO_SECRET_KEY must be set in production.")

DEBUG = False

SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = env_bool("DJANGO_SECURE_SSL_REDIRECT", True)
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
LANGUAGE_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = int(os.environ.get("DJANGO_SECURE_HSTS_SECONDS", "0"))
SECURE_CONTENT_TYPE_NOSNIFF = True
