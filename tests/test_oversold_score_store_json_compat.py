from __future__ import annotations

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from types import SimpleNamespace
from uuid import UUID, uuid4

from app import oversold_score_store as live_store
from app.oversold_score_store_json_compat import patch_module
from app.oversold_sec_json_compat import json_safe


def test_json_safe_handles_nested_provider_and_model_types() -> None:
    payload = {
        "price_session_context": {
            "latest_trade_timestamp": datetime(2026, 8, 20, 11, 12, tzinfo=UTC),
        },
        "fundamentals": {
            "available_from": date(2026, 8, 1),
            "market_cap": Decimal("1234567.89"),
        },
        "scan_id": UUID("00000000-0000-0000-0000-000000000001"),
        "flags": {"a", "b"},
    }
    safe = json_safe(payload)
    encoded = json.dumps(safe)
    assert safe["price_session_context"]["latest_trade_timestamp"] == "2026-08-20T11:12:00+00:00"
    assert safe["fundamentals"]["available_from"] == "2026-08-01"
    assert safe["fundamentals"]["market_cap"] == 1234567.89
    assert safe["scan_id"] == "00000000-0000-0000-0000-000000000001"
    assert '"latest_trade_timestamp"' in encoded


def test_persistence_wrapper_normalizes_json_objects_but_preserves_cutoff() -> None:
    captured: dict = {}

    def original_persist(
        cur,
        *,
        candidate_id,
        scan_id,
        item,
        score,
        evidence_cutoff,
    ):
        captured.update(
            item=item,
            score=score,
            evidence_cutoff=evidence_cutoff,
            scan_id=scan_id,
            candidate_id=candidate_id,
        )
        json.dumps(item)
        json.dumps(score)
        return 10, 20

    module = SimpleNamespace(persist_original_score=original_persist)
    patch_module(module)
    cutoff = datetime(2026, 8, 20, 11, 12, tzinfo=UTC)
    scan_id = uuid4()
    result = module.persist_original_score(
        object(),
        candidate_id=7,
        scan_id=scan_id,
        item={"price_session_context": {"latest_trade_timestamp": cutoff}},
        score={"catalyst_analysis": {"filing_date": date(2026, 8, 1)}},
        evidence_cutoff=cutoff,
    )
    assert result == (10, 20)
    assert captured["item"]["price_session_context"]["latest_trade_timestamp"] == cutoff.isoformat()
    assert captured["score"]["catalyst_analysis"]["filing_date"] == "2026-08-01"
    assert captured["evidence_cutoff"] is cutoff
    assert captured["scan_id"] == scan_id


def test_application_bootstrap_installs_json_safe_evidence_persistence() -> None:
    assert getattr(live_store, "_json_safe_persistence_installed", False) is True
