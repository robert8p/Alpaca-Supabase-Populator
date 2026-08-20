-- Applied to the Rapid Discovery worker database for reliability v3.
-- Browser roles retain no direct table access; the Edge Function uses service_role.

CREATE TABLE IF NOT EXISTS public.ip_model_audits (
    model_version text PRIMARY KEY,
    active boolean NOT NULL DEFAULT false,
    status text NOT NULL CHECK (status IN ('RESEARCH_ONLY','VALIDATED','REJECTED')),
    audit_completed_at timestamptz NOT NULL,
    discovery_start date NOT NULL,
    discovery_end date NOT NULL,
    validation_start date NOT NULL,
    validation_end date NOT NULL,
    internal_test_start date,
    internal_test_end date,
    holdout_start date NOT NULL,
    holdout_end date NOT NULL,
    discovery_states bigint NOT NULL CHECK (discovery_states >= 0),
    validation_states bigint NOT NULL CHECK (validation_states >= 0),
    internal_test_states bigint NOT NULL CHECK (internal_test_states >= 0),
    holdout_states bigint NOT NULL CHECK (holdout_states >= 0),
    registered_robust_candidates integer NOT NULL CHECK (registered_robust_candidates >= 0),
    robust_candidates_passed integer NOT NULL CHECK (robust_candidates_passed >= 0),
    large_sample_generic_rules_passed integer NOT NULL CHECK (large_sample_generic_rules_passed >= 0),
    findings jsonb NOT NULL DEFAULT '{}'::jsonb,
    summary text NOT NULL,
    created_at timestamptz NOT NULL DEFAULT now()
);
CREATE UNIQUE INDEX IF NOT EXISTS ip_model_audits_one_active_idx
    ON public.ip_model_audits ((1)) WHERE active;
ALTER TABLE public.ip_model_audits ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.ip_model_audits FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE public.ip_model_audits TO service_role;

ALTER TABLE public.ip_selected_candidates
    ADD COLUMN IF NOT EXISTS user_selected boolean NOT NULL DEFAULT true,
    ADD COLUMN IF NOT EXISTS user_selected_at timestamptz,
    ADD COLUMN IF NOT EXISTS auto_enrolled_at timestamptz,
    ADD COLUMN IF NOT EXISTS horizon_end_at timestamptz,
    ADD COLUMN IF NOT EXISTS entry_price double precision,
    ADD COLUMN IF NOT EXISTS entry_at timestamptz,
    ADD COLUMN IF NOT EXISTS adverse_extreme_price double precision,
    ADD COLUMN IF NOT EXISTS adverse_extreme_at timestamptz,
    ADD COLUMN IF NOT EXISTS horizon_price double precision,
    ADD COLUMN IF NOT EXISTS horizon_at timestamptz,
    ADD COLUMN IF NOT EXISTS horizon_status text NOT NULL DEFAULT 'pending',
    ADD COLUMN IF NOT EXISTS tracking_version text NOT NULL DEFAULT 'ip-tracking-v3';

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint
        WHERE conrelid='public.ip_selected_candidates'::regclass
          AND conname='ip_selected_candidates_horizon_status_check'
    ) THEN
        ALTER TABLE public.ip_selected_candidates
            ADD CONSTRAINT ip_selected_candidates_horizon_status_check
            CHECK (horizon_status IN ('pending','matured','error'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ip_selected_candidates_user_selected_idx
    ON public.ip_selected_candidates(user_selected, user_selected_at DESC);
CREATE INDEX IF NOT EXISTS ip_selected_candidates_horizon_idx
    ON public.ip_selected_candidates(horizon_status, horizon_end_at, status);

ALTER TABLE public.ip_selected_candidates ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.ip_selected_candidates FROM anon, authenticated;
GRANT SELECT, INSERT, UPDATE ON TABLE public.ip_selected_candidates TO service_role;

-- The active audit row is inserted by the production migration after the
-- historical result set has been independently recomputed and reviewed.
