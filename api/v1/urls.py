from django.urls import path

from . import views

urlpatterns = [
    path("posts/update", views.posts_update, name="api_v1_posts_update"),
    path("posts/add", views.posts_add, name="api_v1_posts_add"),
    path("posts/delete", views.posts_delete, name="api_v1_posts_delete"),
    path("posts/get", views.posts_get, name="api_v1_posts_get"),
    path("posts/recent", views.posts_recent, name="api_v1_posts_recent"),
    path("posts/all", views.posts_all, name="api_v1_posts_all"),
    path("posts/dates", views.posts_dates, name="api_v1_posts_dates"),
    path("posts/suggest", views.posts_suggest, name="api_v1_posts_suggest"),
    path("tags/get", views.tags_get, name="api_v1_tags_get"),
    path("tags/delete", views.tags_delete, name="api_v1_tags_delete"),
    path("tags/rename", views.tags_rename, name="api_v1_tags_rename"),
    path("user/secret", views.user_secret, name="api_v1_user_secret"),
    path("user/api_token", views.user_api_token, name="api_v1_user_api_token"),
    path("notes/list", views.notes_list, name="api_v1_notes_list"),
    path("notes/<str:note_id>", views.notes_detail, name="api_v1_notes_detail"),
]
