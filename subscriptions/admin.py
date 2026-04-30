from django.contrib import admin

from .models import Subscription


@admin.register(Subscription)
class SubscriptionAdmin(admin.ModelAdmin):
    list_display = ["user", "expires_at", "active_badge", "created_at"]
    list_filter = ["expires_at"]
    search_fields = ["user__username", "user__id"]
    readonly_fields = ["created_at", "updated_at"]
    date_hierarchy = "expires_at"

    @admin.display(boolean=True, description="Active")
    def active_badge(self, obj):
        return obj.is_active
