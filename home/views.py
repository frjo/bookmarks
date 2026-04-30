from django.conf import settings
from django.shortcuts import redirect, render


def index(request):
    if not request.user.is_authenticated:
        return render(
            request,
            "home/home.html",
            {
                "subscription_free_limit": settings.SUBSCRIPTION_FREE_LIMIT,
                "subscription_price_sek": settings.SUBSCRIPTION_PRICE_SEK,
            },
        )
    return redirect("bookmark_list", slug=request.user.slug)
