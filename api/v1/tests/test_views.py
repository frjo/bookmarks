"""Tests for the Pinboard-compatible v1 API."""

import pytest
from django.urls import reverse

from links.models import Bookmark


def get(client, path, token, **params):
    return client.get(path, {"auth_token": token, **params})


def post(client, path, token, **params):
    return client.post(path, {"auth_token": token, **params})


@pytest.mark.django_db
class TestAuth:
    def test_no_token_returns_401(self, client):
        response = client.get(reverse("api_v1_posts_update"))
        assert response.status_code == 401

    def test_invalid_token_returns_401(self, client, user):
        response = client.get(
            reverse("api_v1_posts_update"), {"auth_token": f"{user.username}:badtoken"}
        )
        assert response.status_code == 401

    def test_malformed_token_returns_401(self, client):
        response = client.get(
            reverse("api_v1_posts_update"), {"auth_token": "notokencolon"}
        )
        assert response.status_code == 401

    def test_valid_token_succeeds(self, client, auth_token_str):
        response = get(client, reverse("api_v1_posts_update"), auth_token_str)
        assert response.status_code == 200

    def test_post_method_also_works(self, client, auth_token_str):
        response = post(client, reverse("api_v1_posts_update"), auth_token_str)
        assert response.status_code == 200


@pytest.mark.django_db
class TestPostsUpdate:
    def test_returns_xml_by_default(self, client, auth_token_str):
        response = get(client, reverse("api_v1_posts_update"), auth_token_str)
        assert "text/xml" in response["Content-Type"]
        assert b"<update" in response.content

    def test_returns_json_with_format_param(self, client, auth_token_str):
        response = get(
            client, reverse("api_v1_posts_update"), auth_token_str, format="json"
        )
        assert response.status_code == 200
        data = response.json()
        assert "update_time" in data

    def test_timestamp_format(self, client, auth_token_str):
        response = get(
            client, reverse("api_v1_posts_update"), auth_token_str, format="json"
        )
        ts = response.json()["update_time"]
        assert "T" in ts
        assert ts.endswith("Z")


@pytest.mark.django_db
class TestPostsAdd:
    def test_add_new_bookmark(self, client, auth_token_str, user):
        response = get(
            client,
            reverse("api_v1_posts_add"),
            auth_token_str,
            url="https://new-v1.com",
            description="New V1",
        )
        assert response.status_code == 200
        assert b"done" in response.content
        assert Bookmark.objects.filter(user=user, url="https://new-v1.com").exists()

    def test_add_with_tags(self, client, auth_token_str, user):
        get(
            client,
            reverse("api_v1_posts_add"),
            auth_token_str,
            url="https://tagged-v1.com",
            description="Tagged",
            tags="python web",
        )
        bm = Bookmark.objects.get(user=user, url="https://tagged-v1.com")
        assert "python" in bm.tags
        assert "web" in bm.tags

    def test_add_requires_url(self, client, auth_token_str):
        response = get(
            client, reverse("api_v1_posts_add"), auth_token_str, description="No URL"
        )
        assert response.status_code == 400

    def test_update_existing_bookmark(self, client, auth_token_str, user, bookmark):
        get(
            client,
            reverse("api_v1_posts_add"),
            auth_token_str,
            url=bookmark.url,
            description="Updated Title",
        )
        bookmark.refresh_from_db()
        assert bookmark.title == "Updated Title"

    def test_replace_no_skips_existing(self, client, auth_token_str, bookmark):
        response = get(
            client,
            reverse("api_v1_posts_add"),
            auth_token_str,
            url=bookmark.url,
            description="Wont Replace",
            replace="no",
        )
        assert response.status_code == 400
        assert b"already exists" in response.content

    def test_returns_json(self, client, auth_token_str):
        response = get(
            client,
            reverse("api_v1_posts_add"),
            auth_token_str,
            url="https://json-add.com",
            description="JSON add",
            format="json",
        )
        assert response.json()["result_code"] == "done"

    def test_shared_and_toread(self, client, auth_token_str, user):
        get(
            client,
            reverse("api_v1_posts_add"),
            auth_token_str,
            url="https://private-toread.com",
            description="Private toread",
            shared="no",
            toread="yes",
        )
        bm = Bookmark.objects.get(user=user, url="https://private-toread.com")
        assert bm.shared is False
        assert bm.toread is True


@pytest.mark.django_db
class TestPostsDelete:
    def test_delete_existing(self, client, auth_token_str, user, bookmark):
        pk = bookmark.pk
        get(client, reverse("api_v1_posts_delete"), auth_token_str, url=bookmark.url)
        assert not Bookmark.objects.filter(pk=pk).exists()

    def test_delete_nonexistent_returns_404(self, client, auth_token_str):
        response = get(
            client,
            reverse("api_v1_posts_delete"),
            auth_token_str,
            url="https://doesnotexist.com",
        )
        assert response.status_code == 404

    def test_delete_requires_url(self, client, auth_token_str):
        response = get(client, reverse("api_v1_posts_delete"), auth_token_str)
        assert response.status_code == 400

    def test_returns_done_on_success(self, client, auth_token_str, bookmark):
        response = get(
            client,
            reverse("api_v1_posts_delete"),
            auth_token_str,
            url=bookmark.url,
            format="json",
        )
        assert response.json()["result_code"] == "done"


