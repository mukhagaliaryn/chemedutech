from django.urls import path

from . import views

app_name = "labs"

urlpatterns = [
    path("<slug:lab_key>/<slug:experiment_key>/", views.run_experiment, name="run"),
    path("api/attempts/<int:pk>/events/", views.api_events, name="api_events"),
    path("api/attempts/<int:pk>/journal/", views.api_journal, name="api_journal"),
    path("api/attempts/<int:pk>/finish/", views.api_finish, name="api_finish"),
    path("api/attempts/<int:pk>/analysis/", views.api_analysis, name="api_analysis"),
]
