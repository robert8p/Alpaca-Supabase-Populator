-- Runtime role readback found that production uses these two restricted login
-- roles, not service_role. Both already manage existing reversion outcomes and
-- calibration runs. Keep anonymous/authenticated API users excluded.
GRANT SELECT, INSERT, UPDATE ON TABLE public.or_calibration_checks
    TO rapid_web_20260906, rapid_worker_20260906;

DROP POLICY IF EXISTS or_calibration_checks_app_runtime
    ON public.or_calibration_checks;
CREATE POLICY or_calibration_checks_app_runtime
    ON public.or_calibration_checks
    FOR ALL TO rapid_web_20260906, rapid_worker_20260906
    USING (true) WITH CHECK (true);

COMMENT ON POLICY or_calibration_checks_app_runtime ON public.or_calibration_checks
    IS 'Restricted server-side reversion identities; table grants allow only SELECT/INSERT/UPDATE of operational checks. No anonymous/authenticated access or probability activation authority.';
