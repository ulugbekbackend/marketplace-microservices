import pytest
from django.core.exceptions import ValidationError
from pytest_django import Settings

from accounts.phone import InvalidPhoneError, normalize_phone, validate_e164_phone


@pytest.mark.parametrize(
    "raw",
    ["+998901234567", "998901234567", "90 123 45 67", "+998 (90) 123-45-67", " 901234567 "],
)
def test_uzbek_formats_normalise_to_e164(raw: str) -> None:
    assert normalize_phone(raw) == "+998901234567"


@pytest.mark.parametrize("raw", ["", "hello", "+99890123", "+9989012345678901", "12"])
def test_invalid_numbers_are_rejected(raw: str) -> None:
    with pytest.raises(InvalidPhoneError):
        normalize_phone(raw)


def test_other_countries_are_rejected_by_default() -> None:
    with pytest.raises(InvalidPhoneError, match="not supported"):
        normalize_phone("+14155552671")


def test_allowed_regions_come_from_settings(settings: Settings) -> None:
    settings.PHONE_ALLOWED_REGIONS = ["UZ", "US"]

    assert normalize_phone("+1 415 555 2671") == "+14155552671"


def test_model_validator_requires_the_normalised_form() -> None:
    validate_e164_phone("+998901234567")
    with pytest.raises(ValidationError):
        validate_e164_phone("901234567")
    with pytest.raises(ValidationError):
        validate_e164_phone("nonsense")
