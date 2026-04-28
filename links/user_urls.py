from django.urls import path

from accounts import views as accounts_views

from . import views

urlpatterns = [
    path("", views.bookmark_list, name="bookmark_list"),
    path("tags/", views.bookmark_tags, name="bookmark_tags"),
    path("add/", views.bookmark_add, name="bookmark_add"),
    path("<str:pk>/edit/", views.bookmark_edit, name="bookmark_edit"),
    path("<str:pk>/delete/", views.bookmark_delete, name="bookmark_delete"),
    path("fetch-meta/", views.bookmark_fetch_meta, name="bookmark_fetch_meta"),
    path("import/", views.bookmark_import, name="bookmark_import"),
    path("export/", views.bookmark_export, name="bookmark_export"),
    path("account/", accounts_views.account_view, name="account"),
]
