from __future__ import annotations

"""Three-session path metrics for Oversold Reversion outcomes."""

import math
from datetime import UTC, datetime
from typing import Any


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
) -> dict[str, Any]:
    signal_ts = parse_ts(row.get("signal_timestamp"))
    if signal_ts is None:
        raise ValueError("invalid signal timestamp")
    signal_price = float(row["signal_price"])
    eligible: list[tuple[datetime, dict[str, Any]]] = []
    for bar in bars:
        ts = parse_ts(bar.get("t"))
        if ts is None or ts <= signal_ts:
            continue
        eligible.append((ts, bar))
    eligible.sort(key=lambda item: item[0])
    sessions = eligible[:3]
    if not sessions:
        return {
            "bar_count": 0,
            "matured": False,
            "mfe_3d": None,
            "mae_3d": None,
            "mfe_3d_ts": None,
            "mae_3d_ts": None,
            "time_to_mfe_3d_sessions": None,
            "time_to_mae_3d_sessions": None,
        }

    highs: list[tuple[float, datetime, int]] = []
    lows: list[tuple[float, datetime, int]] = []
    for index, (ts, bar) in enumerate(sessions, 1):
        high = _finite(bar.get("h"))
        low = _finite(bar.get("l"))
        if high is not None:
            highs.append((((high / signal_price) - 1.0) * 100.0, ts, index))
        if low is not None:
            lows.append((((low / signal_price) - 1.0) * 100.0, ts, index))
    best = max(highs, key=lambda item: item[0]) if highs else None
    worst = min(lows, key=lambda item: item[0]) if lows else None
    return {
        "bar_count": len(sessions),
        "matured": len(sessions) >= 3,
        "mfe_3d": best[0] if best else None,
        "mae_3d": worst[0] if worst else None,
        "mfe_3d_ts": best[1] if best else None,
        "mae_3d_ts": worst[1] if worst else None,
        "time_to_mfe_3d_sessions": best[2] if best else None,
        "time_to_mae_3d_sessions": worst[2] if worst else None,
    }


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
                            parse_ts=module._parse_ts,
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
