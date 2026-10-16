from django.conf import settings

from ..models import User


def set_language(user: User, language: str) -> None:
    if language in dict(settings.LANGUAGES) and user.language != language:
        user.language = language
        user.save(update_fields=["language", "updated_at"])


PROFILE_FIELDS = ("last_name", "first_name", "middle_name", "email", "phone", "language")


def update_profile(user: User, data: dict) -> list[str]:
    """Save the cabinet profile form; returns the changed field names."""
    changed = [name for name in PROFILE_FIELDS if name in data and getattr(user, name) != data[name]]
    for name in changed:
        setattr(user, name, data[name])
    if changed:
        user.save(update_fields=[*changed, "updated_at"])
    return changed
