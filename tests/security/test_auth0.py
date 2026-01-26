import time

import pytest
from jose import jwt
from jose.exceptions import ExpiredSignatureError, JWTError
from jose.utils import base64url_encode

from app.core.auth import auth0


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
    auth0.clear_jwks_cache()
    monkeypatch.setattr(
        jwt, "get_unverified_header", lambda _t: {"kid": "missing", "alg": "RS256"}
    )

    def fake_fetch():
        return {"keys": [{"kid": "other"}]}

    monkeypatch.setattr(auth0, "_fetch_jwks", fake_fetch)

    with pytest.raises(auth0.Auth0Error) as exc:
        auth0.decode_auth0_token("tok")
    assert "Signing key not found" in str(exc.value.detail)


def test_decode_auth0_token_invalid_signature(monkeypatch):
    auth0.clear_jwks_cache()
    monkeypatch.setattr(
        jwt, "get_unverified_header", lambda _t: {"kid": "k1", "alg": "RS256"}
    )

    def fake_fetch():
        return {"keys": [{"kid": "k1"}]}

    monkeypatch.setattr(auth0, "_fetch_jwks", fake_fetch)

    def bad_decode(token, key, algorithms, audience, issuer, options):
        raise JWTError("invalid")

    monkeypatch.setattr(jwt, "decode", bad_decode)

    with pytest.raises(auth0.Auth0Error) as exc:
        auth0.decode_auth0_token("tok")
    assert "Invalid token" in str(exc.value.detail)


def test_get_jwks_fetches_and_caches(monkeypatch):
    auth0.clear_jwks_cache()

    calls = []

    def fake_fetch():
        calls.append("fetch")
        return {"keys": [{"kid": "k1"}]}

    monkeypatch.setattr(auth0, "_fetch_jwks", fake_fetch)

    jwks = auth0.get_jwks()
    assert jwks["keys"][0]["kid"] == "k1"
    assert calls == ["fetch"]

    jwks = auth0.get_jwks()
    assert jwks["keys"][0]["kid"] == "k1"
    assert calls == ["fetch"]


def test_decode_auth0_token_success(monkeypatch):
    auth0.clear_jwks_cache()
    monkeypatch.setattr(
        jwt, "get_unverified_header", lambda _t: {"kid": "kid1", "alg": "RS256"}
    )

    def fake_fetch():
        return {"keys": [{"kid": "kid1"}]}

    monkeypatch.setattr(auth0, "_fetch_jwks", fake_fetch)

    def ok_decode(token, key, algorithms, audience, issuer, options):
        assert isinstance(algorithms, list)
        assert "RS256" in algorithms
        assert options["leeway"] == auth0.settings.auth.AUTH0_LEEWAY_SECONDS
        return {"email": "ok@example.com"}

    monkeypatch.setattr(jwt, "decode", ok_decode)

    claims = auth0.decode_auth0_token("tok")
    assert claims["email"] == "ok@example.com"


def test_decode_auth0_token_invalid_issuer(monkeypatch):
    auth0.clear_jwks_cache()
    monkeypatch.setattr(
        jwt, "get_unverified_header", lambda _t: {"kid": "kid1", "alg": "RS256"}
    )

    def fake_fetch():
        return {"keys": [{"kid": "kid1"}]}

    monkeypatch.setattr(auth0, "_fetch_jwks", fake_fetch)

    def bad_decode(token, key, algorithms, audience, issuer, options):
        assert issuer == auth0.settings.auth.issuer
        raise JWTError("invalid issuer")

    monkeypatch.setattr(jwt, "decode", bad_decode)

    with pytest.raises(auth0.Auth0Error):
        auth0.decode_auth0_token("tok")


def test_decode_auth0_token_invalid_audience(monkeypatch):
    auth0.clear_jwks_cache()
    monkeypatch.setattr(
        jwt, "get_unverified_header", lambda _t: {"kid": "kid1", "alg": "RS256"}
    )

    def fake_fetch():
        return {"keys": [{"kid": "kid1"}]}

    monkeypatch.setattr(auth0, "_fetch_jwks", fake_fetch)

    def bad_decode(token, key, algorithms, audience, issuer, options):
        assert audience == auth0.settings.auth.audience
        raise JWTError("invalid audience")

    monkeypatch.setattr(jwt, "decode", bad_decode)

    with pytest.raises(auth0.Auth0Error):
        auth0.decode_auth0_token("tok")


def test_decode_auth0_token_rejects_unapproved_alg(monkeypatch):
    auth0.clear_jwks_cache()
    monkeypatch.setattr(
        jwt, "get_unverified_header", lambda _t: {"kid": "kid1", "alg": "HS256"}
    )
    with pytest.raises(auth0.Auth0Error) as excinfo:
        auth0.decode_auth0_token("tok")
    assert "algorithm" in excinfo.value.detail


