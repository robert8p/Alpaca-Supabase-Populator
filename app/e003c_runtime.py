from __future__ import annotations

import hashlib
import json
import logging
import os
import socket
import uuid
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import psycopg
from psycopg.rows import dict_row
from psycopg.types.json import Jsonb

from app.config import get_settings
from app.db import connection, database_write_diagnostics
from app.e003c_live import (
    BAR_COUNT_LOG_CHANGE_MIN,
    DOLLAR_VOLUME_LOG_CHANGE_MIN,
    MIN_BASKET_NAMES,
    RANGE_LOG_CHANGE_MIN,
    RULE_VERSION,
)

logger = logging.getLogger(__name__)
NY = ZoneInfo("America/New_York")

RULE_SOURCE_GIT_SHA = "2019c4cb260816b672133154f76f65011c15ef73"
ENTRY_START = time(9, 30)
ENTRY_END = time(9, 35, 59)
EXIT_START = time(15, 54)
EXIT_END = time(15, 59, 59)
EXIT_FINALISE_NOT_BEFORE = time(15, 58, 30)
ALL_SESSION_SAFE_AT = time(20, 15)
WRITER_LOCK_NAME = f"{RULE_VERSION}:prospective-writer"

RULE_DEFINITION: dict[str, Any] = {
    "rule_version": RULE_VERSION,
    "timezone": "America/New_York",
    "signal_source": {
        "relation": "public.rd_daily_features",
        "timeframe": "1Min",
        "feed": "sip",
        "adjustment": "raw",
        "session_label": "all",
        "signal_date": "latest completed trade date before trade_date",
        "prior_date": "previous available trade date before signal_date",
    },
    "signal_filters": {
        "signal_open_gte": 5.0,
        "signal_close_gte": 5.0,
        "signal_return_pct_gte": 2.0,
        "signal_dollar_volume_gte": 1_000_000.0,
        "signal_bar_count_gte": 200,
        "signal_range_pct_gt": 0.0,
        "prior_range_pct_gt": 0.0,
        "signal_dollar_volume_gt": 0.0,
        "prior_dollar_volume_gt": 0.0,
        "prior_bar_count_gt": 0,
        "range_log_change_formula": "ln((signal_range_pct+0.01)/(prior_range_pct+0.01))",
        "range_log_change_gte": RANGE_LOG_CHANGE_MIN,
        "dollar_volume_log_change_formula": "ln((signal_dollar_volume+1)/(prior_dollar_volume+1))",
        "dollar_volume_log_change_gte": DOLLAR_VOLUME_LOG_CHANGE_MIN,
        "bar_count_log_change_formula": "ln((signal_bar_count+1)/(prior_bar_count+1))",
        "bar_count_log_change_gte": BAR_COUNT_LOG_CHANGE_MIN,
    },
    "entry": {
        "window_et": ["09:30:00", "09:35:59"],
        "require_shortable": True,
        "require_easy_to_borrow": True,
        "require_valid_bid_ask_mid": True,
        "entry_mid_gte": 5.0,
        "entry_proxy_price": "bid",
    },
    "basket": {
        "minimum_executable_names": MIN_BASKET_NAMES,
        "membership": "all executable names if minimum is met",
    },
    "exit": {
        "snapshot_window_et": ["15:54:00", "15:59:59"],
        "finalise_not_before_et": "15:58:30",
        "require_valid_bid_ask_mid": True,
        "exit_proxy_price": "ask",
    },
    "returns": {
        "gross_short_return_pct": "(entry_mid-exit_mid)/entry_mid*100",
        "net_short_return_pct": "(entry_bid-exit_ask)/entry_bid*100",
        "estimated_slippage_bp": 0.0,
        "assumed_cost_budget_bp": 25.0,
    },
}


def canonical_rule_json(definition: dict[str, Any] | None = None) -> str:
    return json.dumps(definition or RULE_DEFINITION, sort_keys=True, separators=(",", ":"), ensure_ascii=True)


RULE_HASH = hashlib.sha256(canonical_rule_json().encode("utf-8")).hexdigest()




def _json_safe(value: Any) -> Any:
    if isinstance(value, (datetime, date, time)):
        return value.isoformat()
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(item) for item in value]
    if isinstance(value, uuid.UUID):
        return str(value)
    return value

def _truthy(value: str | None) -> bool:
    return str(value or "").strip().lower() in {"1", "true", "yes", "on"}


