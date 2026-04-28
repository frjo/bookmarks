"""Pinboard-compatible JSON/XML API (v1).

Authentication
--------------
Token-based: ?auth_token=username:TOKEN

Endpoints
---------
GET  /api/v1/posts/update      Timestamp of last bookmark change.
GET  /api/v1/posts/add         Add or update a bookmark.
GET  /api/v1/posts/delete      Delete a bookmark.
GET  /api/v1/posts/get         Return bookmarks matching criteria.
GET  /api/v1/posts/recent      Most-recent bookmarks.
GET  /api/v1/posts/all         All bookmarks with optional filters.
GET  /api/v1/posts/dates       Number of bookmarks per date.
GET  /api/v1/posts/suggest     Suggested tags for a URL.
GET  /api/v1/tags/get          All tags with counts.
GET  /api/v1/tags/delete       Delete a tag.
GET  /api/v1/tags/rename       Rename a tag.
GET  /api/v1/user/secret       RSS secret key.
GET  /api/v1/user/api_token    API token.
GET  /api/v1/notes/list        All notes (not supported — returns empty list).
GET  /api/v1/notes/<id>        Single note (not supported — returns 404).

All methods accept both GET and POST.
Responses are XML by default; pass ?format=json for JSON.
"""

import datetime
import hashlib
import hmac
from functools import wraps
from xml.etree.ElementTree import Element, SubElement, tostring

import nh3
from django.conf import settings
from django.db.models import Count
from django.http import HttpResponse, JsonResponse
from django.utils import timezone
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django_ratelimit.decorators import ratelimit

from accounts.models import APIToken
from links.models import Bookmark

