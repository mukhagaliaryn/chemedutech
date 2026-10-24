from django.urls import path

from . import sections, views

app_name = "student"

STAGE = "learn/<slug:course_slug>/<int:topic_number>/<int:stage_pk>/"

urlpatterns = [
    path("me/", views.dashboard, name="dashboard"),
    path("me/sections/<int:number>/", sections.section, name="section"),
    path("me/sections/<int:number>/diagnostic/<str:phase>/", sections.diagnostic, name="diagnostic"),
    path("me/sections/<int:number>/diagnostic/<str:phase>/start/", sections.diagnostic_start, name="diagnostic_start"),
    path(
        "me/sections/<int:number>/diagnostic/<str:phase>/<int:attempt_id>/submit/",
        sections.diagnostic_submit,
        name="diagnostic_submit",
    ),
    path("me/icpai/", sections.results, name="icpai"),
    path("me/search/", views.search, name="search"),
    path("me/results/", views.results, name="results"),
    path("me/certificates/", views.certificates, name="certificates"),
    path("me/profile/", views.profile, name="profile"),
    path("me/courses/", views.courses, name="courses"),
    path("me/courses/<slug:course_slug>/", views.course, name="course"),
    path("me/courses/<slug:course_slug>/enroll/", views.enroll, name="enroll"),
    path("me/courses/<slug:course_slug>/knowledge-test/<str:phase>/", views.benchmark_page, name="benchmark"),
    path(
        "me/courses/<slug:course_slug>/knowledge-test/<str:phase>/start/",
        views.benchmark_start,
        name="benchmark_start",
    ),
    path(
        "me/courses/<slug:course_slug>/knowledge-test/<str:phase>/<int:attempt_id>/submit/",
        views.benchmark_submit,
        name="benchmark_submit",
    ),
    path("learn/<slug:course_slug>/<int:topic_number>/", views.topic, name="topic"),
    path(STAGE, views.stage, name="stage"),
    path(STAGE + "material-done/", views.material_done, name="material_done"),
    path(STAGE + "watch/", views.watch, name="watch"),
    path(STAGE + "ping/", views.ping, name="ping"),
    path(STAGE + "comment/", views.comment, name="comment"),
    path(STAGE + "lab/<slug:experiment_key>/", views.lab_run, name="lab_run"),
    path(STAGE + "lab/<slug:experiment_key>/analysis/<int:attempt_id>/", views.lab_analysis, name="lab_analysis"),
    path(STAGE + "practice/", views.practice_submit, name="practice_submit"),
    path(STAGE + "practice/<int:submission_id>/status/", views.practice_status, name="practice_status"),
    path(STAGE + "quiz/", views.quiz_take, name="quiz_take"),
    path(STAGE + "quiz/retry/", views.quiz_retry, name="quiz_retry"),
    path(STAGE + "quiz/<int:attempt_id>/submit/", views.quiz_submit, name="quiz_submit"),
    path(STAGE + "quiz/<int:attempt_id>/check/<int:question_id>/", views.quiz_check, name="quiz_check"),
    path(STAGE + "quiz/<int:attempt_id>/", views.quiz_review, name="quiz_review"),
]
