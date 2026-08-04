from __future__ import annotations

import contextlib
import logging
from pathlib import Path
from typing import Iterator

from psycopg import Connection
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


def execute_schema() -> None:
    schema_path = Path(__file__).resolve().parent.parent / "sql" / "schema.sql"
    sql_text = schema_path.read_text(encoding="utf-8")
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(sql_text)
        conn.commit()
    logger.info("Database schema is ready")


def close_pool() -> None:
    global _pool
    if _pool is not None:
        _pool.close()
        _pool = None
