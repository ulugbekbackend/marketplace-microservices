"""Users, one time passwords, seller applications and the event outbox."""

from typing import Any, ClassVar

from django.contrib.auth.base_user import AbstractBaseUser, BaseUserManager
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import Q
from django.utils import timezone

from accounts.phone import normalize_phone, validate_e164_phone
from contracts.enums import UserRole
from contracts.ids import uuid7


class Role(models.TextChoices):
    CUSTOMER = UserRole.CUSTOMER.value, "Customer"
    SELLER = UserRole.SELLER.value, "Seller"
    ADMIN = UserRole.ADMIN.value, "Admin"


class UserManager(BaseUserManager["User"]):
    use_in_migrations = True

    def create_user(self, phone: str, password: str | None = None, **extra: Any) -> "User":
        """Customers and sellers sign in by OTP only, so they get an unusable password."""
        user = self.model(phone=normalize_phone(phone), **extra)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.full_clean(exclude=["password"])
        user.save(using=self._db)
        return user

    def create_superuser(self, phone: str, password: str | None = None, **extra: Any) -> "User":
        """Admins also sign in to the Django admin, so they need a password."""
        if not password:
            raise ValueError("An admin needs a password.")
        extra["role"] = Role.ADMIN
        return self.create_user(phone, password, **extra)


class User(AbstractBaseUser):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    phone = models.CharField(max_length=16, unique=True, validators=[validate_e164_phone])
    full_name = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=16, choices=Role.choices, default=Role.CUSTOMER)
    is_active = models.BooleanField(default=True)
    date_joined = models.DateTimeField(default=timezone.now)

    objects: ClassVar[UserManager] = UserManager()

    USERNAME_FIELD = "phone"
    REQUIRED_FIELDS: ClassVar[list[str]] = []

    class Meta:
        ordering = ("date_joined",)

    def __str__(self) -> str:
        return self.phone

    # The Django admin is the only session based UI and is open to admins only.
    @property
    def is_staff(self) -> bool:
        return self.is_active and self.role == Role.ADMIN

    @property
    def is_superuser(self) -> bool:
        return self.is_staff

    def has_perm(self, perm: str, obj: object = None) -> bool:
        return self.is_staff

    def has_perms(self, perm_list: Any, obj: object = None) -> bool:
        return self.is_staff

    def has_module_perms(self, app_label: str) -> bool:
        return self.is_staff


class OtpCode(models.Model):
    """A sent code. Only its HMAC is stored; the newest row of a phone is the valid one."""

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    phone = models.CharField(max_length=16)
    code_hash = models.CharField(max_length=64)
    expires_at = models.DateTimeField()
    attempts = models.PositiveSmallIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = (models.Index(fields=("phone", "-created_at"), name="otp_phone_created_idx"),)

    def __str__(self) -> str:
        return f"OTP for {self.phone}"


class ApplicationStatus(models.TextChoices):
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class SellerApplication(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="seller_applications")
    shop_name = models.CharField(max_length=120)
    inn = models.CharField(
        max_length=9,
        validators=[RegexValidator(r"^\d{9}$", "INN must be exactly 9 digits.")],
    )
    description = models.TextField(blank=True)
    status = models.CharField(
        max_length=16, choices=ApplicationStatus.choices, default=ApplicationStatus.PENDING
    )
    reviewed_by = models.ForeignKey(
        User,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_seller_applications",
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ("created_at",)
        constraints = (
            # The database, not only the view, keeps a user to one open application.
            models.UniqueConstraint(
                fields=("user",),
                condition=Q(status="pending"),
                name="one_pending_application_per_user",
            ),
        )
        indexes = (models.Index(fields=("status", "created_at"), name="application_status_idx"),)

    def __str__(self) -> str:
        return f"{self.shop_name} ({self.status})"


class Outbox(models.Model):
    """Events waiting to be published; written in the same transaction as the change.

    ``payload`` holds the whole EventEnvelope as JSON, so the publisher sends it unchanged.
    """

    id = models.UUIDField(primary_key=True, default=uuid7, editable=False)
    event_id = models.UUIDField(unique=True)
    event_type = models.CharField(max_length=64)
    payload = models.JSONField()
    created_at = models.DateTimeField(default=timezone.now)
    published_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        verbose_name_plural = "outbox"
        indexes = (
            models.Index(
                fields=("created_at",),
                condition=Q(published_at__isnull=True),
                name="outbox_unpublished_idx",
            ),
        )

    def __str__(self) -> str:
        return f"{self.event_type} {self.event_id}"
