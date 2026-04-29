from django.conf import settings
from django.contrib import admin
from django.urls import include, path

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("home.urls")),
    path("", include("accounts.urls")),
    path("api/v1/", include("api.v1.urls")),
    path("api/v2/", include("api.v2.urls")),
    path("<str:slug>/", include("links.urls")),
]

if settings.DEBUG:
    from debug_toolbar.toolbar import debug_toolbar_urls

    urlpatterns += debug_toolbar_urls()
