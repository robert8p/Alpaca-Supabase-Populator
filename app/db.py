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


def get_pool() -> ConnectionPool:
    global _pool
    if _pool is None:
        settings = get_settings()
        _pool = ConnectionPool(
            conninfo=settings.database_url,
            min_size=1,
            max_size=max(4, settings.max_global_concurrency + 3),
            kwargs={"row_factory": dict_row, "autocommit": False},
            open=True,
            timeout=30,
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
    schema_path = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"
    sql_text = schema_path.read_text(encoding="utf-8")
    try:
        assert_database_writable()
        with connection() as conn:
            with conn.cursor() as cur:
                cur.execute(sql_text)
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
