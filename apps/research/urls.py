from django.urls import path

from . import views

app_name = "research"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("export/attempts.csv", views.export_attempts, name="export_attempts"),
    path("export/events.csv", views.export_events, name="export_events"),
]
