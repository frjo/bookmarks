"""Tests for the v2 JSON API."""

import pytest
from django.urls import reverse

from links.models import Bookmark


def get(client, path, token=None, header=False, **params):
    kwargs = {}
    if token:
        if header:
            kwargs["HTTP_X_AUTH_TOKEN"] = token
        else:
            params["auth_token"] = token
    return client.get(path, params, **kwargs)


def post(client, path, token=None, header=False, **params):
    kwargs = {}
    if token:
        if header:
            kwargs["HTTP_X_AUTH_TOKEN"] = token
        else:
            params["auth_token"] = token
    return client.post(path, params, **kwargs)


@pytest.mark.django_db
class TestAuth:
    def test_no_token_returns_401(self, client):
        response = client.get(reverse("api_v2_posts_get"))
        assert response.status_code == 401
        assert response.json()["status"] == "error"

    def test_invalid_token_returns_401(self, client, user):
        response = get(client, reverse("api_v2_posts_get"), f"{user.username}:badtoken")
        assert response.status_code == 401

    def test_malformed_token_returns_401(self, client):
        response = get(client, reverse("api_v2_posts_get"), "notokencolon")
        assert response.status_code == 401

    def test_valid_query_param_token(self, client, auth_token_str):
        response = get(client, reverse("api_v2_posts_get"), auth_token_str)
        assert response.status_code == 200

    def test_valid_header_token(self, client, auth_token_str):
        response = get(client, reverse("api_v2_posts_get"), auth_token_str, header=True)
        assert response.status_code == 200

    def test_both_token_methods_returns_400(self, client, auth_token_str):
        response = client.get(
            reverse("api_v2_posts_get"),
            {"auth_token": auth_token_str},
            HTTP_X_AUTH_TOKEN=auth_token_str,
        )
        assert response.status_code == 400
        assert response.json()["error"] == "too_much_auth"

    def test_responses_are_json(self, client):
        response = client.get(reverse("api_v2_posts_get"))
        assert "application/json" in response["Content-Type"]


@pytest.mark.django_db
class TestPostsGet:
    def test_returns_posts(self, client, auth_token_str, user, bookmark):
        response = get(client, reverse("api_v2_posts_get"), auth_token_str)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert len(data["posts"]) == 1

    def test_filter_by_url(self, client, auth_token_str, user, bookmark):
        Bookmark.objects.create(user=user, url="https://other.com", title="Other")
        response = get(
            client, reverse("api_v2_posts_get"), auth_token_str, url=bookmark.url
        )
        data = response.json()
        assert len(data["posts"]) == 1
        assert data["posts"][0]["href"] == bookmark.url

    def test_filter_by_tag(self, client, auth_token_str, user, bookmark):
        Bookmark.objects.create(user=user, url="https://notag.com", title="No Tag")
        response = get(
            client, reverse("api_v2_posts_get"), auth_token_str, tag="python"
        )
        urls = [p["href"] for p in response.json()["posts"]]
        assert bookmark.url in urls
        assert "https://notag.com" not in urls

    def test_pagination(self, client, auth_token_str, user):
        for i in range(5):
            Bookmark.objects.create(
                user=user, url=f"https://pag{i}.com", title=f"Pag {i}"
            )
        response = get(
            client, reverse("api_v2_posts_get"), auth_token_str, start=2, results=2
        )
        assert len(response.json()["posts"]) == 2

    def test_only_own_bookmarks(self, client, auth_token_str, other_user):
        Bookmark.objects.create(
            user=other_user, url="https://notmine.com", title="Not Mine"
        )
        response = get(client, reverse("api_v2_posts_get"), auth_token_str)
        urls = [p["href"] for p in response.json()["posts"]]
        assert "https://notmine.com" not in urls

    def test_post_serialization_fields(self, client, auth_token_str, bookmark):
        response = get(client, reverse("api_v2_posts_get"), auth_token_str)
        post = response.json()["posts"][0]
        assert "href" in post
        assert "description" in post
        assert "extended" in post
        assert "meta" in post
        assert "hash" in post
        assert "time" in post
        assert "shared" in post
        assert "toread" in post
        assert "tags" in post


