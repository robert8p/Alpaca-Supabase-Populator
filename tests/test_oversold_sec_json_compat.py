from __future__ import annotations

import json
from datetime import UTC, date, datetime

from app import oversold_sec_fundamentals as sec
from app.oversold_sec_json_compat import json_safe


def test_sec_payload_dates_are_json_serializable() -> None:
    payload = {
        "available_from": date(2026, 8, 1),
        "report_period_end": date(2026, 6, 30),
        "nested": {"accepted": datetime(2026, 8, 1, 12, 0, tzinfo=UTC)},
    }
    safe = json_safe(payload)
    encoded = json.dumps(safe)
    assert '"available_from": "2026-08-01"' in encoded
    assert safe["nested"]["accepted"] == "2026-08-01T12:00:00+00:00"


def test_application_bootstrap_installs_json_safe_sec_fetchers() -> None:
    assert getattr(sec, "_json_safe_payloads_installed", False) is True
