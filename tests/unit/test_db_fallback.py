from app.core import db


def test_create_engine_uses_sqlite_fallback(monkeypatch):
    class FakeSettings:
        def __init__(self):
            self._called = False

        @property
        def async_url(self):
            self._called = True
            raise ValueError("missing")

    fake_settings = FakeSettings()
    monkeypatch.setattr(db, "settings", type("Obj", (), {"database": fake_settings}))
    monkeypatch.setattr(db, "USING_SQLITE_FALLBACK", False)

    engine = db._create_engine()
    assert "sqlite" in str(engine.url)
    assert db.USING_SQLITE_FALLBACK is True
