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


class Payment(models.Model):
    STATUS_PENDING = "pending"
    STATUS_PAID = "paid"
    STATUS_FAILED = "failed"
    STATUS_CANCELLED = "cancelled"
    STATUS_CHOICES = [
        (STATUS_PENDING, "Pending"),
        (STATUS_PAID, "Paid"),
        (STATUS_FAILED, "Failed"),
        (STATUS_CANCELLED, "Cancelled"),
    ]

    METHOD_SWISH = "swish"
    METHOD_STRIPE = "stripe"
    METHOD_CHOICES = [
        (METHOD_SWISH, "Swish"),
        (METHOD_STRIPE, "Stripe"),
    ]

    id = models.CharField(primary_key=True, max_length=26, default=generate_cuid)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="payments",
    )
    invoice_number = models.CharField(max_length=50, unique=True)
    years = models.PositiveSmallIntegerField(default=1)
    discount_pct = models.DecimalField(max_digits=5, decimal_places=2, default=0)
    amount_excl_vat = models.DecimalField(max_digits=10, decimal_places=2)
    vat_rate = models.DecimalField(max_digits=5, decimal_places=4)
    vat_amount = models.DecimalField(max_digits=10, decimal_places=2)
    amount_incl_vat = models.DecimalField(max_digits=10, decimal_places=2)
    currency = models.CharField(max_length=3, default="SEK")
    vat_number = models.CharField(max_length=30, blank=True)
    payment_method = models.CharField(max_length=20, choices=METHOD_CHOICES)
    status = models.CharField(
        max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING
    )
    swish_payment_id = models.CharField(max_length=100, blank=True)
    swish_payment_reference = models.CharField(max_length=100, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    paid_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self):
        return f"Payment({self.invoice_number}, {self.status})"