def _parse_timestamp(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif isinstance(value, str) and value.strip():
        text = value.strip()
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None
    else:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=NY)
    return parsed.astimezone(NY)


@dataclass(frozen=True)
class RuntimeIdentity:
    owner_id: str
    service_id: str
    service_name: str
    service_type: str
    deployment_id: str | None
    instance_id: str
    git_sha: str
    git_branch: str
    repo_slug: str
    release_sha: str
    expected_branch: str | None
    expected_service_name: str
    expected_service_id: str | None

    @classmethod
    def from_environment(cls) -> "RuntimeIdentity":
        service_id = os.getenv("RENDER_SERVICE_ID", "local-service")
        instance_id = os.getenv("RENDER_INSTANCE_ID") or socket.gethostname()
        release_sha = os.getenv("E003C_RELEASE_SHA", "").strip()
        git_sha = os.getenv("RENDER_GIT_COMMIT", "").strip() or release_sha
        owner_id = os.getenv("E003C_OWNER_ID") or f"{service_id}:{instance_id}:{uuid.uuid4().hex}"
        return cls(
            owner_id=owner_id,
            service_id=service_id,
            service_name=os.getenv("RENDER_SERVICE_NAME", "e003c-prospective-capture"),
            service_type=os.getenv("RENDER_SERVICE_TYPE", "unknown"),
            deployment_id=(os.getenv("RENDER_DEPLOY_ID") or os.getenv("E003C_DEPLOYMENT_ID") or None),
            instance_id=instance_id,
            git_sha=git_sha,
            git_branch=os.getenv("RENDER_GIT_BRANCH", ""),
            repo_slug=os.getenv("RENDER_GIT_REPO_SLUG", ""),
            release_sha=release_sha,
            expected_branch=(os.getenv("E003C_EXPECTED_BRANCH") or None),
            expected_service_name=os.getenv("E003C_EXPECTED_SERVICE_NAME", "alpaca-e003c-prospective-worker"),
            expected_service_id=(os.getenv("E003C_EXPECTED_SERVICE_ID") or None),
        )


def release_pin_readiness(identity: RuntimeIdentity) -> dict[str, Any]:
    sha_is_full = len(identity.release_sha) == 40 and all(ch in "0123456789abcdef" for ch in identity.release_sha.lower())
    git_matches_release = bool(sha_is_full and identity.git_sha == identity.release_sha)
    branch_matches = identity.expected_branch is None or identity.git_branch == identity.expected_branch
    service_type_ok = identity.service_type in {"worker", "background_worker"}
    service_name_ok = identity.service_name == identity.expected_service_name
    service_id_ok = identity.expected_service_id is None or identity.service_id == identity.expected_service_id
    deployment_id_ok = bool(identity.deployment_id and identity.deployment_id.startswith("dep-"))
    repo_ok = identity.repo_slug == "robert8p/Alpaca-Supabase-Populator"
    return {
        "ok": bool(
            git_matches_release
            and branch_matches
            and service_type_ok
            and service_name_ok
            and service_id_ok
            and deployment_id_ok
            and repo_ok
        ),
        "release_sha": identity.release_sha,
        "git_sha": identity.git_sha,
        "git_matches_release": git_matches_release,
        "expected_branch": identity.expected_branch,
        "git_branch": identity.git_branch,
        "branch_matches": branch_matches,
        "service_type": identity.service_type,
        "service_type_ok": service_type_ok,
        "service_name": identity.service_name,
        "expected_service_name": identity.expected_service_name,
        "service_name_ok": service_name_ok,
        "service_id": identity.service_id,
        "expected_service_id": identity.expected_service_id,
        "service_id_ok": service_id_ok,
        "deployment_id": identity.deployment_id,
        "deployment_id_ok": deployment_id_ok,
        "repo_slug": identity.repo_slug,
        "repo_ok": repo_ok,
    }


