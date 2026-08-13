-- E003C prospective-capture runtime isolation control plane.
-- This migration creates control metadata only. It does not modify E003C scientific evidence.

CREATE SCHEMA IF NOT EXISTS research_control;

CREATE TABLE IF NOT EXISTS research_control.e003c_rule_registry (
    rule_version text PRIMARY KEY,
    rule_hash text NOT NULL CHECK (rule_hash ~ '^[0-9a-f]{64}$'),
    rule_definition jsonb NOT NULL,
    source_git_sha text NOT NULL CHECK (source_git_sha ~ '^[0-9a-f]{40}$'),
    provenance jsonb NOT NULL DEFAULT '{}'::jsonb,
    registered_at timestamptz NOT NULL DEFAULT now(),
    registered_by text NOT NULL DEFAULT current_user
);

CREATE TABLE IF NOT EXISTS research_control.e003c_cutover_control (
    rule_version text PRIMARY KEY REFERENCES research_control.e003c_rule_registry(rule_version),
    status text NOT NULL DEFAULT 'prepared' CHECK (status IN (
        'prepared','readiness_verified','legacy_disabled','transfer_authorized',
        'writer_active','writer_released','rollback_verified'
    )),
    baseline_checkpoint_job_id uuid NOT NULL,
    baseline_checkpoint_event_id bigint NOT NULL,
    baseline_audit_hash text NOT NULL CHECK (baseline_audit_hash ~ '^[0-9a-f]{32}$'),
    legacy_service_id text NOT NULL,
    legacy_git_sha text NOT NULL CHECK (legacy_git_sha ~ '^[0-9a-f]{40}$'),
    readiness_service_id text,
    readiness_git_sha text CHECK (readiness_git_sha IS NULL OR readiness_git_sha ~ '^[0-9a-f]{40}$'),
    readiness_owner_id text,
    readiness_verified_at timestamptz,
    legacy_capture_disabled_at timestamptz,
    legacy_maintenance_disabled_at timestamptz,
    transfer_authorized_at timestamptz,
    writer_service_id text,
    writer_git_sha text CHECK (writer_git_sha IS NULL OR writer_git_sha ~ '^[0-9a-f]{40}$'),
    writer_owner_id text,
    writer_activated_at timestamptz,
    writer_released_at timestamptz,
    rollback_verified_at timestamptz,
    rollback_details jsonb,
    notes jsonb NOT NULL DEFAULT '{}'::jsonb,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS research_control.e003c_runtime_instances (
    owner_id text PRIMARY KEY,
    rule_version text NOT NULL REFERENCES research_control.e003c_rule_registry(rule_version),
    service_id text NOT NULL,
    service_name text NOT NULL,
    service_type text NOT NULL,
    deployment_id text,
    instance_id text NOT NULL,
    git_sha text NOT NULL CHECK (git_sha ~ '^[0-9a-f]{40}$'),
    git_branch text NOT NULL,
    repo_slug text NOT NULL,
    release_sha text NOT NULL CHECK (release_sha ~ '^[0-9a-f]{40}$'),
    runtime_mode text NOT NULL CHECK (runtime_mode IN ('readiness','writer','standby','stopped','legacy_shared')),
    writer_active boolean NOT NULL DEFAULT false,
    advisory_lock_key bigint,
    advisory_backend_pid integer,
    current_phase text,
    next_phase text,
    next_phase_at timestamptz,
    readiness jsonb NOT NULL DEFAULT '{}'::jsonb,
    last_checkpoint jsonb,
    last_error text,
    started_at timestamptz NOT NULL DEFAULT now(),
    heartbeat_at timestamptz NOT NULL DEFAULT now(),
    stopped_at timestamptz,
    updated_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS e003c_runtime_instances_rule_heartbeat_idx
    ON research_control.e003c_runtime_instances(rule_version, heartbeat_at DESC);
CREATE INDEX IF NOT EXISTS e003c_runtime_instances_writer_idx
    ON research_control.e003c_runtime_instances(rule_version, writer_active, heartbeat_at DESC);

CREATE TABLE IF NOT EXISTS research_control.e003c_writer_lease (
    rule_version text PRIMARY KEY REFERENCES research_control.e003c_rule_registry(rule_version),
    owner_id text NOT NULL REFERENCES research_control.e003c_runtime_instances(owner_id),
    service_id text NOT NULL,
    deployment_id text,
    instance_id text NOT NULL,
    git_sha text NOT NULL CHECK (git_sha ~ '^[0-9a-f]{40}$'),
    advisory_lock_key bigint NOT NULL,
    advisory_backend_pid integer NOT NULL,
    lease_epoch bigint NOT NULL DEFAULT 1,
    acquired_at timestamptz NOT NULL,
    renewed_at timestamptz NOT NULL,
    expires_at timestamptz NOT NULL,
    released_at timestamptz,
    release_reason text,
    updated_at timestamptz NOT NULL DEFAULT now(),
    CHECK (expires_at >= renewed_at)
);

CREATE TABLE IF NOT EXISTS research_control.e003c_runtime_heartbeats (
    id bigserial PRIMARY KEY,
    rule_version text NOT NULL REFERENCES research_control.e003c_rule_registry(rule_version),
    owner_id text NOT NULL,
    service_id text NOT NULL,
    deployment_id text,
    instance_id text NOT NULL,
    git_sha text NOT NULL CHECK (git_sha ~ '^[0-9a-f]{40}$'),
    runtime_mode text NOT NULL,
    writer_active boolean NOT NULL,
    advisory_lock_key bigint,
    advisory_backend_pid integer,
    current_phase text,
    next_phase text,
    next_phase_at timestamptz,
    readiness jsonb NOT NULL DEFAULT '{}'::jsonb,
    checkpoint jsonb,
    error text,
    created_at timestamptz NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS e003c_runtime_heartbeats_rule_created_idx
    ON research_control.e003c_runtime_heartbeats(rule_version, created_at DESC);
CREATE INDEX IF NOT EXISTS e003c_runtime_heartbeats_owner_created_idx
    ON research_control.e003c_runtime_heartbeats(owner_id, created_at DESC);

CREATE OR REPLACE FUNCTION research_control.e003c_reject_immutable_change()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, research_control
AS $$
BEGIN
    RAISE EXCEPTION '% is append-only/immutable; % is not permitted', TG_TABLE_SCHEMA || '.' || TG_TABLE_NAME, TG_OP
        USING ERRCODE = '55000';
END;
$$;

DROP TRIGGER IF EXISTS e003c_rule_registry_immutable ON research_control.e003c_rule_registry;
CREATE TRIGGER e003c_rule_registry_immutable
BEFORE UPDATE OR DELETE ON research_control.e003c_rule_registry
FOR EACH ROW EXECUTE FUNCTION research_control.e003c_reject_immutable_change();

DROP TRIGGGER IF EXISTS e003c_runtime_heartbeats_append_only ON research_control.e003c_runtime_heartbeats;
CREATE TRIGGER e003c_runtime_heartbeats_append_only
BEFORE UPDATE OR DELETE ON research_control.e003c_runtime_heartbeats
FOR EACH ROW EXECUTE FUNCTION research_control.e003c_reject_immutable_change();

CREATE OR REPLACE FUNCTION research_control.e003c_set_updated_at()
RETURNS trigger
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, research_control
AS $$
BEGIN
    NEW.updated_at := clock_timestamp();
    RETURN NEW;
END;
$$;

DROP TRIGGGER IF EXISTS e003c_cutover_control_updated_at ON research_control.e003c_cutover_control;
CREATE TRIGGER e003c_cutover_control_updated_at
BEFORE UPDATE ON research_control.e003c_cutover_control
FOR EACH ROW EXECUTE FUNCTION research_control.e003c_set_updated_at();

DROP TRIGGGER IF EXISTS e003c_runtime_instances_updated_at ON research_control.e003c_runtime_instances;
CREATE TRIGGER e003c_runtime_instances_updated_at
BEFORE UPDATE ON research_control.e003c_runtime_instances
FOR EACH ROW EXECUTE FUNCTION research_control.e003c_set_updated_at();

DROP TRIGGER IF EXISTS e003c_writer_lease_updated_at ON research_control.e003c_writer_lease;
CREATE TRIGGER e003c_writer_lease_updated_at
BEFORE UPDATE ON research_control.e003c_writer_lease
FOR EACH ROW EXECUTE FUNCTION research_control.e003c_set_updated_at();

CREATE OR REPLACE FUNCTION research_control.e003c_try_acquire_writer_lease(
    p_rule_version text,
    p_owner_id text,
    p_service_id text,
    p_deployment_id text,
    p_instance_id text,
    p_git_sha text,
    p_advisory_lock_key bigint,
    p_advisory_backend_pid integer,
    p_ttl_seconds integer
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, research_control
AS $$
DECLARE
    v_now timestamptz := clock_timestamp();
    v_acquired boolean := false;
BEGIN
    IF p_ttl_seconds < 60 OR p_ttl_seconds > 300 THEN
        RAISE EXCEPTION 'E003C lease TTL must be between 60 and 300 seconds';
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM e003c_cutover_control c
        WHERE c.rule_version = p_rule_version
          AND c.readiness_service_id = p_service_id
          AND c.readiness_git_sha = p_git_sha
          AND c.readiness_verified_at IS NOT NULL
          AND c.legacy_capture_disabled_at IS NOT NULL
          AND c.legacy_maintenance_disabled_at IS NOT NULL
          AND c.transfer_authorized_at IS NOT NULL
    ) THEN
        RETURN false;
    END IF;

    INSERT INTO e003c_writer_lease(
        rule_version, owner_id, service_id, deployment_id, instance_id, git_sha,
        advisory_lock_key, advisory_backend_pid, lease_epoch,
        acquired_at, renewed_at, expires_at, released_at, release_reason, updated_at
    ) VALUES (
        p_rule_version, p_owner_id, p_service_id, p_deployment_id, p_instance_id, p_git_sha,
        p_advisory_lock_key, p_advisory_backend_pid, 1,
        v_now, v_now, v_now + make_interval(secs => p_ttl_seconds), NULL, NULL, v_now
    )
    ON CONFLICT(rule_version) DO UPDATE SET
        owner_id = EXCLUDED.owner_id,
        service_id = EXCLUDED.service_id,
        deployment_id = EXCLUDED.deployment_id,
        instance_id = EXCLUDED.instance_id,
        git_sha = EXCLUDED.git_sha,
        advisory_lock_key = EXCLUDED.advisory_lock_key,
        advisory_backend_pid = EXCLUDED.advisory_backend_pid,
        lease_epoch = e003c_writer_lease.lease_epoch +
            CASE WHEN e003c_writer_lease.owner_id = EXCLUDED.owner_id THEN 0 ELSE 1 END,
        acquired_at = CASE
            WHEN e003c_writer_lease.owner_id = EXCLUDED.owner_id
             AND e003c_writer_lease.released_at IS NULL
             AND e003c_writer_lease.expires_at > v_now
            THEN e003c_writer_lease.acquired_at
            ELSE v_now
        END,
        renewed_at = v_now,
        expires_at = v_now + make_interval(secs => p_ttl_seconds),
        released_at = NULL,
        release_reason = NULL,
        updated_at = v_now
    WHERE e003c_writer_lease.owner_id = EXCLUDED.owner_id
       OR e003c_writer_lease.released_at IS NOT NULL
       OR e003c_writer_lease.expires_at <= v_now
    RETURNING true INTO v_acquired;

    IF COALESCE(v_acquired, false) THEN
        UPDATE e003c_runtime_instances
        SET writer_active = false,
            last_error = CASE
                WHEN owner_id <> p_owner_id THEN 'Writer lease superseded after release or expiry.'
                ELSE last_error
            END,
            updated_at = v_now
        WHERE rule_version = p_rule_version
          AND owner_id <> p_owner_id
          AND writer_active = true;

        UPDATE e003c_cutover_control
        SET status = 'writer_active',
            writer_service_id = p_service_id,
            writer_git_sha = p_git_sha,
            writer_owner_id = p_owner_id,
            writer_activated_at = COALESCE(writer_activated_at, v_now),
            writer_released_at = NULL
        WHERE rule_version = p_rule_version;
    END IF;

    RETURN COALESCE(v_acquired, false);
END;
$$;

CREATE OR REPLACE FUNCTION research_control.e003c_renew_writer_lease(
    p_rule_version text,
    p_owner_id text,
    p_ttl_seconds integer
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, research_control
AS $$
DECLARE
    v_now timestamptz := clock_timestamp();
    v_rows integer;
BEGIN
    IF p_ttl_seconds < 60 OR p_ttl_seconds > 300 THEN
        RAISE EXCEPTION 'E003C lease TTL must be between 60 and 300 seconds';
    END IF;

    UPDATE e003c_writer_lease
    SET renewed_at = v_now,
        expires_at = v_now + make_interval(secs => p_ttl_seconds),
        updated_at = v_now
    WHERE rule_version = p_rule_version
      AND owner_id = p_owner_id
      AND released_at IS NULL
      AND expires_at > v_now;
    GET DIAGNOSTICS v_rows = ROW_COUNT;
    RETURN v_rows = 1;
END;
$$;

CREATE OR REPLACE FUNCTION research_control.e003c_release_writer_lease(
    p_rule_version text,
    p_owner_id text,
    p_reason text
)
RETURNS boolean
LANGUAGE plpgsql
SECURITY INVOKER
SET search_path = pg_catalog, research_control
AS $$
DECLARE
    v_now timestamptz := clock_timestamp();
    v_rows integer;
BEGIN
    UPDATE e003c_writer_lease
    SET renewed_at = v_now,
        expires_at = v_now,
        released_at = v_now,
        release_reason = left(COALESCE(p_reason, 'released'), 500),
        updated_at = v_now
    WHERE rule_version = p_rule_version
      AND owner_id = p_owner_id
      AND released_at IS NULL;
    GET DIAGNOSTICS v_rows = ROW_COUNT;

    IF v_rows = 1 THEN
        UPDATE e003c_runtime_instances
        SET writer_active = false,
            updated_at = v_now
        WHERE owner_id = p_owner_id;

        UPDATE e003c_cutover_control
        SET status = 'writer_released',
            writer_released_at = v_now
        WHERE rule_version = p_rule_version
          AND writer_owner_id = p_owner_id;
    END IF;

    RETURN v_rows = 1;
END;
$$;

CREATE OR REPLACE FUNCTION research_control.e003c_writer_lease_is_current(
    p_rule_version text,
    p_owner_id text
)
RETURNS boolean
LANGUAGE sql
STABLE
SECURITY INVOKER
SET search_path = pg_catalog, research_control
AS $$
    SELECT EXISTS (
        SELECT 1
        FROM e003c_writer_lease
        WHERE rule_version = p_rule_version
          AND owner_id = p_owner_id
          AND released_at IS NULL
          AND expires_at > now()
    );
$$;

CREATE OR REPLACE VIEW research_control.e003c_runtime_authority_v1
WITH (security_invoker = true)
AS
SELECT
    c.rule_version,
    c.status AS cutover_status,
    c.baseline_checkpoint_job_id,
    c.baseline_checkpoint_event_id,
    c.baseline_audit_hash,
    c.legacy_service_id,
    c.legacy_git_sha,
    c.readiness_service_id,
    c.readiness_git_sha,
    c.readiness_owner_id,
    c.readiness_verified_at,
    c.legacy_capture_disabled_at,
    c.legacy_maintenance_disabled_at,
    c.transfer_authorized_at,
    c.writer_service_id,
    c.writer_git_sha,
    c.writer_owner_id,
    c.writer_activated_at,
    c.writer_released_at,
    c.rollback_verified_at,
    l.owner_id AS lease_owner_id,
    l.service_id AS lease_service_id,
    l.deployment_id AS lease_deployment_id,
    l.instance_id AS lease_instance_id,
    l.git_sha AS lease_git_sha,
    l.advisory_lock_key,
    l.advisory_backend_pid,
    l.lease_epoch,
    l.acquired_at,
    l.renewed_at,
    l.expires_at,
    l.released_at,
    l.release_reason,
    (l.owner_id IS NOT NULL AND l.released_at IS NULL AND l.expires_at > clock_timestamp()) AS lease_current,
    r.service_name AS runtime_service_name,
    r.service_type AS runtime_service_type,
    r.git_branch AS runtime_git_branch,
    r.repo_slug AS runtime_repo_slug,
    r.release_sha AS runtime_release_sha,
    r.runtime_mode,
    r.writer_active,
    r.current_phase,
    r.next_phase,
    r.next_phase_at,
    r.readiness,
    r.last_checkpoint,
    r.last_error,
    r.heartbeat_at,
    r.stopped_at,
    CASE WHEN r.heartbeat_at IS NULL THEN NULL ELSE clock_timestamp() - r.heartbeat_at END AS heartbeat_age
FROM research_control.e003c_cutover_control c
LEFT JOIN research_control.e003c_writer_lease l USING(rule_version)
LEFT JOIN LATERAL (
    SELECT ri.*
    FROM research_control.e003c_runtime_instances ri
    WHERE ri.rule_version = c.rule_version
    ORDER BY
        CASE WHEN l.owner_id IS NOT NULL AND ri.owner_id = l.owner_id THEN 0 ELSE 1 END,
        ri.heartbeat_at DESC
    LIMIT 1
) r ON true;

ALTER TABLE research_control.e003c_rule_registry ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_control.e003c_cutover_control ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_control.e003c_runtime_instances ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_control.e003c_writer_lease ENABLE ROW LEVEL SECURITY;
ALTER TABLE research_control.e003c_runtime_heartbeats ENABLE ROW LEVEL SECURITY;

REVOKE ALL ON TABLE research_control.e003c_rule_registry FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE research_control.e003c_cutover_control FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE research_control.e003c_runtime_instances FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE research_control.e003c_writer_lease FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE research_control.e003c_runtime_heartbeats FROM PUBLIC, anon, authenticated;
REVOKE ALL ON TABLE research_control.e003c_runtime_authority_v1 FROM PUBLIC, anon, authenticated;
REVOKE ALL ON SEQUENCE research_control.e003c_runtime_heartbeats_id_seq FROM PUBLIC, anon, authenticated;

REVOKE EXECUTE ON FUNCTION research_control.e003c_reject_immutable_change() FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION research_control.e003c_set_updated_at() FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION research_control.e003c_try_acquire_writer_lease(text,text,text,text,text,text,bigint,integer,integer) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION research_control.e003c_renew_writer_lease(text,text,integer) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION research_control.e003c_release_writer_lease(text,text,text) FROM PUBLIC, anon, authenticated;
REVOKE EXECUTE ON FUNCTION research_control.e003c_writer_lease_is_current(text,text) FROM PUBLIC, anon, authenticated;

GRANT USAGE ON SCHEMA research_control TO service_role;
GRANT SELECT ON TABLE research_control.e003c_rule_registry TO service_role;
GRANT SELECT, INSERT, UPDATE ON TABLE research_control.e003c_cutover_control TO service_role;
GRANT SELECT, INSERT, UPDATE ON TABLE research_control.e003c_runtime_instances TO service_role;
GRANT SELECT, INSERT, UPDATE ON TABLE research_control.e003c_writer_lease TO service_role;
GRANT SELECT, INSERT ON TABLE research_control.e003c_runtime_heartbeats TO service_role;
GRANT SELECT ON TABLE research_control.e003c_runtime_authority_v1 TO service_role;
GRANT USAGE, SELECT ON SEQUENCE research_control.e003c_runtime_heartbeats_id_seq TO service_role;
GRANT EXECUTE ON FUNCTION research_control.e003c_try_acquire_writer_lease(text,text,text,text,text,text,bigint,integer,integer) TO service_role;
GRANT EXECUTE ON FUNCTION research_control.e003c_renew_writer_lease(text,text,integer) TO service_role;
GRANT EXECUTE ON FUNCTION research_control.e003c_release_writer_lease(text,text,text) TO service_role;
GRANT EXECUTE ON FUNCTION research_control.e003c_writer_lease_is_current(text,text) TO service_role;

INSERT INTO research_control.e003c_rule_registry(
    rule_version, rule_hash, rule_definition, source_git_sha, provenance
) VALUES (
    'E003C_v1',
    '4bcd161f68c824365d8a0f0dda47a78ea8f410a04dfe0250c36e142c472e2562',
    '{"basket":{"membership":"all executable names if minimum is met","minimum_executable_names":6},"entry":{"entry_mid_gte":5.0,"entry_proxy_price":"bid","require_easy_to_borrow":true,"require_shortable":true,"require_valid_bid_ask_mid":true,"window_et":["09:30:00","09:35:59"]},"exit":{"exit_proxy_price":"ask","finalise_not_before_et":"15:58:30","require_valid_bid_ask_mid":true,"snapshot_window_et":["15:54:00","15:59:59"]},"returns":{"assumed_cost_budget_bp":25.0,"estimated_slippage_bp":0.0,"gross_short_return_pct":"(entry_mid-exit_mid)/entry_mid*100","net_short_return_pct":"(entry_bid-exit_ask)/entry_bid*100"},"rule_version":"E003C_v1","signal_filters":{"bar_count_log_change_formula":"ln((signal_bar_count+1)/(prior_bar_count+1))","bar_count_log_change_gte":0.23375466939777,"dollar_volume_log_change_formula":"ln((signal_dollar_volume+1)/(prior_dollar_volume+1))","dollar_volume_log_change_gte":0.652913500220726,"prior_bar_count_gt":0,"prior_dollar_volume_gt":0.0,"prior_range_pct_gt":0.0,"range_log_change_formula":"ln((signal_range_pct+0.01)/(prior_range_pct+0.01))","range_log_change_gte":0.785659891999253,"signal_bar_count_gte":200,"signal_close_gte":5.0,"signal_dollar_volume_gt":0.0,"signal_dollar_volume_gte":1000000.0,"signal_open_gte":5.0,"signal_range_pct_gt":0.0,"signal_return_pct_gte":2.0},"signal_source":{"adjustment":"raw","feed":"sip","prior_date":"previous available trade date before signal_date","relation":"public.rd_daily_features","session_label":"all","signal_date":"latest completed trade date before trade_date","timeframe":"1Min"},"timezone":"America/New_York"}'::jsonb,
    '2019c4cb260816b672133154f76f65011c15ef73',
    jsonb_build_object(
        'programme','5.6 Investing cleanroom',
        'purpose','Prospective E003C runtime isolation control',
        'baseline_trade_date','2026-08-13',
        'baseline_signal_date','2026-08-12',
        'baseline_checkpoint_job_id','9c19eea7-2401-481a-a9f3-1d75a75a07f6',
        'baseline_checkpoint_event_id',275,
        'baseline_audit_hash','29e2168dd128e60ed7e454acce9b973b',
        'scientific_evidence_mutated',false
    )
)
ON CONFLICT(rule_version) DO NOTHING;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM research_control.e003c_rule_registry
        WHERE rule_version='E003C_v1'
          AND rule_hash='4bcd161f68c824365d8a0f0dda47a78ea8f410a04dfe0250c36e142c472e2562'
          AND source_git_sha='2019c4cb260816b672133154f76f65011c15ef73'
          AND rule_definition->>'rule_version'='E003C_v1'
    ) THEN
        RAISE EXCEPTION 'Existing E003C_v1 rule registry row does not match the frozen release';
    END IF;
END;
$$;
INSERT INTO research_control.e003c_cutover_control(
    rule_version,status,baseline_checkpoint_job_id,baseline_checkpoint_event_id,
    baseline_audit_hash,legacy_service_id,legacy_git_sha,notes
) VALUES (
    'E003C_v1','prepared','9c19eea7-2401-481a-a9f3-1d75a75a07f6'::uuid,275,
    '29e2168dd128e60ed7e454acce9b973b',
    'srv-d9p2vljncjis73evkocg',
    '2019c4cb260816b672133154f76f65011c15ef73',
    jsonb_build_object(
        'legacy_service_name','alpaca-rapid-discovery-worker',
        'baseline_render_instance_id','srv-d9p2vljncjis73evkocg-9kf7q',
        'baseline_checkpoint_passed_at','2026-08-13T20:21:17.815087Z',
        'runtime_change_freeze_released_by','Mission Control',
        'scientific_evidence_mutated',false
    )
)
ON CONFLICT(rule_version) DO NOTHING;
