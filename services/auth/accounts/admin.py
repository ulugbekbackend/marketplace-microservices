"""Django admin for staff: users, seller applications and the outbox (read only)."""

from typing import TYPE_CHECKING

from django.contrib import admin
from django.http import HttpRequest

from accounts.models import Outbox, SellerApplication, User

if TYPE_CHECKING:  # ModelAdmin is generic for the type checker only
    UserModelAdmin = admin.ModelAdmin[User]
    ApplicationModelAdmin = admin.ModelAdmin[SellerApplication]
    OutboxModelAdmin = admin.ModelAdmin[Outbox]
else:
    UserModelAdmin = ApplicationModelAdmin = OutboxModelAdmin = admin.ModelAdmin


@admin.register(User)
class UserAdmin(UserModelAdmin):
    list_display = ("phone", "full_name", "role", "is_active", "date_joined")
    list_filter = ("role", "is_active")
    search_fields = ("phone", "full_name")
    readonly_fields = ("id", "date_joined", "last_login")
    exclude = ("password",)


@admin.register(SellerApplication)
class SellerApplicationAdmin(ApplicationModelAdmin):
    """Reviews go through the API, which also writes the outbox event."""

    list_display = ("shop_name", "user", "status", "created_at", "reviewed_at")
    list_filter = ("status",)
    search_fields = ("shop_name", "inn", "user__phone")

    def has_change_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False


@admin.register(Outbox)
class OutboxAdmin(OutboxModelAdmin):
    list_display = ("event_type", "event_id", "created_at", "published_at")
    list_filter = ("event_type",)

    def has_change_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False

    def has_add_permission(self, request: HttpRequest) -> bool:
        return False

    def has_delete_permission(self, request: HttpRequest, obj: object = None) -> bool:
        return False
