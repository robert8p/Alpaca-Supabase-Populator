from __future__ import annotations

"""Completed three-session paths and explicit, non-fill return proxies."""

import math
from datetime import UTC, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.oversold_tracking import _calendar_datetime

PATH_CONTRACT_VERSION = "completed_sessions_v2"
NEW_YORK = ZoneInfo("America/New_York")
# Assumptions for research sensitivity, never claimed as observed execution costs.
PROXY_ROUND_TRIP_COST_BPS = 30.0
PROXY_STRESS_COST_BPS = 60.0


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (TypeError, ValueError):
        return None


def calculate_three_session_path(
    row: dict[str, Any],
    bars: list[dict[str, Any]],
    *,
    parse_ts: Any,
    now: datetime | None = None,
    calendar: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Use distinct completed sessions; a missing session cannot extend the target.

    Legacy MFE/MAE describe excursions from the original signal reference price.
    Profit proxies separately enter at the next session's daily open and exit at
    the third session's close. Daily OHLC cannot establish executable fills.
    """
    signal_ts = parse_ts(row.get("signal_timestamp"))
    signal_price = _finite(row.get("signal_price"))
    if signal_ts is None or signal_price is None or signal_price <= 0:
        raise ValueError("invalid signal timestamp/price")
    now = now or datetime.now(UTC)
    signal_date = signal_ts.astimezone(NEW_YORK).date()
    expected = []
    for item in calendar or []:
        opened, closed = _calendar_datetime(item, "open"), _calendar_datetime(item, "close")
        if opened.astimezone(NEW_YORK).date() > signal_date:
            expected.append((opened, closed))
    expected = sorted(set(expected))[:3]
    expected_dates = {opened.astimezone(NEW_YORK).date() for opened, _ in expected}
    close_by_date = {opened.astimezone(NEW_YORK).date(): closed for opened, closed in expected}
    by_date: dict[Any, tuple[datetime, dict[str, Any]]] = {}
    conflicts = set()
    for bar in bars:
        ts = parse_ts(bar.get("t"))
        if ts is None:
            continue
        day = ts.astimezone(NEW_YORK).date()
        if day <= signal_date or ts > now:
            continue
        if calendar is not None and day not in expected_dates:
            continue
        # Without a calendar, conservatively wait until the regular close.
        closed = close_by_date.get(day, datetime.combine(day, time(16), tzinfo=NEW_YORK))
        if closed + timedelta(minutes=1) > now:
            continue
        h, l, c = (_finite(bar.get(field)) for field in ("h", "l", "c"))
        if any(value is None or value <= 0 for value in (h, l, c)) or not l <= c <= h:
            conflicts.add(day)
            continue
        previous = by_date.get(day)
        if previous and any(previous[1].get(key) != bar.get(key) for key in ("o", "h", "l", "c")):
            conflicts.add(day)
        by_date[day] = (ts, bar)
    sessions = sorted((item for day, item in by_date.items() if day not in conflicts), key=lambda item: item[0])[:3]
    calendar_verified = bool(calendar is not None and len(expected) == 3 and len(sessions) == 3)
    matured = len(sessions) == 3 and (calendar is None or calendar_verified)
    highs = [(((float(bar["h"]) / signal_price) - 1) * 100, ts, idx) for idx, (ts, bar) in enumerate(sessions, 1)]
    lows = [(((float(bar["l"]) / signal_price) - 1) * 100, ts, idx) for idx, (ts, bar) in enumerate(sessions, 1)]
    best = max(highs, key=lambda item: item[0]) if highs else None
    worst = min(lows, key=lambda item: item[0]) if lows else None
    result = {
        "bar_count": len(sessions), "matured": matured,
        "calendar_verified": calendar_verified,
        "path_contract_version": PATH_CONTRACT_VERSION,
        "window_end_ts": expected[-1][1] if len(expected) == 3 else None,
        "mfe_3d": best[0] if best else None, "mae_3d": worst[0] if worst else None,
        "mfe_3d_ts": best[1] if best else None, "mae_3d_ts": worst[1] if worst else None,
        "time_to_mfe_3d_sessions": best[2] if best else None,
        "time_to_mae_3d_sessions": worst[2] if worst else None,
        "profit_proxy": {
            "status": "unavailable", "entry_rule": "next_session_daily_open",
            "exit_rule": "third_session_daily_close", "actual_fills_verified": False,
            "round_trip_cost_bps_assumption": PROXY_ROUND_TRIP_COST_BPS,
            "stress_round_trip_cost_bps_assumption": PROXY_STRESS_COST_BPS,
            "limitation": "Daily-bar scenario; no quote, liquidity, execution or portfolio validation. Target touch is not profit.",
        },
    }
    entry = _finite(sessions[0][1].get("o")) if sessions else None
    if matured and calendar_verified and entry is not None and entry > 0:
        first = sessions[0][1]
        if float(first["l"]) <= entry <= float(first["h"]):
            gross = (float(sessions[-1][1]["c"]) / entry - 1) * 100
            result["profit_proxy"].update({
                "status": "modeled", "entry_price": entry,
                "exit_price": float(sessions[-1][1]["c"]), "gross_return_pct": gross,
                "net_return_pct": gross - PROXY_ROUND_TRIP_COST_BPS / 100,
                "stress_net_return_pct": gross - PROXY_STRESS_COST_BPS / 100,
                "mae_pct": (min(float(bar["l"]) for _, bar in sessions) / entry - 1) * 100,
                "entry_ts": expected[0][0].isoformat(), "exit_ts": expected[-1][1].isoformat(),
            })
    return result


def install_patch(module: Any) -> None:
    if getattr(module, "_v33_outcome_path_installed", False):
        return
    original_capture = module.capture_signal_outcomes

    def _load_rows(limit: int) -> list[dict[str, Any]]:
        with module.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    """
                    SELECT id,candidate_id,symbol,signal_timestamp,signal_price,horizon_deadline,
                           status,mfe_3d,mae_3d
                    FROM or_signal_outcomes
                    WHERE signal_timestamp >= now() - interval '400 days'
                      AND (
                        mfe_3d IS NULL OR mae_3d IS NULL
                        OR COALESCE(NULLIF(metadata->>'three_session_path_bar_count','')::int,0) < 3
                        OR metadata->>'three_session_path_contract' IS DISTINCT FROM 'completed_sessions_v2'
                      )
                    ORDER BY signal_timestamp,id
                    LIMIT %s
                    """,
                    (limit,),
                )
                rows = [dict(row) for row in cur.fetchall()]
            conn.rollback()
        return rows

    async def enrich_three_session_paths(limit: int = 500) -> dict[str, int]:
        rows = _load_rows(limit)
        if not rows:
            return {"due": 0, "updated": 0, "matured": 0, "errors": 0}
        now = datetime.now(UTC)
        updated = matured = errors = 0
        try:
            async with module.AlpacaClient(target_rpm=1000, max_retries=3, backoff_seconds=0.5) as client:
                bars_by_symbol = await module._fetch_daily_bars(client, rows, now)
                earliest = min(module._parse_ts(row["signal_timestamp"]) for row in rows)
                latest = max(module._parse_ts(row["signal_timestamp"]) for row in rows)
                calendar = await client.get_calendar(
                    start=earliest.astimezone(NEW_YORK).date().isoformat(),
                    end=(latest + timedelta(days=14)).astimezone(NEW_YORK).date().isoformat(),
                )
        except Exception:
            module.logger.exception("Three-session path bars request failed")
            return {"due": len(rows), "updated": 0, "matured": 0, "errors": len(rows)}

        with module.connection() as conn:
            with conn.cursor() as cur:
                for row in rows:
                    try:
                        metrics = calculate_three_session_path(
                            row,
                            bars_by_symbol.get(str(row["symbol"]).upper(), []),
                            parse_ts=module._parse_ts, now=now, calendar=calendar,
                        )
                        cur.execute(
                            """
                            UPDATE or_signal_outcomes
                            SET mfe_3d=%s,mae_3d=%s,mfe_3d_ts=%s,mae_3d_ts=%s,
                                time_to_mfe_3d_sessions=%s,time_to_mae_3d_sessions=%s,
                                metadata=metadata || %s,updated_at=now()
                            WHERE id=%s
                            """,
                            (
                                metrics["mfe_3d"],
                                metrics["mae_3d"],
                                metrics["mfe_3d_ts"],
                                metrics["mae_3d_ts"],
                                metrics["time_to_mfe_3d_sessions"],
                                metrics["time_to_mae_3d_sessions"],
                                module.Jsonb(
                                    {
                                        "three_session_path_bar_count": metrics["bar_count"],
                                        "three_session_path_matured": metrics["matured"],
                                        "three_session_path_resolution": "1Day",
                                        "three_session_path_contract": PATH_CONTRACT_VERSION,
                                        "three_session_calendar_verified": metrics["calendar_verified"],
                                        "calibration_window_end_ts": metrics["window_end_ts"].isoformat() if metrics["window_end_ts"] else None,
                                        "profit_proxy_3d": metrics["profit_proxy"],
                                        "thesis_invalidation_status": "not_assessed",
                                    }
                                ),
                                row["id"],
                            ),
                        )
                        updated += 1
                        matured += 1 if metrics["matured"] else 0
                    except Exception:
                        module.logger.exception(
                            "Three-session path calculation failed for %s",
                            row.get("symbol"),
                        )
                        errors += 1
            conn.commit()
        return {"due": len(rows), "updated": updated, "matured": matured, "errors": errors}

    async def capture_signal_outcomes(limit: int = 500) -> dict[str, int]:
        result = await original_capture(limit=limit)
        path = await enrich_three_session_paths(limit=limit)
        result["three_session_path_due"] = path["due"]
        result["three_session_path_updated"] = path["updated"]
        result["three_session_path_matured"] = path["matured"]
        result["three_session_path_errors"] = path["errors"]
        return result

    module.calculate_three_session_path = calculate_three_session_path
    module.enrich_three_session_paths = enrich_three_session_paths
    module.capture_signal_outcomes = capture_signal_outcomes
    module._v33_outcome_path_installed = True
