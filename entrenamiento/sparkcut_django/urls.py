from django.urls import path

from . import views

app_name = "sparkcut_django"

urlpatterns = [
    path("health/", views.health, name="health"),
    path("score/", views.score_video, name="score_video"),
]
