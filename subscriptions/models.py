from cuid2 import Cuid
from django.conf import settings
from django.db import models
from django.utils import timezone

_cuid = Cuid(length=24)


def generate_cuid() -> str:
    return _cuid.generate()


class Subscription(models.Model):
    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="subscription",
    )
    expires_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Subscription({self.user}, expires={self.expires_at})"

    @property
    def is_active(self):
        return self.expires_at is not None and self.expires_at > timezone.now()

    @property
    def is_expiring_soon(self):
        if not self.is_active:
            return False
        from datetime import timedelta

        warning_days = settings.SUBSCRIPTION_EXPIRY_WARNING_DAYS
        return self.expires_at <= timezone.now() + timedelta(days=warning_days)
