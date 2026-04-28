import pytest

from accounts.models import APIToken, User, WebAuthnCredential


@pytest.mark.django_db
class TestUserModel:
    def test_create_user(self):
        user = User.objects.create_user(username="alice")
        assert user.username == "alice"
        assert user.is_active is True
        assert user.is_staff is False
        assert not user.has_usable_password()

    def test_cuid_primary_key(self):
        user = User.objects.create_user(username="bob")
        assert len(user.id) == 24
        assert user.id != ""

    def test_unique_pk_per_user(self):
        u1 = User.objects.create_user(username="u1")
        u2 = User.objects.create_user(username="u2")
        assert u1.id != u2.id

    def test_slug_from_username(self):
        user = User.objects.create_user(username="Hello World")
        assert user.slug == "hello-world"

    def test_slug_falls_back_to_id(self):
        user = User.objects.create_user(username=None)
        assert user.slug == user.id

    def test_str(self):
        user = User.objects.create_user(username="carol")
        assert str(user) == "carol"

    def test_str_without_username(self):
        user = User.objects.create_user(username=None)
        assert str(user) == user.id

    def test_create_superuser(self):
        user = User.objects.create_superuser(username="admin")
        assert user.is_staff is True
        assert user.is_superuser is True

    def test_username_unique(self):
        from django.db import IntegrityError

        User.objects.create_user(username="unique")
        with pytest.raises(IntegrityError):
            User.objects.create_user(username="unique")


@pytest.mark.django_db
class TestAPITokenModel:
    def test_generate_token_length(self):
        token = APIToken.generate_token()
        assert len(token) > 0
        assert isinstance(token, str)

    def test_generate_token_unique(self):
        t1 = APIToken.generate_token()
        t2 = APIToken.generate_token()
        assert t1 != t2

    def test_create_api_token(self, user):
        token = APIToken.objects.create(user=user, token=APIToken.generate_token())
        assert token.user == user
        assert token.created_at is not None

    def test_str(self, user):
        token = APIToken.objects.create(user=user, token=APIToken.generate_token())
        assert str(token) == f"{user.username} API token"

    def test_one_to_one_constraint(self, user):
        from django.db import IntegrityError

        APIToken.objects.create(user=user, token=APIToken.generate_token())
        with pytest.raises(IntegrityError):
            APIToken.objects.create(user=user, token=APIToken.generate_token())


@pytest.mark.django_db
class TestWebAuthnCredentialModel:
    def test_create_credential(self, user):
        cred = WebAuthnCredential.objects.create(
            user=user,
            credential_id=b"test_cred_id",
            public_key=b"test_public_key",
            sign_count=0,
            transports=["internal"],
            name="My Passkey",
        )
        assert cred.user == user
        assert cred.sign_count == 0
        assert cred.last_used_at is None
        assert cred.name == "My Passkey"

    def test_str(self, user):
        cred = WebAuthnCredential.objects.create(
            user=user,
            credential_id=b"cred123",
            public_key=b"pubkey",
        )
        assert user.username in str(cred)
        assert "passkey" in str(cred)

    def test_user_cascade_delete(self, user):
        WebAuthnCredential.objects.create(
            user=user,
            credential_id=b"cred_del",
            public_key=b"pubkey",
        )
        user.delete()
        assert WebAuthnCredential.objects.filter(credential_id=b"cred_del").count() == 0
