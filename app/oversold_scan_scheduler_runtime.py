from __future__ import annotations

"""Attach the worker-owned scan scheduler without coupling it to worker.py."""

import asyncio
from typing import Any

from app.oversold_scan_scheduler import run_oversold_scan_scheduler


def patch_module(module: Any) -> None:
    if getattr(module, "_worker_scan_scheduler_installed", False):
        return
    original = module.run_oversold_outcome_scheduler

    async def run_oversold_outcome_scheduler(stop_event: asyncio.Event) -> None:
        scan_task = asyncio.create_task(
            run_oversold_scan_scheduler(stop_event),
            name="oversold-reversion-scans",
        )
        try:
            await original(stop_event)
        finally:
            scan_task.cancel()
            await asyncio.gather(scan_task, return_exceptions=True)

    module.run_oversold_outcome_scheduler = run_oversold_outcome_scheduler
    module._worker_scan_scheduler_installed = True