def phase_state(now_et: datetime, provider_clock: dict[str, Any] | None = None) -> dict[str, Any]:
    current = now_et.astimezone(NY)
    current_time = current.timetz().replace(tzinfo=None)
    provider_clock = provider_clock or {}
    is_open = bool(provider_clock.get("is_open"))
    next_open = _parse_timestamp(provider_clock.get("next_open"))

    if is_open and ENTRY_START <= current_time <= ENTRY_END:
        phase = "entry_capture"
        next_phase = "intraday_wait"
        next_phase_at = datetime.combine(current.date(), time(9, 36), tzinfo=NY)
    elif is_open and ENTRY_END < current_time < EXIT_START:
        phase = "intraday_wait"
        next_phase = "exit_capture"
        next_phase_at = datetime.combine(current.date(), EXIT_START, tzinfo=NY)
    elif is_open and EXIT_START <= current_time <= EXIT_END:
        phase = "exit_capture"
        next_phase = "post_close"
        next_phase_at = datetime.combine(current.date(), time(16, 0), tzinfo=NY)
    elif current.weekday() < 5 and current_time >= ALL_SESSION_SAFE_AT:
        phase = "signal_maintenance"
        next_phase = "entry_capture"
        next_phase_at = next_open
    elif current.weekday() < 5 and current_time >= time(16, 0):
        phase = "post_close_wait"
        next_phase = "signal_maintenance"
        next_phase_at = datetime.combine(current.date(), ALL_SESSION_SAFE_AT, tzinfo=NY)
    elif next_open is not None and next_open.date() == current.date() and current < next_open:
        phase = "pre_market"
        next_phase = "entry_capture"
        next_phase_at = next_open
    else:
        phase = "market_closed"
        next_phase = "entry_capture"
        next_phase_at = next_open

    return {
        "current_phase": phase,
        "next_phase": next_phase,
        "next_phase_at": next_phase_at,
        "is_open": is_open,
        "now_et": current,
    }


def database_readiness() -> dict[str, Any]:
    diagnostics = database_write_diagnostics()
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT current_database() AS database_name,
                       current_user AS database_role,
                       to_regclass('research_control.e003c_rule_registry') IS NOT NULL AS rule_registry_ready,
                       to_regclass('research_control.e003c_runtime_instances') IS NOT NULL AS instance_registry_ready,
                       to_regclass('research_control.e003c_writer_lease') IS NOT NULL AS lease_registry_ready,
                       to_regclass('research_control.e003c_runtime_heartbeats') IS NOT NULL AS heartbeat_registry_ready
                """
            )
            row = dict(cur.fetchone())
        conn.rollback()
    objects_ready = all(
        bool(row[key])
        for key in ("rule_registry_ready", "instance_registry_ready", "lease_registry_ready", "heartbeat_registry_ready")
    )
    return {"ok": bool(diagnostics["writable"] and objects_ready), **diagnostics, **row}


def rule_registry_readiness() -> dict[str, Any]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT rule_version, rule_hash, rule_definition, source_git_sha, registered_at
                FROM research_control.e003c_rule_registry
                WHERE rule_version=%s
                """,
                (RULE_VERSION,),
            )
            row = cur.fetchone()
        conn.rollback()
    if not row:
        return {"ok": False, "reason": "rule_not_registered", "expected_rule_hash": RULE_HASH}
    definition = dict(row["rule_definition"])
    stored_definition_hash = hashlib.sha256(canonical_rule_json(definition).encode("utf-8")).hexdigest()
    return {
        "ok": bool(
            row["rule_hash"] == RULE_HASH
            and stored_definition_hash == RULE_HASH
            and row["source_git_sha"] == RULE_SOURCE_GIT_SHA
        ),
        "rule_version": row["rule_version"],
        "expected_rule_hash": RULE_HASH,
        "stored_rule_hash": row["rule_hash"],
        "stored_definition_hash": stored_definition_hash,
        "source_git_sha": row["source_git_sha"],
        "expected_source_git_sha": RULE_SOURCE_GIT_SHA,
        "registered_at": row["registered_at"],
    }


