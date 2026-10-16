from django.db import IntegrityError, transaction

from ..models import AcademicGroup, generate_join_code


def regenerate_join_code(group: AcademicGroup, attempts: int = 5) -> str:
    """Give the group a fresh join code (the old one stops working immediately)."""
    for _ in range(attempts):
        group.join_code = generate_join_code()
        try:
            with transaction.atomic():
                group.save(update_fields=["join_code", "updated_at"])
            return group.join_code
        except IntegrityError:  # astronomically rare collision — try another code
            continue
    raise RuntimeError("Could not generate a unique join code")