_ALLOW = require_http_methods(["GET", "POST"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _xml_response(root: Element) -> HttpResponse:
    xml = tostring(root, encoding="unicode")
    return HttpResponse(
        f'<?xml version="1.0" encoding="UTF-8" ?>\n{xml}',
        content_type="text/xml; charset=utf-8",
    )


def _fmt(request) -> str:
    params = request.GET if request.method == "GET" else request.POST
    return (params.get("format") or "xml").lower()


def _result_done(request) -> HttpResponse:
    if _fmt(request) == "json":
        return JsonResponse({"result_code": "done"})
    root = Element("result", code="done")
    return _xml_response(root)


def _result_error(request, msg: str, status: int = 400) -> HttpResponse:
    if _fmt(request) == "json":
        return JsonResponse({"result_code": msg}, status=status)
    root = Element("result", code=msg)
    return HttpResponse(
        f'<?xml version="1.0" encoding="UTF-8" ?>\n{tostring(root, encoding="unicode")}',
        content_type="text/xml; charset=utf-8",
        status=status,
    )


def _url_hash(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()  # noqa: S324


def _bookmark_meta(bm: Bookmark) -> str:
    """Derive a change-detection hash from the bookmark's updated_at."""
    raw = f"{bm.url}{bm.updated_at.isoformat()}"
    return hashlib.md5(raw.encode()).hexdigest()  # noqa: S324


def _serialize_post(bm: Bookmark, *, include_meta: bool = False) -> dict:
    data = {
        "href": bm.url,
        "description": bm.title,
        "extended": bm.description,
        "meta": _bookmark_meta(bm) if include_meta else "",
        "hash": _url_hash(bm.url),
        "time": bm.created_at.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "shared": "yes" if bm.shared else "no",
        "toread": "yes" if bm.toread else "no",
        "tags": " ".join(bm.tags),
    }
    return data


def _post_element(bm: Bookmark, *, include_meta: bool = False) -> Element:
    attrs = _serialize_post(bm, include_meta=include_meta)
    # count how many other users have bookmarked the same URL
    others = (
        Bookmark.objects.filter(url=bm.url, shared=True).exclude(user=bm.user).count()
    )
    attrs["others"] = str(others)
    return Element("post", **attrs)


def _rss_secret(token_str: str) -> str:
    return hmac.new(token_str.encode(), b"rss", hashlib.sha256).hexdigest()[:20]


# ---------------------------------------------------------------------------
# Auth decorator — username:token format
# ---------------------------------------------------------------------------


def _api_auth(view_func):
    @wraps(view_func)
    @csrf_exempt
    def wrapper(request, *args, **kwargs):
        params = request.GET if request.method == "GET" else request.POST
        auth_token = params.get("auth_token")
        if not auth_token or ":" not in auth_token:
            return _result_error(request, "authentication required", 401)
        username, _, token = auth_token.partition(":")
        try:
            record = APIToken.objects.select_related("user").get(
                user__username=username, token=token
            )
        except APIToken.DoesNotExist:
            return _result_error(request, "invalid token", 401)
        request.api_user = record.user
        request.api_token = record.token
        # Set request.user so @ratelimit(key="user") can key per API user.
        request.user = record.user
        return view_func(request, *args, **kwargs)

    return wrapper


# ---------------------------------------------------------------------------
# posts/update
# ---------------------------------------------------------------------------


@_ALLOW
@_api_auth
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def posts_update(request):
    """Return the timestamp of the most recent bookmark change."""
    latest = (
        Bookmark.objects.filter(user=request.api_user)
        .order_by("-updated_at")
        .values_list("updated_at", flat=True)
        .first()
    )
    ts = (latest or timezone.now()).strftime("%Y-%m-%dT%H:%M:%SZ")
    if _fmt(request) == "json":
        return JsonResponse({"update_time": ts})
    root = Element("update", time=ts)
    return _xml_response(root)


# ---------------------------------------------------------------------------
# posts/add
# ---------------------------------------------------------------------------


@_ALLOW
@_api_auth
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def posts_add(request):
    """Add or update a bookmark (matched by URL)."""
    user = request.api_user
    params = request.GET if request.method == "GET" else request.POST

    url = params.get("url", "").strip()
    if not url:
        return _result_error(request, "url is required")

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
    replace = params.get("replace", "yes").lower() != "no"
    shared = params.get("shared", "yes").lower() != "no"
    toread = params.get("toread", "no").lower() == "yes"

    existing = Bookmark.objects.filter(user=user, url=url).first()
    if existing and not replace:
        return _result_error(request, "item already exists")

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

    return _result_done(request)


# ---------------------------------------------------------------------------
# posts/delete
# ---------------------------------------------------------------------------


@_ALLOW
@_api_auth
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def posts_delete(request):
    user = request.api_user
    params = request.GET if request.method == "GET" else request.POST
    url = params.get("url", "").strip()
    if not url:
        return _result_error(request, "url is required")
    deleted, _ = Bookmark.objects.filter(user=user, url=url).delete()
    if not deleted:
        return _result_error(request, "item not found", 404)
    return _result_done(request)


# ---------------------------------------------------------------------------
# posts/get
# ---------------------------------------------------------------------------


@_ALLOW
@_api_auth
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def posts_get(request):
    """Return bookmarks matching URL, tags, and/or date."""
    user = request.api_user
    params = request.GET if request.method == "GET" else request.POST
    include_meta = params.get("meta", "no").lower() == "yes"

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

    qs = qs.order_by("-created_at")
    tag_param = params.get("tag", "")
    dt_param = params.get("dt", timezone.now().strftime("%Y-%m-%d"))

    if _fmt(request) == "json":
        return JsonResponse(
            {
                "date": dt_param,
                "user": user.username,
                "posts": [_serialize_post(bm, include_meta=include_meta) for bm in qs],
            }
        )

    root = Element("posts", dt=dt_param, tag=tag_param, user=user.username)
    for bm in qs:
        root.append(_post_element(bm, include_meta=include_meta))
    return _xml_response(root)


# ---------------------------------------------------------------------------
# posts/recent
# ---------------------------------------------------------------------------


@_ALLOW
@_api_auth
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def posts_recent(request):
    user = request.api_user
    params = request.GET if request.method == "GET" else request.POST

    try:
        count = min(int(params.get("count", 15)), 100)
    except ValueError:
        count = 15

    tag_param = params.get("tag", "")
    qs = Bookmark.objects.filter(user=user)
    if tag_param:
        for tag in tag_param.split()[:3]:
            qs = qs.filter(tags__contains=[tag])
    qs = qs.order_by("-created_at")[:count]
    total = Bookmark.objects.filter(user=user).count()

    if _fmt(request) == "json":
        return JsonResponse(
            {
                "date": timezone.now().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "user": user.username,
                "posts": [_serialize_post(bm) for bm in qs],
            }
        )

    root = Element("posts", tag=tag_param, total=str(total), user=user.username)
    for bm in qs:
        root.append(_post_element(bm))
    return _xml_response(root)


# ---------------------------------------------------------------------------
# posts/all
# ---------------------------------------------------------------------------


@_ALLOW
@_api_auth
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def posts_all(request):
    user = request.api_user
    params = request.GET if request.method == "GET" else request.POST
    include_meta = params.get("meta", "no").lower() == "yes"

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

    if _fmt(request) == "json":
        return JsonResponse(
            [_serialize_post(bm, include_meta=include_meta) for bm in qs],
            safe=False,
        )

    root = Element("posts")
    for bm in qs:
        root.append(_post_element(bm, include_meta=include_meta))
    return _xml_response(root)


# ---------------------------------------------------------------------------
# posts/dates
# ---------------------------------------------------------------------------


@_ALLOW
@_api_auth
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def posts_dates(request):
    user = request.api_user
    params = request.GET if request.method == "GET" else request.POST
    tag_param = params.get("tag", "")

    qs = Bookmark.objects.filter(user=user)
    if tag_param:
        for tag in tag_param.split():
            qs = qs.filter(tags__contains=[tag])

    from django.db.models.functions import TruncDate

    rows = (
        qs.annotate(date=TruncDate("created_at"))
        .values("date")
        .annotate(count=Count("id"))
        .order_by("-date")
    )

    if _fmt(request) == "json":
        return JsonResponse(
            {
                "user": user.username,
                "tag": tag_param,
                "dates": {str(r["date"]): r["count"] for r in rows},
            }
        )

    root = Element("dates", tag=tag_param, user=user.username)
    for r in rows:
        SubElement(root, "date", date=str(r["date"]), count=str(r["count"]))
    return _xml_response(root)


# ---------------------------------------------------------------------------
# posts/suggest
# ---------------------------------------------------------------------------


@_ALLOW
@_api_auth
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def posts_suggest(request):
    """Return popular (site-wide) and recommended (personal) tags for a URL."""
    user = request.api_user
    params = request.GET if request.method == "GET" else request.POST
    url = params.get("url", "").strip()

    from links.models import Unnest

    # Popular: tags used for this URL across all users, sorted by frequency
    popular_rows = (
        Bookmark.objects.filter(url=url, shared=True)
        .annotate(tag=Unnest("tags"))
        .values("tag")
        .annotate(count=Count("id"))
        .order_by("-count")[:100]
    )
    popular = [r["tag"] for r in popular_rows]

    # Recommended: user's own tags for this URL, falling back to their top tags
    user_bm = Bookmark.objects.filter(user=user, url=url).first()
    if user_bm:
        recommended = user_bm.tags
    else:
        rec_rows = (
            Bookmark.objects.filter(user=user)
            .annotate(tag=Unnest("tags"))
            .values("tag")
            .annotate(count=Count("id"))
            .order_by("-count")[:100]
        )
        recommended = [r["tag"] for r in rec_rows]

    if _fmt(request) == "json":
        return JsonResponse(
            [{"popular": popular}, {"recommended": recommended}],
            safe=False,
        )

    root = Element("suggest")
    for tag in popular:
        el = SubElement(root, "popular")
        el.text = tag
    for tag in recommended:
        el = SubElement(root, "recommended")
        el.text = tag
    return _xml_response(root)


# ---------------------------------------------------------------------------
# tags/get
# ---------------------------------------------------------------------------


@_ALLOW
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

    if _fmt(request) == "json":
        return JsonResponse({r["tag"]: str(r["count"]) for r in rows})

    root = Element("tags")
    for r in rows:
        SubElement(root, "tag", tag=r["tag"], count=str(r["count"]))
    return _xml_response(root)


# ---------------------------------------------------------------------------
# tags/delete
# ---------------------------------------------------------------------------


@_ALLOW
@_api_auth
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def tags_delete(request):
    user = request.api_user
    params = request.GET if request.method == "GET" else request.POST
    tag = params.get("tag", "").strip()
    if not tag:
        return _result_error(request, "tag is required")

    for bm in Bookmark.objects.filter(user=user, tags__contains=[tag]):
        bm.tags = [t for t in bm.tags if t != tag]
        bm.save(update_fields=["tags"])

    return _result_done(request)


# ---------------------------------------------------------------------------
# tags/rename
# ---------------------------------------------------------------------------


@_ALLOW
@_api_auth
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def tags_rename(request):
    user = request.api_user
    params = request.GET if request.method == "GET" else request.POST
    old = params.get("old", "").strip()
    new = nh3.clean(params.get("new", "").strip().lower(), tags=set())
    if not old or not new:
        return _result_error(request, "old and new are required")

    for bm in Bookmark.objects.filter(user=user, tags__contains=[old]):
        tags = [new if t == old else t for t in bm.tags]
        bm.tags = sorted(set(tags))
        bm.save(update_fields=["tags"])

    return _result_done(request)


# ---------------------------------------------------------------------------
# user/secret
# ---------------------------------------------------------------------------


@_ALLOW
@_api_auth
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def user_secret(request):
    secret = _rss_secret(request.api_token)
    if _fmt(request) == "json":
        return JsonResponse({"result": secret})
    root = Element("result", code=secret)
    return _xml_response(root)


# ---------------------------------------------------------------------------
# user/api_token
# ---------------------------------------------------------------------------


@_ALLOW
@_api_auth
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def user_api_token(request):
    user = request.api_user
    result = f"{user.username}:{request.api_token}"
    if _fmt(request) == "json":
        return JsonResponse({"result": result})
    root = Element("result", code=result)
    return _xml_response(root)


# ---------------------------------------------------------------------------
# notes/list
# ---------------------------------------------------------------------------


@_ALLOW
@_api_auth
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def notes_list(request):
    user = request.api_user
    if _fmt(request) == "json":
        return JsonResponse({"count": 0, "notes": []})
    root = Element("notes", count="0", user=user.username)
    return _xml_response(root)


# ---------------------------------------------------------------------------
# notes/<id>
# ---------------------------------------------------------------------------


@_ALLOW
@_api_auth
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def notes_detail(request, note_id):
    return _result_error(request, "note not found", 404)
