from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("api/v1/", include("api.v1.urls")),
    path("api/v2/", include("api.v2.urls")),
    path("", include("links.urls")),
    path("my/", include("links.user_urls")),
    path("<str:slug>/", include("links.user_urls")),
]
