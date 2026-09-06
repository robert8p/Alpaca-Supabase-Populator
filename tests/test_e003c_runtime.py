from datetime import date, datetime
from pathlib import Path
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
from app.e003c_worker import _mode


def test_rule_hash_is_frozen() -> None:
    assert (
        RULE_HASH == "4bcd161f68c824365d8a0f0dda47a78ea8f410a04dfe0250c36e142c472e2562"
    )
    assert canonical_rule_json().startswith('{"basket":')


def test_release_pin_requires_worker_and_exact_sha() -> None:
    sha = "a" * 40
    identity = RuntimeIdentity(
        owner_id="owner",
        service_id="srv-test",
        service_name="e003c",
        service_type="worker",
        deployment_id="dep-test",
        instance_id="srv-test-instance",
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
        instance_id="srv-test-instance",
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
    assert (
        phase_state(datetime(2026, 8, 14, 9, 32, tzinfo=ny), clock)["current_phase"]
        == "entry_capture"
    )
    assert (
        phase_state(datetime(2026, 8, 14, 12, 0, tzinfo=ny), clock)["current_phase"]
        == "intraday_wait"
    )
    assert (
        phase_state(datetime(2026, 8, 14, 15, 56, tzinfo=ny), clock)["current_phase"]
        == "exit_capture"
    )


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


def test_release_pin_accepts_render_background_worker_type() -> None:
    sha = "c" * 40
    identity = RuntimeIdentity(
        owner_id="owner",
        service_id="srv-test",
        service_name="e003c",
        service_type="background_worker",
        deployment_id="dep-test",
        instance_id="srv-test-instance",
        git_sha=sha,
        git_branch="release/e003c-prospective-20260813",
        repo_slug="robert8p/Alpaca-Supabase-Populator",
        release_sha=sha,
        expected_branch="release/e003c-prospective-20260813",
        expected_service_name="e003c",
        expected_service_id="srv-test",
    )
    assert release_pin_readiness(identity)["ok"] is True


def test_dedicated_worker_excludes_generic_rapid_maintenance() -> None:
    worker_source = (
        Path(__file__).resolve().parents[1] / "app" / "e003c_worker.py"
    ).read_text()
    assert "queue_safe_missing_days" not in worker_source
    assert "app.live_maintenance" not in worker_source


def test_dedicated_worker_accepts_fail_closed_retired_mode(monkeypatch) -> None:
    monkeypatch.setenv("E003C_RUNTIME_MODE", "retired")
    assert _mode() == "retired"


def test_retired_mode_precedes_runtime_settings_and_database_access() -> None:
    worker_source = (
        Path(__file__).resolve().parents[1] / "app" / "e003c_worker.py"
    ).read_text()
    run_source = worker_source.split("async def run_dedicated_worker() -> None:", 1)[1]
    retired_branch = run_source.split("settings = get_settings()", 1)[0]
    assert 'mode == "retired"' in retired_branch
    assert "assert_database_writable" not in retired_branch


def test_release_pin_accepts_missing_render_deployment_id_with_strict_identity() -> (
    None
):
    sha = "d" * 40
    identity = RuntimeIdentity(
        owner_id="owner",
        service_id="srv-test",
        service_name="e003c",
        service_type="worker",
        deployment_id=None,
        instance_id="srv-test-instance-123",
        git_sha=sha,
        git_branch="release/e003c-prospective-20260813",
        repo_slug="robert8p/Alpaca-Supabase-Populator",
        release_sha=sha,
        expected_branch="release/e003c-prospective-20260813",
        expected_service_name="e003c",
        expected_service_id="srv-test",
    )
    result = release_pin_readiness(identity)
    assert result["ok"] is True
    assert result["deployment_id"] is None
    assert result["deployment_id_present"] is False
    assert result["deployment_id_ok"] is True
    assert result["deployment_identity_source"] == "independent_render_identity"
    assert result["instance_id_ok"] is True
    assert result["independent_render_identity_ok"] is True


def test_release_pin_rejects_missing_deployment_id_with_foreign_instance() -> None:
    sha = "e" * 40
    identity = RuntimeIdentity(
        owner_id="owner",
        service_id="srv-test",
        service_name="e003c",
        service_type="worker",
        deployment_id=None,
        instance_id="srv-other-instance-123",
        git_sha=sha,
        git_branch="release/e003c-prospective-20260813",
        repo_slug="robert8p/Alpaca-Supabase-Populator",
        release_sha=sha,
        expected_branch="release/e003c-prospective-20260813",
        expected_service_name="e003c",
        expected_service_id="srv-test",
    )
    result = release_pin_readiness(identity)
    assert result["ok"] is False
    assert result["instance_id_ok"] is False
    assert result["deployment_id_ok"] is False
    assert result["independent_render_identity_ok"] is False


def test_release_pin_rejects_invalid_exposed_deployment_id() -> None:
    sha = "f" * 40
    identity = RuntimeIdentity(
        owner_id="owner",
        service_id="srv-test",
        service_name="e003c",
        service_type="worker",
        deployment_id="not-a-render-deploy",
        instance_id="srv-test-instance-123",
        git_sha=sha,
        git_branch="release/e003c-prospective-20260813",
        repo_slug="robert8p/Alpaca-Supabase-Populator",
        release_sha=sha,
        expected_branch="release/e003c-prospective-20260813",
        expected_service_name="e003c",
        expected_service_id="srv-test",
    )
    result = release_pin_readiness(identity)
    assert result["ok"] is False
    assert result["independent_render_identity_ok"] is True
    assert result["deployment_id_present"] is True
    assert result["deployment_id_format_ok"] is False
    assert result["deployment_id_ok"] is False
