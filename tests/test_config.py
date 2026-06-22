import pytest

from app.config import Settings


def test_production_rejects_missing_security_keys():
    settings = Settings(
        _env_file=None,
        app_env="production",
        admin_api_key="",
        inbound_api_key="",
    )

    with pytest.raises(RuntimeError, match="ADMIN_API_KEY"):
        settings.validate_production()


def test_production_accepts_explicit_security_keys():
    settings = Settings(
        _env_file=None,
        app_env="production",
        admin_api_key="admin-segura-123",
        inbound_api_key="inbound-segura-123",
    )

    settings.validate_production()
