from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import Iterator

from psycopg import Connection
from psycopg.errors import ReadOnlySqlTransaction
from psycopg.rows import dict_row
from psycopg_pool import ConnectionPool

from app.config import get_settings

logger = logging.getLogger(__name__)
_pool: ConnectionPool | None = None


def _pool_budget() -> dict[str, int | float | str]:
    settings = get_settings()
    min_size = max(0, int(settings.db_pool_min_size))
    max_size = max(min_size or 1, int(settings.db_pool_max_size))
    return {
        "min_size": min_size,
        "max_size": max_size,
        "timeout": max(1.0, float(settings.db_pool_timeout_seconds)),
        "max_idle": max(30.0, float(settings.db_pool_max_idle_seconds)),
        "max_lifetime": max(120.0, float(settings.db_pool_max_lifetime_seconds)),
        "max_waiting": max(1, int(settings.db_pool_max_waiting)),
        "application_name": str(settings.db_application_name or "alpaca-rapid-discovery")[:63],
    }


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        settings = get_settings()
        budget = _pool_budget()
        logger.info(
            "Opening PostgreSQL pool application=%s min=%s max=%s max_idle=%ss max_lifetime=%ss",
            budget["application_name"],
            budget["min_size"],
            budget["max_size"],
            budget["max_idle"],
            budget["max_lifetime"],
        )
        _pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=int(budget["min_size"]),
            max_size=int(budget["max_size"]),
            kwargs={
                "row_factory": dict_row,
                "autocommit": False,
                "application_name": budget["application_name"],
            },
            open=True,
            timeout=float(budget["timeout"]),
            max_idle=float(budget["max_idle"]),
            max_lifetime=float(budget["max_lifetime"]),
            max_waiting=int(budget["max_waiting"]),
        )
    return _pool


@contextlib.contextmanager
def connection() -> Iterator[Connection]:
    with get_pool().connection() as conn:
        yield conn


def database_write_diagnostics() -> dict[str, object]:
    """Return the connection's write-state without modifying application data."""
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SHOW default_transaction_read_only")
            default_read_only = str(cur.fetchone()["default_transaction_read_only"]).lower()
            cur.execute("SHOW transaction_read_only")
            transaction_read_only = str(cur.fetchone()["transaction_read_only"]).lower()
            cur.execute("SELECT pg_is_in_recovery() AS in_recovery")
            in_recovery = bool(cur.fetchone()["in_recovery"])
        conn.rollback()
    return {
        "default_transaction_read_only": default_read_only,
        "transaction_read_only": transaction_read_only,
        "in_recovery": in_recovery,
        "writable": default_read_only == "off" and transaction_read_only == "off" and not in_recovery,
    }


def assert_database_writable() -> None:
    state = database_write_diagnostics()
    if not state["writable"]:
        raise RuntimeError(
            "Database connection is read-only "
            f"({state}). Use the PRIMARY Supabase Session Pooler connection on port 5432 "
            "for this persistent Render service; do not use a read replica or the transaction "
            "pooler on port 6543."
        )


def execute_schema() -> None:
    root = Path(__file__).resolve().parent.parent
    schema_paths = [
        root / "sql" / "schema.sql",
        # Additive and idempotent.  Keeping the active model's columns in the
        # application bootstrap makes a fresh environment equivalent to production
        # without replaying every historical one-off migration.
        root / "sql" / "oversold_reversion_v33_outcomes.sql",
    ]
    try:
        assert_database_writable()
        with connection() as conn:
            with conn.cursor() as cur:
                for schema_path in schema_paths:
                    if schema_path.exists():
                        cur.execute(schema_path.read_text(encoding="utf-8"))
            conn.commit()
    except ReadOnlySqlTransaction as exc:
        raise RuntimeError(
            "Schema migration reached a read-only PostgreSQL transaction. Use the PRIMARY "
            "Supabase Session Pooler URL on port 5432 and set AUTO_MIGRATE=false on the worker "
            "after the schema has been installed by the web service."
        ) from exc
    logger.info("Database schema is ready")


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
