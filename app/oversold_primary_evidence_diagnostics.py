from __future__ import annotations

"""Primary-evidence coverage diagnostics for the live Oversold model."""

import sys
from typing import Any

from app.db import connection
from app.oversold_primary_evidence import PRIMARY_EVIDENCE_VERSION


def _coverage() -> dict[str, Any]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH latest AS (
                    SELECT id FROM or_scans
                    WHERE status='completed'
                    ORDER BY completed_at DESC NULLS LAST,started_at DESC
                    LIMIT 1
                )
                SELECT
                    (SELECT id FROM latest) AS scan_id,
                    count(pe.id) AS evidence_items,
                    count(DISTINCT pe.symbol) AS symbols_with_primary_evidence,
                    count(pe.id) FILTER (WHERE pe.source_kind='sec_filing') AS sec_filings,
                    count(pe.id) FILTER (WHERE pe.source_kind='clinical_trial_registry') AS exact_clinical_trial_records,
                    count(pe.id) FILTER (WHERE pe.source_kind='clinical_trial_sponsor_match') AS sponsor_matched_trial_records,
                    count(pe.id) FILTER (WHERE pe.source_kind='fda_regulatory_record') AS exact_fda_application_records,
                    count(pe.id) FILTER (WHERE pe.source_kind='fda_drug_enforcement') AS fda_drug_enforcement_records,
                    count(pe.id) FILTER (WHERE pe.source_kind='fda_device_enforcement') AS fda_device_enforcement_records,
                    count(pe.id) FILTER (WHERE pe.available_at > pe.evidence_cutoff) AS cutoff_violations,
                    count(pe.id) FILTER (WHERE pe.content_excerpt IS NULL OR length(trim(pe.content_excerpt))=0) AS empty_excerpts,
                    max(pe.available_at) AS freshest_available_at
                FROM latest
                LEFT JOIN or_primary_evidence pe ON pe.scan_id=latest.id
                """
            )
            summary = dict(cur.fetchone() or {})
            cur.execute(
                """
                WITH latest AS (
                    SELECT id FROM or_scans
                    WHERE status='completed'
                    ORDER BY completed_at DESC NULLS LAST,started_at DESC
                    LIMIT 1
                )
                SELECT pe.source_kind,pe.source_authority,count(*) AS evidence_items,
                       count(DISTINCT pe.symbol) AS symbols
                FROM or_primary_evidence pe
                JOIN latest ON latest.id=pe.scan_id
                GROUP BY pe.source_kind,pe.source_authority
                ORDER BY evidence_items DESC,pe.source_kind
                """
            )
            by_source = [dict(row) for row in cur.fetchall()]
        conn.rollback()
    summary["version"] = PRIMARY_EVIDENCE_VERSION
    summary["clinical_trial_records"] = int(summary.get("exact_clinical_trial_records") or 0) + int(
        summary.get("sponsor_matched_trial_records") or 0
    )
    summary["fda_records"] = (
        int(summary.get("exact_fda_application_records") or 0)
        + int(summary.get("fda_drug_enforcement_records") or 0)
        + int(summary.get("fda_device_enforcement_records") or 0)
    )
    summary["by_source"] = by_source
    return summary


def patch_module(target_module: Any) -> None:
    if getattr(target_module, "_primary_evidence_diagnostics_installed", False):
        return
    original = target_module._model_diagnostics

    def model_diagnostics() -> dict[str, Any]:
        result = original()
        try:
            coverage = _coverage()
        except Exception as exc:
            coverage = {
                "version": PRIMARY_EVIDENCE_VERSION,
                "status": "unavailable",
                "error": str(exc)[:500],
                "evidence_items": 0,
                "symbols_with_primary_evidence": 0,
                "cutoff_violations": None,
                "by_source": [],
            }
        output = dict(result)
        output["primary_event_evidence"] = coverage
        summary = dict(output.get("summary") or {})
        summary["primary_evidence_items"] = coverage.get("evidence_items")
        summary["primary_evidence_symbols"] = coverage.get("symbols_with_primary_evidence")
        summary["primary_evidence_cutoff_violations"] = coverage.get("cutoff_violations")
        summary["fda_enforcement_records"] = (
            int(coverage.get("fda_drug_enforcement_records") or 0)
            + int(coverage.get("fda_device_enforcement_records") or 0)
        )
        summary["sponsor_matched_trial_records"] = coverage.get("sponsor_matched_trial_records")
        output["summary"] = summary
        return output

    target_module._model_diagnostics = model_diagnostics
    target_module._primary_evidence_diagnostics_installed = True

    if "pytest" not in sys.modules:
        from app import oversold_public

        oversold_public._model_diagnostics = model_diagnostics
