"""Settings: the mock provider exists only with PAYMENT_MOCK_ENABLED and DEBUG both on."""

import pytest
from app.core.config import load_settings


@pytest.mark.parametrize(
    ("flag", "debug", "enabled"),
    [("True", "True", True), ("True", "False", False), ("False", "True", False)],
)
def test_mock_needs_the_flag_and_debug(
    monkeypatch: pytest.MonkeyPatch, flag: str, debug: str, enabled: bool
) -> None:
    monkeypatch.setenv("PAYMENT_MOCK_ENABLED", flag)
    monkeypatch.setenv("DEBUG", debug)

    assert load_settings().mock_enabled is enabled
