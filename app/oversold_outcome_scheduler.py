from __future__ import annotations

import asyncio
import logging
import os
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.oversold_calibration_runtime import run_calibration_if_changed
from app.oversold_corporate_actions import review_corporate_actions
from app.oversold_evaluation import original_vs_rescore_report, rescore_historical_snapshots
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


async def _refresh_point_in_time_rescores() -> tuple[dict[str, int], dict[str, object]]:
    """Append missing v3.2 rescores without mutating any original signal state."""
    rescore = await asyncio.to_thread(rescore_historical_snapshots, limit=500)
    comparison = await asyncio.to_thread(original_vs_rescore_report)
    return rescore, comparison


async def _run_oversold_outcomes(stop_event: asyncio.Event) -> None:
    enabled = os.getenv("OVERSOLD_OUTCOME_CAPTURE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}
    if not enabled:
        logger.info("Oversold Reversion outcome scheduler disabled")
        await stop_event.wait()
        return

    poll_seconds = max(300.0, float(os.getenv("OVERSOLD_OUTCOME_CAPTURE_POLL_SECONDS", str(DEFAULT_POLL_SECONDS))))
    last_run_date: date | None = None
    logger.info("Oversold Reversion outcome scheduler enabled; daily cutoff=%s ET", CAPTURE_AFTER_ET.isoformat(timespec="minutes"))

    # On worker start/deploy, create any missing point-in-time rescores immediately.
    # This is database-only and uses immutable Evidence Snapshots, so it is safe to
    # run before the six-week outcome cycle is due.
    try:
        bootstrap_rescore, bootstrap_comparison = await _refresh_point_in_time_rescores()
        logger.info(
            "Oversold Reversion v3.2 historical rescore bootstrap: rescore=%s paired=%s matured_pairs=%s",
            bootstrap_rescore,
            bootstrap_comparison.get("paired_signals"),
            bootstrap_comparison.get("matured_paired_signals"),
        )
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Oversold Reversion v3.2 historical rescore bootstrap failed")

    while not stop_event.is_set():
        try:
            now_et = datetime.now(tz=NY)
            if outcome_capture_due(now_et, last_run_date):
                decision_result = await capture_due_checkpoints()
                signal_result = await capture_signal_outcomes()
                corporate_action_result = await review_corporate_actions()
                rescore_result, comparison_result = await _refresh_point_in_time_rescores()
                calibration_result = await asyncio.to_thread(run_calibration_if_changed)
                last_run_date = now_et.date()
                logger.info(
                    "Oversold Reversion outcomes refreshed for %s: decision=%s signal=%s corporate_actions=%s rescore=%s paired=%s matured_pairs=%s calibration=%s",
                    last_run_date,
                    decision_result,
                    signal_result,
                    corporate_action_result,
                    rescore_result,
                    comparison_result.get("paired_signals"),
                    comparison_result.get("matured_paired_signals"),
                    calibration_result,
                )
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Oversold Reversion outcome scheduler error")

        try:
            await asyncio.wait_for(stop_event.wait(), timeout=poll_seconds)
        except TimeoutError:
            pass


async def run_oversold_outcome_scheduler(stop_event: asyncio.Event) -> None:
    """Run the existing outcome scheduler and the web-independent SIP request queue."""
    # Import lazily so pure outcome-scheduling helpers remain importable in tests and
    # maintenance tooling that deliberately do not provide live database/Alpaca secrets.
    from app.intraday_profitability_worker import run_intraday_profitability_request_scheduler

    oversold_task = asyncio.create_task(_run_oversold_outcomes(stop_event), name="oversold-outcomes-core")
    intraday_task = asyncio.create_task(
        run_intraday_profitability_request_scheduler(stop_event),
        name="intraday-profitability-requests",
    )
    try:
        await asyncio.gather(oversold_task, intraday_task)
    finally:
        oversold_task.cancel()
        intraday_task.cancel()
        await asyncio.gather(oversold_task, intraday_task, return_exceptions=True)
