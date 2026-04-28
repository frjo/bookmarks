from django.core.cache import cache
from django.db.models import Count
from django.db.models.functions import TruncDate
from django.utils import timezone

from .models import Bookmark, Unnest, tags_for_user

_TTL_TAGS = 60
_TTL_UPDATE = 60
_TTL_TOP_TAGS = 60
_TTL_DATES = 120


def _tags_key(user):
    return f"user_tags:{user.pk}"


def _update_key(user):
    return f"posts_update:{user.pk}"


def _top_tags_key(user):
    return f"user_top_tags:{user.pk}"


def _dates_key(user, tag_param=""):
    return f"posts_dates:{user.pk}:{tag_param}"


def get_user_tags(user):
    key = _tags_key(user)
    tags = cache.get(key)
    if tags is None:
        tags = list(tags_for_user(user))
        cache.set(key, tags, _TTL_TAGS)
    return tags


def get_posts_update_time(user):
    key = _update_key(user)
    ts = cache.get(key)
    if ts is None:
        latest = (
            Bookmark.objects.filter(user=user)
            .order_by("-updated_at")
            .values_list("updated_at", flat=True)
            .first()
        )
        ts = (latest or timezone.now()).strftime("%Y-%m-%dT%H:%M:%SZ")
        cache.set(key, ts, _TTL_UPDATE)
    return ts


def get_user_top_tags(user):
    key = _top_tags_key(user)
    tags = cache.get(key)
    if tags is None:
        rows = (
            Bookmark.objects.filter(user=user)
            .annotate(tag=Unnest("tags"))
            .values("tag")
            .annotate(count=Count("id"))
            .order_by("-count")[:100]
        )
        tags = [r["tag"] for r in rows]
        cache.set(key, tags, _TTL_TOP_TAGS)
    return tags


def get_posts_dates(user, tag_param=""):
    key = _dates_key(user, tag_param)
    result = cache.get(key)
    if result is None:
        qs = Bookmark.objects.filter(user=user)
        if tag_param:
            for tag in tag_param.split():
                qs = qs.filter(tags__contains=[tag])
        rows = (
            qs.annotate(date=TruncDate("created_at"))
            .values("date")
            .annotate(count=Count("id"))
            .order_by("-date")
        )
        result = {str(r["date"]): r["count"] for r in rows}
        cache.set(key, result, _TTL_DATES)
    return result


def invalidate_user_caches(user):
    cache.delete_many(
        [
            _tags_key(user),
            _update_key(user),
            _top_tags_key(user),
            _dates_key(user, ""),
        ]
    )
