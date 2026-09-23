"""Map the gateway identity to a shop."""

from rest_framework.request import Request

from py_common.web.drf import ApiError, current_user
from sellers.models import Seller


def resolve_seller(request: Request) -> Seller:
    """The caller's shop. The seller id is the user id; X-Seller-Id carries it."""
    user = current_user(request)
    seller = None
    if user is not None:
        seller = Seller.objects.filter(id=user.seller_id or user.user_id).first()
    if seller is None:
        raise ApiError(
            "SELLER_NOT_FOUND", "No shop is registered for this seller account.", status=403
        )
    return seller
