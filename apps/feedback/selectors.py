from django.contrib.contenttypes.models import ContentType
from django.db.models import Prefetch

from .models import Comment, Notification


def unread_count(user) -> int:
    if not user.is_authenticated:
        return 0
    return Notification.objects.filter(user=user, is_read=False).count()


def recent(user, limit: int | None = None, unread_only: bool = False):
    qs = Notification.objects.filter(user=user)
    if unread_only:
        qs = qs.filter(is_read=False)
    return qs[:limit] if limit else qs


def thread(target) -> list[Comment]:
    """First comments with their replies (oldest first)."""
    if target is None:
        return []
    content_type = ContentType.objects.get_for_model(target)
    return list(
        Comment.objects.filter(content_type=content_type, object_id=target.pk, parent=None)
        .select_related("author")
        .prefetch_related(Prefetch("replies", queryset=Comment.objects.select_related("author")))
    )


def comment_counts(targets) -> dict[int, int]:
    """{target.pk: comments} for works of one model."""
    targets = list(targets)
    if not targets:
        return {}
    content_type = ContentType.objects.get_for_model(targets[0])
    counts = {}
    for object_id in Comment.objects.filter(
        content_type=content_type, object_id__in=[t.pk for t in targets]
    ).values_list("object_id", flat=True):
        counts[object_id] = counts.get(object_id, 0) + 1
    return counts


def latest_for_student(enrollment, limit=3):
    """Teachers' comments on the student's works, newest first (dashboard)."""
    return (
        Comment.objects.filter(enrollment=enrollment)
        .exclude(author_id=enrollment.student_id)
        .select_related("author", "stage__topic__module__course")
        .order_by("-created_at", "-pk")[:limit]
    )


def thread_comment(target, comment_id):
    """The comment being replied to, only if it belongs to the same work."""
    if not comment_id or not str(comment_id).isdigit():
        return None
    content_type = ContentType.objects.get_for_model(target)
    return Comment.objects.filter(pk=comment_id, content_type=content_type, object_id=target.pk).first()
