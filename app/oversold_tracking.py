from __future__ import annotations

import logging
from collections import defaultdict
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from psycopg.types.json import Jsonb

from app.alpaca import AlpacaClient
from app.db import connection

logger = logging.getLogger(__name__)
NY = ZoneInfo("America/New_York")
TRACKED_DECISIONS = {"investigate", "pass"}
CHECKPOINT_KINDS = ("open_plus_1h", "mid_session", "close")


def _iso_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        dt = value
    elif value:
        text = str(value).strip().replace("Z", "+00:00")
        try:
            dt = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC)


def _calendar_datetime(row: dict[str, Any], field: str) -> datetime:
    raw = row.get(field)
    if not raw:
        raise ValueError(f"Calendar row missing {field}: {row}")

    text = str(raw).strip().replace("Z", "+00:00")
    if "T" in text or "+" in text[1:]:
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=NY)
        return parsed.astimezone(UTC)

    session_date = date.fromisoformat(str(row.get("date")))
    parts = text.split(":")
    if len(parts) < 2:
        raise ValueError(f"Unexpected calendar {field}: {raw}")
    local_time = time(int(parts[0]), int(parts[1]), int(parts[2]) if len(parts) > 2 else 0)
    return datetime.combine(session_date, local_time, tzinfo=NY).astimezone(UTC)


def _checkpoint_times(open_at: datetime, close_at: datetime) -> dict[str, datetime]:
    if close_at <= open_at:
        raise ValueError("Market close must be after market open")
    midpoint = open_at + ((close_at - open_at) / 2)
    return {
        "open_plus_1h": open_at + timedelta(hours=1),
        "mid_session": midpoint,
        "close": close_at,
    }


def _trade_from_payload(payload: Any, symbol: str) -> tuple[float | None, datetime | None]:
    if not isinstance(payload, dict):
        return None, None
    trades = payload.get("trades")
    if not isinstance(trades, dict):
        trades = payload
    trade = trades.get(symbol) if isinstance(trades, dict) else None
    if not isinstance(trade, dict):
        return None, None
    try:
        price = float(trade.get("p"))
    except (TypeError, ValueError):
        price = None
    return price, _iso_datetime(trade.get("t"))


def _bars_by_symbol(payload: Any) -> dict[str, list[dict[str, Any]]]:
    if not isinstance(payload, dict):
        return {}
    bars = payload.get("bars")
    if not isinstance(bars, dict):
        return {}
    return {
        str(symbol).upper(): [bar for bar in values if isinstance(bar, dict)]
        for symbol, values in bars.items()
        if isinstance(values, list)
    }


def _last_completed_bar(bars: list[dict[str, Any]], scheduled_at: datetime) -> dict[str, Any] | None:
    candidates: list[tuple[datetime, dict[str, Any]]] = []
    for bar in bars:
        ts = _iso_datetime(bar.get("t"))
        if ts is not None and ts < scheduled_at:
            candidates.append((ts, bar))
    return max(candidates, key=lambda item: item[0])[1] if candidates else None


async def _next_two_sessions(client: AlpacaClient, selected_at: datetime) -> list[dict[str, Any]]:
    local_date = selected_at.astimezone(NY).date()
    calendar = await client.get_calendar(
        start=local_date.isoformat(),
        end=(local_date + timedelta(days=21)).isoformat(),
    )
    sessions: list[dict[str, Any]] = []
    for row in calendar:
        open_at = _calendar_datetime(row, "open")
        close_at = _calendar_datetime(row, "close")
        if open_at <= selected_at:
            continue
        sessions.append(
            {
                "date": date.fromisoformat(str(row["date"])),
                "open": open_at,
                "close": close_at,
            }
        )
        if len(sessions) == 2:
            return sessions
    raise RuntimeError("Alpaca calendar did not return two future trading sessions")


def _load_candidate(candidate_id: int) -> dict[str, Any] | None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id,symbol,name,last_price,decision,review_notes,reviewed_at FROM or_candidates WHERE id=%s",
                (candidate_id,),
            )
            row = cur.fetchone()
        conn.rollback()
    return row


def _existing_track(candidate_id: int) -> dict[str, Any] | None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM or_decision_tracks WHERE candidate_id=%s", (candidate_id,))
            row = cur.fetchone()
        conn.rollback()
    return row


