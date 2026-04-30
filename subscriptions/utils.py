from datetime import timedelta
from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings
from django.db import transaction
from django.utils import timezone

_TWO_PLACES = Decimal("0.01")


def calculate_price(
    years: int, currency: str = "SEK", include_vat: bool = True
) -> dict:
    """Return a full price breakdown for N years of subscription."""
    base_price = Decimal(
        str(
            settings.SUBSCRIPTION_PRICE_SEK
            if currency == "SEK"
            else settings.SUBSCRIPTION_PRICE_EUR
        )
    )
    vat_rate = Decimal(str(settings.SUBSCRIPTION_VAT_RATE))
    discount_pct_per_year = Decimal(str(settings.SUBSCRIPTION_DISCOUNT_PCT_PER_YEAR))

    discount_pct = (years - 1) * discount_pct_per_year
    discount_factor = 1 - (discount_pct / 100)

    amount_excl_vat = (base_price * years * discount_factor).quantize(
        _TWO_PLACES, ROUND_HALF_UP
    )

    if include_vat:
        vat_amount = (amount_excl_vat * vat_rate).quantize(_TWO_PLACES, ROUND_HALF_UP)
    else:
        vat_rate = Decimal("0.0000")
        vat_amount = Decimal("0.00")

    amount_incl_vat = amount_excl_vat + vat_amount

    return {
        "years": years,
        "currency": currency,
        "base_price": base_price,
        "discount_pct": discount_pct,
        "amount_excl_vat": amount_excl_vat,
        "vat_rate": vat_rate,
        "vat_amount": vat_amount,
        "amount_incl_vat": amount_incl_vat,
    }


def get_max_payable_years(user) -> int:
    """How many years can this user still pay for (respecting advance limit)?"""
    max_years = settings.SUBSCRIPTION_MAX_ADVANCE_YEARS
    now = timezone.now()
    max_expiry = now + timedelta(days=365 * max_years)

    try:
        sub = user.subscription
        current_expiry = (
            sub.expires_at if sub.expires_at and sub.expires_at > now else now
        )
    except Exception:
        current_expiry = now

    remaining_days = (max_expiry - current_expiry).days
    return max(1, min(max_years, remaining_days // 365))


def can_add_bookmark(user) -> bool:
    """True if the user is allowed to save another bookmark."""
    try:
        if user.subscription.is_active:
            return True
    except Exception:
        pass

    from links.models import Bookmark

    count = Bookmark.objects.filter(user=user).count()
    return count < settings.SUBSCRIPTION_FREE_LIMIT


@transaction.atomic
def generate_invoice_number() -> str:
    """Generate a unique sequential invoice number for the current year."""
    from .models import Payment

    year = timezone.now().year
    last = (
        Payment.objects.filter(invoice_number__startswith=f"INV-{year}-")
        .select_for_update()
        .order_by("-invoice_number")
        .first()
    )

    if last:
        try:
            seq = int(last.invoice_number.split("-")[-1]) + 1
        except (ValueError, IndexError):
            seq = 1
    else:
        seq = 1

    return f"INV-{year}-{seq:04d}"


def extend_subscription(user, years: int):
    """Extend user's subscription by years, stacking from current expiry."""
    from .models import Subscription

    sub, _ = Subscription.objects.get_or_create(user=user)
    now = timezone.now()
    start = sub.expires_at if sub.expires_at and sub.expires_at > now else now
    sub.expires_at = start + timedelta(days=365 * years)
    sub.save(update_fields=["expires_at", "updated_at"])
    return sub
