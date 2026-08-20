from pathlib import Path


def test_three_session_backfill_types_jsonb_build_parameters() -> None:
    source = Path("app/oversold_three_session_reliability.py").read_text(encoding="utf-8")
    assert "'calibration_target_definition', %s::text" in source
    assert "'target_contract_version', %s::text" in source
    assert "mfe_3d >= %s::double precision" in source
    assert "IS DISTINCT FROM %s::text" in source
