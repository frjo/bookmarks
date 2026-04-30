from django.contrib import messages
from django.utils.formats import date_format
from django.utils.html import format_html
from django.utils.translation import gettext as _


class SubscriptionWarningMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.user.is_authenticated:
            try:
                sub = request.user.subscription
                if sub.is_expiring_soon:
                    from django.urls import reverse

                    pay_url = reverse("subscriptions:pay")
                    date = date_format(sub.expires_at, "DATE_FORMAT")
                    msg = format_html(
                        _(
                            'Your subscription expires on {date}. <a href="{url}">Renew now</a> to keep full access.'
                        ),
                        date=date,
                        url=pay_url,
                    )
                    messages.warning(request, msg)
            except Exception:
                pass
        return self.get_response(request)