async def sync_candidate_tracking(candidate_id: int, decision: str) -> dict[str, Any] | None:
    decision = decision.lower()
    candidate = _load_candidate(candidate_id)
    if not candidate:
        raise ValueError(f"Candidate {candidate_id} not found")

    existing = _existing_track(candidate_id)
    if decision not in TRACKED_DECISIONS:
        if existing and existing.get("active"):
            with connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        "UPDATE or_decision_tracks SET active=false,updated_at=now() WHERE candidate_id=%s",
                        (candidate_id,),
                    )
                conn.commit()
        return None

    if existing and existing.get("active") and existing.get("decision") == decision:
        return existing

    selected_at = datetime.now(UTC)
    fallback_price = float(candidate["last_price"]) if candidate.get("last_price") else None

    async with AlpacaClient(target_rpm=1000, max_retries=3, backoff_seconds=0.5) as client:
        latest = await client.fetch_latest_trades(symbols=[candidate["symbol"]], feed="sip")
        trade_price, trade_ts = _trade_from_payload(latest.data, candidate["symbol"])
        selected_price = trade_price or fallback_price
        if selected_price is None or selected_price <= 0:
            raise RuntimeError(f"No usable decision-time price for {candidate['symbol']}")
        sessions = await _next_two_sessions(client, selected_at)

    s1, s2 = sessions
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO or_decision_tracks(
                    candidate_id,symbol,name,decision,selected_at,selected_price,selected_trade_ts,
                    session1_date,session1_open,session1_close,session2_date,session2_open,session2_close,
                    active,completed_at,updated_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,true,NULL,now())
                ON CONFLICT (candidate_id) DO UPDATE SET
                    symbol=EXCLUDED.symbol,name=EXCLUDED.name,decision=EXCLUDED.decision,
                    selected_at=EXCLUDED.selected_at,selected_price=EXCLUDED.selected_price,
                    selected_trade_ts=EXCLUDED.selected_trade_ts,
                    session1_date=EXCLUDED.session1_date,session1_open=EXCLUDED.session1_open,
                    session1_close=EXCLUDED.session1_close,session2_date=EXCLUDED.session2_date,
                    session2_open=EXCLUDED.session2_open,session2_close=EXCLUDED.session2_close,
                    active=true,completed_at=NULL,updated_at=now()
                RETURNING id
                """,
                (
                    candidate_id,
                    candidate["symbol"],
                    candidate.get("name"),
                    decision,
                    selected_at,
                    selected_price,
                    trade_ts,
                    s1["date"],
                    s1["open"],
                    s1["close"],
                    s2["date"],
                    s2["open"],
                    s2["close"],
                ),
            )
            track_id = cur.fetchone()["id"]
            cur.execute("DELETE FROM or_track_checkpoints WHERE track_id=%s", (track_id,))
            for session_no, session in ((1, s1), (2, s2)):
                for kind, scheduled_at in _checkpoint_times(session["open"], session["close"]).items():
                    cur.execute(
                        """
                        INSERT INTO or_track_checkpoints(track_id,session_no,checkpoint_kind,scheduled_at)
                        VALUES (%s,%s,%s,%s)
                        """,
                        (track_id, session_no, kind, scheduled_at),
                    )
        conn.commit()

    return _existing_track(candidate_id)


async def ensure_existing_tracks(limit: int = 100) -> int:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT c.id,c.decision
                FROM or_candidates c
                LEFT JOIN or_decision_tracks t ON t.candidate_id=c.id
                WHERE c.decision IN ('investigate','pass')
                  AND (t.id IS NULL OR t.active=false)
                ORDER BY c.reviewed_at DESC NULLS LAST,c.id DESC
                LIMIT %s
                """,
                (limit,),
            )
            rows = cur.fetchall()
        conn.rollback()

    created = 0
    for row in rows:
        try:
            await sync_candidate_tracking(row["id"], row["decision"])
            created += 1
        except Exception:
            logger.exception("Failed to initialise track for candidate %s", row["id"])
    return created


