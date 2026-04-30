def subscription_status(request):
    if not request.user.is_authenticated:
        return {}
    try:
        sub = request.user.subscription
        return {
            "subscription": sub,
            "subscription_is_active": sub.is_active,
        }
    except Exception:
        return {
            "subscription": None,
            "subscription_is_active": False,
        }
