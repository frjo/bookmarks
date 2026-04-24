from django.contrib.postgres.fields import ArrayField
from django.contrib.postgres.indexes import GinIndex
from django.contrib.postgres.search import SearchVectorField
from django.db import models
from django.utils import timezone

from accounts.models import User, generate_cuid


class Bookmark(models.Model):
    id = models.CharField(
        primary_key=True,
        max_length=32,
        default=generate_cuid,
        editable=False,
    )
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="bookmarks")
    url = models.URLField(max_length=2000)
    title = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    tags = ArrayField(models.CharField(max_length=100), blank=True, default=list)
    shared = models.BooleanField(default=True)
    toread = models.BooleanField(default=False)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)
    # Populated asynchronously via a post-save signal.
    search_vector = SearchVectorField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            GinIndex(fields=["search_vector"], name="links_bookmark_fts_idx"),
            GinIndex(fields=["tags"], name="links_bookmark_tags_idx"),
            models.Index(
                fields=["user", "-created_at"], name="links_bookmark_user_date_idx"
            ),
        ]

    def __str__(self) -> str:
        return self.title or self.url
