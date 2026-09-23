from decimal import Decimal

from django.db import models


class Seller(models.Model):
    """A shop. Its id is the owner's auth user id (the gateway's X-Seller-Id)."""

    id = models.UUIDField(primary_key=True)
    user_id = models.UUIDField(unique=True)
    shop_name = models.CharField(max_length=120)
    slug = models.SlugField(max_length=140, unique=True)
    commission_rate = models.DecimalField(max_digits=5, decimal_places=4, default=Decimal("0.1000"))
    is_verified = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("shop_name",)
        constraints = (
            models.CheckConstraint(
                condition=models.Q(commission_rate__gte=0, commission_rate__lte=1),
                name="seller_commission_rate_range",
            ),
            models.CheckConstraint(
                condition=models.Q(id=models.F("user_id")),
                name="seller_id_is_user_id",
            ),
        )

    def __str__(self) -> str:
        return self.shop_name
