from django.urls import path

from . import views

urlpatterns = [
    path("modelo/", views.model_info, name="model_info"),
    path("modelo/probar/", views.model_try, name="model_try"),
]