def test_decode_auth0_token_expired(monkeypatch):
    auth0.clear_jwks_cache()
    monkeypatch.setattr(
        jwt, "get_unverified_header", lambda _t: {"kid": "kid1", "alg": "RS256"}
    )

    def fake_fetch():
        return {"keys": [{"kid": "kid1"}]}

    monkeypatch.setattr(auth0, "_fetch_jwks", fake_fetch)

    def bad_decode(token, key, algorithms, audience, issuer, options):
        raise ExpiredSignatureError("expired")

    monkeypatch.setattr(jwt, "decode", bad_decode)

    with pytest.raises(auth0.Auth0Error) as exc:
        auth0.decode_auth0_token("tok")
    assert "expired" in str(exc.value.detail).lower()


def test_get_jwks_fetch_failure(monkeypatch):
    auth0.clear_jwks_cache()

    def bad_fetch():
        raise auth0.httpx.ConnectError("down")

    monkeypatch.setattr(auth0, "_fetch_jwks", bad_fetch)

    with pytest.raises(auth0.Auth0Error) as exc:
        auth0.get_jwks()
    assert exc.value.status_code == 503


def test_decode_auth0_token_refreshes_jwks_on_kid_miss(monkeypatch):
    auth0.clear_jwks_cache()
    monkeypatch.setattr(
        jwt, "get_unverified_header", lambda _t: {"kid": "kid2", "alg": "RS256"}
    )

    responses = [{"keys": [{"kid": "kid1"}]}, {"keys": [{"kid": "kid2"}]}]

    def fake_fetch():
        return responses.pop(0)

    monkeypatch.setattr(auth0, "_fetch_jwks", fake_fetch)

    def ok_decode(token, key, algorithms, audience, issuer, options):
        return {"email": "ok@example.com"}

    monkeypatch.setattr(jwt, "decode", ok_decode)

    claims = auth0.decode_auth0_token("tok")
    assert claims["email"] == "ok@example.com"


def test_decode_auth0_token_refreshes_once_and_still_missing(monkeypatch):
    auth0.clear_jwks_cache()
    monkeypatch.setattr(
        jwt, "get_unverified_header", lambda _t: {"kid": "missing", "alg": "RS256"}
    )

    calls = []

    def fake_fetch():
        calls.append("fetch")
        return {"keys": [{"kid": "other"}]}

    monkeypatch.setattr(auth0, "_fetch_jwks", fake_fetch)

    with pytest.raises(auth0.Auth0Error) as exc:
        auth0.decode_auth0_token("tok")
    assert "Signing key not found" in str(exc.value.detail)
    assert calls == ["fetch", "fetch"]


def test_decode_auth0_token_accepts_audience_list(monkeypatch):
    auth0.clear_jwks_cache()
    monkeypatch.setattr(
        jwt, "get_unverified_header", lambda _t: {"kid": "kid1", "alg": "RS256"}
    )

    def fake_fetch():
        return {"keys": [{"kid": "kid1"}]}

    monkeypatch.setattr(auth0, "_fetch_jwks", fake_fetch)

    def ok_decode(token, key, algorithms, audience, issuer, options):
        assert audience == auth0.settings.auth.audience
        return {"email": "ok@example.com", "aud": [audience, "other"]}

    monkeypatch.setattr(jwt, "decode", ok_decode)

    claims = auth0.decode_auth0_token("tok")
    assert claims["email"] == "ok@example.com"


def test_decode_auth0_token_leeway_allows_recent_expiry(monkeypatch):
    auth0.clear_jwks_cache()
    secret = "test-secret"
    kid = "hs1"
    leeway_seconds = 30

    jwks = {
        "keys": [
            {
                "kid": kid,
                "kty": "oct",
                "k": base64url_encode(secret.encode("utf-8")).decode("ascii"),
                "alg": "HS256",
                "use": "sig",
            }
        ]
    }

    monkeypatch.setattr(auth0, "_fetch_jwks", lambda: jwks)
    monkeypatch.setattr(auth0.settings.auth, "AUTH0_ALGORITHMS", "HS256")
    monkeypatch.setattr(auth0.settings.auth, "AUTH0_API_AUDIENCE", "api://aud")
    monkeypatch.setattr(auth0.settings.auth, "AUTH0_ISSUER", "https://issuer.test/")
    monkeypatch.setattr(auth0.settings.auth, "AUTH0_LEEWAY_SECONDS", leeway_seconds)

    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "auth0|leeway",
            "aud": auth0.settings.auth.audience,
            "iss": auth0.settings.auth.issuer,
            "exp": now - (leeway_seconds - 5),
        },
        secret,
        algorithm="HS256",
        headers={"kid": kid},
    )

    claims = auth0.decode_auth0_token(token)
    assert claims["sub"] == "auth0|leeway"