def list_tracked() -> dict[str, Any]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT t.*,c.review_notes,c.catalyst_class,c.catalyst_summary,c.heuristic_score,c.triage_label
                FROM or_decision_tracks t
                JOIN or_candidates c ON c.id=t.candidate_id
                WHERE t.active=true
                ORDER BY t.selected_at DESC,t.id DESC
                """
            )
            tracks = cur.fetchall()
            track_ids = [row["id"] for row in tracks]
            checkpoints: list[dict[str, Any]] = []
            if track_ids:
                cur.execute(
                    """
                    SELECT * FROM or_track_checkpoints
                    WHERE track_id=ANY(%s)
                    ORDER BY track_id,session_no,
                      CASE checkpoint_kind WHEN 'open_plus_1h' THEN 1 WHEN 'mid_session' THEN 2 ELSE 3 END
                    """,
                    (track_ids,),
                )
                checkpoints = cur.fetchall()
        conn.rollback()

    by_track: dict[int, list[dict[str, Any]]] = defaultdict(list)
    for row in checkpoints:
        by_track[row["track_id"]].append(row)
    for track in tracks:
        track["checkpoints"] = by_track.get(track["id"], [])

    return {
        "investigate": [row for row in tracks if row["decision"] == "investigate"],
        "pass": [row for row in tracks if row["decision"] == "pass"],
    }


async def capture_due_checkpoints() -> dict[str, int]:
    now = datetime.now(UTC)
    due_cutoff = now - timedelta(seconds=60)
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT cp.id,cp.track_id,cp.scheduled_at,t.symbol,t.selected_price
                FROM or_track_checkpoints cp
                JOIN or_decision_tracks t ON t.id=cp.track_id
                WHERE cp.status='pending' AND cp.scheduled_at <= %s AND t.active=true
                ORDER BY cp.scheduled_at,cp.id
                LIMIT 500
                """,
                (due_cutoff,),
            )
            due = cur.fetchall()
        conn.rollback()

    if not due:
        return {"due": 0, "captured": 0, "missed": 0, "pending": 0}

    groups: dict[datetime, list[dict[str, Any]]] = defaultdict(list)
    for row in due:
        groups[row["scheduled_at"]].append(row)

    captured = 0
    missed = 0
    pending = 0
    async with AlpacaClient(target_rpm=1000, max_retries=3, backoff_seconds=0.5) as client:
        for scheduled_at, rows in groups.items():
            symbols = sorted({row["symbol"] for row in rows})
            try:
                result = await client.fetch_bars_page(
                    symbols=symbols,
                    timeframe="1Min",
                    start=(scheduled_at - timedelta(minutes=30)).isoformat(),
                    end=scheduled_at.isoformat(),
                    feed="sip",
                    adjustment="raw",
                    asof=None,
                    limit=10000,
                    page_token=None,
                )
                bars = _bars_by_symbol(result.data)
            except Exception as exc:
                logger.exception("Outcome bar request failed for %s", scheduled_at)
                with connection() as conn:
                    with conn.cursor() as cur:
                        for row in rows:
                            cur.execute(
                                "UPDATE or_track_checkpoints SET error=%s,updated_at=now() WHERE id=%s",
                                (str(exc)[:1000], row["id"]),
                            )
                    conn.commit()
                pending += len(rows)
                continue

            with connection() as conn:
                with conn.cursor() as cur:
                    for row in rows:
                        bar = _last_completed_bar(bars.get(row["symbol"], []), scheduled_at)
                        if bar is None:
                            if now >= scheduled_at + timedelta(hours=2):
                                cur.execute(
                                    """
                                    UPDATE or_track_checkpoints
                                    SET status='missed',captured_at=now(),error=%s,updated_at=now()
                                    WHERE id=%s
                                    """,
                                    ("No regular-session minute bar found within 30 minutes of checkpoint", row["id"]),
                                )
                                missed += 1
                            else:
                                cur.execute(
                                    "UPDATE or_track_checkpoints SET error=%s,updated_at=now() WHERE id=%s",
                                    ("No minute bar available yet; will retry", row["id"]),
                                )
                                pending += 1
                            continue

                        try:
                            price = float(bar["c"])
                        except (KeyError, TypeError, ValueError):
                            cur.execute(
                                "UPDATE or_track_checkpoints SET error=%s,updated_at=now() WHERE id=%s",
                                ("Selected bar had no usable close price", row["id"]),
                            )
                            pending += 1
                            continue

                        baseline = float(row["selected_price"])
                        return_pct = ((price / baseline) - 1.0) * 100.0
                        cur.execute(
                            """
                            UPDATE or_track_checkpoints
                            SET status='captured',captured_at=now(),bar_ts=%s,price=%s,return_pct=%s,
                                error=NULL,raw_bar=%s,updated_at=now()
                            WHERE id=%s
                            """,
                            (_iso_datetime(bar.get("t")), price, return_pct, Jsonb(bar), row["id"]),
                        )
                        captured += 1
                conn.commit()

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE or_decision_tracks t
                SET completed_at=COALESCE(t.completed_at,now()),updated_at=now()
                WHERE t.active=true
                  AND NOT EXISTS (
                    SELECT 1 FROM or_track_checkpoints cp
                    WHERE cp.track_id=t.id AND cp.status='pending'
                  )
                  AND EXISTS (
                    SELECT 1 FROM or_track_checkpoints cp WHERE cp.track_id=t.id
                  )
                """
            )
        conn.commit()

    return {"due": len(due), "captured": captured, "missed": missed, "pending": pending}