def freeze_readiness() -> dict[str, Any]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH latest AS (
                    SELECT signal_date, candidate_count, frozen_at, source_feature_max_refreshed_at
                    FROM ra_e003c_signal_freeze_days
                    WHERE rule_version=%s
                    ORDER BY signal_date DESC
                    LIMIT 1
                )
                SELECT l.signal_date, l.candidate_count, l.frozen_at,
                       l.source_feature_max_refreshed_at,
                       count(c.*)::integer AS candidate_rows,
                       md5(COALESCE(string_agg(
                           concat_ws('|', c.symbol, c.signal_open, c.signal_high, c.signal_low,
                                     c.signal_close, c.signal_return_pct, c.signal_range_pct,
                                     c.signal_dollar_volume, c.signal_bar_count, c.prior_range_pct,
                                     c.prior_dollar_volume, c.prior_bar_count, c.range_log_change,
                                     c.dollar_volume_log_change, c.bar_count_log_change),
                           E'\n' ORDER BY c.symbol
                       ), '')) AS candidate_set_md5
                FROM latest l
                LEFT JOIN ra_e003c_signal_freeze_candidates c
                  ON c.signal_date=l.signal_date AND c.rule_version=%s
                GROUP BY l.signal_date,l.candidate_count,l.frozen_at,l.source_feature_max_refreshed_at
                """,
                (RULE_VERSION, RULE_VERSION),
            )
            row = cur.fetchone()
        conn.rollback()
    if not row:
        return {"ok": False, "reason": "no_frozen_signal_day"}
    return {
        "ok": int(row["candidate_count"]) == int(row["candidate_rows"]),
        "signal_date": row["signal_date"],
        "expected_candidate_count": int(row["candidate_count"]),
        "candidate_rows": int(row["candidate_rows"]),
        "candidate_set_md5": row["candidate_set_md5"],
        "frozen_at": row["frozen_at"],
        "source_feature_max_refreshed_at": row["source_feature_max_refreshed_at"],
    }


def basket_readiness(now_et: datetime | None = None) -> dict[str, Any]:
    current = (now_et or datetime.now(tz=NY)).astimezone(NY)
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH latest AS (
                    SELECT *
                    FROM ra_e003c_live_days
                    WHERE rule_version=%s
                    ORDER BY trade_date DESC
                    LIMIT 1
                )
                SELECT l.trade_date,l.signal_date,l.signal_count,l.executable_count,l.basket_eligible,
                       count(c.*)::integer AS candidate_rows,
                       count(*) FILTER (WHERE c.executable)::integer AS executable_rows,
                       count(*) FILTER (WHERE c.included_in_basket)::integer AS included_rows,
                       count(*) FILTER (WHERE c.included_in_basket AND c.entry_observed_at IS NOT NULL)::integer AS included_entry_rows,
                       count(*) FILTER (WHERE c.included_in_basket AND c.exit_observed_at IS NOT NULL)::integer AS included_exit_rows,
                       count(*) FILTER (WHERE c.included_in_basket AND c.net_short_return_pct IS NOT NULL)::integer AS included_net_rows,
                       max(c.updated_at) AS candidate_last_updated_at
                FROM latest l
                LEFT JOIN ra_e003c_live_candidates c
                  ON c.trade_date=l.trade_date AND c.rule_version=%s
                GROUP BY l.trade_date,l.signal_date,l.signal_count,l.executable_count,l.basket_eligible
                """,
                (RULE_VERSION, RULE_VERSION),
            )
            row = cur.fetchone()
        conn.rollback()
    if not row:
        return {"ok": True, "reason": "no_live_observation_yet", "applicable": False}

    candidate_rows = int(row["candidate_rows"])
    executable_rows = int(row["executable_rows"])
    included_rows = int(row["included_rows"])
    expected_included = executable_rows if bool(row["basket_eligible"]) else 0
    count_consistent = (
        candidate_rows == int(row["signal_count"])
        and executable_rows == int(row["executable_count"])
        and included_rows == expected_included
    )
    completion_expected = row["trade_date"] < current.date() or (
        row["trade_date"] == current.date() and current.timetz().replace(tzinfo=None) >= time(16, 0)
    )
    completion_ok = True
    if completion_expected and included_rows:
        completion_ok = (
            int(row["included_entry_rows"]) == included_rows
            and int(row["included_exit_rows"]) == included_rows
            and int(row["included_net_rows"]) == included_rows
        )
    return {
        "ok": bool(count_consistent and completion_ok),
        "applicable": True,
        "trade_date": row["trade_date"],
        "signal_date": row["signal_date"],
        "signal_count": int(row["signal_count"]),
        "candidate_rows": candidate_rows,
        "executable_count": int(row["executable_count"]),
        "executable_rows": executable_rows,
        "basket_eligible": bool(row["basket_eligible"]),
        "included_rows": included_rows,
        "included_entry_rows": int(row["included_entry_rows"]),
        "included_exit_rows": int(row["included_exit_rows"]),
        "included_net_rows": int(row["included_net_rows"]),
        "count_consistent": count_consistent,
        "completion_expected": completion_expected,
        "completion_ok": completion_ok,
        "candidate_last_updated_at": row["candidate_last_updated_at"],
    }


