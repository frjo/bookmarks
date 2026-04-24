from django.urls import path

from . import views

urlpatterns = [
    path("posts/get", views.posts_get, name="api_v2_posts_get"),
    path("posts/recent", views.posts_recent, name="api_v2_posts_recent"),
    path("posts/all", views.posts_all, name="api_v2_posts_all"),
    path("posts/add", views.posts_add, name="api_v2_posts_add"),
    path("posts/delete", views.posts_delete, name="api_v2_posts_delete"),
    path("posts/dates", views.posts_dates, name="api_v2_posts_dates"),
    path("tags/get", views.tags_get, name="api_v2_tags_get"),
    path("tags/rename", views.tags_rename, name="api_v2_tags_rename"),
    path("tags/delete", views.tags_delete, name="api_v2_tags_delete"),
    path("user/api_token", views.user_api_token, name="api_v2_user_token"),
]