@pytest.mark.django_db
class TestPostsGet:
    def test_returns_all_bookmarks(self, client, auth_token_str, user, bookmark):
        response = get(
            client, reverse("api_v1_posts_get"), auth_token_str, format="json"
        )
        assert response.status_code == 200
        data = response.json()
        assert "posts" in data
        assert len(data["posts"]) == 1

    def test_filter_by_url(self, client, auth_token_str, user, bookmark):
        Bookmark.objects.create(user=user, url="https://other.com", title="Other")
        response = get(
            client,
            reverse("api_v1_posts_get"),
            auth_token_str,
            url=bookmark.url,
            format="json",
        )
        data = response.json()
        assert len(data["posts"]) == 1
        assert data["posts"][0]["href"] == bookmark.url

    def test_filter_by_tag(self, client, auth_token_str, user, bookmark):
        Bookmark.objects.create(
            user=user, url="https://notag.com", title="No Tag", tags=[]
        )
        response = get(
            client,
            reverse("api_v1_posts_get"),
            auth_token_str,
            tag="python",
            format="json",
        )
        data = response.json()
        urls = [p["href"] for p in data["posts"]]
        assert bookmark.url in urls
        assert "https://notag.com" not in urls

    def test_returns_xml_by_default(self, client, auth_token_str, bookmark):
        response = get(client, reverse("api_v1_posts_get"), auth_token_str)
        assert b"<posts" in response.content

    def test_only_own_bookmarks(self, client, auth_token_str, user, other_user):
        Bookmark.objects.create(
            user=other_user, url="https://notmine.com", title="Not Mine"
        )
        response = get(
            client, reverse("api_v1_posts_get"), auth_token_str, format="json"
        )
        urls = [p["href"] for p in response.json()["posts"]]
        assert "https://notmine.com" not in urls

    def test_meta_flag(self, client, auth_token_str, bookmark):
        response = get(
            client,
            reverse("api_v1_posts_get"),
            auth_token_str,
            meta="yes",
            format="json",
        )
        post = response.json()["posts"][0]
        assert post["meta"] != ""


@pytest.mark.django_db
class TestPostsRecent:
    def test_returns_recent_bookmarks(self, client, auth_token_str, user, bookmark):
        response = get(
            client, reverse("api_v1_posts_recent"), auth_token_str, format="json"
        )
        assert response.status_code == 200
        data = response.json()
        assert "posts" in data
        assert len(data["posts"]) >= 1

    def test_count_param(self, client, auth_token_str, user):
        for i in range(5):
            Bookmark.objects.create(
                user=user, url=f"https://bm{i}.com", title=f"BM {i}"
            )
        response = get(
            client,
            reverse("api_v1_posts_recent"),
            auth_token_str,
            count=3,
            format="json",
        )
        assert len(response.json()["posts"]) == 3

    def test_count_capped_at_100(self, client, auth_token_str, user):
        for i in range(5):
            Bookmark.objects.create(
                user=user, url=f"https://cap{i}.com", title=f"Cap {i}"
            )
        response = get(
            client,
            reverse("api_v1_posts_recent"),
            auth_token_str,
            count=200,
            format="json",
        )
        assert len(response.json()["posts"]) <= 100

    def test_filter_by_tag(self, client, auth_token_str, user):
        Bookmark.objects.create(
            user=user, url="https://tagbm.com", title="Tagged", tags=["special"]
        )
        Bookmark.objects.create(
            user=user, url="https://notagbm.com", title="Untagged", tags=[]
        )
        response = get(
            client,
            reverse("api_v1_posts_recent"),
            auth_token_str,
            tag="special",
            format="json",
        )
        urls = [p["href"] for p in response.json()["posts"]]
        assert "https://tagbm.com" in urls
        assert "https://notagbm.com" not in urls


