-- Oversold Reversion scoring v2: additive, append-only evidence/model history.
CREATE TABLE IF NOT EXISTS or_evidence_snapshots (
    id bigserial PRIMARY KEY,
    candidate_id bigint NOT NULL REFERENCES or_candidates(id) ON DELETE RESTRICT,
    scan_id uuid NOT NULL REFERENCES or_scans(id) ON DELETE RESTRICT,
    symbol text NOT NULL,
    company_name text,
    signal_timestamp timestamptz NOT NULL,
    evidence_cutoff timestamptz NOT NULL,
    signal_price double precision NOT NULL CHECK (signal_price > 0),
    sector_hint text NOT NULL DEFAULT 'unknown',
    market_data jsonb NOT NULL DEFAULT '{}'::jsonb,
    technical_inputs jsonb NOT NULL DEFAULT '{}'::jsonb,
    news_items jsonb NOT NULL DEFAULT '[]'::jsonb,
    filing_refs jsonb NOT NULL DEFAULT '[]'::jsonb,
    analyst_events jsonb NOT NULL DEFAULT '[]'::jsonb,
    source_quality jsonb NOT NULL DEFAULT '{}'::jsonb,
    snapshot_hash text NOT NULL,
    snapshot_kind text NOT NULL DEFAULT 'original' CHECK (snapshot_kind IN ('original','research_reconstruction')),
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(candidate_id, snapshot_kind, evidence_cutoff)
);
CREATE INDEX IF NOT EXISTS or_evidence_snapshots_candidate_idx ON or_evidence_snapshots(candidate_id, created_at DESC);
CREATE INDEX IF NOT EXISTS or_evidence_snapshots_symbol_idx ON or_evidence_snapshots(symbol, signal_timestamp DESC);

CREATE TABLE IF NOT EXISTS or_model_runs (
    id bigserial PRIMARY KEY,
    candidate_id bigint NOT NULL REFERENCES or_candidates(id) ON DELETE RESTRICT,
    evidence_snapshot_id bigint NOT NULL REFERENCES or_evidence_snapshots(id) ON DELETE RESTRICT,
    run_kind text NOT NULL DEFAULT 'original' CHECK (run_kind IN ('original','rescore','research_backfill')),
    scoring_model_version text NOT NULL,
    scoring_config_version text NOT NULL,
    catalyst_prompt_version text NOT NULL,
    catalyst_schema_version text NOT NULL,
    calibration_model_version text,
    model_status text NOT NULL DEFAULT 'uncalibrated' CHECK (model_status IN ('uncalibrated','calibrated')),
    target_definition text NOT NULL DEFAULT 'hit_plus_5pct_within_6_weeks',
    setup_score double precision CHECK (setup_score BETWEEN 0 AND 100),
    catalyst_score double precision CHECK (catalyst_score BETWEEN 0 AND 100),
    resilience_score double precision CHECK (resilience_score BETWEEN 0 AND 100),
    confirmation_score double precision CHECK (confirmation_score BETWEEN 0 AND 100),
    damage_risk double precision CHECK (damage_risk BETWEEN 0 AND 100),
    evidence_confidence double precision CHECK (evidence_confidence BETWEEN 0 AND 100),
    core_score double precision CHECK (core_score BETWEEN 0 AND 100),
    confidence_adjusted_score double precision CHECK (confidence_adjusted_score BETWEEN 0 AND 100),
    damage_penalty double precision NOT NULL DEFAULT 0 CHECK (damage_penalty BETWEEN 0 AND 100),
    damage_cap double precision NOT NULL DEFAULT 100 CHECK (damage_cap BETWEEN 0 AND 100),
    final_score double precision NOT NULL CHECK (final_score BETWEEN 0 AND 100),
    calibrated_probability double precision CHECK (calibrated_probability BETWEEN 0 AND 1),
    verdict text NOT NULL CHECK (verdict IN ('INVESTIGATE','WATCH','PASS')),
    hard_veto boolean NOT NULL DEFAULT false,
    hard_veto_reason text,
    missing_inputs jsonb NOT NULL DEFAULT '[]'::jsonb,
    catalyst_analysis jsonb NOT NULL DEFAULT '{}'::jsonb,
    calculation_trace jsonb NOT NULL DEFAULT '{}'::jsonb,
    explanation text,
    created_at timestamptz NOT NULL DEFAULT now(),
    UNIQUE(candidate_id, evidence_snapshot_id, run_kind, scoring_model_version, scoring_config_version)
);
CREATE INDEX IF NOT EXISTS or_model_runs_candidate_idx ON or_model_runs(candidate_id, created_at DESC);
CREATE INDEX IF NOT EXISTS or_model_runs_score_idx ON or_model_runs(final_score DESC, created_at DESC);
CREATE INDEX IF NOT EXISTS or_model_runs_version_idx ON or_model_runs(scoring_model_version, scoring_config_version, created_at DESC);

