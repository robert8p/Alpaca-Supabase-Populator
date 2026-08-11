from __future__ import annotations

import logging
from datetime import date
from typing import Any

from app.db import connection

logger = logging.getLogger(__name__)


def _latest_loaded_date() -> date | None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT max(trade_date) AS trade_date
                FROM rd_daily_features
                WHERE timeframe='1Min'
                  AND feed='sip'
                  AND adjustment='raw'
                  AND session_label='all'
                """
            )
            row = cur.fetchone()
        conn.rollback()
    return row["trade_date"] if row else None


def freeze_latest_spy_ms001_signal() -> dict[str, Any]:
    trade_date = _latest_loaded_date()
    if trade_date is None:
        return {"frozen": False, "reason": "no_loaded_date"}

    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT * FROM blankcanvas_freeze_spy_ms001_signal(%s)",
                (trade_date,),
            )
            row = cur.fetchone()
        conn.commit()

    if not row:
        return {"frozen": False, "reason": "no_signal_row", "signal_date": trade_date.isoformat()}

    result = dict(row)
    result["signal_date"] = result["signal_date"].isoformat()
    result["frozen_at"] = result["frozen_at"].isoformat()
    result["frozen"] = True
    return result


def settle_spy_ms001_outcomes() -> int:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT blankcanvas_settle_spy_ms001_outcomes() AS inserted")
            row = cur.fetchone()
        conn.commit()
    return int(row["inserted"] if row else 0)


def maintain_spy_ms001_shadow() -> dict[str, Any]:
    signal = freeze_latest_spy_ms001_signal()
    settled = settle_spy_ms001_outcomes()
    result = {"signal": signal, "outcomes_settled": settled}
    logger.info("SPY-MS-001 shadow maintenance: %s", result)
    return result
