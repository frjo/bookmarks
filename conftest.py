import pytest

from accounts.models import APIToken, User
from links.models import Bookmark


@pytest.fixture(autouse=True)
def disable_ratelimit(settings):
    settings.RATELIMIT_ENABLE = False


@pytest.fixture
def user(db):
    return User.objects.create_user(username="testuser")


@pytest.fixture
def other_user(db):
    return User.objects.create_user(username="otheruser")


@pytest.fixture
def api_token(user):
    return APIToken.objects.create(user=user, token=APIToken.generate_token())


@pytest.fixture
def auth_token_str(user, api_token):
    return f"{user.id}:{api_token.token}"


@pytest.fixture
def bookmark(user):
    return Bookmark.objects.create(
        user=user,
        url="https://example.com",
        title="Example",
        description="An example bookmark",
        tags=["python", "web"],
    )
