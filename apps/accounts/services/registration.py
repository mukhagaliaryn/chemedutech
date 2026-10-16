from django.db import transaction
from django.utils import timezone

from apps.organizations.models import AcademicGroup, StudentProfile

from ..models import User


@transaction.atomic
def register_student(
    *,
    username: str,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    group: AcademicGroup,
    research_consent: bool = False,
    language: str | None = None,
) -> User:
    """Self sign-up. Always creates a student — teachers are added by the admin only."""
    extra = {"language": language} if language else {}
    user = User.objects.create_user(
        username=username,
        email=email,
        password=password,
        first_name=first_name,
        last_name=last_name,
        role=User.Role.STUDENT,
        **extra,
    )
    StudentProfile.objects.create(
        user=user,
        group=group,
        study_year=group.study_year,
        research_consent=research_consent,
        research_consent_at=timezone.now() if research_consent else None,
    )
    return user
