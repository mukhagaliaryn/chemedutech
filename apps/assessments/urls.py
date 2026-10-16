from django.urls import path

from . import views

app_name = "assessments"

urlpatterns = [
    path("<int:quiz_id>/", views.take, name="take"),
    path("<int:quiz_id>/retry/", views.retry, name="retry"),
    path("attempts/<int:attempt_id>/submit/", views.submit, name="submit"),
    path("attempts/<int:attempt_id>/", views.result, name="result"),
]
