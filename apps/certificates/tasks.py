"""Background tasks: the certificate PDF (WeasyPrint takes a second or two)."""

from django.tasks import task


@task
def render_certificate_pdf(certificate_id: int) -> None:
    from .models import Certificate
    from .services import render_pdf

    certificate = Certificate.objects.filter(pk=certificate_id).first()
    if certificate is not None:
        render_pdf(certificate)
