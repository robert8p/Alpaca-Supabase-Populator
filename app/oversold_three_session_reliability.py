from __future__ import annotations

"""Make the three-session target explicit from signal creation through maturity."""

import asyncio
import logging
import os
from typing import Any

from psycopg.types.json import Jsonb

from app.db import connection

logger = logging.getLogger(__name__)
TARGET_DEFINITION = "hit_reversion_within_3_trading_sessions"
TARGET_CONTRACT_VERSION = "three_session_target_v3"
TARGET_RETURN_PCT = 5.0  # internal calibration threshold; deliberately not UI copy


def backfill_target_metadata() -> dict[str, int]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE or_signal_outcomes
                SET metadata = COALESCE(metadata,'{}'::jsonb) || jsonb_build_object(
                    'calibration_target_definition', %s::text,
                    'calibration_window_sessions', 3,
                    'target_contract_version', %s::text,
                    'calibration_target_matured',
                        (COALESCE(metadata->>'three_session_path_matured','false')='true'
                          AND metadata->>'three_session_path_contract' IS NOT DISTINCT FROM 'completed_sessions_v2'
                          AND metadata->>'three_session_calendar_verified' IS NOT DISTINCT FROM 'true'),
                    'hit_reversion_within_3_sessions',
                        CASE
                          WHEN (COALESCE(metadata->>'three_session_path_matured','false')='true'
                          AND metadata->>'three_session_path_contract' IS NOT DISTINCT FROM 'completed_sessions_v2'
                          AND metadata->>'three_session_calendar_verified' IS NOT DISTINCT FROM 'true')
                            THEN COALESCE(mfe_3d >= %s::double precision,false)
                          ELSE NULL
                        END,
                    'calibration_window_end_ts',
                        COALESCE(
                          NULLIF(metadata->>'calibration_window_end_ts',''),
                          CASE
                            WHEN (COALESCE(metadata->>'three_session_path_matured','false')='true'
                          AND metadata->>'three_session_path_contract' IS NOT DISTINCT FROM 'completed_sessions_v2'
                          AND metadata->>'three_session_calendar_verified' IS NOT DISTINCT FROM 'true')
                              THEN (signal_timestamp + interval '7 days')::text
                            ELSE NULL
                          END
                        )
                ),
                updated_at=now()
                WHERE metadata->>'calibration_target_definition' IS DISTINCT FROM %s::text
                   OR metadata->>'target_contract_version' IS DISTINCT FROM %s::text
                   OR metadata->>'calibration_target_matured' IS NULL
                   OR (metadata->>'calibration_target_matured'='true'
                       AND (metadata->>'three_session_path_matured' IS DISTINCT FROM 'true'
                            OR metadata->>'three_session_calendar_verified' IS DISTINCT FROM 'true'
                            OR metadata->>'three_session_path_contract' IS DISTINCT FROM 'completed_sessions_v2'))
                   OR (
                        (COALESCE(metadata->>'three_session_path_matured','false')='true'
                          AND metadata->>'three_session_path_contract' IS NOT DISTINCT FROM 'completed_sessions_v2'
                          AND metadata->>'three_session_calendar_verified' IS NOT DISTINCT FROM 'true')
                        AND metadata->>'hit_reversion_within_3_sessions' IS NULL
                      )
                """,
                (
                    TARGET_DEFINITION,
                    TARGET_CONTRACT_VERSION,
                    TARGET_RETURN_PCT,
                    TARGET_DEFINITION,
                    TARGET_CONTRACT_VERSION,
                ),
            )
            updated = max(0, cur.rowcount or 0)
            cur.execute(
                """
                SELECT
                  count(*) FILTER (WHERE metadata->>'calibration_target_definition'=%s::text) AS target_rows,
                  count(*) FILTER (
                    WHERE metadata->>'calibration_target_definition'=%s::text
                      AND metadata->>'calibration_target_matured'='true'
                  ) AS matured_rows,
                  count(*) FILTER (
                    WHERE metadata->>'calibration_target_definition'=%s::text
                      AND metadata->>'calibration_target_matured'='true'
                      AND (metadata->>'hit_reversion_within_3_sessions')::boolean=true
                  ) AS hits
                FROM or_signal_outcomes
                """,
                (TARGET_DEFINITION, TARGET_DEFINITION, TARGET_DEFINITION),
            )
            counts = dict(cur.fetchone() or {})
        conn.commit()
    return {
        "updated": updated,
        "target_rows": int(counts.get("target_rows") or 0),
        "matured_rows": int(counts.get("matured_rows") or 0),
        "hits": int(counts.get("hits") or 0),
    }


def patch_score_store(module: Any) -> None:
    if getattr(module, "_three_session_target_store_installed", False):
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
        evidence_snapshot_id, model_run_id = original(
            cur,
            candidate_id=candidate_id,
            scan_id=scan_id,
            item=item,
            score=score,
            evidence_cutoff=evidence_cutoff,
        )
        cur.execute(
            """
            UPDATE or_signal_outcomes
            SET metadata=COALESCE(metadata,'{}'::jsonb) || %s,updated_at=now()
            WHERE candidate_id=%s
            """,
            (
                Jsonb(
                    {
                        "calibration_target_definition": TARGET_DEFINITION,
                        "calibration_window_sessions": 3,
                        "target_contract_version": TARGET_CONTRACT_VERSION,
                        "calibration_target_matured": False,
                        "hit_reversion_within_3_sessions": None,
                        "calibration_exclusion": "pending_three_session_path_and_corporate_action_review",
                    }
                ),
                candidate_id,
            ),
        )
        return evidence_snapshot_id, model_run_id

    module.persist_original_score = persist_original_score
    module._three_session_target_store_installed = True


def patch_outcomes(module: Any) -> None:
    if getattr(module, "_three_session_target_reliability_installed", False):
        return
    original_capture = module.capture_signal_outcomes

    async def capture_signal_outcomes(limit: int = 500) -> dict[str, int]:
        before = await asyncio.to_thread(backfill_target_metadata)
        result = await original_capture(limit=limit)
        after = await asyncio.to_thread(backfill_target_metadata)
        result.update(
            {
                "three_session_target_rows": after["target_rows"],
                "three_session_target_matured": after["matured_rows"],
                "three_session_target_hits": after["hits"],
                "three_session_target_metadata_updated": before["updated"] + after["updated"],
            }
        )
        return result

    module.capture_signal_outcomes = capture_signal_outcomes
    module._three_session_target_reliability_installed = True


def patch_outcome_scheduler(module: Any) -> None:
    if getattr(module, "_three_session_outcome_bootstrap_installed", False):
        return
    original = module._run_oversold_outcomes

    async def run_core(stop_event: asyncio.Event) -> None:
        enabled = os.getenv("OVERSOLD_THREE_SESSION_BOOTSTRAP", "true").strip().lower() in {
            "1", "true", "yes", "on"
        }
        if enabled:
            try:
                metadata = await asyncio.to_thread(backfill_target_metadata)
                signal = await module.capture_signal_outcomes(limit=500)
                logger.info(
                    "Oversold three-session target bootstrap: metadata=%s signal=%s",
                    metadata,
                    signal,
                )
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Oversold three-session target bootstrap failed")
        await original(stop_event)

    module._run_oversold_outcomes = run_core
    module._three_session_outcome_bootstrap_installed = True
