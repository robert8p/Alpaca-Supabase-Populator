from __future__ import annotations

"""Append-only persistence for cutoff-valid primary event evidence."""

import logging
from typing import Any

from psycopg.types.json import Jsonb

from app.oversold_sec_json_compat import json_safe

logger = logging.getLogger(__name__)


def _records(item: dict[str, Any]) -> list[dict[str, Any]]:
    output: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for article in item.get("headlines") or []:
        if not isinstance(article, dict) or article.get("is_primary_evidence") is not True:
            continue
        record = article.get("primary_evidence")
        if not isinstance(record, dict):
            continue
        source_kind = str(record.get("source_kind") or article.get("source_kind") or "unknown")
        external_id = str(record.get("external_id") or article.get("id") or "")
        if not external_id:
            continue
        key = (source_kind, external_id)
        if key in seen:
            continue
        seen.add(key)
        output.append(record)
    return output


def patch_module(module: Any) -> None:
    if getattr(module, "_primary_evidence_store_installed", False):
        return
    original = module.persist_original_score

    def persist_original_score(
        cur: Any,
        *,
        candidate_id: int,
        scan_id: Any,
        item: dict[str, Any],
        score: dict[str, Any],
        evidence_cutoff: Any,
    ) -> tuple[int, int]:
        records = _records(item)
        analysis = score.setdefault("catalyst_analysis", {})
        analysis["primary_event_evidence_persisted_count"] = len(records)
        evidence_snapshot_id, model_run_id = original(
            cur,
            candidate_id=candidate_id,
            scan_id=scan_id,
            item=item,
            score=score,
            evidence_cutoff=evidence_cutoff,
        )
        if not records:
            return evidence_snapshot_id, model_run_id

        cur.execute("SAVEPOINT or_primary_evidence_store")
        try:
            for record in records:
                metadata = json_safe(record.get("metadata") or {})
                documents = json_safe(record.get("documents") or [])
                cur.execute(
                    """
                    INSERT INTO or_primary_evidence(
                        candidate_id,evidence_snapshot_id,scan_id,symbol,
                        source_kind,source_authority,external_id,accession_number,form,
                        accepted_at,filed_date,available_at,evidence_cutoff,title,source_url,
                        summary,content_excerpt,content_hash,documents,metadata
                    ) VALUES (
                        %s,%s,%s,%s,
                        %s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s,%s,
                        %s,%s,%s,%s,%s
                    )
                    ON CONFLICT (evidence_snapshot_id,source_kind,external_id) DO NOTHING
                    """,
                    (
                        candidate_id,
                        evidence_snapshot_id,
                        scan_id,
                        item.get("symbol"),
                        record.get("source_kind"),
                        record.get("source_authority"),
                        record.get("external_id"),
                        record.get("accession_number"),
                        record.get("form"),
                        record.get("accepted_at"),
                        record.get("filed_date"),
                        record.get("available_at"),
                        evidence_cutoff,
                        record.get("title"),
                        record.get("source_url"),
                        record.get("summary"),
                        record.get("content_excerpt"),
                        record.get("content_hash"),
                        Jsonb(documents),
                        Jsonb(metadata),
                    ),
                )
            cur.execute("RELEASE SAVEPOINT or_primary_evidence_store")
        except Exception as exc:
            cur.execute("ROLLBACK TO SAVEPOINT or_primary_evidence_store")
            cur.execute("RELEASE SAVEPOINT or_primary_evidence_store")
            # The complete primary records are still retained inside the immutable
            # Evidence Snapshot's news_items. The auxiliary index table must not
            # destroy an otherwise valid scan if its migration is temporarily late.
            logger.warning(
                "Primary evidence auxiliary persistence failed for candidate %s: %s",
                candidate_id,
                exc,
            )
        return evidence_snapshot_id, model_run_id

    module.persist_original_score = persist_original_score
    module._primary_evidence_store_installed = True
