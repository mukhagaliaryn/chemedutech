"""Certificate pages: the public verification page and the PDF (holder, the course's teachers, the admin)."""

from django.contrib.auth.decorators import login_required
from django.http import FileResponse, Http404
from django.shortcuts import render

from apps.core.permissions import ADMIN, has_role

from . import selectors, services


def verify(request, code):
    """Public: anyone with the QR code / link checks that the certificate is real."""
    certificate = selectors.by_code(code)
    status = 200 if certificate else 404
    return render(request, "certificates/verify.html", {"certificate": certificate}, status=status)


def _may_download(user, certificate) -> bool:
    if has_role(user, ADMIN) or certificate.enrollment.student_id == user.pk:
        return True
    return certificate.enrollment.course.course_teachers.filter(teacher=user).exists()


@login_required
def pdf(request, code):
    certificate = selectors.by_code(code)
    if certificate is None or not _may_download(request.user, certificate):
        raise Http404
    if not certificate.pdf:
        services.render_pdf(certificate)  # the background task has not run yet
    return FileResponse(
        certificate.pdf.open("rb"), filename=f"{certificate.number}.pdf", content_type="application/pdf"
    )
