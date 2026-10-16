"""CKEditor 5 image upload, allowed to teachers and admins (the package's own view only knows is_staff)."""

from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.http import JsonResponse
from django.utils.translation import gettext as _
from django.views.decorators.http import require_POST
from django_ckeditor_5.views import upload_file

from .permissions import ADMIN, TEACHER, has_role


class CKEditorStorage(FileSystemStorage):
    """MEDIA_ROOT/ckeditor/ — set as CKEDITOR_5_FILE_STORAGE."""

    def __init__(self, **kwargs):
        kwargs.setdefault("location", settings.MEDIA_ROOT / "ckeditor")
        kwargs.setdefault("base_url", f"{settings.MEDIA_URL}ckeditor/")
        super().__init__(**kwargs)


@require_POST
def ckeditor_upload(request):
    if not has_role(request.user, TEACHER, ADMIN):
        return JsonResponse({"error": {"message": _("You do not have permission to upload files.")}}, status=403)
    return upload_file(request)
