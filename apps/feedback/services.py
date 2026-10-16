"""Notifications (writes). Other apps call notify(); it never fails the action that caused it."""

import logging

from .models import Notification

logger = logging.getLogger(__name__)
Kind = Notification.Kind


def notify(user, kind: str, title: str = "", url: str = "") -> Notification | None:
    try:
        return Notification.objects.create(user=user, kind=kind, title=title[:255], url=url[:500])
    except Exception:  # a lost notification must not roll back a grade
        logger.exception("Notification for user %s was not saved", getattr(user, "pk", None))
        return None


def mark_read(user, notification_id: int) -> Notification | None:
    notification = Notification.objects.filter(user=user, pk=notification_id).first()
    if notification and not notification.is_read:
        notification.is_read = True
        notification.save(update_fields=["is_read"])
    return notification


def mark_all_read(user) -> int:
    return Notification.objects.filter(user=user, is_read=False).update(is_read=True)