@pytest.mark.django_db
class TestPostsRecent:
    def test_returns_recent(self, client, auth_token_str, bookmark):
        response = get(client, reverse("api_v2_posts_recent"), auth_token_str)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert len(data["posts"]) >= 1

    def test_count_param(self, client, auth_token_str, user):
        for i in range(5):
            Bookmark.objects.create(
                user=user, url=f"https://rec{i}.com", title=f"Rec {i}"
            )
        response = get(client, reverse("api_v2_posts_recent"), auth_token_str, count=3)
        assert len(response.json()["posts"]) == 3

    def test_count_capped_at_100(self, client, auth_token_str, user):
        for i in range(5):
            Bookmark.objects.create(
                user=user, url=f"https://cap2{i}.com", title=f"Cap {i}"
            )
        response = get(
            client, reverse("api_v2_posts_recent"), auth_token_str, count=500
        )
        assert len(response.json()["posts"]) <= 100


@pytest.mark.django_db
class TestPostsAll:
    def test_returns_all(self, client, auth_token_str, user, bookmark):
        response = get(client, reverse("api_v2_posts_all"), auth_token_str)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert len(data["posts"]) == 1

    def test_tag_filter(self, client, auth_token_str, user, bookmark):
        Bookmark.objects.create(user=user, url="https://untagged.com", title="Untagged")
        response = get(
            client, reverse("api_v2_posts_all"), auth_token_str, tag="python"
        )
        urls = [p["href"] for p in response.json()["posts"]]
        assert bookmark.url in urls
        assert "https://untagged.com" not in urls

    def test_if_modified_since_returns_304_when_not_changed(
        self, client, auth_token_str, bookmark
    ):
        from email.utils import format_datetime

        from django.utils import timezone

        future = timezone.now().replace(year=2099)
        response = client.get(
            reverse("api_v2_posts_all"),
            {"auth_token": auth_token_str},
            HTTP_IF_MODIFIED_SINCE=format_datetime(future),
        )
        assert response.status_code == 304

    def test_if_modified_since_returns_200_when_changed(
        self, client, auth_token_str, bookmark
    ):
        from datetime import datetime
        from datetime import timezone as dt_tz
        from email.utils import format_datetime

        past = datetime(2000, 1, 1, tzinfo=dt_tz.utc)
        response = client.get(
            reverse("api_v2_posts_all"),
            {"auth_token": auth_token_str},
            HTTP_IF_MODIFIED_SINCE=format_datetime(past),
        )
        assert response.status_code == 200


@pytest.mark.django_db
class TestPostsAdd:
    def test_add_new_bookmark(self, client, auth_token_str, user):
        response = post(
            client,
            reverse("api_v2_posts_add"),
            auth_token_str,
            url="https://v2new.com",
            description="V2 New",
        )
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["result_code"] == "done"
        assert Bookmark.objects.filter(user=user, url="https://v2new.com").exists()

    def test_add_requires_url(self, client, auth_token_str):
        response = post(
            client, reverse("api_v2_posts_add"), auth_token_str, description="No URL"
        )
        assert response.status_code == 400
        assert response.json()["status"] == "error"

    def test_add_with_tags(self, client, auth_token_str, user):
        post(
            client,
            reverse("api_v2_posts_add"),
            auth_token_str,
            url="https://v2tagged.com",
            description="Tagged",
            tags="alpha beta",
        )
        bm = Bookmark.objects.get(user=user, url="https://v2tagged.com")
        assert "alpha" in bm.tags
        assert "beta" in bm.tags

    def test_update_existing(self, client, auth_token_str, bookmark):
        post(
            client,
            reverse("api_v2_posts_add"),
            auth_token_str,
            url=bookmark.url,
            description="Updated V2",
        )
        bookmark.refresh_from_db()
        assert bookmark.title == "Updated V2"

    def test_replace_no_returns_item_exists(self, client, auth_token_str, bookmark):
        response = post(
            client,
            reverse("api_v2_posts_add"),
            auth_token_str,
            url=bookmark.url,
            description="Wont Replace",
            replace="no",
        )
        assert response.status_code == 200
        assert response.json()["result_code"] == "item already exists"

    def test_shared_and_toread_numeric(self, client, auth_token_str, user):
        post(
            client,
            reverse("api_v2_posts_add"),
            auth_token_str,
            url="https://v2flags.com",
            description="Flags",
            shared="0",
            toread="1",
        )
        bm = Bookmark.objects.get(user=user, url="https://v2flags.com")
        assert bm.shared is False
        assert bm.toread is True

    def test_get_method_also_works(self, client, auth_token_str, user):
        response = get(
            client,
            reverse("api_v2_posts_add"),
            auth_token_str,
            url="https://v2getadd.com",
            description="Get Add",
        )
        assert response.status_code == 200
        assert Bookmark.objects.filter(user=user, url="https://v2getadd.com").exists()


