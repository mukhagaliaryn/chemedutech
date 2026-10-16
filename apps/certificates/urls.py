from django.urls import path

from . import views

app_name = "certificates"

urlpatterns = [
    path("verify/<uuid:code>/", views.verify, name="verify"),
    path("<uuid:code>/pdf/", views.pdf, name="pdf"),
]
