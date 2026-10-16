from django.urls import path

from . import views

app_name = "student"

STAGE = "learn/<slug:course_slug>/<int:topic_number>/<int:stage_pk>/"

urlpatterns = [
    path("me/courses/", views.courses, name="courses"),
    path("me/courses/<slug:course_slug>/", views.course, name="course"),
    path("me/courses/<slug:course_slug>/enroll/", views.enroll, name="enroll"),
    path("learn/<slug:course_slug>/<int:topic_number>/", views.topic, name="topic"),
    path(STAGE, views.stage, name="stage"),
    path(STAGE + "material-done/", views.material_done, name="material_done"),
    path(STAGE + "watch/", views.watch, name="watch"),
    path(STAGE + "ping/", views.ping, name="ping"),
    path(STAGE + "quiz/", views.quiz_take, name="quiz_take"),
    path(STAGE + "quiz/retry/", views.quiz_retry, name="quiz_retry"),
    path(STAGE + "quiz/<int:attempt_id>/submit/", views.quiz_submit, name="quiz_submit"),
    path(STAGE + "quiz/<int:attempt_id>/", views.quiz_review, name="quiz_review"),
]
