"""Pinboard-compatible JSON API (v1 subset).

Authentication
--------------
Every request must include ``?auth_token=<user_id>:<token>`` as a query
or POST parameter.

Endpoints
---------
GET  /api/v1/posts/get         Return bookmarks (filter by URL or tag/date).
GET  /api/v1/posts/recent      Most-recent bookmarks.
GET  /api/v1/posts/all         All bookmarks with optional filters.
GET  /api/v1/posts/add         Add or update a bookmark.
GET  /api/v1/posts/delete      Delete a bookmark.
GET  /api/v1/posts/dates       Number of bookmarks per date.
GET  /api/v1/tags/get          All tags with counts.
GET  /api/v1/tags/rename       Rename a tag.
GET  /api/v1/tags/delete       Delete a tag.
GET  /api/v1/user/api_token/   Return current token.

All methods accept both GET and POST.
"""

import datetime
import json
from functools import wraps

from django.db.models import Count, Q
from django.http import JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods

from accounts.models import APIToken
from links.models import Bookmark

_ALLOW = require_http_methods(["GET", "POST"])


# ---------------------------------------------------------------------------
# Auth decorator
# ---------------------------------------------------------------------------


def _api_auth(view_func):
    @wraps(view_func)
    @csrf_exempt
    def wrapper(request, *args, **kwargs):
        auth_token = request.GET.get("auth_token") or request.POST.get("auth_token")
        if not auth_token or ":" not in auth_token:
            return JsonResponse({"error": "authentication required"}, status=401)
        user_id, _, token = auth_token.partition(":")
        try:
            record = APIToken.objects.select_related("user").get(
                user_id=user_id, token=token
            )
        except APIToken.DoesNotExist:
            return JsonResponse({"error": "invalid token"}, status=401)
        request.api_user = record.user
        return view_func(request, *args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# Serialisation
# ---------------------------------------------------------------------------


def _serialize(bm: Bookmark) -> dict:
    return {
        "href": bm.url,
        "description": bm.title,
        "extended": bm.description,
        "meta": "",
        "hash": "",
        "time": bm.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "shared": "no",
        "toread": "no",
        "tags": " ".join(bm.tags),
    }


def _result_done() -> JsonResponse:
    return JsonResponse({"result_code": "done"})


def _result_error(msg: str, status: int = 400) -> JsonResponse:
    return JsonResponse({"result_code": msg}, status=status)


# ---------------------------------------------------------------------------
# Post endpoints
# ---------------------------------------------------------------------------


@_ALLOW
@_api_auth
def posts_get(request):
    """Return bookmarks matching URL, tags, and/or date."""
    user = request.api_user
    params = request.GET if request.method == "GET" else request.POST

    qs = Bookmark.objects.filter(user=user)

    if url := params.get("url"):
        qs = qs.filter(url=url)

    if tag_str := params.get("tag", ""):
        for tag in tag_str.split()[:3]:
            qs = qs.filter(tags__contains=[tag])

    if dt_str := params.get("dt"):
        try:
            dt = datetime.date.fromisoformat(dt_str)
            qs = qs.filter(created_at__date=dt)
        except ValueError:
            pass

    start = int(params.get("start", 0))
    results = min(int(params.get("results", 100)), 1000)
    qs = qs.order_by("-created_at")[start : start + results]

    return JsonResponse(
        {
            "date": timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "user": user.username,
            "posts": [_serialize(bm) for bm in qs],
        }
    )


@_ALLOW
@_api_auth
def posts_recent(request):
    user = request.api_user
    params = request.GET if request.method == "GET" else request.POST

    count = min(int(params.get("count", 15)), 100)
    qs = Bookmark.objects.filter(user=user).order_by("-created_at")[:count]
    return JsonResponse(
        {
            "date": timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "user": user.username,
            "posts": [_serialize(bm) for bm in qs],
        }
    )


@_ALLOW
@_api_auth
def posts_all(request):
    user = request.api_user
    params = request.GET if request.method == "GET" else request.POST

    qs = Bookmark.objects.filter(user=user)

    if tag_str := params.get("tag", ""):
        for tag in tag_str.split():
            qs = qs.filter(tags__contains=[tag])

    if fromdt := params.get("fromdt"):
        try:
            qs = qs.filter(created_at__gte=datetime.datetime.fromisoformat(fromdt))
        except ValueError:
            pass

    if todt := params.get("todt"):
        try:
            qs = qs.filter(created_at__lte=datetime.datetime.fromisoformat(todt))
        except ValueError:
            pass

    start = int(params.get("start", 0))
    results = min(int(params.get("results", 1000)), 10_000)
    qs = qs.order_by("-created_at")[start : start + results]

    return JsonResponse([_serialize(bm) for bm in qs], safe=False)


@_ALLOW
@_api_auth
def posts_add(request):
    """Add or update a bookmark (matched by URL)."""
    user = request.api_user
    params = request.GET if request.method == "GET" else request.POST

    url = params.get("url", "").strip()
    if not url:
        return _result_error("url is required")

    title = params.get("description", "").strip()
    description = params.get("extended", "").strip()
    tags_str = params.get("tags", "")
    tags = sorted({t.lower().strip() for t in tags_str.split() if t.strip()})
    replace = params.get("replace", "yes").lower() != "no"

    existing = Bookmark.objects.filter(user=user, url=url).first()
    if existing and not replace:
        return _result_done()

    if existing:
        existing.title = title or existing.title
        existing.description = description
        existing.tags = tags
        existing.save()
    else:
        created_at = None
        if dt_str := params.get("dt"):
            try:
                created_at = datetime.datetime.fromisoformat(dt_str)
            except ValueError:
                pass
        Bookmark.objects.create(
            user=user,
            url=url[:2000],
            title=title[:500] or url[:500],
            description=description,
            tags=tags,
            **({"created_at": created_at} if created_at else {}),
        )

    return _result_done()


@_ALLOW
@_api_auth
def posts_delete(request):
    user = request.api_user
    params = request.GET if request.method == "GET" else request.POST
    url = params.get("url", "").strip()
    if not url:
        return _result_error("url is required")
    Bookmark.objects.filter(user=user, url=url).delete()
    return _result_done()


@_ALLOW
@_api_auth
def posts_dates(request):
    user = request.api_user
    params = request.GET if request.method == "GET" else request.POST

    qs = Bookmark.objects.filter(user=user)
    if tag_str := params.get("tag", ""):
        for tag in tag_str.split():
            qs = qs.filter(tags__contains=[tag])

    from django.db.models.functions import TruncDate

    rows = (
        qs.annotate(date=TruncDate("created_at"))
        .values("date")
        .annotate(count=Count("id"))
        .order_by("-date")[:30]
    )
    return JsonResponse(
        {
            "user": user.username,
            "tag": params.get("tag", ""),
            "dates": {str(r["date"]): r["count"] for r in rows},
        }
    )


# ---------------------------------------------------------------------------
# Tag endpoints
# ---------------------------------------------------------------------------


@_ALLOW
@_api_auth
def tags_get(request):
    from django.db.models import Func, IntegerField
    from django.db.models.functions import Unnest

    user = request.api_user
    rows = (
        Bookmark.objects.filter(user=user)
        .annotate(tag=Unnest("tags"))
        .values("tag")
        .annotate(count=Count("id"))
        .order_by("tag")
    )
    return JsonResponse({r["tag"]: r["count"] for r in rows})


@_ALLOW
@_api_auth
def tags_rename(request):
    user = request.api_user
    params = request.GET if request.method == "GET" else request.POST
    old = params.get("old", "").strip()
    new = params.get("new", "").strip().lower()
    if not old or not new:
        return _result_error("old and new are required")

    for bm in Bookmark.objects.filter(user=user, tags__contains=[old]):
        tags = [new if t == old else t for t in bm.tags]
        bm.tags = sorted(set(tags))
        bm.save(update_fields=["tags"])

    return _result_done()


@_ALLOW
@_api_auth
def tags_delete(request):
    user = request.api_user
    params = request.GET if request.method == "GET" else request.POST
    tag = params.get("tag", "").strip()
    if not tag:
        return _result_error("tag is required")

    for bm in Bookmark.objects.filter(user=user, tags__contains=[tag]):
        bm.tags = [t for t in bm.tags if t != tag]
        bm.save(update_fields=["tags"])

    return _result_done()


# ---------------------------------------------------------------------------
# User endpoints
# ---------------------------------------------------------------------------


@_ALLOW
@_api_auth
def user_api_token(request):
    user = request.api_user
    token = APIToken.objects.filter(user=user).first()
    if not token:
        return JsonResponse({"result": f"{user.id}:no_token_set"})
    return JsonResponse({"result": f"{user.id}:{token.token}"})
