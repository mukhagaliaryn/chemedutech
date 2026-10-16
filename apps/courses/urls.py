from django.urls import path

from . import views

app_name = "courses"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("<slug:course_slug>/topics/<int:number>/", views.topic_detail, name="topic"),
]
