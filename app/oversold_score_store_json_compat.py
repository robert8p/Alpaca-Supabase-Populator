from __future__ import annotations

"""Defensive JSON normalization for immutable Oversold evidence persistence.

Market, news, filing and scoring payloads are assembled from several providers.
The database timestamps remain native PostgreSQL values, while every nested JSONB
payload is normalized immediately before the canonical persistence function runs.
This provides one boundary guarantee rather than relying on every upstream source
to remember to stringify dates independently.
"""

from typing import Any

from app.oversold_sec_json_compat import json_safe


def patch_module(module: Any) -> None:
    if getattr(module, "_json_safe_persistence_installed", False):
        return

    original_persist = module.persist_original_score

    def persist_original_score(
        cur: Any,
        *,
        candidate_id: int,
        scan_id: Any,
        item: dict[str, Any],
        score: dict[str, Any],
        evidence_cutoff: Any,
    ) -> tuple[int, int]:
        # Keep evidence_cutoff native because it is written to timestamptz columns
        # and used for horizon arithmetic. Only JSONB-bound objects are cloned and
        # normalized; original signal inputs remain otherwise unchanged.
        safe_item = json_safe(item)
        safe_score = json_safe(score)
        return original_persist(
            cur,
            candidate_id=candidate_id,
            scan_id=scan_id,
            item=safe_item,
            score=safe_score,
            evidence_cutoff=evidence_cutoff,
        )

    module.persist_original_score = persist_original_score
    module._json_safe_persistence_installed = True