CREATE TABLE IF NOT EXISTS or_signal_outcomes (
    id bigserial PRIMARY KEY,
    candidate_id bigint NOT NULL UNIQUE REFERENCES or_candidates(id) ON DELETE RESTRICT,
    evidence_snapshot_id bigint REFERENCES or_evidence_snapshots(id) ON DELETE RESTRICT,
    model_run_id bigint REFERENCES or_model_runs(id) ON DELETE RESTRICT,
    symbol text NOT NULL,
    signal_timestamp timestamptz NOT NULL,
    signal_price double precision NOT NULL CHECK (signal_price > 0),
    horizon_deadline timestamptz NOT NULL,
    return_1d double precision,
    return_3d double precision,
    return_1w double precision,
    return_2w double precision,
    return_4w double precision,
    return_6w double precision,
    mfe_6w double precision,
    mae_6w double precision,
    hit_plus_5pct_within_6_weeks boolean,
    first_plus_5_ts timestamptz,
    trading_days_to_plus_5 integer,
    hours_to_plus_5 double precision,
    minus_5_before_plus_5 boolean,
    minus_10_before_plus_5 boolean,
    minus_20_before_plus_5 boolean,
    corporate_action_status text NOT NULL DEFAULT 'unchecked' CHECK (corporate_action_status IN ('unchecked','clear','affected','review_error')),
    trading_status text NOT NULL DEFAULT 'normal',
    outcome_resolution text NOT NULL DEFAULT '1Day',
    eligible_for_calibration boolean NOT NULL DEFAULT false,
    status text NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','matured','error','excluded')),
    error text,
    metadata jsonb NOT NULL DEFAULT '{}'::jsonb,
    last_evaluated_at timestamptz,
    created_at timestamptz NOT NULL DEFAULT now(),
    updated_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS or_signal_outcomes_status_idx ON or_signal_outcomes(status, horizon_deadline, candidate_id);
CREATE INDEX IF NOT EXISTS or_signal_outcomes_symbol_idx ON or_signal_outcomes(symbol, signal_timestamp DESC);

CREATE TABLE IF NOT EXISTS or_calibration_runs (
    id bigserial PRIMARY KEY,
    calibration_model_version text NOT NULL,
    scoring_model_version text NOT NULL,
    scoring_config_version text NOT NULL,
    training_cutoff timestamptz NOT NULL,
    temporal_holdout_start timestamptz,
    temporal_holdout_end timestamptz,
    matured_count integer NOT NULL DEFAULT 0,
    positive_count integer NOT NULL DEFAULT 0,
    negative_count integer NOT NULL DEFAULT 0,
    brier_score double precision,
    base_rate_brier double precision,
    brier_skill double precision,
    calibration_error double precision,
    metrics jsonb NOT NULL DEFAULT '{}'::jsonb,
    quality_checks jsonb NOT NULL DEFAULT '{}'::jsonb,
    passed boolean NOT NULL DEFAULT false,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS or_calibration_runs_created_idx ON or_calibration_runs(created_at DESC);

CREATE OR REPLACE FUNCTION or_reject_immutable_mutation()
RETURNS trigger
LANGUAGE plpgsql
SET search_path = ''
AS $$
BEGIN
    RAISE EXCEPTION '% is append-only and immutable', TG_TABLE_NAME;
END;
$$;

DROP TRIGGER IF EXISTS or_evidence_snapshots_immutable ON or_evidence_snapshots;
CREATE TRIGGER or_evidence_snapshots_immutable
BEFORE UPDATE OR DELETE ON or_evidence_snapshots
FOR EACH ROW EXECUTE FUNCTION or_reject_immutable_mutation();

DROP TRIGGER IF EXISTS or_model_runs_immutable ON or_model_runs;
CREATE TRIGGER or_model_runs_immutable
BEFORE UPDATE OR DELETE ON or_model_runs
FOR EACH ROW EXECUTE FUNCTION or_reject_immutable_mutation();

DROP TRIGGER IF EXISTS or_calibration_runs_immutable ON or_calibration_runs;
CREATE TRIGGER or_calibration_runs_immutable
BEFORE UPDATE OR DELETE ON or_calibration_runs
FOR EACH ROW EXECUTE FUNCTION or_reject_immutable_mutation();

ALTER TABLE or_evidence_snapshots ENABLE ROW LEVEL SECURITY;
ALTER TABLE or_model_runs ENABLE ROW LEVEL SECURITY;
ALTER TABLE or_signal_outcomes ENABLE ROW LEVEL SECURITY;
ALTER TABLE or_calibration_runs ENABLE ROW LEVEL SECURITY;
