# E003C prospective runtime isolation

## Frozen scientific identity

This release does not change `E003C_v1`. Its rule implementation remains the implementation inherited from Git commit `2019c4cb260816b672133154f76f65011c15ef73`. The canonical rule hash is:

`4bcd161f68c824365d8a0f0dda47a78ea8f410a04dfe0250c36e142c472e2562`

The cutover baseline is the independently preserved 13 August 2026 checkpoint:

- job `9c19eea7-2401-481a-a9f3-1d75a75a07f6`
- event `275`
- audit hash `29e2168dd128e60ed7e454acce9b973b`

No migration or worker startup path rewrites historical evidence.

## Architecture

The isolated service runs `python -m app.e003c_worker`. It performs only:

1. E003C provider/database/rule/freeze/basket/readiness checks.
2. E003C entry, exit and quote-snapshot capture through the unchanged `app.e003c_live` functions.
3. E003C-specific daily ingestion queuing and signal freezing.
4. Runtime heartbeat and checkpoint writes in `research_control`.

It does not claim or process general Rapid Discovery jobs, run the intraday compactor, run net-5 post-processing, run RV30 audits, or maintain unrelated shadow candidates.

## Single-writer controls

Writer mode requires both:

- a session-level PostgreSQL advisory lock; and
- an expiring atomic database lease in `research_control.e003c_writer_lease`.

Writer startup is blocked unless `research_control.e003c_cutover_control` proves that:

- readiness was verified for the same Render service and exact Git SHA;
- the shared worker's E003C capture and maintenance schedulers were disabled; and
- transfer was explicitly authorised.

Every write phase rechecks writer authority. Lease renewal or lock failure stops the dedicated runtime fail-closed.

## Cutover sequence

1. Apply `sql/migrations/20260813_e003c_runtime_isolation.sql`.
2. Create the dedicated Render Background Worker from the immutable release branch with auto-deploy disabled.
3. Set `E003C_RUNTIME_MODE=readiness`; do not enable writer mode.
4. After the first readiness deployment, set `E003C_EXPECTED_SERVICE_ID` and `E003C_DEPLOYMENT_ID` to the actual Render identifiers and redeploy the same pinned SHA.
5. Verify service name/type/ID, deployment ID, release pin, database, provider, rule hash, frozen signal count, basket state, baseline checkpoint and phase heartbeat.
6. Record the readiness service ID, Git SHA, owner ID and deployment ID in the control plane.
7. Disable `E003C_LIVE_CAPTURE_ENABLED` and `E003C_DAILY_INGEST_ENABLED` on the shared Rapid worker and verify it restarts healthy without those schedulers.
8. Record the legacy-disable evidence and authorise transfer in the control plane.
9. Set the dedicated worker to `E003C_RUNTIME_MODE=writer`.
10. Verify exactly one current lease, one advisory-lock owner, one active writer heartbeat and the pinned release SHA.

## Rollback

1. Change the dedicated worker to `standby` and deploy the same pinned release SHA.
2. Verify its database lease is released or expired and `writer_active=false`.
3. Re-enable the two E003C scheduler variables on the legacy Rapid worker at its recorded rollback SHA.
4. Verify the legacy scheduler logs and provider/database health.
5. Record rollback evidence in `research_control.e003c_cutover_control`.

Never re-enable the legacy writer before the dedicated lease is no longer current.
