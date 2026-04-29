"""Pinboard-compatible JSON API (v2).

Authentication
--------------
Pass the API token as exactly one of:
  - Query parameter: ?auth_token=user_id:TOKEN
  - HTTP header:     X-Auth-Token: user_id:TOKEN

Supplying both simultaneously returns a 400 error.

Endpoints
---------
GET          /api/v2/posts/get        Return bookmarks (filter by URL, tag, date).
GET          /api/v2/posts/recent     Most-recent bookmarks.
GET          /api/v2/posts/all        All bookmarks with optional filters.
GET/POST/PUT /api/v2/posts/add        Add or update a bookmark.
GET/DELETE   /api/v2/posts/delete     Delete a bookmark.
GET          /api/v2/posts/dates      Number of bookmarks per date.
GET          /api/v2/tags/get         All tags with counts.
GET/POST/PUT /api/v2/tags/rename      Rename a tag.
GET/DELETE   /api/v2/tags/delete      Delete a tag.
GET          /api/v2/user/api_token   Return current token.

All responses are JSON: {"status": "ok|error", ...}.
Errors include "error", "error_code", and "error_message" fields.
"""

import datetime
import hashlib
from functools import wraps

import nh3
from django.conf import settings
from django.db.models import Count
from django.http import JsonResponse
from django.utils import timezone
from django.utils.translation import gettext as _
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from accounts.models import APIToken
from links.cache import get_posts_dates, invalidate_user_caches
from links.models import Bookmark

_READ = require_http_methods(["GET"])
_WRITE = require_http_methods(["GET", "POST", "PUT"])
_DELETE = require_http_methods(["GET", "DELETE"])


# ---------------------------------------------------------------------------
# Response helpers
# ---------------------------------------------------------------------------


def _ok(data: dict | None = None) -> JsonResponse:
    payload = {"status": "ok"}
    if data:
        payload.update(data)
    return JsonResponse(payload)


def _error(error: str, message: str, status: int = 400) -> JsonResponse:
    return JsonResponse(
        {
            "status": "error",
            "error": error,
            "error_code": str(status),
            "error_message": message,
        },
        status=status,
    )


def _url_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()  # noqa: S324


def _bookmark_meta(bm: Bookmark) -> str:
    raw = f"{bm.url}{bm.updated_at.isoformat()}"
    return hashlib.md5(raw.encode()).hexdigest()  # noqa: S324


def _serialize(bm: Bookmark) -> dict:
    return {
        "href": bm.url,
        "description": bm.title,
        "extended": bm.description,
        "meta": _bookmark_meta(bm),
        "hash": _url_hash(bm.url),
        "time": bm.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "shared": 1 if bm.shared else 0,
        "toread": 1 if bm.toread else 0,
        "tags": " ".join(bm.tags),
    }


# ---------------------------------------------------------------------------
# Auth decorator — user_id:token, query param or X-Auth-Token header
# ---------------------------------------------------------------------------


def _api_auth(view_func):
    @wraps(view_func)
    @csrf_exempt
    def wrapper(request, *args, **kwargs):
        param_token = request.GET.get("auth_token") or request.POST.get("auth_token")
        header_token = request.headers.get("X-Auth-Token")

        if param_token and header_token:
            return _error(
                "too_much_auth", _("Supply auth_token or X-Auth-Token, not both"), 400
            )

        auth_token = param_token or header_token
        if not auth_token or ":" not in auth_token:
            return _error("no_auth_token", _("Authentication required"), 401)

        user_id, _sep, token = auth_token.partition(":")
        try:
            record = APIToken.objects.select_related("user").get(
                user__id=user_id, token=token
            )
        except APIToken.DoesNotExist:
            return _error("unauthorized", _("Invalid auth token"), 401)

        request.api_user = record.user
        request.api_token = record.token
        # Set request.user so @ratelimit(key="user") can key per API user.
        request.user = record.user
        return view_func(request, *args, **kwargs)

    return wrapper


def _params(request):
    """Return the appropriate parameter dict for the request method."""
    if request.method in ("POST", "PUT"):
        return request.POST
    return request.GET


# ---------------------------------------------------------------------------
# posts/get
# ---------------------------------------------------------------------------


@_READ
@_api_auth
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def posts_get(request):
    """Return bookmarks matching URL, tags, and/or date."""
    user = request.api_user
    params = _params(request)

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

    return _ok(
        {
            "date": timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "user": user.username,
            "posts": [_serialize(bm) for bm in qs],
        }
    )


# ---------------------------------------------------------------------------
# posts/recent
# ---------------------------------------------------------------------------


@_READ
@_api_auth
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def posts_recent(request):
    user = request.api_user
    params = _params(request)

    try:
        count = min(int(params.get("count", 15)), 100)
    except ValueError:
        count = 15

    tag_str = params.get("tag", "")
    qs = Bookmark.objects.filter(user=user)
    if tag_str:
        for tag in tag_str.split()[:3]:
            qs = qs.filter(tags__contains=[tag])
    qs = qs.order_by("-created_at")[:count]

    return _ok(
        {
            "date": timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
            "user": user.username,
            "posts": [_serialize(bm) for bm in qs],
        }
    )


