from __future__ import annotations

import asyncio
import logging
import os
import signal
from datetime import datetime
from typing import Any

from app.alpaca import AlpacaClient
from app.config import get_settings
from app.db import assert_database_writable, close_pool
from app.e003c_freeze import freeze_latest_completed_signal
from app.e003c_live import capture_entry, capture_exit, capture_quote_snapshot
from app.e003c_runtime import (
    AdvisoryWriterLock,
    ENTRY_END,
    ENTRY_START,
    EXIT_END,
    EXIT_FINALISE_NOT_BEFORE,
    EXIT_START,
    NY,
    RuntimeIdentity,
    assert_writer_authority,
    baseline_checkpoint_readiness,
    basket_readiness,
    critical_readiness_ok,
    cutover_readiness,
    database_readiness,
    freeze_readiness,
    phase_state,
    release_pin_readiness,
    release_writer_lease,
    renew_writer_lease,
    rule_registry_readiness,
    try_acquire_writer_lease,
    upsert_runtime_instance,
)

VERSION = "e003c-isolation-1.0.1"
logger = logging.getLogger(__name__)
stop_event = asyncio.Event()


def _mode() -> str:
    value = os.getenv("E003C_RUNTIME_MODE", "readiness").strip().lower()
    if value not in {"readiness", "writer", "standby", "retired"}:
        raise RuntimeError(f"Unsupported E003C_RUNTIME_MODE={value!r}")
    return value


def _seconds(name: str, default: float, minimum: float, maximum: float) -> float:
    value = float(os.getenv(name, str(default)))
    return min(max(value, minimum), maximum)


def _signal_freeze_enabled() -> bool:
    return os.getenv("E003C_SIGNAL_FREEZE_ENABLED", "true").strip().lower() in {"1", "true", "yes", "on"}


async def _provider_readiness() -> tuple[dict[str, Any], dict[str, Any]]:
    settings = get_settings()
    try:
        async with AlpacaClient(target_rpm=min(60, settings.default_target_rpm), max_retries=2, backoff_seconds=1.0) as client:
            clock = await client.get_clock()
            quote_result = await client.fetch_latest_quotes(symbols=["SPY"], feed="sip")
        quotes = quote_result.data.get("quotes", {}) if isinstance(quote_result.data, dict) else {}
        spy_quote = quotes.get("SPY") if isinstance(quotes, dict) else None
        return (
            {
                "ok": bool(isinstance(clock, dict) and isinstance(spy_quote, dict)),
                "clock_available": isinstance(clock, dict),
                "sip_quote_available": isinstance(spy_quote, dict),
                "clock_is_open": bool(clock.get("is_open")) if isinstance(clock, dict) else None,
                "clock_timestamp": clock.get("timestamp") if isinstance(clock, dict) else None,
                "next_open": clock.get("next_open") if isinstance(clock, dict) else None,
                "next_close": clock.get("next_close") if isinstance(clock, dict) else None,
                "quote_request_id": quote_result.request_id,
            },
            clock if isinstance(clock, dict) else {},
        )
    except Exception as exc:
        logger.warning("E003C provider readiness failed: %s", exc)
        return ({"ok": False, "error_type": type(exc).__name__, "error": str(exc)[:500]}, {})


async def collect_readiness(identity: RuntimeIdentity, mode: str) -> tuple[dict[str, Any], dict[str, Any]]:
    provider, clock = await _provider_readiness()
    now_et = datetime.now(tz=NY)
    readiness = {
        "release_pin": release_pin_readiness(identity),
        "database": await asyncio.to_thread(database_readiness),
        "rule_registry": await asyncio.to_thread(rule_registry_readiness),
        "freeze": await asyncio.to_thread(freeze_readiness),
        "basket": await asyncio.to_thread(basket_readiness, now_et),
        "baseline_checkpoint": await asyncio.to_thread(baseline_checkpoint_readiness),
        "cutover": await asyncio.to_thread(cutover_readiness, identity, require_authorized=mode == "writer"),
        "provider": provider,
        "runtime_version": VERSION,
    }
    readiness["ok"] = critical_readiness_ok(readiness, require_provider=True)
    return readiness, phase_state(now_et, clock)


