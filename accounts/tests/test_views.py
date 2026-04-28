import json

import pytest
from django.urls import reverse

from accounts.models import APIToken


@pytest.mark.django_db
class TestRegisterView:
    def test_get_renders_form(self, client):
        response = client.get(reverse("register"))
        assert response.status_code == 200

    def test_authenticated_redirects(self, client, user):
        client.force_login(user)
        response = client.get(reverse("register"))
        assert response.status_code == 302


@pytest.mark.django_db
class TestRegisterUsernameView:
    def test_valid_username_stored_in_session(self, client):
        response = client.post(
            reverse("register_username"),
            data=json.dumps({"username": "newuser"}),
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"
        assert client.session["reg_username"] == "newuser"

    def test_too_short_username(self, client):
        response = client.post(
            reverse("register_username"),
            data=json.dumps({"username": "ab"}),
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "error" in response.json()

    def test_too_long_username(self, client):
        response = client.post(
            reverse("register_username"),
            data=json.dumps({"username": "x" * 51}),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_duplicate_username(self, client, user):
        response = client.post(
            reverse("register_username"),
            data=json.dumps({"username": user.username}),
            content_type="application/json",
        )
        assert response.status_code == 400
        assert "already taken" in response.json()["error"]

    def test_invalid_json(self, client):
        response = client.post(
            reverse("register_username"),
            data="not-json",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_empty_username_allowed(self, client):
        response = client.post(
            reverse("register_username"),
            data=json.dumps({"username": ""}),
            content_type="application/json",
        )
        assert response.status_code == 200
        assert response.json()["status"] == "ok"


@pytest.mark.django_db
class TestLoginView:
    def test_get_renders_form(self, client):
        response = client.get(reverse("login"))
        assert response.status_code == 200

    def test_authenticated_redirects(self, client, user):
        client.force_login(user)
        response = client.get(reverse("login"))
        assert response.status_code == 302


@pytest.mark.django_db
class TestLoginBeginView:
    def test_returns_webauthn_options(self, client):
        response = client.post(reverse("login_begin"))
        assert response.status_code == 200
        data = response.json()
        assert "challenge" in data
        assert "auth_challenge" in client.session


@pytest.mark.django_db
class TestLogoutView:
    def test_logout_redirects(self, client, user):
        client.force_login(user)
        response = client.post(reverse("logout"))
        assert response.status_code == 302

    def test_logout_clears_session(self, client, user):
        client.force_login(user)
        client.post(reverse("logout"))
        assert "_auth_user_id" not in client.session


@pytest.mark.django_db
class TestAccountView:
    def test_unauthenticated_redirects(self, client, user):
        response = client.get(reverse("account", kwargs={"slug": user.slug}))
        assert response.status_code == 302
        assert "/login" in response["Location"] or "login" in response["Location"]

    def test_get_renders_account_page(self, client, user):
        client.force_login(user)
        response = client.get(reverse("account", kwargs={"slug": user.slug}))
        assert response.status_code == 200

    def test_update_username(self, client, user):
        client.force_login(user)
        response = client.post(
            reverse("account", kwargs={"slug": user.slug}),
            data={"action": "update_username", "username": "newname"},
        )
        assert response.status_code == 302
        user.refresh_from_db()
        assert user.username == "newname"

    def test_update_username_too_short(self, client, user):
        client.force_login(user)
        client.post(
            reverse("account", kwargs={"slug": user.slug}),
            data={"action": "update_username", "username": "ab"},
        )
        user.refresh_from_db()
        assert user.username == "testuser"

    def test_update_username_duplicate(self, client, user, other_user):
        client.force_login(user)
        client.post(
            reverse("account", kwargs={"slug": user.slug}),
            data={"action": "update_username", "username": other_user.username},
        )
        user.refresh_from_db()
        assert user.username == "testuser"

    def test_regenerate_token(self, client, user, api_token):
        old_token = api_token.token
        client.force_login(user)
        client.post(
            reverse("account", kwargs={"slug": user.slug}),
            data={"action": "regenerate_token"},
        )
        api_token.refresh_from_db()
        assert api_token.token != old_token

    def test_regenerate_token_creates_if_absent(self, client, user):
        client.force_login(user)
        assert not APIToken.objects.filter(user=user).exists()
        client.post(
            reverse("account", kwargs={"slug": user.slug}),
            data={"action": "regenerate_token"},
        )
        assert APIToken.objects.filter(user=user).exists()