# ---------------------------------------------------------------------------
# posts/all
# ---------------------------------------------------------------------------


@_READ
@_api_auth
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def posts_all(request):
    user = request.api_user
    params = _params(request)

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

    try:
        start = int(params.get("start", 0))
        results = min(int(params.get("results", 10_000)), 10_000)
    except ValueError:
        start, results = 0, 10_000

    qs = qs.order_by("-created_at")[start : start + results]

    # Conditional request support
    if_modified = request.headers.get("If-Modified-Since")
    if if_modified:
        latest = (
            Bookmark.objects.filter(user=user)
            .order_by("-updated_at")
            .values_list("updated_at", flat=True)
            .first()
        )
        if latest:
            try:
                from email.utils import parsedate_to_datetime

                since = parsedate_to_datetime(if_modified)
                if latest <= since:
                    from django.http import HttpResponse

                    return HttpResponse(status=304)
            except Exception:
                pass

    return _ok({"posts": [_serialize(bm) for bm in qs]})


# ---------------------------------------------------------------------------
# posts/add
# ---------------------------------------------------------------------------


@_WRITE
@_api_auth
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def posts_add(request):
    """Add or update a bookmark (matched by URL)."""
    user = request.api_user
    params = _params(request)

    url = params.get("url", "").strip()
    if not url:
        return _error("missing_url", _("url is required"))

    title = nh3.clean(params.get("description", "").strip(), tags=set())
    description = nh3.clean(params.get("extended", "").strip(), tags=set())
    tags_str = params.get("tags", "")
    tags = sorted(
        {
            nh3.clean(t.lower().strip(), tags=set())
            for t in tags_str.split()
            if t.strip()
        }
    )
    replace = params.get("replace", "yes").lower() not in ("no", "0")

    # Accept both yes/no and 1/0 for boolean params
    shared_raw = params.get("shared", "1")
    shared = shared_raw not in ("no", "0")

    toread_raw = params.get("toread", "0")
    toread = toread_raw in ("yes", "1")

    existing = Bookmark.objects.filter(user=user, url=url).first()
    if existing and not replace:
        return _ok({"result_code": "item already exists"})

    if existing:
        existing.title = title or existing.title
        existing.description = description
        existing.tags = tags
        existing.shared = shared
        existing.toread = toread
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
            shared=shared,
            toread=toread,
            **({"created_at": created_at} if created_at else {}),
        )

    invalidate_user_caches(user)
    return _ok({"result_code": "done"})


# ---------------------------------------------------------------------------
# posts/delete
# ---------------------------------------------------------------------------


@_DELETE
@_api_auth
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def posts_delete(request):
    user = request.api_user
    params = _params(request)
    url = params.get("url", "").strip()
    if not url:
        return _error("missing_url", _("url is required"))
    Bookmark.objects.filter(user=user, url=url).delete()
    invalidate_user_caches(user)
    return _ok({"result_code": "done"})


# ---------------------------------------------------------------------------
# posts/dates
# ---------------------------------------------------------------------------


@_READ
@_api_auth
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def posts_dates(request):
    user = request.api_user
    params = _params(request)
    tag_param = params.get("tag", "")
    dates = get_posts_dates(user, tag_param)
    return _ok({"user": user.username, "tag": tag_param, "dates": dates})


# ---------------------------------------------------------------------------
# tags/get
# ---------------------------------------------------------------------------


@_READ
@_api_auth
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def tags_get(request):
    from links.models import Unnest

    user = request.api_user
    rows = (
        Bookmark.objects.filter(user=user)
        .annotate(tag=Unnest("tags"))
        .values("tag")
        .annotate(count=Count("id"))
        .order_by("tag")
    )
    return _ok({"tags": {r["tag"]: r["count"] for r in rows}})


# ---------------------------------------------------------------------------
# tags/rename
# ---------------------------------------------------------------------------


@_WRITE
@_api_auth
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def tags_rename(request):
    user = request.api_user
    params = _params(request)
    old = params.get("old", "").strip()
    new = nh3.clean(params.get("new", "").strip().lower(), tags=set())
    if not old or not new:
        return _error("missing_params", _("old and new are required"))

    for bm in Bookmark.objects.filter(user=user, tags__contains=[old]):
        bm.tags = sorted({new if t == old else t for t in bm.tags})
        bm.save(update_fields=["tags"])

    invalidate_user_caches(user)
    return _ok({"result_code": "done"})


# ---------------------------------------------------------------------------
# tags/delete
# ---------------------------------------------------------------------------


@_DELETE
@_api_auth
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def tags_delete(request):
    user = request.api_user
    params = _params(request)
    tag = params.get("tag", "").strip()
    if not tag:
        return _error("missing_tag", _("tag is required"))

    for bm in Bookmark.objects.filter(user=user, tags__contains=[tag]):
        bm.tags = [t for t in bm.tags if t != tag]
        bm.save(update_fields=["tags"])

    invalidate_user_caches(user)
    return _ok({"result_code": "done"})


# ---------------------------------------------------------------------------
# user/api_token
# ---------------------------------------------------------------------------


@_READ
@_api_auth
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def user_api_token(request):
    user = request.api_user
    return _ok({"result": f"{user.id}:{request.api_token}"})