@pytest.mark.django_db
class TestPostsDelete:
    def test_delete_existing(self, client, auth_token_str, user, bookmark):
        pk = bookmark.pk
        response = client.delete(
            reverse("api_v2_posts_delete")
            + f"?auth_token={auth_token_str}&url={bookmark.url}"
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert not Bookmark.objects.filter(pk=pk).exists()

    def test_delete_via_get(self, client, auth_token_str, bookmark):
        pk = bookmark.pk
        response = get(
            client, reverse("api_v2_posts_delete"), auth_token_str, url=bookmark.url
        )
        assert response.status_code == 200
        assert not Bookmark.objects.filter(pk=pk).exists()

    def test_delete_requires_url(self, client, auth_token_str):
        response = get(client, reverse("api_v2_posts_delete"), auth_token_str)
        assert response.status_code == 400

    def test_delete_nonexistent_still_ok(self, client, auth_token_str):
        response = get(
            client,
            reverse("api_v2_posts_delete"),
            auth_token_str,
            url="https://doesnotexist.com",
        )
        assert response.status_code == 200
        assert response.json()["result_code"] == "done"


@pytest.mark.django_db
class TestPostsDates:
    def test_returns_dates(self, client, auth_token_str, user, bookmark):
        response = get(client, reverse("api_v2_posts_dates"), auth_token_str)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "dates" in data
        assert len(data["dates"]) >= 1


@pytest.mark.django_db
class TestTagsGet:
    def test_returns_tags(self, client, auth_token_str, user, bookmark):
        response = get(client, reverse("api_v2_tags_get"), auth_token_str)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "python" in data["tags"]
        assert "web" in data["tags"]

    def test_empty_for_no_bookmarks(self, client, auth_token_str):
        response = get(client, reverse("api_v2_tags_get"), auth_token_str)
        data = response.json()
        assert data["tags"] == {}


@pytest.mark.django_db
class TestTagsRename:
    def test_renames_tag(self, client, auth_token_str, user, bookmark):
        response = get(
            client,
            reverse("api_v2_tags_rename"),
            auth_token_str,
            old="python",
            new="py",
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        bookmark.refresh_from_db()
        assert "py" in bookmark.tags
        assert "python" not in bookmark.tags

    def test_old_and_new_required(self, client, auth_token_str):
        response = get(
            client, reverse("api_v2_tags_rename"), auth_token_str, old="python"
        )
        assert response.status_code == 400
        assert response.json()["status"] == "error"

    def test_post_method(self, client, auth_token_str, bookmark):
        response = post(
            client,
            reverse("api_v2_tags_rename"),
            auth_token_str,
            old="python",
            new="py",
        )
        assert response.status_code == 200


@pytest.mark.django_db
class TestTagsDelete:
    def test_removes_tag(self, client, auth_token_str, user, bookmark):
        response = get(
            client, reverse("api_v2_tags_delete"), auth_token_str, tag="python"
        )
        assert response.status_code == 200
        bookmark.refresh_from_db()
        assert "python" not in bookmark.tags

    def test_tag_required(self, client, auth_token_str):
        response = get(client, reverse("api_v2_tags_delete"), auth_token_str)
        assert response.status_code == 400

    def test_delete_method(self, client, auth_token_str, bookmark):
        response = client.delete(
            reverse("api_v2_tags_delete") + f"?auth_token={auth_token_str}&tag=python"
        )
        assert response.status_code == 200
        bookmark.refresh_from_db()
        assert "python" not in bookmark.tags


@pytest.mark.django_db
class TestUserApiToken:
    def test_returns_token(self, client, user, auth_token_str):
        response = get(client, reverse("api_v2_user_token"), auth_token_str)
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["result"].startswith(f"{user.username}:")
