from __future__ import annotations

import asyncio
from datetime import date, datetime
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app import oversold_scan_scheduler as scheduler
from app.oversold_scan_scheduler_runtime import patch_module

LONDON = ZoneInfo("Europe/London")


def test_scheduled_scan_due_only_inside_london_window() -> None:
    run_date = date(2026, 8, 20)
    assert scheduler.scheduled_scan_due(
        datetime(2026, 8, 20, 22, 50, tzinfo=LONDON),
        None,
    ) is True
    assert scheduler.scheduled_scan_due(
        datetime(2026, 8, 20, 22, 44, tzinfo=LONDON),
        None,
    ) is False
    assert scheduler.scheduled_scan_due(
        datetime(2026, 8, 20, 23, 6, tzinfo=LONDON),
        None,
    ) is False
    assert scheduler.scheduled_scan_due(
        datetime(2026, 8, 20, 22, 50, tzinfo=LONDON),
        run_date,
    ) is False
    assert scheduler.scheduled_scan_due(
        datetime(2026, 8, 22, 22, 50, tzinfo=LONDON),
        None,
    ) is False


def test_bootstrap_requires_missing_current_primary_version(monkeypatch) -> None:
    monkeypatch.setattr(
        scheduler,
        "_scan_state",
        lambda: {
            "scan_running": False,
            "latest": {"status": "completed", "primary_version": None},
        },
    )
    assert scheduler.bootstrap_scan_required(enabled=True) is True
    assert scheduler.bootstrap_scan_required(enabled=False) is False

    monkeypatch.setattr(
        scheduler,
        "_scan_state",
        lambda: {
            "scan_running": False,
            "latest": {
                "status": "completed",
                "primary_version": scheduler.PRIMARY_EVIDENCE_VERSION,
            },
        },
    )
    assert scheduler.bootstrap_scan_required(enabled=True) is False

    monkeypatch.setattr(
        scheduler,
        "_scan_state",
        lambda: {"scan_running": True, "latest": None},
    )
    assert scheduler.bootstrap_scan_required(enabled=True) is False


def test_runtime_patch_runs_scan_and_outcome_tasks_together(monkeypatch) -> None:
    events: list[str] = []
    stop = asyncio.Event()

    async def original(stop_event: asyncio.Event) -> None:
        events.append("outcome")
        await asyncio.sleep(0)
        stop_event.set()

    async def scan(stop_event: asyncio.Event) -> None:
        events.append("scan")
        await stop_event.wait()

    monkeypatch.setattr(
        "app.oversold_scan_scheduler_runtime.run_oversold_scan_scheduler",
        scan,
    )
    module = SimpleNamespace(run_oversold_outcome_scheduler=original)
    patch_module(module)
    asyncio.run(module.run_oversold_outcome_scheduler(stop))
    assert set(events) == {"scan", "outcome"}
    assert getattr(module, "_worker_scan_scheduler_installed", False) is True
