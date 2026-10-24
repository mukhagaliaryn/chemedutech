from decimal import Decimal

from apps.courses.models import Enrollment
from apps.progress import selectors as progress_selectors

from .base import Provider, share


def course_enrollment(enrollment) -> Enrollment | None:
    """The student's enrolment in the programme's course (section 1), if any and not dropped."""
    return (
        Enrollment.objects.filter(student_id=enrollment.student_id, course_id=enrollment.programme.course_id)
        .exclude(status=Enrollment.Status.DROPPED)
        .first()
    )


class CourseProvider(Provider):
    """Section 1 — the course: the share of the required stages of the published topics that are done
    (passed or awaiting check). Not the score: the course score, pass mark and certificate stay apart (D68)."""

    def percent(self, enrollment, section) -> Decimal:
        course_enr = course_enrollment(enrollment)
        if course_enr is None:
            return Decimal(0)
        return share(*progress_selectors.required_stages_done(course_enr))
