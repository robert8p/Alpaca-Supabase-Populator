from datetime import date, datetime
from zoneinfo import ZoneInfo

from app.e003c_runtime import (
    RULE_HASH,
    RuntimeIdentity,
    _json_safe,
    canonical_rule_json,
    critical_readiness_ok,
    phase_state,
    release_pin_readiness,
)


def test_rule_hash_is_frozen() -> None:
    assert RULE_HASH == "4bcd161f68c824365d8a0f0dda47a78ea8f410a04dfe0250c36e142c472e2562"
    assert canonical_rule_json().startswith('{"basket":')


def test_release_pin_requires_worker_and_exact_sha() -> None:
    sha = "a" * 40
    identity = RuntimeIdentity(
        owner_id="owner",
        service_id="srv-test",
        service_name="e003c",
        service_type="worker",
        deployment_id="dep-test",
        instance_id="instance",
        git_sha=sha,
        git_branch="release/e003c-prospective-20260813",
        repo_slug="robert8p/Alpaca-Supabase-Populator",
        release_sha=sha,
        expected_branch="release/e003c-prospective-20260813",
        expected_service_name="e003c",
        expected_service_id="srv-test",
    )
    assert release_pin_readiness(identity)["ok"] is True


def test_release_pin_rejects_unrelated_commit() -> None:
    identity = RuntimeIdentity(
        owner_id="owner",
        service_id="srv-test",
        service_name="e003c",
        service_type="worker",
        deployment_id="dep-test",
        instance_id="instance",
        git_sha="b" * 40,
        git_branch="release/e003c-prospective-20260813",
        repo_slug="robert8p/Alpaca-Supabase-Populator",
        release_sha="a" * 40,
        expected_branch="release/e003c-prospective-20260813",
        expected_service_name="e003c",
        expected_service_id="srv-test",
    )
    assert release_pin_readiness(identity)["ok"] is False


def test_phase_state_entry_and_exit_windows() -> None:
    ny = ZoneInfo("America/New_York")
    clock = {"is_open": True}
    assert phase_state(datetime(2026, 8, 14, 9, 32, tzinfo=ny), clock)["current_phase"] == "entry_capture"
    assert phase_state(datetime(2026, 8, 14, 12, 0, tzinfo=ny), clock)["current_phase"] == "intraday_wait"
    assert phase_state(datetime(2026, 8, 14, 15, 56, tzinfo=ny), clock)["current_phase"] == "exit_capture"


def test_writer_readiness_requires_cutover_gate() -> None:
    readiness = {
        name: {"ok": True}
        for name in (
            "release_pin",
            "database",
            "rule_registry",
            "freeze",
            "basket",
            "baseline_checkpoint",
            "provider",
            "cutover",
        )
    }
    assert critical_readiness_ok(readiness, require_provider=True) is True
    readiness["cutover"] = {"ok": False}
    assert critical_readiness_ok(readiness, require_provider=True) is False


def test_json_safe_serialises_control_timestamps() -> None:
    value = {
        "trade_date": date(2026, 8, 13),
        "observed_at": datetime(2026, 8, 13, 20, 21, tzinfo=ZoneInfo("UTC")),
    }
    assert _json_safe(value) == {
        "trade_date": "2026-08-13",
        "observed_at": "2026-08-13T20:21:00+00:00",
    }
