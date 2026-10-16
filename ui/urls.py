from django.urls import path

from . import views

app_name = "ui"

urlpatterns = [
    path("styleguide/", views.styleguide, name="styleguide"),
]
