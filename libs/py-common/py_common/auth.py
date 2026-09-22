"""Identity comes from the gateway: services read headers, they never verify tokens."""

from collections.abc import Mapping
from dataclasses import dataclass
from uuid import UUID

from contracts.enums import UserRole
from contracts.headers import X_SELLER_ID, X_USER_ID, X_USER_ROLE


class AuthError(Exception):
    """Headers were present but malformed — the gateway or a caller is misbehaving."""


@dataclass(frozen=True, slots=True)
class CurrentUser:
    user_id: UUID
    role: UserRole
    seller_id: UUID | None = None

    @property
    def is_seller(self) -> bool:
        return self.role is UserRole.SELLER

    @property
    def is_admin(self) -> bool:
        return self.role is UserRole.ADMIN


def parse_user_headers(headers: Mapping[str, str]) -> CurrentUser | None:
    """Build the current user from gateway headers, or None for an anonymous request."""
    lookup = {key.lower(): value for key, value in headers.items()}
    raw_id = lookup.get(X_USER_ID.lower())
    raw_role = lookup.get(X_USER_ROLE.lower())
    if not raw_id and not raw_role:
        return None
    if not raw_id or not raw_role:
        raise AuthError("incomplete identity headers")

    try:
        user_id = UUID(raw_id)
    except ValueError as exc:
        raise AuthError("invalid user id header") from exc
    try:
        role = UserRole(raw_role)
    except ValueError as exc:
        raise AuthError("unknown role header") from exc

    seller_id: UUID | None = None
    raw_seller = lookup.get(X_SELLER_ID.lower())
    if raw_seller:
        try:
            seller_id = UUID(raw_seller)
        except ValueError as exc:
            raise AuthError("invalid seller id header") from exc

    return CurrentUser(user_id=user_id, role=role, seller_id=seller_id)
