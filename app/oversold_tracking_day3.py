from __future__ import annotations

"""Extend decision tracking from two to three actual US trading sessions.

The v1 tracking tables were intentionally two-session.  v5 keeps those historical
rows and adds a nullable third session, backfilled from the Alpaca market calendar.
New/changed Investigate and Pass decisions are extended immediately; the frequent
checkpoint collector also repairs any older episode that still lacks Day 3.
"""

from datetime import date, timedelta
from typing import Any

from psycopg.types.json import Jsonb

from app.alpaca import AlpacaClient
from app.db import connection


def _rows_needing_day3(limit: int = 200) -> list[dict[str, Any]]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.id,t.candidate_id,t.symbol,t.session2_date,t.session2_close,
                       t.session3_date,t.session3_open,t.session3_close
                FROM or_decision_tracks t
                WHERE t.session3_date IS NULL
                   OR NOT EXISTS (
                        SELECT 1 FROM or_track_checkpoints cp
                        WHERE cp.track_id=t.id AND cp.session_no=3
                   )
                ORDER BY t.id
                LIMIT %s
                """,
                (limit,),
            )
            rows = [dict(row) for row in cur.fetchall()]
        conn.rollback()
    return rows


async def ensure_third_session_checkpoints(module: Any, *, limit: int = 200) -> int:
    rows = _rows_needing_day3(limit=limit)
    if not rows:
        return 0

    calendar_cache: dict[date, dict[str, Any]] = {}
    async with AlpacaClient(target_rpm=500, max_retries=3, backoff_seconds=0.5) as client:
        for row in rows:
            if row.get("session3_date") and row.get("session3_open") and row.get("session3_close"):
                continue
            session2_date = row.get("session2_date")
            if not isinstance(session2_date, date):
                session2_date = date.fromisoformat(str(session2_date))
            if session2_date not in calendar_cache:
                start = session2_date + timedelta(days=1)
                calendar = await client.get_calendar(
                    start=start.isoformat(),
                    end=(start + timedelta(days=14)).isoformat(),
                )
                chosen = None
                for item in calendar:
                    session_date = date.fromisoformat(str(item.get("date")))
                    if session_date <= session2_date:
                        continue
                    chosen = {
                        "date": session_date,
                        "open": module._calendar_datetime(item, "open"),
                        "close": module._calendar_datetime(item, "close"),
                    }
                    break
                if chosen is None:
                    raise RuntimeError(f"No third trading session found after {session2_date}")
                calendar_cache[session2_date] = chosen

    changed = 0
    with connection() as conn:
        with conn.cursor() as cur:
            for row in rows:
                session = None
                if row.get("session3_date") and row.get("session3_open") and row.get("session3_close"):
                    session = {
                        "date": row["session3_date"],
                        "open": row["session3_open"],
                        "close": row["session3_close"],
                    }
                else:
                    session2_date = row.get("session2_date")
                    if not isinstance(session2_date, date):
                        session2_date = date.fromisoformat(str(session2_date))
                    session = calendar_cache[session2_date]
                    cur.execute(
                        """
                        UPDATE or_decision_tracks
                        SET session3_date=%s,session3_open=%s,session3_close=%s,
                            completed_at=NULL,updated_at=now()
                        WHERE id=%s
                        """,
                        (session["date"], session["open"], session["close"], row["id"]),
                    )
                for kind, scheduled_at in module._checkpoint_times(session["open"], session["close"]).items():
                    cur.execute(
                        """
                        INSERT INTO or_track_checkpoints(track_id,session_no,checkpoint_kind,scheduled_at)
                        VALUES (%s,3,%s,%s)
                        ON CONFLICT (track_id,session_no,checkpoint_kind) DO NOTHING
                        """,
                        (row["id"], kind, scheduled_at),
                    )
                changed += 1
        conn.commit()
    return changed


def patch_module(module: Any) -> None:
    original_sync = module.sync_candidate_tracking
    original_capture = module.capture_due_checkpoints

    async def sync_candidate_tracking(candidate_id: int, decision: str):
        result = await original_sync(candidate_id, decision)
        if result is not None and str(decision).lower() in module.TRACKED_DECISIONS:
            await ensure_third_session_checkpoints(module)
            return module._active_track(candidate_id)
        return result

    async def capture_due_checkpoints():
        await ensure_third_session_checkpoints(module)
        return await original_capture()

    module.sync_candidate_tracking = sync_candidate_tracking
    module.capture_due_checkpoints = capture_due_checkpoints
    module.ensure_third_session_checkpoints = lambda limit=200: ensure_third_session_checkpoints(module, limit=limit)
