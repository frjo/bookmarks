import io

import pytest
from django.urls import reverse

from links.models import Bookmark


@pytest.mark.django_db
class TestBookmarkList:
    def test_unauthenticated_redirects(self, client, user):
        response = client.get(reverse("bookmark_list", kwargs={"slug": user.slug}))
        assert response.status_code == 302

    def test_renders_for_authenticated(self, client, user, bookmark):
        client.force_login(user)
        response = client.get(reverse("bookmark_list", kwargs={"slug": user.slug}))
        assert response.status_code == 200

    def test_filter_by_tag(self, client, user):
        client.force_login(user)
        Bookmark.objects.create(
            user=user, url="https://a.com", title="A", tags=["python"]
        )
        Bookmark.objects.create(
            user=user, url="https://b.com", title="B", tags=["django"]
        )
        response = client.get(
            reverse("bookmark_list", kwargs={"slug": user.slug}), {"tag": "python"}
        )
        assert response.status_code == 200
        assert b"https://a.com" in response.content
        assert b"https://b.com" not in response.content

    def test_htmx_returns_partial(self, client, user, bookmark):
        client.force_login(user)
        response = client.get(
            reverse("bookmark_list", kwargs={"slug": user.slug}),
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200


@pytest.mark.django_db
class TestBookmarkAdd:
    def test_unauthenticated_redirects(self, client, user):
        response = client.get(reverse("bookmark_add", kwargs={"slug": user.slug}))
        assert response.status_code == 302

    def test_get_renders_form(self, client, user):
        client.force_login(user)
        response = client.get(reverse("bookmark_add", kwargs={"slug": user.slug}))
        assert response.status_code == 200

    def test_get_with_prefill_params(self, client, user):
        client.force_login(user)
        response = client.get(
            reverse("bookmark_add", kwargs={"slug": user.slug}),
            {"url": "https://prefill.com", "title": "Prefill"},
        )
        assert response.status_code == 200
        assert b"https://prefill.com" in response.content

    def test_post_creates_bookmark(self, client, user):
        client.force_login(user)
        response = client.post(
            reverse("bookmark_add", kwargs={"slug": user.slug}),
            {
                "url": "https://new.com",
                "title": "New Bookmark",
                "description": "",
                "tags": "",
            },
        )
        assert response.status_code == 302
        assert Bookmark.objects.filter(user=user, url="https://new.com").exists()

    def test_post_with_tags(self, client, user):
        client.force_login(user)
        client.post(
            reverse("bookmark_add", kwargs={"slug": user.slug}),
            {
                "url": "https://tagged.com",
                "title": "Tagged",
                "description": "",
                "tags": "python django web",
            },
        )
        bm = Bookmark.objects.get(user=user, url="https://tagged.com")
        assert "python" in bm.tags
        assert "django" in bm.tags

    def test_post_invalid_form(self, client, user):
        client.force_login(user)
        response = client.post(
            reverse("bookmark_add", kwargs={"slug": user.slug}),
            {"url": "", "title": ""},
        )
        assert response.status_code == 200
        assert not Bookmark.objects.filter(user=user).exists()


@pytest.mark.django_db
class TestBookmarkEdit:
    def test_unauthenticated_redirects(self, client, bookmark, user):
        response = client.get(
            reverse("bookmark_edit", kwargs={"slug": user.slug, "pk": bookmark.pk})
        )
        assert response.status_code == 302

    def test_get_renders_form(self, client, user, bookmark):
        client.force_login(user)
        response = client.get(
            reverse("bookmark_edit", kwargs={"slug": user.slug, "pk": bookmark.pk})
        )
        assert response.status_code == 200

    def test_other_user_gets_404(self, client, bookmark, other_user):
        client.force_login(other_user)
        response = client.get(
            reverse(
                "bookmark_edit",
                kwargs={"slug": other_user.slug, "pk": bookmark.pk},
            )
        )
        assert response.status_code == 404

    def test_post_updates_bookmark(self, client, user, bookmark):
        client.force_login(user)
        response = client.post(
            reverse("bookmark_edit", kwargs={"slug": user.slug, "pk": bookmark.pk}),
            {
                "url": "https://updated.com",
                "title": "Updated Title",
                "description": "updated",
                "tags": "updated",
            },
        )
        assert response.status_code == 302
        bookmark.refresh_from_db()
        assert bookmark.url == "https://updated.com"
        assert bookmark.title == "Updated Title"


@pytest.mark.django_db
class TestBookmarkDelete:
    def test_unauthenticated_redirects(self, client, bookmark, user):
        response = client.get(
            reverse("bookmark_delete", kwargs={"slug": user.slug, "pk": bookmark.pk})
        )
        assert response.status_code == 302

    def test_get_renders_confirm(self, client, user, bookmark):
        client.force_login(user)
        response = client.get(
            reverse("bookmark_delete", kwargs={"slug": user.slug, "pk": bookmark.pk})
        )
        assert response.status_code == 200

    def test_other_user_gets_404(self, client, bookmark, other_user):
        client.force_login(other_user)
        response = client.get(
            reverse(
                "bookmark_delete",
                kwargs={"slug": other_user.slug, "pk": bookmark.pk},
            )
        )
        assert response.status_code == 404

    def test_post_deletes_bookmark(self, client, user, bookmark):
        pk = bookmark.pk
        client.force_login(user)
        response = client.post(
            reverse("bookmark_delete", kwargs={"slug": user.slug, "pk": pk})
        )
        assert response.status_code == 302
        assert not Bookmark.objects.filter(pk=pk).exists()


@pytest.mark.django_db
class TestBookmarkImport:
    def test_get_renders_form(self, client, user):
        client.force_login(user)
        response = client.get(reverse("bookmark_import", kwargs={"slug": user.slug}))
        assert response.status_code == 200

    def test_import_netscape_html(self, client, user):
        client.force_login(user)
        html = (
            "<!DOCTYPE NETSCAPE-Bookmark-file-1>\n"
            "<DL><p>\n"
            '<DT><A HREF="https://imported.com" ADD_DATE="1609459200" TAGS="test">Imported</A>\n'
            "</DL><p>"
        )
        f = io.BytesIO(html.encode())
        f.name = "bookmarks.html"
        response = client.post(
            reverse("bookmark_import", kwargs={"slug": user.slug}),
            {"file": f},
        )
        assert response.status_code == 200
        assert Bookmark.objects.filter(user=user, url="https://imported.com").exists()

    def test_import_pinboard_json(self, client, user):
        import json

        client.force_login(user)
        data = [
            {
                "href": "https://pinboard-import.com",
                "description": "Pinboard Import",
                "extended": "",
                "tags": "python web",
                "time": "2021-01-01T00:00:00Z",
            }
        ]
        f = io.BytesIO(json.dumps(data).encode())
        f.name = "bookmarks.json"
        response = client.post(
            reverse("bookmark_import", kwargs={"slug": user.slug}),
            {"file": f},
        )
        assert response.status_code == 200
        assert Bookmark.objects.filter(
            user=user, url="https://pinboard-import.com"
        ).exists()

    def test_import_no_file(self, client, user):
        client.force_login(user)
        response = client.post(
            reverse("bookmark_import", kwargs={"slug": user.slug}),
            {},
        )
        assert response.status_code == 200
        assert b"No file selected" in response.content


@pytest.mark.django_db
class TestBookmarkExport:
    def test_export_html(self, client, user, bookmark):
        client.force_login(user)
        response = client.get(
            reverse("bookmark_export", kwargs={"slug": user.slug}),
            {"format": "html"},
        )
        assert response.status_code == 200
        assert response["Content-Type"].startswith("text/html")
        assert b"NETSCAPE-Bookmark" in response.content
        assert bookmark.url.encode() in response.content

    def test_export_json(self, client, user, bookmark):
        import json

        client.force_login(user)
        response = client.get(
            reverse("bookmark_export", kwargs={"slug": user.slug}),
            {"format": "json"},
        )
        assert response.status_code == 200
        assert response["Content-Type"].startswith("application/json")
        data = json.loads(response.content)
        assert len(data) == 1
        assert data[0]["href"] == bookmark.url

    def test_export_default_is_html(self, client, user, bookmark):
        client.force_login(user)
        response = client.get(reverse("bookmark_export", kwargs={"slug": user.slug}))
        assert response.status_code == 200
        assert (
            response["Content-Disposition"] == 'attachment; filename="bookmarks.html"'
        )


@pytest.mark.django_db
class TestIndexView:
    def test_unauthenticated_redirects_to_login(self, client):
        response = client.get("/")
        assert response.status_code == 302

    def test_authenticated_redirects_to_list(self, client, user):
        client.force_login(user)
        response = client.get("/")
        assert response.status_code == 302
        assert user.slug in response["Location"]
