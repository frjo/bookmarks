from django.urls import path

from . import api

urlpatterns = [
    path("posts/get", api.posts_get, name="api_posts_get"),
    path("posts/recent", api.posts_recent, name="api_posts_recent"),
    path("posts/all", api.posts_all, name="api_posts_all"),
    path("posts/add", api.posts_add, name="api_posts_add"),
    path("posts/delete", api.posts_delete, name="api_posts_delete"),
    path("posts/dates", api.posts_dates, name="api_posts_dates"),
    path("tags/get", api.tags_get, name="api_tags_get"),
    path("tags/rename", api.tags_rename, name="api_tags_rename"),
    path("tags/delete", api.tags_delete, name="api_tags_delete"),
    path("user/api_token/", api.user_api_token, name="api_user_token"),
]
