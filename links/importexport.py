"""Import and export bookmarks.

Supported formats
-----------------
Import:  Netscape HTML bookmark file (standard browser export),
         Pinboard JSON export.
Export:  Netscape HTML, JSON (Pinboard-compatible).
"""

import datetime
import html as html_module
import json
from html.parser import HTMLParser

import nh3
from django.contrib.postgres.search import SearchVector
from django.utils import timezone

# ---------------------------------------------------------------------------
# Netscape HTML parser
# ---------------------------------------------------------------------------


class _NetscapeParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.bookmarks: list[dict] = []
        self._pending: dict | None = None
        self._in_a = False
        self._in_dd = False

    # ------------------------------------------------------------------
    def _flush_pending(self):
        if self._pending and self._pending["url"]:
            bm = self._pending.copy()
            bm["title"] = bm["title"].strip() or bm["url"]
            bm["description"] = bm["description"].strip()
            self.bookmarks.append(bm)
        self._pending = None

    def handle_starttag(self, tag, attrs):
        tag = tag.lower()
        attrs_dict = dict(attrs)
        if tag == "dt":
            self._flush_pending()
            self._in_a = False
            self._in_dd = False
        elif tag == "a":
            self._flush_pending()
            tags_str = attrs_dict.get("tags", "")
            tags = [t.lower().strip() for t in tags_str.split(",") if t.strip()]
            self._pending = {
                "url": attrs_dict.get("href", "").strip(),
                "title": "",
                "description": "",
                "tags": tags,
                "add_date": attrs_dict.get("add_date", ""),
            }
            self._in_a = True
            self._in_dd = False
        elif tag == "dd" and self._pending:
            self._in_a = False
            self._in_dd = True

    def handle_data(self, data):
        if not self._pending:
            return
        if self._in_a:
            self._pending["title"] += data
        elif self._in_dd:
            self._pending["description"] += data

    def handle_endtag(self, tag):
        tag = tag.lower()
        if tag == "a":
            self._in_a = False
        elif tag in ("dl", "body", "html"):
            self._flush_pending()
            self._in_dd = False

    def close(self):
        super().close()
        self._flush_pending()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _parse_add_date(value: str) -> datetime.datetime:
    try:
        ts = int(value)
        return datetime.datetime.fromtimestamp(ts, tz=datetime.timezone.utc)
    except (ValueError, TypeError, OSError):
        return timezone.now()


def _parse_pinboard_time(value: str) -> datetime.datetime:
    try:
        return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return timezone.now()


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------


def _update_search_vectors(bookmarks) -> None:
    if not bookmarks:
        return
    from .models import Bookmark

    pks = [b.pk for b in bookmarks]
    Bookmark.objects.filter(pk__in=pks).update(
        search_vector=(
            SearchVector("title", weight="A")
            + SearchVector("description", weight="B")
            + SearchVector("url", weight="C")
        )
    )


def import_netscape(content: str, user) -> tuple[int, int]:
    """Parse a Netscape HTML bookmark file and create Bookmark objects.

    Returns ``(created, skipped)`` counts.
    """
    from .models import Bookmark

    parser = _NetscapeParser()
    parser.feed(content)

    existing_urls = set(
        Bookmark.objects.filter(user=user).values_list("url", flat=True)
    )
    seen_urls: set[str] = set()
    to_create = []
    skipped = 0
    for item in parser.bookmarks:
        url = item["url"][:500]
        if not url or url in existing_urls or url in seen_urls:
            skipped += 1
            continue
        seen_urls.add(url)
        tags = [nh3.clean(t, tags=set()) for t in item["tags"] if t]
        to_create.append(
            Bookmark(
                user=user,
                url=url,
                title=nh3.clean(item["title"], tags=set())[:500],
                description=nh3.clean(item["description"], tags=set())[:2000],
                tags=tags,
                created_at=_parse_add_date(item["add_date"]),
            )
        )

    created_objs = Bookmark.objects.bulk_create(to_create)
    _update_search_vectors(created_objs)
    return len(created_objs), skipped


def import_pinboard_json(content: str, user) -> tuple[int, int]:
    """Parse a Pinboard JSON export and create Bookmark objects.

    Returns ``(created, skipped)`` counts.
    """
    from .models import Bookmark

    try:
        items = json.loads(content)
    except (json.JSONDecodeError, ValueError):
        return 0, 0

    existing_urls = set(
        Bookmark.objects.filter(user=user).values_list("url", flat=True)
    )
    seen_urls: set[str] = set()
    to_create = []
    skipped = 0
    for item in items:
        url = item.get("href", "").strip()[:500]
        if not url or url in existing_urls or url in seen_urls:
            skipped += 1
            continue
        seen_urls.add(url)
        tags_str = item.get("tags", "")
        tags = [
            nh3.clean(t.strip().lower(), tags=set())
            for t in tags_str.split()
            if t.strip()
        ]
        to_create.append(
            Bookmark(
                user=user,
                url=url,
                title=nh3.clean(item.get("description", url), tags=set())[:500],
                description=nh3.clean(item.get("extended", ""), tags=set())[:2000],
                tags=tags,
                created_at=_parse_pinboard_time(item.get("time", "")),
            )
        )

    created_objs = Bookmark.objects.bulk_create(to_create)
    _update_search_vectors(created_objs)
    return len(created_objs), skipped


# ---------------------------------------------------------------------------
# Export
# ---------------------------------------------------------------------------


def export_netscape(bookmarks) -> str:
    """Serialise bookmarks as a Netscape HTML bookmark file."""
    lines = [
        "<!DOCTYPE NETSCAPE-Bookmark-file-1>",
        '<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">',
        "<TITLE>Bookmarks</TITLE>",
        "<H1>Bookmarks</H1>",
        "<DL><p>",
    ]
    for bm in bookmarks:
        tags = html_module.escape(",".join(bm.tags), quote=True)
        url = html_module.escape(bm.url, quote=True)
        title = html_module.escape(bm.title or bm.url)
        timestamp = int(bm.created_at.timestamp())
        lines.append(
            f'    <DT><A HREF="{url}" ADD_DATE="{timestamp}" TAGS="{tags}">{title}</A>'
        )
        if bm.description:
            lines.append(f"    <DD>{html_module.escape(bm.description)}")
    lines.append("</DL><p>")
    return "\n".join(lines)


def export_json(bookmarks) -> str:
    """Serialise bookmarks as Pinboard-compatible JSON."""
    result = [
        {
            "href": bm.url,
            "description": bm.title,
            "extended": bm.description,
            "meta": "",
            "hash": "",
            "time": bm.created_at.isoformat(),
            "shared": "no",
            "toread": "no",
            "tags": " ".join(bm.tags),
        }
        for bm in bookmarks
    ]
    return json.dumps(result, indent=2, ensure_ascii=False)
