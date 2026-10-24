from django.urls import path

from . import views

app_name = "research"

# mounted at /teacher/ (STEP-12); the old /research/ redirects here
urlpatterns = [
    path("research/", views.dashboard, name="dashboard"),
    path("research/export/attempts.csv", views.export_attempts, name="export_attempts"),
    path("research/export/events.csv", views.export_events, name="export_events"),
    path("research/export/quiz_answers.csv", views.export_quiz_answers, name="export_quiz_answers"),
    path("research/export/ai_reviews.csv", views.export_ai_reviews, name="export_ai_reviews"),
    path("research/export/diagnostics.csv", views.export_diagnostics, name="export_diagnostics"),
    path("analytics/", views.analytics_page, name="analytics"),
    path("analytics/<slug:slug>/", views.analytics_page, name="analytics_course"),
    path("analytics/<slug:slug>/sample/", views.draw_sample, name="draw_sample"),
]
