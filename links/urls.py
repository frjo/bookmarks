from django.urls import path

from . import views

urlpatterns = [
    path("", views.bookmark_list, name="bookmark_list"),
    path("add/", views.bookmark_add, name="bookmark_add"),
    path("<str:pk>/edit/", views.bookmark_edit, name="bookmark_edit"),
    path("<str:pk>/delete/", views.bookmark_delete, name="bookmark_delete"),
    path("import/", views.bookmark_import, name="bookmark_import"),
    path("export/", views.bookmark_export, name="bookmark_export"),
]