def cutover_readiness(identity: RuntimeIdentity, *, require_authorized: bool) -> dict[str, Any]:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT status,baseline_checkpoint_job_id,baseline_checkpoint_event_id,
                       baseline_audit_hash,legacy_service_id,legacy_git_sha,
                       readiness_service_id,readiness_git_sha,readiness_verified_at,
                       legacy_capture_disabled_at,legacy_maintenance_disabled_at,
                       transfer_authorized_at,writer_service_id,writer_git_sha,writer_activated_at,
                       rollback_verified_at,updated_at
                FROM research_control.e003c_cutover_control
                WHERE rule_version=%s
                """,
                (RULE_VERSION,),
            )
            row = cur.fetchone()
        conn.rollback()
    if not row:
        return {"ok": False, "reason": "cutover_control_missing"}

    baseline_ok = (
        str(row["baseline_checkpoint_job_id"]) == os.getenv(
            "E003C_BASELINE_CHECKPOINT_JOB_ID", "9c19eea7-2401-481a-a9f3-1d75a75a07f6"
        )
        and int(row["baseline_checkpoint_event_id"])
        == int(os.getenv("E003C_BASELINE_CHECKPOINT_EVENT_ID", "275"))
        and row["baseline_audit_hash"]
        == os.getenv("E003C_BASELINE_AUDIT_HASH", "29e2168dd128e60ed7e454acce9b973b")
    )
    readiness_identity_ok = (
        row["readiness_service_id"] == identity.service_id
        and row["readiness_git_sha"] == identity.git_sha
        and row["readiness_verified_at"] is not None
    )
    legacy_disabled = (
        row["legacy_capture_disabled_at"] is not None
        and row["legacy_maintenance_disabled_at"] is not None
    )
    transfer_authorized = row["transfer_authorized_at"] is not None
    if require_authorized:
        ok = baseline_ok and readiness_identity_ok and legacy_disabled and transfer_authorized
    else:
        ok = baseline_ok and row["status"] in {
            "prepared",
            "readiness_verified",
            "legacy_disabled",
            "transfer_authorized",
            "writer_active",
            "writer_released",
            "rollback_verified",
        }
    return {
        "ok": bool(ok),
        "require_authorized": require_authorized,
        "status": row["status"],
        "baseline_ok": baseline_ok,
        "legacy_service_id": row["legacy_service_id"],
        "legacy_git_sha": row["legacy_git_sha"],
        "readiness_service_id": row["readiness_service_id"],
        "readiness_git_sha": row["readiness_git_sha"],
        "readiness_verified_at": row["readiness_verified_at"],
        "readiness_identity_ok": readiness_identity_ok,
        "legacy_capture_disabled_at": row["legacy_capture_disabled_at"],
        "legacy_maintenance_disabled_at": row["legacy_maintenance_disabled_at"],
        "legacy_disabled": legacy_disabled,
        "transfer_authorized_at": row["transfer_authorized_at"],
        "transfer_authorized": transfer_authorized,
        "writer_service_id": row["writer_service_id"],
        "writer_git_sha": row["writer_git_sha"],
        "writer_activated_at": row["writer_activated_at"],
        "rollback_verified_at": row["rollback_verified_at"],
        "updated_at": row["updated_at"],
    }


def baseline_checkpoint_readiness() -> dict[str, Any]:
    expected_job_id = os.getenv("E003C_BASELINE_CHECKPOINT_JOB_ID", "9c19eea7-2401-481a-a9f3-1d75a75a07f6")
    expected_event_id = int(os.getenv("E003C_BASELINE_CHECKPOINT_EVENT_ID", "275"))
    expected_hash = os.getenv("E003C_BASELINE_AUDIT_HASH", "29e2168dd128e60ed7e454acce9b973b")
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT j.status, j.result, e.event_type, e.details
                FROM ra_jobs j
                LEFT JOIN ra_job_events e ON e.id=%s AND e.job_id=j.id
                WHERE j.id=%s::uuid
                """,
                (expected_event_id, expected_job_id),
            )
            row = cur.fetchone()
        conn.rollback()
    if not row:
        return {"ok": False, "reason": "baseline_checkpoint_missing", "job_id": expected_job_id}
    result = dict(row["result"] or {})
    event_details = dict(row["details"] or {})
    return {
        "ok": bool(
            row["status"] == "completed"
            and result.get("audit_status") == "PASS"
            and result.get("audit_hash") == expected_hash
            and row["event_type"] == "e003c_post_close_audit_checkpoint"
            and event_details.get("audit_hash") == expected_hash
        ),
        "job_id": expected_job_id,
        "event_id": expected_event_id,
        "expected_audit_hash": expected_hash,
        "job_status": row["status"],
        "audit_status": result.get("audit_status"),
        "job_audit_hash": result.get("audit_hash"),
        "event_type": row["event_type"],
        "event_audit_hash": event_details.get("audit_hash"),
    }


