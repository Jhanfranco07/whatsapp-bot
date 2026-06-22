from fastapi import Header, HTTPException

from app.config import get_settings


def verify_admin_key(value: str | None) -> None:
    expected = get_settings().admin_api_key
    if expected and value != expected:
        raise HTTPException(401, "Clave admin inválida")


def verify_inbound_key(value: str | None) -> None:
    expected = get_settings().inbound_api_key
    if expected and value != expected:
        raise HTTPException(401, "Clave inbound inválida")


def require_admin_key(
    x_admin_api_key: str | None = Header(default=None),
) -> None:
    verify_admin_key(x_admin_api_key)


def require_inbound_key(
    x_inbound_api_key: str | None = Header(default=None),
) -> None:
    verify_inbound_key(x_inbound_api_key)
