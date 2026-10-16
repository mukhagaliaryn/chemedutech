"""Background tasks (Django 6 django.tasks): the database backend + `manage.py db_worker` in production."""

from django.tasks import task

from .models import PracticeSubmission


@task
def grade_submission(submission_id: int) -> None:
    """AI-grade the open answers of a submission, then total it and record the stage result."""
    from .services.submissions import grade_open_answers

    submission = PracticeSubmission.objects.filter(pk=submission_id, status=PracticeSubmission.Status.GRADING).first()
    if submission is not None:
        grade_open_answers(submission)