def test_decode_auth0_token_leeway_rejects_too_old(monkeypatch):
    auth0.clear_jwks_cache()
    secret = "test-secret"
    kid = "hs1"
    leeway_seconds = 30

    jwks = {
        "keys": [
            {
                "kid": kid,
                "kty": "oct",
                "k": base64url_encode(secret.encode("utf-8")).decode("ascii"),
                "alg": "HS256",
                "use": "sig",
            }
        ]
    }

    monkeypatch.setattr(auth0, "_fetch_jwks", lambda: jwks)
    monkeypatch.setattr(auth0.settings.auth, "AUTH0_ALGORITHMS", "HS256")
    monkeypatch.setattr(auth0.settings.auth, "AUTH0_API_AUDIENCE", "api://aud")
    monkeypatch.setattr(auth0.settings.auth, "AUTH0_ISSUER", "https://issuer.test/")
    monkeypatch.setattr(auth0.settings.auth, "AUTH0_LEEWAY_SECONDS", leeway_seconds)

    now = int(time.time())
    token = jwt.encode(
        {
            "sub": "auth0|leeway",
            "aud": auth0.settings.auth.audience,
            "iss": auth0.settings.auth.issuer,
            "exp": now - (leeway_seconds + 5),
        },
        secret,
        algorithm="HS256",
        headers={"kid": kid},
    )

    with pytest.raises(auth0.Auth0Error) as exc:
        auth0.decode_auth0_token(token)
    assert "expired" in str(exc.value.detail).lower()


def test_issuer_normalization_used_for_decode(monkeypatch):
    auth0.clear_jwks_cache()
    monkeypatch.setattr(auth0.settings.auth, "AUTH0_ISSUER", "https://issuer.test")
    monkeypatch.setattr(
        jwt, "get_unverified_header", lambda _t: {"kid": "kid1", "alg": "RS256"}
    )

    def fake_fetch():
        return {"keys": [{"kid": "kid1"}]}

    monkeypatch.setattr(auth0, "_fetch_jwks", fake_fetch)

    def ok_decode(token, key, algorithms, audience, issuer, options):
        assert issuer == "https://issuer.test/"
        return {"email": "ok@example.com"}

    monkeypatch.setattr(jwt, "decode", ok_decode)

    claims = auth0.decode_auth0_token("tok")
    assert claims["email"] == "ok@example.com"


def test_decode_auth0_token_does_not_pass_leeway_kwarg(monkeypatch):
    auth0.clear_jwks_cache()
    monkeypatch.setattr(
        jwt, "get_unverified_header", lambda _t: {"kid": "kid1", "alg": "RS256"}
    )

    def fake_fetch():
        return {"keys": [{"kid": "kid1"}]}

    monkeypatch.setattr(auth0, "_fetch_jwks", fake_fetch)

    def ok_decode(token, key, algorithms, audience, issuer, options):
        return {"email": "ok@example.com"}

    monkeypatch.setattr(jwt, "decode", ok_decode)

    claims = auth0.decode_auth0_token("tok")
    assert claims["email"] == "ok@example.com"


def test_auth_settings_properties_and_algorithms():
    obj = auth0.settings.auth
    obj.AUTH0_DOMAIN = "tenant.auth0.com"
    obj.AUTH0_API_AUDIENCE = "api://aud"
    obj.AUTH0_ALGORITHMS = "RS256,HS256"
    assert obj.issuer.endswith("/")
    assert obj.jwks_url.endswith(".well-known/jwks.json")
    assert obj.algorithms == ["RS256", "HS256"]


def test_close_http_client(monkeypatch):
    closed = {}

    class DummyClient:
        def close(self):
            closed["closed"] = True

    monkeypatch.setattr(auth0, "_http_client", DummyClient())
    auth0._close_http_client()
    assert closed.get("closed") is True


def test_fetch_jwks_uses_http_client(monkeypatch):
    called = {}

    class DummyResponse:
        def raise_for_status(self):
            called["raised"] = True

        def json(self):
            return {"keys": []}

    class DummyClient:
        def get(self, url):
            called["url"] = url
            return DummyResponse()

    monkeypatch.setattr(auth0, "_http_client", DummyClient())
    monkeypatch.setattr(auth0.settings.auth, "AUTH0_DOMAIN", "tenant.auth0.com")
    data = auth0._fetch_jwks()
    assert data["keys"] == []
    assert called.get("raised") is True


def test_get_jwks_returns_cached_inside_lock(monkeypatch):
    auth0.clear_jwks_cache()
    auth0._jwks_cache["jwks"] = {"keys": [{"kid": "k1"}]}
    auth0._jwks_cache["fetched_at"] = 0.0
    times = iter([5000.0, 0.0])
    monkeypatch.setattr(auth0.time, "time", lambda: next(times))
    monkeypatch.setattr(auth0.settings.auth, "AUTH0_JWKS_CACHE_TTL_SECONDS", 3600)
    jwks = auth0.get_jwks()
    assert jwks["keys"][0]["kid"] == "k1"
