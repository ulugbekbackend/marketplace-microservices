"""Shared fixtures: throwaway RSA keys, fake Redis, users and gateway-authenticated clients."""

from collections.abc import Callable, Iterator
from dataclasses import dataclass
from pathlib import Path

import fakeredis
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from pytest_django import Settings
from rest_framework.test import APIClient

from accounts import redis_client
from accounts.models import Role, User
from contracts.headers import X_SELLER_ID, X_USER_ID, X_USER_ROLE
from tests.factories import make_user


@dataclass(frozen=True)
class KeyPair:
    private_pem: str
    public_pem: str
    private_path: Path
    public_path: Path


def _make_key_pair(directory: Path) -> KeyPair:
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    private_pem = key.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    ).decode()
    public_pem = (
        key.public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )
    directory.mkdir(parents=True, exist_ok=True)
    private_path = directory / "private.pem"
    public_path = directory / "public.pem"
    private_path.write_text(private_pem, encoding="utf-8")
    public_path.write_text(public_pem, encoding="utf-8")
    return KeyPair(private_pem, public_pem, private_path, public_path)


@pytest.fixture(scope="session")
def jwt_keys(tmp_path_factory: pytest.TempPathFactory) -> KeyPair:
    return _make_key_pair(tmp_path_factory.mktemp("jwt") / "service")


@pytest.fixture(scope="session")
def foreign_keys(tmp_path_factory: pytest.TempPathFactory) -> KeyPair:
    """A key pair the service does not trust."""
    return _make_key_pair(tmp_path_factory.mktemp("jwt") / "foreign")


@pytest.fixture(autouse=True)
def _jwt_settings(settings: Settings, jwt_keys: KeyPair) -> None:
    settings.JWT_PRIVATE_KEY_PATH = str(jwt_keys.private_path)
    settings.JWT_PUBLIC_KEY_PATH = str(jwt_keys.public_path)


@pytest.fixture(autouse=True)
def fake_redis(monkeypatch: pytest.MonkeyPatch) -> Iterator[fakeredis.FakeRedis]:
    client = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(redis_client, "_client", client)
    yield client
    client.flushall()


@pytest.fixture
def api() -> APIClient:
    return APIClient()


def gateway_headers(user: User) -> dict[str, str]:
    """The headers Traefik adds after /verify/ accepted the user's token."""
    headers = {f"HTTP_{X_USER_ID.upper().replace('-', '_')}": str(user.id)}
    headers[f"HTTP_{X_USER_ROLE.upper().replace('-', '_')}"] = user.role
    if user.role == Role.SELLER:
        headers[f"HTTP_{X_SELLER_ID.upper().replace('-', '_')}"] = str(user.id)
    return headers


@pytest.fixture
def client_for() -> Callable[[User], APIClient]:
    def build(user: User) -> APIClient:
        client = APIClient()
        client.credentials(**gateway_headers(user))
        return client

    return build


@pytest.fixture
def customer(db: None) -> User:
    return make_user()


@pytest.fixture
def seller(db: None) -> User:
    return make_user(role=Role.SELLER)


@pytest.fixture
def admin_user(db: None) -> User:
    return make_user(role=Role.ADMIN)
