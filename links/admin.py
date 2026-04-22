from django.contrib import admin

from .models import Bookmark


@admin.register(Bookmark)
class BookmarkAdmin(admin.ModelAdmin):
    list_display = ("title", "url", "user", "tags", "created_at")
    list_filter = ("user",)
    search_fields = ("title", "url", "description")
    readonly_fields = ("id", "created_at", "updated_at", "search_vector")
    ordering = ("-created_at",)
