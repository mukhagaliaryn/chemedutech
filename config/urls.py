from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path
from django.views.generic import RedirectView

from apps.accounts import views as accounts_views
from apps.core.uploads import ckeditor_upload

urlpatterns = [
    path("admin/", admin.site.urls),
    path("i18n/setlang/", accounts_views.set_language, name="set_language"),
    path("accounts/", include("apps.accounts.urls")),
    path("courses/", RedirectView.as_view(pattern_name="student:courses", permanent=False)),
    path("labs/", include("apps.labs.urls")),
    path("notifications/", include("apps.feedback.urls")),
    path("quiz/", include("apps.assessments.urls")),
    path("research/", include("apps.research.urls")),
    path("teacher/", include("apps.teacher.urls")),
    path("ui/", include("ui.urls")),
    path("ckeditor5/image_upload/", ckeditor_upload, name="ckeditor_upload"),
    path("", include("apps.student.urls")),
    path("", include("apps.core.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
if "django_browser_reload" in settings.INSTALLED_APPS:
    urlpatterns.insert(0, path("__reload__/", include("django_browser_reload.urls")))
