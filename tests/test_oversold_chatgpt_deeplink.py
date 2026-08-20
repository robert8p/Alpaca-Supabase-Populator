from pathlib import Path


SCRIPT = Path("app/static/oversold_top5.js")


def test_chatgpt_launches_with_prefilled_query() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "const CHATGPT_BASE = 'https://chatgpt.com/?q=';" in source
    assert "encodeURIComponent(prompt)" in source
    assert "window.analyseInChatGPT = function analyseInChatGPTPrefilled" in source
    assert "window.open(chatGPTUrl(compactPrompt)" in source


def test_top_audits_use_prefilled_prompt_after_latest_scan_fetch() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "const popup = window.open('about:blank', '_blank');" in source
    assert "popup.location.replace(chatGPTUrl(prompt));" in source
    assert "compactTopPrompt(candidates)" in source


def test_single_audit_keeps_full_prompt_clipboard_fallback() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    assert "typeof buildChatGPTPrompt === 'function' ? buildChatGPTPrompt(c) : compactPrompt" in source
    assert "copyText(fullPrompt)" in source
