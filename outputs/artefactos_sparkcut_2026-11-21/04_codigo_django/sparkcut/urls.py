from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.urls import include, path

from . import views

handler400 = "sparkcut.views.handler400"
handler403 = "sparkcut.views.handler403"
handler404 = "sparkcut.views.handler404"
handler500 = "sparkcut.views.handler500"

urlpatterns = [
    path("", views.home, name="home"),
    path("admin/", admin.site.urls),
    path("healthz/", views.healthz, name="healthz"),
    path("readyz/", views.readyz, name="readyz"),
    path("accounts/", include("allauth.urls")),
    path("", include("videos.urls")),
    path("", include("scoring.urls")),
    path("", include("clips.urls")),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
