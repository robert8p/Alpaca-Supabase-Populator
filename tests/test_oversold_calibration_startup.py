import asyncio

from app import oversold_outcome_scheduler as scheduler


def run_stopped_scheduler():
    async def run():
        stop = asyncio.Event()
        stop.set()
        await scheduler._run_oversold_outcomes(stop)
    asyncio.run(run())


def test_startup_records_readiness_before_legacy_rescore_cycle(monkeypatch):
    monkeypatch.setenv("OVERSOLD_OUTCOME_CAPTURE_ENABLED", "true")
    calls = []
    def check():
        calls.append("calibration")
        return {"status": "not_ready", "sample_count": 0}
    async def rescore():
        calls.append("rescore")
        raise RuntimeError("legacy cycle failed")
    monkeypatch.setattr(scheduler, "run_calibration_if_changed", check)
    monkeypatch.setattr(scheduler, "_refresh_point_in_time_rescores", rescore)
    run_stopped_scheduler()
    assert calls == ["calibration", "rescore"]


def test_calibration_failure_does_not_disable_outcome_recovery(monkeypatch):
    monkeypatch.setenv("OVERSOLD_OUTCOME_CAPTURE_ENABLED", "true")
    calls = []
    def check():
        calls.append("calibration")
        raise RuntimeError("calibration temporarily unavailable")
    async def rescore():
        calls.append("rescore")
        return ({}, {})
    monkeypatch.setattr(scheduler, "run_calibration_if_changed", check)
    monkeypatch.setattr(scheduler, "_refresh_point_in_time_rescores", rescore)
    run_stopped_scheduler()
    assert calls == ["calibration", "rescore"]


def test_disabled_scheduler_stays_disabled(monkeypatch):
    monkeypatch.setenv("OVERSOLD_OUTCOME_CAPTURE_ENABLED", "false")
    def unexpected_check():
        raise AssertionError("Disabled scheduler ran calibration")
    monkeypatch.setattr(scheduler, "run_calibration_if_changed", unexpected_check)
    run_stopped_scheduler()
