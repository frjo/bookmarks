from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("accounts.urls")),
    path("api/v1/", include("links.api_urls")),
    path("", include("links.urls")),
    path("<str:handle>/", include("links.user_urls")),
]
