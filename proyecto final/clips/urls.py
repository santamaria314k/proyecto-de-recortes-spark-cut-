from django.urls import path

from . import views

urlpatterns = [
    path("clips/<int:pk>/media/", views.clip_media, name="clip_media"),
    path("clips/<int:pk>/download/", views.clip_download, name="clip_download"),
    path("clips/<int:pk>/trim/", views.clip_trim, name="clip_trim"),
    path("clips/<int:pk>/status/", views.clip_status, name="clip_status"),
    path("clips/<int:pk>/restore/", views.clip_restore, name="clip_restore"),
    path("clips/<int:pk>/delete/", views.clip_delete, name="clip_delete"),
]
