from django.contrib.postgres.search import SearchVector
from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender="links.Bookmark")
def update_search_vector(sender, instance, **kwargs):
    """Keep the search_vector column in sync after every save."""
    sender.objects.filter(pk=instance.pk).update(
        search_vector=(
            SearchVector("title", weight="A")
            + SearchVector("description", weight="B")
            + SearchVector("url", weight="C")
        )
    )
