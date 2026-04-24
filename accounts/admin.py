from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import APIToken, User, WebAuthnCredential


class CredentialInline(admin.TabularInline):
    model = WebAuthnCredential
    extra = 0
    readonly_fields = ("credential_id", "sign_count", "created_at", "last_used_at")
    can_delete = True


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "id", "is_active", "is_staff", "created_at")
    search_fields = ("username", "id")
    ordering = ("-created_at",)
    readonly_fields = ("id", "created_at")
    inlines = [CredentialInline]

    fieldsets = (
        (None, {"fields": ("id", "username")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        ("Dates", {"fields": ("created_at", "last_login")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("username",)}),)
    filter_horizontal = ("groups", "user_permissions")


@admin.register(APIToken)
class APITokenAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at")
    readonly_fields = ("created_at",)
