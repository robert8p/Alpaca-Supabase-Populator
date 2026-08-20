from pathlib import Path


SCRIPT = Path("app/static/oversold_score_ui.js")


def test_v32_ui_exposes_cause_spike_dilution_and_investigate_gates() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    for token in (
        "cause_verification_status",
        "economic_damage_class",
        "spike_adjustment",
        "dilution_analysis",
        "eligibility_gates",
        "Pre-signal price path / spike adjustment",
        "Financing / dilution severity",
        "INVESTIGATE eligibility gates",
        "Source-quality hierarchy",
    ):
        assert token in source


def test_v32_ui_rerender_guard_remains_idempotent() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "if (tr.dataset.scoreModelKey === key) return;" in source
