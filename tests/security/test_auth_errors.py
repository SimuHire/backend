from fastapi import status

from app.core.auth.errors import AuthError


def test_auth_error_defaults():
    err = AuthError("nope")
    assert err.status_code == status.HTTP_401_UNAUTHORIZED
    assert err.detail == "nope"


def test_auth_error_custom_status():
    err = AuthError("forbidden", status_code=status.HTTP_403_FORBIDDEN)
    assert err.status_code == status.HTTP_403_FORBIDDEN
