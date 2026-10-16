from django.conf import settings

from ..models import User


def set_language(user: User, language: str) -> None:
    if language in dict(settings.LANGUAGES) and user.language != language:
        user.language = language
        user.save(update_fields=["language", "updated_at"])
