"""Phone numbers: parsed with libphonenumber and stored in E.164 (+998901234567)."""

import phonenumbers
from django.conf import settings
from django.core.exceptions import ValidationError

DEFAULT_REGION = "UZ"


class InvalidPhoneError(ValueError):
    """The value is not a valid phone number of an allowed region."""


def normalize_phone(raw: str) -> str:
    """Return the E.164 form of ``raw``; local Uzbek formats (90 123 45 67) are accepted."""
    try:
        number = phonenumbers.parse(raw.strip(), DEFAULT_REGION)
    except phonenumbers.NumberParseException as exc:
        raise InvalidPhoneError("Not a phone number.") from exc
    if not phonenumbers.is_valid_number(number):
        raise InvalidPhoneError("Not a valid phone number.")
    region = phonenumbers.region_code_for_number(number)
    if region not in settings.PHONE_ALLOWED_REGIONS:
        raise InvalidPhoneError("Phone numbers of this country are not supported.")
    return phonenumbers.format_number(number, phonenumbers.PhoneNumberFormat.E164)


def validate_e164_phone(value: str) -> None:
    """Model validator: the stored value must already be normalised."""
    try:
        normalized = normalize_phone(value)
    except InvalidPhoneError as exc:
        raise ValidationError(str(exc), code="invalid_phone") from exc
    if normalized != value:
        raise ValidationError("Phone must be stored in E.164 format.", code="invalid_phone")
