from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from apps.accounts import views as accounts_views

urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/setlang/", accounts_views.set_language, name="set_language"),
    path("accounts/", include("apps.accounts.urls")),
    path("courses/", include("apps.courses.urls")),
    path("labs/", include("apps.labs.urls")),
    path("research/", include("apps.research.urls")),
    path("ui/", include("ui.urls")),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
if "django_browser_reload" in settings.INSTALLED_APPS:
    urlpatterns.insert(0, path("__reload__/", include("django_browser_reload.urls")))
