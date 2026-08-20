from pathlib import Path


UI = Path("app/static/oversold_v33_ui.js")
CHAT = Path("app/static/oversold_chatgpt_v33.js")
LOADER = Path("app/static/oversold_tracking_v3.js")


def test_v33_ui_exposes_purpose_components_and_evidence_filters() -> None:
    source = UI.read_text(encoding="utf-8")
    assert "verified price damage" in source
    assert "Overreaction" in source
    assert "Survivability" in source
    assert "3-session fit" in source
    assert "Tail risk" in source
    assert "INVESTIGATE eligible" in source
    assert "Primary fundamentals available" in source
    assert "characterData:true" not in source


def test_v33_chatgpt_prompt_is_independent_and_complete() -> None:
    source = CHAT.read_text(encoding="utf-8")
    assert "What precisely caused the sell-off?" in source
    assert "How much underlying economic value appears impaired?" in source
    assert "Can the company financially survive the event" in source
    assert "Is expected upside attractive relative to downside" in source
    assert "What single additional evidence item would most change the conclusion?" in source
    assert "https://chatgpt.com/?q=" in source
    assert "Allocate exactly 100.0%" in source
    assert "No Buy-or-better INVESTIGATE candidates; no allocation." in source


def test_v33_scripts_load_after_existing_ui_layers() -> None:
    source = LOADER.read_text(encoding="utf-8")
    base = source.index("oversold_tracking_v3_base.js")
    day3 = source.index("oversold_day3_ui.js")
    fundamentals = source.index("oversold_fundamentals_rating_v2.js")
    v33_ui = source.index("oversold_v33_ui.js")
    v33_chat = source.index("oversold_chatgpt_v33.js")
    assert base < day3 < fundamentals < v33_ui < v33_chat
