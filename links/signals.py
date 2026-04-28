from django.contrib.postgres.search import SearchVector
from django.db.models.signals import post_save
from django.dispatch import receiver

_CONTENT_FIELDS = {"title", "description", "url"}


@receiver(post_save, sender="links.Bookmark")
def update_search_vector(sender, instance, created, update_fields, **kwargs):
    """Keep the search_vector column in sync after every save."""
    if (
        not created
        and update_fields is not None
        and not _CONTENT_FIELDS.intersection(update_fields)
    ):
        return
    sender.objects.filter(pk=instance.pk).update(
        search_vector=(
            SearchVector("title", weight="A")
            + SearchVector("description", weight="B")
            + SearchVector("url", weight="C")
        )
    )
