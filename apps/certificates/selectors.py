from .models import Certificate


def of_student(user):
    return Certificate.objects.filter(enrollment__student=user).select_related("enrollment__course")


def by_code(code):
    return Certificate.objects.filter(verification_code=code).select_related("enrollment__course").first()
