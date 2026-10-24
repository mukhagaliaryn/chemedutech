from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, {"page": 1}, name="about"),
    path("about/<int:page>/", views.about, name="about_page"),
]
