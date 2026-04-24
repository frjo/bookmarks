from django.urls import path

from accounts import views as accounts_views

from . import views

urlpatterns = [
    path("", views.user_bookmark_list, name="user_bookmark_list"),
    path("add/", views.bookmark_add, name="bookmark_add"),
    path("<str:pk>/edit/", views.bookmark_edit, name="bookmark_edit"),
    path("<str:pk>/delete/", views.bookmark_delete, name="bookmark_delete"),
    path("import/", views.bookmark_import, name="bookmark_import"),
    path("export/", views.bookmark_export, name="bookmark_export"),
    path("settings/", accounts_views.settings_view, name="settings"),
]
