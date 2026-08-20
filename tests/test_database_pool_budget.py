from __future__ import annotations

from types import SimpleNamespace

import app.db as db
from app.config import Settings


def test_pool_defaults_are_independent_of_job_concurrency(monkeypatch) -> None:
    monkeypatch.setenv("DATABASE_URL", "postgresql://test:test@localhost/test")
    monkeypatch.setenv("ALPACA_API_KEY", "test")
    monkeypatch.setenv("ALPACA_SECRET_KEY", "test")
    monkeypatch.setenv("MAX_GLOBAL_CONCURRENCY", "50")
    monkeypatch.delenv("DB_POOL_MAX_SIZE", raising=False)
    settings = Settings()
    assert settings.max_global_concurrency == 50
    assert settings.db_pool_max_size == 4
    assert settings.db_pool_max_idle_seconds == 120.0


def test_pool_budget_clamps_invalid_relationships(monkeypatch) -> None:
    monkeypatch.setattr(
        db,
        "get_settings",
        lambda: SimpleNamespace(
            db_pool_min_size=3,
            db_pool_max_size=1,
            db_pool_timeout_seconds=0,
            db_pool_max_idle_seconds=5,
            db_pool_max_lifetime_seconds=10,
            db_pool_max_waiting=0,
            db_application_name="x" * 100,
        ),
    )
    budget = db._pool_budget()
    assert budget["min_size"] == 3
    assert budget["max_size"] == 3
    assert budget["timeout"] == 1.0
    assert budget["max_idle"] == 30.0
    assert budget["max_lifetime"] == 120.0
    assert budget["max_waiting"] == 1
    assert len(str(budget["application_name"])) == 63


def test_connection_pool_receives_bounded_recycling_configuration(monkeypatch) -> None:
    captured = {}

    class FakePool:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def close(self):
            captured["closed"] = True

    settings = SimpleNamespace(
        database_url="postgresql://test:test@localhost/test",
        db_pool_min_size=1,
        db_pool_max_size=2,
        db_pool_timeout_seconds=12.0,
        db_pool_max_idle_seconds=45.0,
        db_pool_max_lifetime_seconds=300.0,
        db_pool_max_waiting=9,
        db_application_name="oversold-test",
    )
    monkeypatch.setattr(db, "get_settings", lambda: settings)
    monkeypatch.setattr(db, "ConnectionPool", FakePool)
    db._pool = None
    try:
        pool = db.get_pool()
        assert isinstance(pool, FakePool)
        assert captured["min_size"] == 1
        assert captured["max_size"] == 2
        assert captured["timeout"] == 12.0
        assert captured["max_idle"] == 45.0
        assert captured["max_lifetime"] == 300.0
        assert captured["max_waiting"] == 9
        assert captured["kwargs"]["application_name"] == "oversold-test"
    finally:
        db.close_pool()
        db._pool = None
