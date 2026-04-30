def subscription_status(request):
    if not request.user.is_authenticated:
        return {}
    try:
        sub = request.user.subscription
        return {
            "subscription": sub,
            "subscription_is_active": sub.is_active,
            "subscription_is_expiring_soon": sub.is_expiring_soon,
        }
    except Exception:
        return {
            "subscription": None,
            "subscription_is_active": False,
            "subscription_is_expiring_soon": False,
        }