def upsert_runtime_instance(
    identity: RuntimeIdentity,
    *,
    mode: str,
    writer_active: bool,
    phase: dict[str, Any],
    readiness: dict[str, Any],
    advisory_lock_key: int | None = None,
    advisory_backend_pid: int | None = None,
    checkpoint: dict[str, Any] | None = None,
    error: str | None = None,
    stopped: bool = False,
) -> None:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO research_control.e003c_runtime_instances(
                    owner_id,rule_version,service_id,service_name,service_type,deployment_id,
                    instance_id,git_sha,git_branch,repo_slug,release_sha,runtime_mode,
                    writer_active,advisory_lock_key,advisory_backend_pid,current_phase,
                    next_phase,next_phase_at,readiness,last_checkpoint,last_error,
                    started_at,heartbeat_at,stopped_at,updated_at
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    now(),now(),CASE WHEN %s THEN now() ELSE NULL END,now()
                )
                ON CONFLICT(owner_id) DO UPDATE SET
                    service_id=excluded.service_id,service_name=excluded.service_name,
                    service_type=excluded.service_type,
                    deployment_id=COALESCE(excluded.deployment_id,research_control.e003c_runtime_instances.deployment_id),
                    instance_id=excluded.instance_id,git_sha=excluded.git_sha,
                    git_branch=excluded.git_branch,repo_slug=excluded.repo_slug,
                    release_sha=excluded.release_sha,runtime_mode=excluded.runtime_mode,
                    writer_active=excluded.writer_active,
                    advisory_lock_key=excluded.advisory_lock_key,
                    advisory_backend_pid=excluded.advisory_backend_pid,
                    current_phase=excluded.current_phase,next_phase=excluded.next_phase,
                    next_phase_at=excluded.next_phase_at,readiness=excluded.readiness,
                    last_checkpoint=COALESCE(excluded.last_checkpoint,research_control.e003c_runtime_instances.last_checkpoint),
                    last_error=excluded.last_error,heartbeat_at=now(),
                    stopped_at=CASE WHEN %s THEN now() ELSE NULL END,updated_at=now()
                """,
                (
                    identity.owner_id,
                    RULE_VERSION,
                    identity.service_id,
                    identity.service_name,
                    identity.service_type,
                    identity.deployment_id,
                    identity.instance_id,
                    identity.git_sha,
                    identity.git_branch,
                    identity.repo_slug,
                    identity.release_sha,
                    mode,
                    writer_active,
                    advisory_lock_key,
                    advisory_backend_pid,
                    phase.get("current_phase"),
                    phase.get("next_phase"),
                    phase.get("next_phase_at"),
                    Jsonb(_json_safe(readiness)),
                    Jsonb(_json_safe(checkpoint)) if checkpoint is not None else None,
                    error,
                    stopped,
                    stopped,
                ),
            )
            cur.execute(
                """
                INSERT INTO research_control.e003c_runtime_heartbeats(
                    rule_version,owner_id,service_id,deployment_id,instance_id,git_sha,
                    runtime_mode,writer_active,advisory_lock_key,advisory_backend_pid,
                    current_phase,next_phase,next_phase_at,readiness,checkpoint,error,created_at
                ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,now())
                """,
                (
                    RULE_VERSION,
                    identity.owner_id,
                    identity.service_id,
                    identity.deployment_id,
                    identity.instance_id,
                    identity.git_sha,
                    mode,
                    writer_active,
                    advisory_lock_key,
                    advisory_backend_pid,
                    phase.get("current_phase"),
                    phase.get("next_phase"),
                    phase.get("next_phase_at"),
                    Jsonb(_json_safe(readiness)),
                    Jsonb(_json_safe(checkpoint)) if checkpoint is not None else None,
                    error,
                ),
            )
        conn.commit()


def try_acquire_writer_lease(
    identity: RuntimeIdentity,
    *,
    advisory_lock_key: int,
    advisory_backend_pid: int,
    ttl_seconds: int,
) -> bool:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT research_control.e003c_try_acquire_writer_lease(
                    %s,%s,%s,%s,%s,%s,%s,%s,%s
                ) AS acquired
                """,
                (
                    RULE_VERSION,
                    identity.owner_id,
                    identity.service_id,
                    identity.deployment_id,
                    identity.instance_id,
                    identity.git_sha,
                    advisory_lock_key,
                    advisory_backend_pid,
                    ttl_seconds,
                ),
            )
            row = cur.fetchone()
        conn.commit()
    return bool(row and row["acquired"])


