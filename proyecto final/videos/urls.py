from django.urls import path

from . import views

urlpatterns = [
    path("dashboard/", views.dashboard, name="dashboard"),
    path("videos/new/", views.video_new, name="video_new"),
    path("videos/<int:pk>/", views.video_detail, name="video_detail"),
    path("videos/<int:pk>/status/", views.video_status, name="video_status"),
    path("videos/<int:pk>/delete/", views.video_delete, name="video_delete"),
    path("videos/<int:pk>/clips/", views.video_clips, name="video_clips"),
]
