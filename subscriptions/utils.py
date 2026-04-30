from decimal import ROUND_HALF_UP, Decimal

from django.conf import settings

_WHOLE = Decimal("1")


def calculate_price(
    years: int, currency: str = "SEK", include_vat: bool = True
) -> dict:
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
        _WHOLE, ROUND_HALF_UP
    )

    if include_vat:
        vat_amount = (amount_excl_vat * vat_rate).quantize(_WHOLE, ROUND_HALF_UP)
    else:
        vat_rate = Decimal("0.0000")
        vat_amount = Decimal("0")

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


def can_add_bookmark(user) -> bool:
    try:
        if user.subscription.is_active:
            return True
    except Exception:
        pass

    from links.models import Bookmark

    count = Bookmark.objects.filter(user=user).count()
    return count < settings.SUBSCRIPTION_FREE_LIMIT
