from django.urls import path

from . import views

app_name = "feedback"

urlpatterns = [
    path("", views.notifications, name="notifications"),
    path("<int:pk>/", views.open_notification, name="open"),
    path("read-all/", views.read_all, name="read_all"),
    path("badge/", views.badge, name="badge"),
]
