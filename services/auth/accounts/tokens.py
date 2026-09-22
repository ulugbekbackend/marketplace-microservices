"""RS256 tokens: issue, rotate, revoke, verify, and publish the public key as JWKS.

simplejwt handles claims, expiry and the blacklist tables. The keys are read lazily from
the files named in settings, so importing this module never needs a key on disk.
"""

import base64
import functools
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import UUID

import jwt
from django.conf import settings
from django.db import transaction
from jwt.algorithms import RSAAlgorithm
from rest_framework_simplejwt.backends import TokenBackend
from rest_framework_simplejwt.exceptions import TokenBackendError, TokenError
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.token_blacklist.models import BlacklistedToken, OutstandingToken
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken
from rest_framework_simplejwt.utils import datetime_from_epoch

from accounts.models import Role, User
from contracts.enums import UserRole

ROLE_CLAIM = "role"
SELLER_ID_CLAIM = "seller_id"


class InvalidTokenError(Exception):
    """The token is malformed, expired, revoked, signed by another key or of a wrong type."""


class KeyedTokenBackend(TokenBackend):
    """simplejwt backend that stamps a ``kid`` header, so verifiers can pick the JWKS key."""

    def __init__(self, *, private_key: str, public_key: str, issuer: str) -> None:
        super().__init__("RS256", private_key, public_key, issuer=issuer)
        self.jwk = public_jwk(public_key)
        self.kid = str(self.jwk["kid"])

    def encode(self, payload: dict[str, Any]) -> str:
        claims = dict(payload)
        if self.issuer is not None:
            claims["iss"] = self.issuer
        return jwt.encode(
            claims, self.prepared_signing_key, algorithm=self.algorithm, headers={"kid": self.kid}
        )


def public_jwk(public_pem: str) -> dict[str, Any]:
    """The public key as a JWK with an RFC 7638 thumbprint as ``kid``."""
    key = RSAAlgorithm(RSAAlgorithm.SHA256).prepare_key(public_pem)
    jwk: dict[str, Any] = RSAAlgorithm.to_jwk(key, as_dict=True)
    canonical = json.dumps(
        {"e": jwk["e"], "kty": jwk["kty"], "n": jwk["n"]}, separators=(",", ":"), sort_keys=True
    )
    thumbprint = hashlib.sha256(canonical.encode()).digest()
    kid = base64.urlsafe_b64encode(thumbprint).rstrip(b"=").decode()
    return {
        "kty": jwk["kty"],
        "use": "sig",
        "alg": "RS256",
        "kid": kid,
        "n": jwk["n"],
        "e": jwk["e"],
    }


@functools.cache
def _backend_for(private_path: str, public_path: str, issuer: str) -> KeyedTokenBackend:
    return KeyedTokenBackend(
        private_key=Path(private_path).read_text(encoding="utf-8"),
        public_key=Path(public_path).read_text(encoding="utf-8"),
        issuer=issuer,
    )


def token_backend() -> KeyedTokenBackend:
    """The backend for the key files currently configured (cached per path)."""
    return _backend_for(
        settings.JWT_PRIVATE_KEY_PATH, settings.JWT_PUBLIC_KEY_PATH, settings.JWT_ISSUER
    )


class _ServiceBackendMixin:
    @property
    def token_backend(self) -> TokenBackend:
        return token_backend()


class ServiceAccessToken(_ServiceBackendMixin, AccessToken):
    pass


class ServiceRefreshToken(_ServiceBackendMixin, RefreshToken):  # type: ignore[misc]
    access_token_class = ServiceAccessToken


@dataclass(frozen=True, slots=True)
class TokenPair:
    access: str
    refresh: str


@dataclass(frozen=True, slots=True)
class Identity:
    """What the gateway forwards to the services after a successful check."""

    user_id: UUID
    role: UserRole
    seller_id: UUID | None


def issue_tokens(user: User) -> TokenPair:
    """A new refresh/access pair with the user's current role; the refresh is tracked."""
    refresh = ServiceRefreshToken()
    refresh[api_settings.USER_ID_CLAIM] = str(user.id)
    refresh[ROLE_CLAIM] = user.role
    if user.role == Role.SELLER:
        refresh[SELLER_ID_CLAIM] = str(user.id)
    encoded = str(refresh)
    OutstandingToken.objects.create(
        user=user,
        jti=refresh["jti"],
        token=encoded,
        created_at=refresh.current_time,
        expires_at=datetime_from_epoch(refresh["exp"]),
    )
    return TokenPair(access=str(refresh.access_token), refresh=encoded)


def _parse_refresh(raw: str) -> ServiceRefreshToken:
    try:
        return ServiceRefreshToken(raw)  # type: ignore[arg-type]
    except TokenError as exc:
        raise InvalidTokenError(str(exc)) from exc


def _lock_outstanding(jti: str) -> OutstandingToken | None:
    """Row lock on the token, so two concurrent uses of one refresh cannot both pass."""
    # order_by(): the default ordering joins the nullable user, which FOR UPDATE refuses.
    return OutstandingToken.objects.select_for_update().filter(jti=jti).order_by().first()


def _user_id(token: ServiceRefreshToken | ServiceAccessToken) -> str:
    return str(token.get(api_settings.USER_ID_CLAIM, ""))


def rotate_refresh(raw: str) -> TokenPair:
    """Spend a refresh token once: blacklist it and issue a fresh pair with current claims."""
    token = _parse_refresh(raw)
    with transaction.atomic():
        outstanding = _lock_outstanding(str(token["jti"]))
        if outstanding is None or BlacklistedToken.objects.filter(token=outstanding).exists():
            raise InvalidTokenError("Token is blacklisted")
        user = User.objects.filter(pk=_user_id(token), is_active=True).first()
        if user is None:
            raise InvalidTokenError("User is inactive or gone")
        BlacklistedToken.objects.create(token=outstanding)
        return issue_tokens(user)


def revoke_refresh(raw: str) -> None:
    """Blacklist a refresh token (logout). Revoking an already revoked token is a no-op."""
    try:
        payload = token_backend().decode(raw)  # type: ignore[arg-type]
    except TokenBackendError as exc:
        raise InvalidTokenError(str(exc)) from exc
    if payload.get("token_type") != ServiceRefreshToken.token_type or "jti" not in payload:
        raise InvalidTokenError("Token has wrong type")
    with transaction.atomic():
        outstanding = _lock_outstanding(str(payload["jti"]))
        if outstanding is None:
            raise InvalidTokenError("Token is unknown")
        BlacklistedToken.objects.get_or_create(token=outstanding)


def verify_access(raw: str) -> Identity:
    """Check an access token for the gateway: signature and expiry locally, then one PK lookup.

    The lookup makes deactivation and role changes effective at once instead of after up to
    ACCESS_TOKEN_LIFETIME; it hits the primary key index and reads one column.
    """
    try:
        token = ServiceAccessToken(raw)  # type: ignore[arg-type]
    except TokenError as exc:
        raise InvalidTokenError(str(exc)) from exc
    try:
        user_id = UUID(_user_id(token))
    except ValueError as exc:
        raise InvalidTokenError("Token has no valid subject") from exc
    row = User.objects.filter(pk=user_id, is_active=True).values_list("role", flat=True).first()
    if row is None:
        raise InvalidTokenError("User is inactive or gone")
    role = UserRole(row)
    return Identity(
        user_id=user_id, role=role, seller_id=user_id if role is UserRole.SELLER else None
    )


def jwks() -> dict[str, list[dict[str, Any]]]:
    return {"keys": [token_backend().jwk]}
