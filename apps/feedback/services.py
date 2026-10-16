"""Notifications and comments (writes). notify() never fails the action that caused it."""

import logging

from django.contrib.contenttypes.models import ContentType
from django.db import transaction
from django.utils.translation import gettext as _

from .models import Comment, Notification

logger = logging.getLogger(__name__)
Kind = Notification.Kind


class CommentError(Exception):
    """Shown to the user as is (already translated)."""


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


# --- comments ------------------------------------------------------------------------------


def _teachers_of(enrollment):
    """Who hears a student's reply: course teachers and the teacher of the group's stream."""
    course = enrollment.course
    teachers = {ct.teacher for ct in course.course_teachers.select_related("teacher")}
    teachers |= {
        cg.teacher
        for cg in course.course_groups.filter(group=enrollment.group_id).select_related("teacher")
        if cg.teacher
    }
    return teachers


@transaction.atomic
def add_comment(author, target, body: str, parent: Comment | None = None, student_url: str = "", teacher_url: str = ""):
    """A comment on ``target`` (a work with .enrollment and .stage). The other side gets a notification."""
    body = (body or "").strip()
    if not body:
        raise CommentError(_("Write the comment first."))
    enrollment = target.enrollment
    if enrollment is None:
        raise CommentError(_("This work is not part of a course."))
    content_type = ContentType.objects.get_for_model(target)
    if parent is not None:
        if (parent.content_type_id, parent.object_id) != (content_type.pk, target.pk):
            raise CommentError(_("The reply belongs to another work."))
        parent = parent.parent or parent  # one level deep
    stage = getattr(target, "stage", None)
    comment = Comment.objects.create(
        author=author,
        enrollment=enrollment,
        stage=stage,
        content_type=content_type,
        object_id=target.pk,
        parent=parent,
        body=body[:5000],
    )
    title = stage.title if stage else ""
    if author.pk == enrollment.student_id:
        earlier = Comment.objects.filter(content_type=content_type, object_id=target.pk).exclude(author=author)
        recipients = {c.author for c in earlier.select_related("author")} or _teachers_of(enrollment)
        url = teacher_url
    else:
        recipients, url = {enrollment.student}, student_url
    for user in recipients:
        transaction.on_commit(lambda user=user: notify(user, Kind.COMMENT, title, url))
    return comment


def mark_thread_read(user, target) -> int:
    """The user opened the work: comments of the other side become read."""
    content_type = ContentType.objects.get_for_model(target)
    return (
        Comment.objects.filter(content_type=content_type, object_id=target.pk, is_read=False)
        .exclude(author=user)
        .update(is_read=True)
    )