@pytest.mark.django_db
class TestPostsAll:
    def test_returns_all_bookmarks(self, client, auth_token_str, user, bookmark):
        response = get(
            client, reverse("api_v1_posts_all"), auth_token_str, format="json"
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        assert len(data) == 1

    def test_returns_xml_by_default(self, client, auth_token_str, bookmark):
        response = get(client, reverse("api_v1_posts_all"), auth_token_str)
        assert b"<posts" in response.content

    def test_tag_filter(self, client, auth_token_str, user, bookmark):
        Bookmark.objects.create(user=user, url="https://untagged.com", title="Untagged")
        response = get(
            client,
            reverse("api_v1_posts_all"),
            auth_token_str,
            tag="python",
            format="json",
        )
        urls = [p["href"] for p in response.json()]
        assert bookmark.url in urls
        assert "https://untagged.com" not in urls

    def test_pagination(self, client, auth_token_str, user):
        for i in range(5):
            Bookmark.objects.create(
                user=user, url=f"https://page{i}.com", title=f"Page {i}"
            )
        response = get(
            client,
            reverse("api_v1_posts_all"),
            auth_token_str,
            start=2,
            results=2,
            format="json",
        )
        assert len(response.json()) == 2


@pytest.mark.django_db
class TestPostsDates:
    def test_returns_dates(self, client, auth_token_str, user, bookmark):
        response = get(
            client, reverse("api_v1_posts_dates"), auth_token_str, format="json"
        )
        assert response.status_code == 200
        data = response.json()
        assert "dates" in data
        assert len(data["dates"]) >= 1

    def test_returns_xml(self, client, auth_token_str, bookmark):
        response = get(client, reverse("api_v1_posts_dates"), auth_token_str)
        assert b"<dates" in response.content


@pytest.mark.django_db
class TestPostsSuggest:
    def test_returns_popular_and_recommended(self, client, auth_token_str, bookmark):
        response = get(
            client,
            reverse("api_v1_posts_suggest"),
            auth_token_str,
            url=bookmark.url,
            format="json",
        )
        assert response.status_code == 200
        data = response.json()
        assert isinstance(data, list)
        keys = [list(item.keys())[0] for item in data]
        assert "popular" in keys
        assert "recommended" in keys

    def test_recommended_from_existing_bookmark(self, client, auth_token_str, bookmark):
        response = get(
            client,
            reverse("api_v1_posts_suggest"),
            auth_token_str,
            url=bookmark.url,
            format="json",
        )
        recommended = next(
            item["recommended"] for item in response.json() if "recommended" in item
        )
        assert "python" in recommended or "web" in recommended


@pytest.mark.django_db
class TestTagsGet:
    def test_returns_tags_with_counts(self, client, auth_token_str, user, bookmark):
        response = get(
            client, reverse("api_v1_tags_get"), auth_token_str, format="json"
        )
        assert response.status_code == 200
        data = response.json()
        assert "python" in data
        assert "web" in data

    def test_returns_xml(self, client, auth_token_str, bookmark):
        response = get(client, reverse("api_v1_tags_get"), auth_token_str)
        assert b"<tags" in response.content


@pytest.mark.django_db
class TestTagsDelete:
    def test_removes_tag_from_bookmarks(self, client, auth_token_str, user, bookmark):
        get(client, reverse("api_v1_tags_delete"), auth_token_str, tag="python")
        bookmark.refresh_from_db()
        assert "python" not in bookmark.tags

    def test_tag_required(self, client, auth_token_str):
        response = get(client, reverse("api_v1_tags_delete"), auth_token_str)
        assert response.status_code == 400

    def test_returns_done(self, client, auth_token_str, bookmark):
        response = get(
            client,
            reverse("api_v1_tags_delete"),
            auth_token_str,
            tag="python",
            format="json",
        )
        assert response.json()["result_code"] == "done"


@pytest.mark.django_db
class TestTagsRename:
    def test_renames_tag(self, client, auth_token_str, user, bookmark):
        get(
            client,
            reverse("api_v1_tags_rename"),
            auth_token_str,
            old="python",
            new="py",
        )
        bookmark.refresh_from_db()
        assert "py" in bookmark.tags
        assert "python" not in bookmark.tags

    def test_old_and_new_required(self, client, auth_token_str):
        response = get(
            client, reverse("api_v1_tags_rename"), auth_token_str, old="python"
        )
        assert response.status_code == 400

    def test_returns_done(self, client, auth_token_str, bookmark):
        response = get(
            client,
            reverse("api_v1_tags_rename"),
            auth_token_str,
            old="python",
            new="py",
            format="json",
        )
        assert response.json()["result_code"] == "done"


@pytest.mark.django_db
class TestUserSecret:
    def test_returns_secret(self, client, auth_token_str):
        response = get(
            client, reverse("api_v1_user_secret"), auth_token_str, format="json"
        )
        assert response.status_code == 200
        data = response.json()
        assert "result" in data
        assert len(data["result"]) > 0

    def test_returns_xml(self, client, auth_token_str):
        response = get(client, reverse("api_v1_user_secret"), auth_token_str)
        assert b"<result" in response.content


@pytest.mark.django_db
class TestUserApiToken:
    def test_returns_token_string(self, client, user, auth_token_str):
        response = get(
            client, reverse("api_v1_user_api_token"), auth_token_str, format="json"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["result"].startswith(f"{user.id}:")

    def test_returns_xml(self, client, auth_token_str):
        response = get(client, reverse("api_v1_user_api_token"), auth_token_str)
        assert b"<result" in response.content


@pytest.mark.django_db
class TestNotes:
    def test_notes_list_returns_empty(self, client, auth_token_str):
        response = get(
            client, reverse("api_v1_notes_list"), auth_token_str, format="json"
        )
        assert response.status_code == 200
        data = response.json()
        assert data["count"] == 0
        assert data["notes"] == []

    def test_notes_detail_returns_404(self, client, auth_token_str):
        response = get(
            client,
            reverse("api_v1_notes_detail", kwargs={"note_id": "abc"}),
            auth_token_str,
            format="json",
        )
        assert response.status_code == 404
