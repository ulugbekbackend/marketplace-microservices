"""Money helpers. Amounts are always integer tiyin (1 so'm = 100 tiyin). No floats."""

from decimal import ROUND_HALF_UP, Decimal
from typing import Annotated

from pydantic import Field

#: A non negative amount in tiyin.
Tiyin = Annotated[int, Field(ge=0)]

TIYIN_IN_SOM = 100


def som_to_tiyin(som: int | str | Decimal) -> int:
    """Convert so'm (integer, string or Decimal) to tiyin, rounding half up."""
    value = Decimal(som) * TIYIN_IN_SOM
    return int(value.quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def apply_commission(gross_tiyin: int, rate: Decimal) -> int:
    """Commission for a gross amount, rounded half up to whole tiyin."""
    if gross_tiyin < 0:
        raise ValueError("gross_tiyin must not be negative")
    if not Decimal(0) <= rate <= Decimal(1):
        raise ValueError("rate must be between 0 and 1")
    return int((Decimal(gross_tiyin) * rate).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_tiyin(amount_tiyin: int) -> str:
    """Human readable amount for notifications: 125000000 -> "1 250 000 so'm"."""
    som, tiyin = divmod(amount_tiyin, TIYIN_IN_SOM)
    grouped = f"{som:,}".replace(",", "\u00a0")
    return f"{grouped},{tiyin:02d} so'm" if tiyin else f"{grouped} so'm"
