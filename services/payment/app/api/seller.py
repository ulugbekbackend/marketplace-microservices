"""Seller payouts: what the marketplace owes the shop, week by week."""

from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select

from app.core.deps import Sessions
from app.models import PayoutLine, SellerPayout
from app.schemas import PayoutOut, PayoutPage
from py_common.auth import CurrentUser
from py_common.web.fastapi import ApiError, required_user

router = APIRouter(prefix="/api/payments/seller", tags=["seller"])

MAX_PAGE_SIZE = 100


def seller_id_of(user: Annotated[CurrentUser, Depends(required_user)]) -> CurrentUser:
    if not user.is_seller or user.seller_id is None:
        raise ApiError("PERMISSION_DENIED", "Only sellers have payouts.", status=403)
    return user


Seller = Annotated[CurrentUser, Depends(seller_id_of)]


@router.get(
    "/payouts/",
    response_model=PayoutPage,
    operation_id="payments_seller_payouts",
    responses={403: {"description": "PERMISSION_DENIED: not a seller"}},
)
async def seller_payouts(
    seller: Seller,
    sessions: Sessions,
    page: Annotated[int, Query(ge=1)] = 1,
    page_size: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 20,
) -> PayoutPage:
    """The seller's weekly payouts, newest week first."""
    lines_count = (
        select(func.count())
        .where(PayoutLine.payout_id == SellerPayout.id)
        .correlate(SellerPayout)
        .scalar_subquery()
    )
    own = SellerPayout.seller_id == seller.seller_id
    async with sessions() as session:
        total = await session.scalar(select(func.count()).select_from(SellerPayout).where(own))
        rows = (
            await session.execute(
                select(SellerPayout, lines_count)
                .where(own)
                .order_by(SellerPayout.period_start.desc())
                .offset((page - 1) * page_size)
                .limit(page_size)
            )
        ).all()
    items = [
        PayoutOut(
            id=payout.id,
            period_start=payout.period_start,
            period_end=payout.period_end,
            gross_tiyin=payout.gross_tiyin,
            commission_tiyin=payout.commission_tiyin,
            net_tiyin=payout.net_tiyin,
            status=payout.status,
            lines_count=count,
            created_at=payout.created_at,
        )
        for payout, count in rows
    ]
    return PayoutPage(items=items, total=int(total or 0), page=page, page_size=page_size)
