from django.conf import settings
from django.shortcuts import redirect, render

from subscriptions.utils import calculate_price


def index(request):
    if not request.user.is_authenticated:
        return render(
            request,
            "home/home.html",
            {
                "subscription_free_limit": settings.SUBSCRIPTION_FREE_LIMIT,
                "subscription_price": calculate_price(1, "SEK"),
            },
        )
    return redirect("bookmark_list", slug=request.user.slug)
