from django.contrib import messages
from django.core.cache import cache
from django.utils.formats import date_format
from django.utils.html import format_html
from django.utils.translation import gettext as _

_CACHE_TTL = 3600  # 1 hour


def _subscription_cache_key(user_id):
    return f"sub_expiry:{user_id}"


class SubscriptionWarningMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            self._maybe_warn(request)
        return self.get_response(request)

    def _maybe_warn(self, request):
        key = _subscription_cache_key(request.user.pk)
        cached = cache.get(key)
        if cached is None:
            try:
                sub = request.user.subscription
                cached = {
                    "expiring_soon": sub.is_expiring_soon,
                    "expires_at": sub.expires_at,
                }
            except Exception:
                cached = {"expiring_soon": False, "expires_at": None}
            cache.set(key, cached, _CACHE_TTL)

        if cached["expiring_soon"]:
            from django.urls import reverse

            pay_url = reverse("subscriptions:pay")
            date = date_format(cached["expires_at"], "DATE_FORMAT")
            messages.warning(
                request,
                format_html(
                    _(
                        'Your subscription expires on {date}. <a href="{url}">Renew now</a> to keep full access.'
                    ),
                    date=date,
                    url=pay_url,
                ),
            )
