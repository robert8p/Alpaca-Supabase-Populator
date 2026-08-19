from __future__ import annotations

import logging
from datetime import UTC, date, datetime, timedelta
from typing import Any

from psycopg.types.json import Jsonb

from app.alpaca import AlpacaClient
from app.db import connection

logger = logging.getLogger(__name__)

POLICY_VERSION = "corporate_action_guard_v1"
REVIEW_LAG_DAYS = 30
RECHECK_INTERVAL_DAYS = 7
RECHECK_HORIZON_DAYS = 180
PROCESS_LOOKBACK_DAYS = 365
REVIEW_BATCH_SIZE = 50
SPECIAL_DIVIDEND_MATERIAL_FRACTION = 0.05

MATERIAL_ACTION_TYPES = {
    "forward_splits",
    "reverse_splits",
    "unit_splits",
    "stock_dividends",
    "spin_offs",
    "cash_mergers",
    "stock_mergers",
    "stock_and_cash_mergers",
    "redemptions",
    "name_changes",
    "worthless_removals",
    "rights_distributions",
    "partial_calls",
    "reorganizations",
}

SYMBOL_FIELDS_BY_TYPE: dict[str, tuple[str, ...]] = {
    "forward_splits": ("symbol",),
    "reverse_splits": ("symbol",),
    "unit_splits": ("old_symbol",),
    "stock_dividends": ("symbol",),
    "cash_dividends": ("symbol",),
    "spin_offs": ("source_symbol",),
    "cash_mergers": ("acquiree_symbol",),
    "stock_mergers": ("acquiree_symbol",),
    "stock_and_cash_mergers": ("acquiree_symbol",),
    "redemptions": ("symbol",),
    "name_changes": ("old_symbol",),
    "worthless_removals": ("symbol",),
    "rights_distributions": ("source_symbol",),
    "partial_calls": ("symbol", "old_symbol", "source_symbol", "acquiree_symbol"),
    "reorganizations": ("symbol", "old_symbol", "source_symbol", "acquiree_symbol"),
}

EVENT_DATE_FIELDS = (
    "ex_date",
    "effective_date",
    "payable_date",
    "record_date",
    "expiration_date",
    "due_bill_on_date",
    "due_bill_off_date",
    "due_bill_redemption_date",
    "process_date",
)

COMPACT_FIELDS = (
    "id",
    "corporate_action_id",
    "symbol",
    "old_symbol",
    "new_symbol",
    "source_symbol",
    "acquirer_symbol",
    "acquiree_symbol",
    "process_date",
    "ex_date",
    "effective_date",
    "record_date",
    "payable_date",
    "expiration_date",
    "old_rate",
    "new_rate",
    "rate",
    "special",
)