async def _capture_scheduler(
    identity: RuntimeIdentity,
    lock: AdvisoryWriterLock,
    local_stop_event: asyncio.Event,
) -> None:
    settings = get_settings()
    logger.info("Dedicated E003C prospective capture scheduler enabled")
    while not local_stop_event.is_set():
        fast_window = False
        try:
            now_et = datetime.now(tz=NY)
            current_time = now_et.timetz().replace(tzinfo=None)
            entry_window = ENTRY_START <= current_time <= ENTRY_END
            exit_window = EXIT_START <= current_time <= EXIT_END
            fast_window = entry_window or exit_window
            if now_et.weekday() < 5:
                async with AlpacaClient(
                    target_rpm=min(300, settings.default_target_rpm),
                    max_retries=3,
                    backoff_seconds=1.0,
                ) as client:
                    clock = await client.get_clock()
                    is_open = bool(clock.get("is_open")) if isinstance(clock, dict) else False
                    if is_open and entry_window:
                        await asyncio.to_thread(assert_writer_authority, identity, lock)
                        await capture_entry(now_et.date(), client)
                        await asyncio.to_thread(assert_writer_authority, identity, lock)
                        await capture_quote_snapshot(now_et.date(), "entry", client)
                    if is_open and exit_window:
                        await asyncio.to_thread(assert_writer_authority, identity, lock)
                        await capture_quote_snapshot(now_et.date(), "exit", client)
                        if current_time >= EXIT_FINALISE_NOT_BEFORE:
                            await asyncio.to_thread(assert_writer_authority, identity, lock)
                            await capture_exit(now_et.date(), client)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Dedicated E003C capture scheduler error")

        try:
            configured_poll = _seconds("E003C_CAPTURE_POLL_SECONDS", 30.0, 10.0, 300.0)
            poll_seconds = min(configured_poll, 60.0) if fast_window else configured_poll
            await asyncio.wait_for(local_stop_event.wait(), timeout=poll_seconds)
        except TimeoutError:
            pass


async def _signal_freeze_scheduler(
    identity: RuntimeIdentity,
    lock: AdvisoryWriterLock,
    local_stop_event: asyncio.Event,
) -> None:
    if not _signal_freeze_enabled():
        return
    logger.info("Dedicated E003C signal-freeze scheduler enabled")
    while not local_stop_event.is_set():
        try:
            await asyncio.to_thread(assert_writer_authority, identity, lock)
            freeze_result = await asyncio.to_thread(freeze_latest_completed_signal)
            if freeze_result.get("frozen"):
                logger.info("Dedicated E003C signal freeze created: %s", freeze_result)
        except asyncio.CancelledError:
            raise
        except Exception:
            logger.exception("Dedicated E003C signal-freeze scheduler error")
        try:
            poll_seconds = _seconds("E003C_SIGNAL_FREEZE_POLL_SECONDS", 900.0, 300.0, 3600.0)
            await asyncio.wait_for(local_stop_event.wait(), timeout=poll_seconds)
        except TimeoutError:
            pass


async def _heartbeat_loop(
    identity: RuntimeIdentity,
    mode: str,
    lock: AdvisoryWriterLock | None,
    local_stop_event: asyncio.Event,
    ttl_seconds: int,
) -> None:
    while not local_stop_event.is_set():
        readiness, phase = await collect_readiness(identity, mode)
        writer_active = lock is not None
        error: str | None = None
        if writer_active:
            try:
                await asyncio.to_thread(lock.assert_held)
                renewed = await asyncio.to_thread(renew_writer_lease, identity, ttl_seconds)
                if not renewed:
                    raise RuntimeError("E003C writer lease renewal failed")
            except Exception as exc:
                error = str(exc)
                logger.exception("E003C writer authority lost")
                local_stop_event.set()
        await asyncio.to_thread(
            upsert_runtime_instance,
            identity,
            mode=mode,
            writer_active=writer_active and error is None,
            phase=phase,
            readiness=readiness,
            advisory_lock_key=lock.lock_key if lock else None,
            advisory_backend_pid=lock.backend_pid if lock else None,
            checkpoint=None,
            error=error,
        )
        if writer_active and not critical_readiness_ok(readiness, require_provider=False):
            logger.error("E003C critical readiness control failed; stopping writer")
            local_stop_event.set()
        try:
            poll_seconds = _seconds("E003C_HEARTBEAT_SECONDS", 30.0, 10.0, max(10.0, ttl_seconds / 2.0))
            await asyncio.wait_for(local_stop_event.wait(), timeout=poll_seconds)
        except TimeoutError:
            pass


