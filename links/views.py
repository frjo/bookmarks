from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.postgres.search import SearchQuery, SearchRank
from django.core.paginator import Paginator
from django.db.models import F
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django_ratelimit.decorators import ratelimit

from .forms import BookmarkForm
from .importexport import (
    export_json,
    export_netscape,
    import_netscape,
    import_pinboard_json,
)
from .models import Bookmark


def index(request):
    if not request.user.is_authenticated:
        return redirect("login")
    return redirect("user_bookmark_list", slug=request.user.slug)


@login_required
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def bookmark_add(request, slug: str = ""):
    if request.method == "POST":
        form = BookmarkForm(request.POST)
        if form.is_valid():
            bookmark = form.save(commit=False)
            bookmark.user = request.user
            bookmark.save()
            return redirect("user_bookmark_list", slug=request.user.slug)
    else:
        initial = {
            "url": request.GET.get("url", ""),
            "title": request.GET.get("title", ""),
        }
        form = BookmarkForm(initial=initial)
    return render(request, "links/form.html", {"form": form, "action": "Add bookmark"})


@login_required
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def bookmark_edit(request, slug: str = "", *, pk):
    bookmark = get_object_or_404(Bookmark, pk=pk, user=request.user)
    if request.method == "POST":
        form = BookmarkForm(request.POST, instance=bookmark)
        if form.is_valid():
            form.save()
            return redirect("user_bookmark_list", slug=request.user.slug)
    else:
        form = BookmarkForm(instance=bookmark)
    return render(
        request,
        "links/form.html",
        {"form": form, "action": "Edit bookmark", "bookmark": bookmark},
    )


@login_required
@ratelimit(key="user", rate=settings.DEFAULT_RATE_LIMIT)
def bookmark_delete(request, slug: str = "", *, pk):
    bookmark = get_object_or_404(Bookmark, pk=pk, user=request.user)
    if request.method == "POST":
        bookmark.delete()
        return redirect("user_bookmark_list", slug=request.user.slug)
    return render(request, "links/confirm_delete.html", {"bookmark": bookmark})


@login_required
@ratelimit(key="user", rate="10/h")
def bookmark_import(request, slug: str = ""):
    if request.method == "POST":
        uploaded = request.FILES.get("file")
        if not uploaded:
            return render(request, "links/import.html", {"error": "No file selected."})

        try:
            content = uploaded.read().decode("utf-8", errors="replace")
        except Exception:
            return render(
                request, "links/import.html", {"error": "Could not read the file."}
            )

        if uploaded.name.lower().endswith(".json"):
            created, skipped = import_pinboard_json(content, request.user)
        else:
            created, skipped = import_netscape(content, request.user)

        return render(
            request,
            "links/import.html",
            {"done": True, "created": created, "skipped": skipped},
        )
    return render(request, "links/import.html", {})


@login_required
@ratelimit(key="user", rate="20/h")
def bookmark_export(request, slug: str = ""):
    fmt = request.GET.get("format", "html")
    bookmarks = Bookmark.objects.filter(user=request.user).order_by("-created_at")

    if fmt == "json":
        content = export_json(bookmarks)
        response = HttpResponse(content, content_type="application/json; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="bookmarks.json"'
    else:
        content = export_netscape(bookmarks)
        response = HttpResponse(content, content_type="text/html; charset=utf-8")
        response["Content-Disposition"] = 'attachment; filename="bookmarks.html"'

    return response


@login_required
def user_bookmark_list(request, slug: str = ""):
    user = request.user
    tag = request.GET.get("tag", "").strip()
    query = request.GET.get("q", "").strip()

    qs = Bookmark.objects.filter(user=user)

    if query:
        search_query = SearchQuery(query)
        qs = (
            qs.filter(search_vector=search_query)
            .annotate(rank=SearchRank(F("search_vector"), search_query))
            .order_by("-rank", "-created_at")
        )
    elif tag:
        qs = qs.filter(tags__contains=[tag])

    paginator = Paginator(qs, settings.BOOKMARKS_PER_PAGE)
    page_obj = paginator.get_page(request.GET.get("page", 1))

    context = {
        "user": user,
        "page_obj": page_obj,
        "query": query,
        "tag": tag,
        "total": paginator.count,
    }

    if request.htmx:
        return render(request, "links/_list_partial.html", context)
    return render(request, "links/list.html", context)
