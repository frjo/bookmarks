import json

import pytest

from links.importexport import (
    export_json,
    export_netscape,
    import_netscape,
    import_pinboard_json,
)
from links.models import Bookmark

NETSCAPE_HTML = """\
<!DOCTYPE NETSCAPE-Bookmark-file-1>
<META HTTP-EQUIV="Content-Type" CONTENT="text/html; charset=UTF-8">
<TITLE>Bookmarks</TITLE>
<H1>Bookmarks</H1>
<DL><p>
    <DT><A HREF="https://example.com" ADD_DATE="1609459200" TAGS="python,web">Example</A>
    <DD>An example bookmark
    <DT><A HREF="https://second.com" ADD_DATE="1609545600" TAGS="">Second</A>
</DL><p>
"""

PINBOARD_JSON = json.dumps(
    [
        {
            "href": "https://pinboard.com",
            "description": "Pinboard",
            "extended": "Extended description",
            "tags": "python django",
            "time": "2021-01-01T00:00:00Z",
        },
        {
            "href": "https://other.com",
            "description": "Other",
            "extended": "",
            "tags": "",
            "time": "2021-02-01T00:00:00Z",
        },
    ]
)


@pytest.mark.django_db
class TestImportNetscape:
    def test_creates_bookmarks(self, user):
        created, skipped = import_netscape(NETSCAPE_HTML, user)
        assert created == 2
        assert skipped == 0
        assert Bookmark.objects.filter(user=user).count() == 2

    def test_stores_tags(self, user):
        import_netscape(NETSCAPE_HTML, user)
        bm = Bookmark.objects.get(user=user, url="https://example.com")
        assert "python" in bm.tags
        assert "web" in bm.tags

    def test_stores_description(self, user):
        import_netscape(NETSCAPE_HTML, user)
        bm = Bookmark.objects.get(user=user, url="https://example.com")
        assert "example" in bm.description.lower()

    def test_skips_duplicate_urls(self, user):
        import_netscape(NETSCAPE_HTML, user)
        created, skipped = import_netscape(NETSCAPE_HTML, user)
        assert created == 0
        assert skipped == 2

    def test_skips_empty_url(self, user):
        # Parser silently drops items with empty HREF before they reach the counter
        html = '<DL><p><DT><A HREF="">No URL</A></DL><p>'
        created, skipped = import_netscape(html, user)
        assert created == 0
        assert skipped == 0

    def test_title_falls_back_to_url(self, user):
        html = '<DL><p><DT><A HREF="https://notitle.com" ADD_DATE="0"></A></DL><p>'
        import_netscape(html, user)
        bm = Bookmark.objects.get(user=user, url="https://notitle.com")
        assert bm.title == "https://notitle.com"


@pytest.mark.django_db
class TestImportPinboardJson:
    def test_creates_bookmarks(self, user):
        created, skipped = import_pinboard_json(PINBOARD_JSON, user)
        assert created == 2
        assert skipped == 0

    def test_stores_tags(self, user):
        import_pinboard_json(PINBOARD_JSON, user)
        bm = Bookmark.objects.get(user=user, url="https://pinboard.com")
        assert "python" in bm.tags
        assert "django" in bm.tags

    def test_stores_extended(self, user):
        import_pinboard_json(PINBOARD_JSON, user)
        bm = Bookmark.objects.get(user=user, url="https://pinboard.com")
        assert bm.description == "Extended description"

    def test_skips_duplicates(self, user):
        import_pinboard_json(PINBOARD_JSON, user)
        created, skipped = import_pinboard_json(PINBOARD_JSON, user)
        assert created == 0
        assert skipped == 2

    def test_invalid_json_returns_zeros(self, user):
        created, skipped = import_pinboard_json("not valid json", user)
        assert created == 0
        assert skipped == 0

    def test_skips_missing_href(self, user):
        data = json.dumps([{"description": "No URL", "tags": "", "time": ""}])
        created, skipped = import_pinboard_json(data, user)
        assert created == 0
        assert skipped == 1


@pytest.mark.django_db
class TestExportNetscape:
    def test_produces_netscape_header(self, user, bookmark):
        bookmarks = Bookmark.objects.filter(user=user)
        output = export_netscape(bookmarks)
        assert "NETSCAPE-Bookmark-file-1" in output

    def test_contains_bookmark_url(self, user, bookmark):
        bookmarks = Bookmark.objects.filter(user=user)
        output = export_netscape(bookmarks)
        assert bookmark.url in output

    def test_contains_tags(self, user):
        Bookmark.objects.create(
            user=user,
            url="https://tagged.com",
            title="Tagged",
            tags=["alpha", "beta"],
        )
        bookmarks = Bookmark.objects.filter(user=user)
        output = export_netscape(bookmarks)
        assert "alpha,beta" in output or "beta,alpha" in output

    def test_contains_description(self, user, bookmark):
        bookmarks = Bookmark.objects.filter(user=user)
        output = export_netscape(bookmarks)
        assert bookmark.description in output


@pytest.mark.django_db
class TestExportJson:
    def test_valid_json(self, user, bookmark):
        bookmarks = Bookmark.objects.filter(user=user)
        output = export_json(bookmarks)
        data = json.loads(output)
        assert isinstance(data, list)
        assert len(data) == 1

    def test_contains_bookmark_fields(self, user, bookmark):
        bookmarks = Bookmark.objects.filter(user=user)
        output = export_json(bookmarks)
        data = json.loads(output)
        item = data[0]
        assert item["href"] == bookmark.url
        assert item["description"] == bookmark.title
        assert item["extended"] == bookmark.description

    def test_tags_as_space_separated(self, user):
        Bookmark.objects.create(
            user=user,
            url="https://tagged.com",
            title="Tagged",
            tags=["alpha", "beta"],
        )
        bookmarks = Bookmark.objects.filter(user=user)
        output = export_json(bookmarks)
        data = json.loads(output)
        assert "alpha" in data[0]["tags"]
        assert "beta" in data[0]["tags"]
