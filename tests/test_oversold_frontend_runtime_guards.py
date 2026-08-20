from pathlib import Path


SCRIPT = Path("app/static/oversold_chatgpt_score.js")


def test_row_relabel_is_idempotent() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "if (button.textContent !== 'Audit ↗') button.textContent = 'Audit ↗';" in source
    assert "if (helper && helper.textContent !== 'same cutoff') helper.textContent = 'same cutoff';" in source


def test_latest_scan_refreshes_while_page_is_visible() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "setInterval(refreshLatestView, 30000);" in source
    assert "document.visibilityState !== 'visible'" in source
    assert "latestRefreshInFlight" in source