def _parse_ts(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed.astimezone(UTC) if parsed.tzinfo else parsed.replace(tzinfo=UTC)
    except ValueError:
        return None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def _number(value: Any) -> float | None:
    try:
        return None if value is None else float(value)
    except (TypeError, ValueError):
        return None


def _chunks(values: list[dict[str, Any]], size: int) -> list[list[dict[str, Any]]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def _matches_symbol(action_type: str, event: dict[str, Any], symbol: str) -> bool:
    fields = SYMBOL_FIELDS_BY_TYPE.get(
        action_type,
        ("symbol", "old_symbol", "source_symbol", "acquiree_symbol"),
    )
    target = symbol.upper()
    return any(str(event.get(field) or "").upper() == target for field in fields)


def _event_in_window(event: dict[str, Any], start: date, end: date) -> bool:
    dates = [_parse_date(event.get(field)) for field in EVENT_DATE_FIELDS]
    return any(value is not None and start <= value <= end for value in dates)


def _compact_event(action_type: str, event: dict[str, Any]) -> dict[str, Any]:
    return {
        "type": action_type,
        **{field: event.get(field) for field in COMPACT_FIELDS if event.get(field) is not None},
    }


def classify_corporate_actions(
    row: dict[str, Any],
    actions: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Classify whether a corporate action mechanically contaminates the raw-price target.

    Ordinary cash dividends remain admissible because the target is a price-reversion
    target rather than a total-return target. Special or unusually large cash dividends
    are excluded because they can create a mechanical price discontinuity comparable
    with the +5% outcome threshold.
    """
    signal_ts = _parse_ts(row.get("signal_timestamp"))
    deadline = _parse_ts(row.get("horizon_deadline"))
    if signal_ts is None or deadline is None:
        raise ValueError("Outcome row has invalid signal/deadline timestamp")
    symbol = str(row.get("symbol") or "").upper()
    signal_price = _number(row.get("signal_price")) or 0.0
    start, end = signal_ts.date(), deadline.date()
    material: list[dict[str, Any]] = []
    benign: list[dict[str, Any]] = []

    for action_type, events in actions.items():
        if not isinstance(events, list):
            continue
        for event in events:
            if not isinstance(event, dict) or not _matches_symbol(action_type, event, symbol):
                continue
            if not _event_in_window(event, start, end):
                continue
            compact = _compact_event(action_type, event)
            if action_type == "cash_dividends":
                rate = _number(event.get("rate")) or 0.0
                large = signal_price > 0 and rate / signal_price >= SPECIAL_DIVIDEND_MATERIAL_FRACTION
                if bool(event.get("special")) or large:
                    material.append(compact)
                else:
                    benign.append(compact)
            elif action_type in MATERIAL_ACTION_TYPES:
                material.append(compact)
            else:
                # Unknown future action categories are excluded rather than silently
                # treated as harmless until the policy is explicitly updated.
                material.append(compact)

    return {
        "corporate_action_status": "affected" if material else "clear",
        "eligible_for_calibration": not material,
        "material_events": material,
        "benign_events": benign,
    }


def _load_review_due(limit: int = 500) -> list[dict[str, Any]]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id,candidate_id,symbol,signal_timestamp,signal_price,horizon_deadline,status,
                       corporate_action_status,eligible_for_calibration,metadata
                FROM or_signal_outcomes
                WHERE status='matured'
                  AND horizon_deadline + (%s * interval '1 day') <= now()
                  AND (
                    corporate_action_status IN ('unchecked','review_error')
                    OR (
                        corporate_action_status='clear'
                        AND horizon_deadline >= now() - (%s * interval '1 day')
                        AND COALESCE(NULLIF(metadata->>'corporate_action_checked_at','')::timestamptz,'epoch'::timestamptz)
                            <= now() - (%s * interval '1 day')
                    )
                  )
                ORDER BY horizon_deadline,id
                LIMIT %s
                """,
                (REVIEW_LAG_DAYS, RECHECK_HORIZON_DAYS, RECHECK_INTERVAL_DAYS, limit),
            )
            rows = [dict(row) for row in cur.fetchall()]
        conn.rollback()
    return rows


async def _fetch_actions_for_group(
    client: AlpacaClient,
    rows: list[dict[str, Any]],
    now: datetime,
) -> dict[str, list[dict[str, Any]]]:
    symbols = sorted({str(row["symbol"]).upper() for row in rows})
    signal_dates = [_parse_ts(row["signal_timestamp"]) for row in rows]
    valid_dates = [value for value in signal_dates if value is not None]
    if not symbols or not valid_dates:
        return {}
    start = min(valid_dates).date() - timedelta(days=PROCESS_LOOKBACK_DAYS)
    end = now.date()
    output: dict[str, list[dict[str, Any]]] = {}
    token: str | None = None
    while True:
        result = await client.fetch_corporate_actions_page(
            symbols=symbols,
            start=start.isoformat(),
            end=end.isoformat(),
            limit=1000,
            page_token=token,
            data_quality="complete",
        )
        payload = result.data if isinstance(result.data, dict) else {}
        for key, values in payload.items():
            if key == "next_page_token" or not isinstance(values, list):
                continue
            output.setdefault(str(key), []).extend(value for value in values if isinstance(value, dict))
        token = payload.get("next_page_token")
        if not token:
            break
    return output


async def review_corporate_actions(limit: int = 500) -> dict[str, int]:
    rows = _load_review_due(limit=limit)
    if not rows:
        return {"due": 0, "reviewed": 0, "clear": 0, "affected": 0, "errors": 0, "rechecked": 0}

    now = datetime.now(UTC)
    reviewed = clear = affected = errors = rechecked = 0
    async with AlpacaClient(target_rpm=300, max_retries=3, backoff_seconds=0.5) as client:
        for group in _chunks(rows, REVIEW_BATCH_SIZE):
            try:
                actions = await _fetch_actions_for_group(client, group, now)
            except Exception as exc:
                logger.exception("Corporate-action review request failed")
                with connection() as conn:
                    with conn.cursor() as cur:
                        for row in group:
                            cur.execute(
                                """
                                UPDATE or_signal_outcomes SET
                                    corporate_action_status='review_error',eligible_for_calibration=false,
                                    metadata=metadata || %s,updated_at=now()
                                WHERE id=%s
                                """,
                                (
                                    Jsonb({
                                        "corporate_action_policy": POLICY_VERSION,
                                        "corporate_action_checked_at": now.isoformat(),
                                        "corporate_action_review_error": str(exc)[:1000],
                                    }),
                                    row["id"],
                                ),
                            )
                    conn.commit()
                errors += len(group)
                continue

            with connection() as conn:
                with conn.cursor() as cur:
                    for row in group:
                        try:
                            result = classify_corporate_actions(row, actions)
                            was_clear = row.get("corporate_action_status") == "clear"
                            metadata = {
                                "corporate_action_policy": POLICY_VERSION,
                                "corporate_action_checked_at": now.isoformat(),
                                "corporate_action_review_lag_days": REVIEW_LAG_DAYS,
                                "corporate_action_recheck_horizon_days": RECHECK_HORIZON_DAYS,
                                "corporate_action_data_quality": "complete",
                                "corporate_action_material_events": result["material_events"][:20],
                                "corporate_action_benign_events": result["benign_events"][:20],
                                "corporate_action_review_error": None,
                            }
                            cur.execute(
                                """
                                UPDATE or_signal_outcomes SET
                                    corporate_action_status=%s,eligible_for_calibration=%s,
                                    metadata=metadata || %s,updated_at=now()
                                WHERE id=%s
                                """,
                                (
                                    result["corporate_action_status"],
                                    bool(result["eligible_for_calibration"]),
                                    Jsonb(metadata),
                                    row["id"],
                                ),
                            )
                            reviewed += 1
                            rechecked += 1 if was_clear else 0
                            clear += 1 if result["corporate_action_status"] == "clear" else 0
                            affected += 1 if result["corporate_action_status"] == "affected" else 0
                        except Exception as exc:
                            logger.exception("Corporate-action classification failed for %s", row.get("symbol"))
                            cur.execute(
                                """
                                UPDATE or_signal_outcomes SET
                                    corporate_action_status='review_error',eligible_for_calibration=false,
                                    metadata=metadata || %s,updated_at=now()
                                WHERE id=%s
                                """,
                                (
                                    Jsonb({
                                        "corporate_action_policy": POLICY_VERSION,
                                        "corporate_action_checked_at": now.isoformat(),
                                        "corporate_action_review_error": str(exc)[:1000],
                                    }),
                                    row["id"],
                                ),
                            )
                            errors += 1
                conn.commit()

    return {
        "due": len(rows),
        "reviewed": reviewed,
        "clear": clear,
        "affected": affected,
        "errors": errors,
        "rechecked": rechecked,
    }
