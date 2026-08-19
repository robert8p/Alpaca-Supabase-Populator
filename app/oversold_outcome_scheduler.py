from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.oversold_outcomes import capture_signal_outcomes
from app.oversold_tracking import capture_due_checkpoints

logger = logging.getLogger(__name__)
NY = ZoneInfo("America/New_York")
CAPTURE_AFTER_ET = time(18, 30)
DEFAULT_POLL_SECONDS = 900.0


def outcome_capture_due(now_et: datetime, last_run_date: date | None) -> bool:
    """Run once per US weekday after the scanner and regular session have completed."""
    local = now_et.astimezone(NY) if now_et.tzinfo else now_et.replace(tzinfo=NY)
    return (
        local.weekday() < 5
        and local.timetz().replace(tzinfo=None) >= CAPTURE_AFTER_ET
        and last_run_date != local.date()
    )


async def run_oversold_outcome_scheduler(stop_event: asyncio.Event) -> None:
    enabled = os.getenv("OVERSOLD_OUTCOME_CAPTURE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        logger.info("Oversold Reversion outcome scheduler disabled")
        return

    poll_seconds = max(300.0, float(os.getenv("OVERSOLD_OUTCOME_CAPTURE_POLL_SECONDS", str(DEFAULT_POLL_SECONDS))))
    last_run_date: date | None = None
    logger.info("Oversold Reversion outcome scheduler enabled; daily cutoff=%s ET", CAPTURE_AFTER_ET.isoformat(timespec="minutes"))

    while not stop_event.is_set():
        try:
            now_et = datetime.now(tz=NY)
            if outcome_capture_due(now_et, last_run_date):
                decision_result = await capture_due_checkpoints()
                signal_result = await capture_signal_outcomes()
                last_run_date = now_et.date()
                logger.info(
                    "Oversold Reversion outcomes refreshed for %s: decision=%s signal=%s",
                    last_run_date,
                    decision_result,
                    signal_result,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Oversold Reversion outcome scheduler error")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
        except TimeoutError:
            pass
