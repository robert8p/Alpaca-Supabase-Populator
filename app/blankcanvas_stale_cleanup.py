from __future__ import annotations

import logging

from app.db import connection

logger = logging.getLogger(__name__)
_PATTERNS = (
    "%blankcanvas_pair_spyctx_provisional_net5_v1%",
    "%blankcanvas_pair_provisional_net5_v1%",
    "%blankcanvas_xs_intraday_books_v1%",
    "%blankcanvas_open_close_base_v1%",
)


def cancel_stale_blankcanvas_mgmt_queries() -> int:
    """Cancel only old mgmt-api queries created by the blank-canvas research workflow."""
    cancelled = 0
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                select pid
                from pg_stat_activity
                where pid <> pg_backend_pid()
                  and datname = current_database()
                  and application_name = 'mgmt-api'
                  and state <> 'idle'
                  and query_start < now() - interval '2 minutes'
                  and (
                    query ilike %s or query ilike %s or query ilike %s or query ilike %s
                  )
                """,
                _PATTERNS,
            )
            pids = [int(r["pid"]) for r in cur.fetchall()]
            for pid in pids:
                cur.execute("select pg_cancel_backend(%s) as cancelled", (pid,))
                row = cur.fetchone()
                if row and row["cancelled"]:
                    cancelled += 1
        conn.commit()
    if cancelled:
        logger.warning("Cancelled %s stale blank-canvas mgmt-api queries", cancelled)
    return cancelled
