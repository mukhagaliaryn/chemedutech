from django.urls import path

from . import gradebook, grading, views

app_name = "teacher"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("groups/", views.groups, name="groups"),
    path("groups/new/", views.group_edit, name="group_new"),
    path("groups/<int:pk>/", views.group, name="group"),
    path("groups/<int:pk>/edit/", views.group_edit, name="group_edit"),
    path("groups/<int:pk>/delete/", views.group_delete, name="group_delete"),
    path("groups/<int:pk>/cohort/", views.group_cohort, name="group_cohort"),
    path("groups/<int:pk>/students/add/", views.group_add_student, name="group_add_student"),
    path("groups/<int:pk>/students/<int:student_pk>/remove/", views.group_remove_student, name="group_remove_student"),
    path("groups/<int:pk>/join-code/", views.group_join_code, name="group_join_code"),
    path("groups/<int:pk>/courses/attach/", views.group_attach, name="group_attach"),
    path("groups/<int:pk>/courses/<int:link_pk>/detach/", views.group_detach, name="group_detach"),
    path("grading/", grading.queue, name="grading"),
    path("grading/<int:pk>/", grading.detail, name="grading_detail"),
    path("comments/", grading.comment, name="comment"),
    path("gradebook/", gradebook.gradebook, name="gradebook"),
    path("gradebook/<slug:course_slug>/", gradebook.gradebook, name="gradebook_course"),
    path("students/", views.students, name="students"),
    path("students/<int:pk>/", views.student, name="student"),
    path("students/<int:pk>/stages/<int:stage_pk>/unlock/", views.unlock_stage, name="unlock_stage"),
    path("students/<int:pk>/lab/<int:attempt_pk>/", views.lab_log, name="lab_log"),
]
