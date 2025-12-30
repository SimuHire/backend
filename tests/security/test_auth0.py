import pytest
from jose import jwt
from jose.exceptions import JWTError

from app.infra.security import auth0


def test_decode_auth0_token_invalid_header(monkeypatch):
    def bad_header(_token):
        raise JWTError("bad header")

    monkeypatch.setattr(jwt, "get_unverified_header", bad_header)

    with pytest.raises(auth0.Auth0Error):
        auth0.decode_auth0_token("tok")


def test_decode_auth0_token_missing_kid(monkeypatch):
    monkeypatch.setattr(jwt, "get_unverified_header", lambda _t: {})

    with pytest.raises(auth0.Auth0Error) as exc:
        auth0.decode_auth0_token("tok")
    assert "kid" in str(exc.value.detail)


def test_decode_auth0_token_key_not_found(monkeypatch):
    monkeypatch.setattr(jwt, "get_unverified_header", lambda _t: {"kid": "missing"})
    monkeypatch.setattr(auth0, "get_jwks", lambda: {"keys": [{"kid": "other"}]})

    with pytest.raises(auth0.Auth0Error) as exc:
        auth0.decode_auth0_token("tok")
    assert "Signing key not found" in str(exc.value.detail)


def test_decode_auth0_token_invalid_signature(monkeypatch):
    monkeypatch.setattr(jwt, "get_unverified_header", lambda _t: {"kid": "k1"})
    monkeypatch.setattr(auth0, "get_jwks", lambda: {"keys": [{"kid": "k1"}]})

    def bad_decode(token, key, algorithms, audience, issuer, options):
        raise JWTError("invalid")

    monkeypatch.setattr(jwt, "decode", bad_decode)

    with pytest.raises(auth0.Auth0Error) as exc:
        auth0.decode_auth0_token("tok")
    assert "Invalid token" in str(exc.value.detail)


def test_get_jwks_fetches_and_caches(monkeypatch):
    auth0.get_jwks.cache_clear()

    class DummyResponse:
        def __init__(self):
            self.called = False

        def raise_for_status(self):
            self.called = True

        def json(self):
            return {"keys": [{"kid": "k1"}]}

    resp = DummyResponse()
    monkeypatch.setattr(auth0.httpx, "get", lambda url, timeout=5: resp)

    jwks = auth0.get_jwks()
    assert jwks["keys"][0]["kid"] == "k1"
    assert resp.called is True


def test_decode_auth0_token_success(monkeypatch):
    auth0.get_jwks.cache_clear()
    monkeypatch.setattr(jwt, "get_unverified_header", lambda _t: {"kid": "kid1"})
    monkeypatch.setattr(auth0, "get_jwks", lambda: {"keys": [{"kid": "kid1"}]})
    monkeypatch.setattr(
        jwt,
        "decode",
        lambda token, key, algorithms, audience, issuer, options: {
            "email": "ok@example.com"
        },
    )

    claims = auth0.decode_auth0_token("tok")
    assert claims["email"] == "ok@example.com"
