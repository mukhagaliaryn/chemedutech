import re

from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.organizations.models import AcademicGroup, StudentProfile

from ..models import User

USERNAME_MAX = 150


def username_from_email(email: str) -> str:
    """A free login made from the email's local part: aigerim.s@uni.kz → aigerim.s, then aigerim.s-2, -3, …

    Only Latin letters, digits and . _ - are kept (the login field tells an email from a login by «@»).
    """
    base = re.sub(r"[^a-z0-9._-]+", "", email.split("@", 1)[0].lower()).strip("._-") or "user"
    base = base[: USERNAME_MAX - 6]
    taken = set(
        User.objects.filter(username__iregex=rf"^{re.escape(base)}(-[0-9]+)?$").values_list("username", flat=True)
    )
    taken = {name.lower() for name in taken}
    if base not in taken:
        return base
    n = 2
    while f"{base}-{n}" in taken:
        n += 1
    return f"{base}-{n}"


@transaction.atomic
def register_student(
    *,
    email: str,
    password: str,
    first_name: str,
    last_name: str,
    group: AcademicGroup,
    research_consent: bool = False,
    language: str | None = None,
) -> User:
    """Self sign-up. Always creates a student — teachers are added by the admin only.

    The login is not asked for: it is made from the email (``username_from_email``); students sign in with
    the email or that login.
    """
    extra = {"language": language} if language else {}
    for _attempt in range(5):  # two sign-ups with the same email prefix at once: take the next suffix
        try:
            with transaction.atomic():
                user = User.objects.create_user(
                    username=username_from_email(email),
                    email=email,
                    password=password,
                    first_name=first_name,
                    last_name=last_name,
                    role=User.Role.STUDENT,
                    **extra,
                )
            break
        except IntegrityError:
            continue
    else:
        raise IntegrityError("no free username")
    StudentProfile.objects.create(
        user=user,
        group=group,
        study_year=group.study_year,
        research_consent=research_consent,
        research_consent_at=timezone.now() if research_consent else None,
    )
    return user