def renew_writer_lease(identity: RuntimeIdentity, ttl_seconds: int) -> bool:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT research_control.e003c_renew_writer_lease(%s,%s,%s) AS renewed",
                (RULE_VERSION, identity.owner_id, ttl_seconds),
            )
            row = cur.fetchone()
        conn.commit()
    return bool(row and row["renewed"])


def release_writer_lease(identity: RuntimeIdentity, reason: str) -> bool:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT research_control.e003c_release_writer_lease(%s,%s,%s) AS released",
                (RULE_VERSION, identity.owner_id, reason),
            )
            row = cur.fetchone()
        conn.commit()
    return bool(row and row["released"])


def writer_lease_is_current(identity: RuntimeIdentity) -> bool:
    with connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT research_control.e003c_writer_lease_is_current(%s,%s) AS current",
                (RULE_VERSION, identity.owner_id),
            )
            row = cur.fetchone()
        conn.rollback()
    return bool(row and row["current"])


class AdvisoryWriterLock:
    def __init__(self) -> None:
        self._conn: psycopg.Connection | None = None
        self.lock_key: int | None = None
        self.backend_pid: int | None = None

    def acquire(self) -> bool:
        if self._conn is not None:
            raise RuntimeError("E003C advisory lock acquisition attempted twice")
        settings = get_settings()
        conn = psycopg.connect(
            settings.database_url,
            autocommit=True,
            row_factory=dict_row,
            application_name="e003c-prospective-writer-lock",
        )
        with conn.cursor() as cur:
            cur.execute("SELECT hashtextextended(%s,0) AS lock_key, pg_backend_pid() AS backend_pid", (WRITER_LOCK_NAME,))
            row = cur.fetchone()
            lock_key = int(row["lock_key"])
            backend_pid = int(row["backend_pid"])
            cur.execute("SELECT pg_try_advisory_lock(%s) AS acquired", (lock_key,))
            acquired = bool(cur.fetchone()["acquired"])
        if not acquired:
            conn.close()
            return False
        self._conn = conn
        self.lock_key = lock_key
        self.backend_pid = backend_pid
        return True

    def assert_held(self) -> None:
        if self._conn is None or self.lock_key is None or self.backend_pid is None:
            raise RuntimeError("E003C advisory writer lock is not held")
        try:
            with self._conn.cursor() as cur:
                cur.execute("SELECT pg_backend_pid() AS backend_pid")
                current_pid = int(cur.fetchone()["backend_pid"])
        except Exception as exc:  # pragma: no cover - network failure path
            raise RuntimeError("E003C advisory lock connection is unavailable") from exc
        if current_pid != self.backend_pid:
            raise RuntimeError("E003C advisory lock backend changed unexpectedly")

    def release(self) -> None:
        if self._conn is None:
            return
        try:
            if self.lock_key is not None:
                with self._conn.cursor() as cur:
                    cur.execute("SELECT pg_advisory_unlock(%s)", (self.lock_key,))
        finally:
            self._conn.close()
            self._conn = None
            self.lock_key = None
            self.backend_pid = None


def assert_writer_authority(identity: RuntimeIdentity, lock: AdvisoryWriterLock) -> None:
    lock.assert_held()
    if not writer_lease_is_current(identity):
        raise RuntimeError("E003C database writer lease is not current")


def critical_readiness_ok(readiness: dict[str, Any], *, require_provider: bool) -> bool:
    required = ["release_pin", "database", "rule_registry", "freeze", "basket", "baseline_checkpoint", "cutover"]
    if require_provider:
        required.append("provider")
    return all(bool((readiness.get(name) or {}).get("ok")) for name in required)
