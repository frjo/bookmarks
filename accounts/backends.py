from accounts.models import User


class PasskeyBackend:
    """Authentication backend for passkey (WebAuthn) login.

    We never call authenticate() with credentials here — the WebAuthn
    verification happens in the view before login() is called.  This
    backend exists so Django's login() knows how to look up a user by PK.
    """

    def authenticate(self, request, user=None, **kwargs):
        if isinstance(user, User):
            return user
        return None

    def get_user(self, user_id):
        try:
            return User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None
