from django.contrib import admin
from django.utils.html import format_html

from .models import Payment, Subscription


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


@admin.register(Payment)
class PaymentAdmin(admin.ModelAdmin):
    list_display = [
        "invoice_number",
        "user",
        "years",
        "amount_incl_vat",
        "currency",
        "payment_method",
        "status_badge",
        "created_at",
    ]
    list_filter = ["status", "payment_method", "currency", "created_at"]
    search_fields = [
        "user__username",
        "user__id",
        "invoice_number",
        "swish_payment_reference",
    ]
    readonly_fields = [
        "invoice_number",
        "amount_excl_vat",
        "vat_rate",
        "vat_amount",
        "amount_incl_vat",
        "swish_payment_id",
        "swish_payment_reference",
        "created_at",
        "updated_at",
        "paid_at",
    ]
    date_hierarchy = "created_at"
    ordering = ["-created_at"]

    @admin.display(description="Status")
    def status_badge(self, obj):
        colours = {
            "paid": "green",
            "pending": "orange",
            "failed": "red",
            "cancelled": "grey",
        }
        colour = colours.get(obj.status, "black")
        return format_html(
            '<span style="color:{}">{}</span>', colour, obj.get_status_display()
        )
