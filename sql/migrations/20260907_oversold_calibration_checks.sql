-- Latest operational check is not a fitted calibration and cannot activate one.
CREATE TABLE IF NOT EXISTS public.or_calibration_checks (
    scoring_model_version text NOT NULL,
    scoring_config_version text NOT NULL,
    validation_contract text NOT NULL,
    checked_at timestamptz NOT NULL DEFAULT now(),
    check_count bigint NOT NULL DEFAULT 1,
    result jsonb NOT NULL CHECK (jsonb_typeof(result)='object'),
    PRIMARY KEY (scoring_model_version,scoring_config_version,validation_contract)
);
ALTER TABLE public.or_calibration_checks ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE public.or_calibration_checks FROM PUBLIC,anon,authenticated;
GRANT SELECT,INSERT,UPDATE ON TABLE public.or_calibration_checks TO service_role;
COMMENT ON TABLE public.or_calibration_checks IS 'Latest operational calibration check per exact model/config/validation contract. Not training evidence and never a probability activation record.';
