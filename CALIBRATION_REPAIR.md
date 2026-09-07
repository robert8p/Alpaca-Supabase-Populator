# Reversion calibration pipeline repair — 7 September 2026

The shared backend and both scanner views retain the v3.9 scoring model. This is
an operational repair, not a new calibrated model or evidence of profitability.

## Repairs
- Select least-recently evaluated outcomes, including never-evaluated records,
  instead of repeatedly selecting the same oldest 500 six-week pending records.
- Retry unverified three-session calendars/paths. Persist attempt times and errors,
  isolate each path write with a savepoint, and never manufacture a mature label.
- Fix PostgreSQL double-precision/numeric coercion in reliability diagnostics.
- Report exact-model original signal counts separately from independent eligible
  observations, days, classes and the actual purged training/holdout split.
- Record scheduled `not_ready`, `unchanged`, fitting and error states in a small
  operational table, independently of immutable calibration fits.
- Add one read-only status endpoint and the same accessible refreshable status
  panel in both scanner views; unavailable data is not displayed as zero/success.
- Require clear corporate-action review and completed verified target windows
  explicitly when loading samples. Keep historical rescores out of calibration.

## Deployment order
Apply `sql/migrations/20260907_oversold_calibration_checks.sql` to the canonical
Supabase project before deploying this code. Runtime migrations remain disabled.
The operational table has RLS, no anonymous/authenticated grants, and no ability
to activate a mapping. Then deploy the web and worker from the same repository.

## Preserved safeguards
The 30-calendar-day corporate-action review policy, 300 independent observations,
60 outcomes per class, 30 independent days, 100 temporal holdout observations,
purging, original-only version isolation and existing fit/robustness gates are
unchanged. Historical original scores, snapshots, decisions and outcome labels
are not rewritten by this release. A future passed mapping predicts the existing
price-target-touch event, not net trading profitability.

## Verification
The dedicated regression tests cover eligibility/maturity guards, queue fairness,
failed provider retries, readiness/purge consistency, durable scheduled states,
error privacy, both templates and the JavaScript presentation contract. Run the
full existing release gate; do not equate a passing software test with a passing
statistical calibration. Confirm the new read-only status endpoint and absence
of the former reliability SQL error after deployment.
