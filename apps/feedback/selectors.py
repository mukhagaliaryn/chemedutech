from .models import Notification


def unread_count(user) -> int:
    if not user.is_authenticated:
        return 0
    return Notification.objects.filter(user=user, is_read=False).count()


def recent(user, limit: int | None = None, unread_only: bool = False):
    qs = Notification.objects.filter(user=user)
    if unread_only:
        qs = qs.filter(is_read=False)
    return qs[:limit] if limit else qs
