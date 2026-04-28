import pytest

from links.models import Bookmark, tags_for_user


@pytest.mark.django_db
class TestBookmarkModel:
    def test_create_bookmark(self, user):
        bm = Bookmark.objects.create(
            user=user,
            url="https://example.com",
            title="Example",
        )
        assert bm.user == user
        assert bm.url == "https://example.com"
        assert bm.shared is True
        assert bm.toread is False
        assert bm.tags == []
        assert bm.description == ""

    def test_cuid_primary_key(self, user):
        bm = Bookmark.objects.create(user=user, url="https://a.com", title="A")
        assert len(bm.id) == 24
        assert bm.id != ""

    def test_unique_pk_per_bookmark(self, user):
        b1 = Bookmark.objects.create(user=user, url="https://a.com", title="A")
        b2 = Bookmark.objects.create(user=user, url="https://b.com", title="B")
        assert b1.id != b2.id

    def test_str_returns_title(self, user):
        bm = Bookmark.objects.create(user=user, url="https://x.com", title="My Title")
        assert str(bm) == "My Title"

    def test_str_falls_back_to_url(self, user):
        bm = Bookmark.objects.create(user=user, url="https://x.com", title="")
        assert str(bm) == "https://x.com"

    def test_ordering_newest_first(self, user):
        import datetime

        from django.utils import timezone

        old = Bookmark.objects.create(
            user=user,
            url="https://old.com",
            title="Old",
            created_at=timezone.now() - datetime.timedelta(days=1),
        )
        new = Bookmark.objects.create(
            user=user,
            url="https://new.com",
            title="New",
        )
        bms = list(Bookmark.objects.filter(user=user))
        assert bms[0] == new
        assert bms[1] == old

    def test_tags_stored_as_list(self, user):
        bm = Bookmark.objects.create(
            user=user,
            url="https://tagged.com",
            title="Tagged",
            tags=["python", "django"],
        )
        bm.refresh_from_db()
        assert "python" in bm.tags
        assert "django" in bm.tags

    def test_cascade_delete_with_user(self, user):
        Bookmark.objects.create(user=user, url="https://del.com", title="Del")
        user.delete()
        assert Bookmark.objects.filter(url="https://del.com").count() == 0


@pytest.mark.django_db
class TestTagsForUser:
    def test_returns_unique_sorted_tags(self, user):
        Bookmark.objects.create(
            user=user, url="https://a.com", title="A", tags=["python", "web"]
        )
        Bookmark.objects.create(
            user=user, url="https://b.com", title="B", tags=["django", "python"]
        )
        tags = list(tags_for_user(user))
        assert tags == sorted(set(tags))
        assert "python" in tags
        assert "django" in tags
        assert "web" in tags
        assert tags.count("python") == 1

    def test_empty_for_user_without_bookmarks(self, user):
        tags = list(tags_for_user(user))
        assert tags == []

    def test_only_returns_own_tags(self, user, other_user):
        Bookmark.objects.create(
            user=user, url="https://mine.com", title="Mine", tags=["mine"]
        )
        Bookmark.objects.create(
            user=other_user, url="https://theirs.com", title="Theirs", tags=["theirs"]
        )
        tags = list(tags_for_user(user))
        assert "mine" in tags
        assert "theirs" not in tags