async def run_dedicated_worker() -> None:
    mode = _mode()
    if mode == "retired":
        logging.basicConfig(
            level=getattr(logging, os.getenv("LOG_LEVEL", "INFO").upper(), logging.INFO),
            format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        )
        logger.info(
            "E003C runtime is retired; database and provider connections are disabled"
        )
        await stop_event.wait()
        return

    settings = get_settings()
    logging.basicConfig(
        level=getattr(logging, settings.log_level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    assert_database_writable()
    identity = RuntimeIdentity.from_environment()
    ttl_seconds = int(_seconds("E003C_LEASE_TTL_SECONDS", 120.0, 60.0, 300.0))

    readiness, phase = await collect_readiness(identity, mode)
    await asyncio.to_thread(
        upsert_runtime_instance,
        identity,
        mode=mode,
        writer_active=False,
        phase=phase,
        readiness=readiness,
        checkpoint={"event": "startup_readiness", "passed": readiness.get("ok", False)},
    )
    logger.info(
        "E003C dedicated runtime started mode=%s service=%s instance=%s git_sha=%s readiness=%s",
        mode,
        identity.service_id,
        identity.instance_id,
        identity.git_sha,
        readiness.get("ok"),
    )

    lock: AdvisoryWriterLock | None = None
    tasks: list[asyncio.Task[Any]] = []
    try:
        if mode == "writer":
            if not critical_readiness_ok(readiness, require_provider=True):
                raise RuntimeError("E003C writer startup blocked by failed readiness controls")
            lock = AdvisoryWriterLock()
            if not await asyncio.to_thread(lock.acquire):
                raise RuntimeError("E003C advisory writer lock is already held")
            acquired = await asyncio.to_thread(
                try_acquire_writer_lease,
                identity,
                advisory_lock_key=int(lock.lock_key),
                advisory_backend_pid=int(lock.backend_pid),
                ttl_seconds=ttl_seconds,
            )
            if not acquired:
                lock.release()
                lock = None
                raise RuntimeError("E003C database writer lease is already owned")
            await asyncio.to_thread(assert_writer_authority, identity, lock)
            await asyncio.to_thread(
                upsert_runtime_instance,
                identity,
                mode=mode,
                writer_active=True,
                phase=phase,
                readiness=readiness,
                advisory_lock_key=lock.lock_key,
                advisory_backend_pid=lock.backend_pid,
                checkpoint={"event": "writer_ownership_acquired", "ttl_seconds": ttl_seconds},
            )
            tasks.extend(
                [
                    asyncio.create_task(_capture_scheduler(identity, lock, stop_event), name="e003c-dedicated-capture"),
                    asyncio.create_task(_signal_freeze_scheduler(identity, lock, stop_event), name="e003c-dedicated-signal-freeze"),
                ]
            )
        tasks.append(
            asyncio.create_task(_heartbeat_loop(identity, mode, lock, stop_event, ttl_seconds), name="e003c-runtime-heartbeat")
        )
        await stop_event.wait()
    finally:
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        if lock is not None:
            try:
                await asyncio.to_thread(release_writer_lease, identity, "graceful_shutdown")
            finally:
                lock.release()
        try:
            final_readiness, final_phase = await collect_readiness(identity, "standby")
            await asyncio.to_thread(
                upsert_runtime_instance,
                identity,
                mode="stopped",
                writer_active=False,
                phase=final_phase,
                readiness=final_readiness,
                checkpoint={"event": "runtime_stopped"},
                stopped=True,
            )
        except Exception:
            logger.exception("Unable to write final E003C runtime heartbeat")
        close_pool()


def _signal_handler(*_: Any) -> None:
    stop_event.set()


if __name__ == "__main__":
    signal.signal(signal.SIGTERM, _signal_handler)
    signal.signal(signal.SIGINT, _signal_handler)
    asyncio.run(run_dedicated_worker())
