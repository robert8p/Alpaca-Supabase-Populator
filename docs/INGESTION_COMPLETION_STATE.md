# ASTRA ingestion completion — durable coordination state

**Checkpoint version:** 2 (2026-10-29 02:30 UTC; reconciled interim recovery claim)
**Programme:** isolated ASTRA ingestion reliability; no bulk ingestion or scientific certification.
**Owner:** originating user conversation, bounded interim repair `interim-recovery-20261029T0230Z`.
**Exclusive implementation lease:** expires **2026-10-29 03:15 UTC**. The scheduled implementation task has been temporarily paused and read back as disabled; its last run is terminal **failed**, completed 2026-10-29T02:20:28.644931Z. This claim does not infer that an in-progress remote operation was cancelled. A successor must read the current owner, task state, branch head and exact content SHA, then use CAS; never overwrite newer work.
**Operation:** repair the preserved SQL verifier candidate and add focused disposable PostgreSQL regressions; GitHub qualification follows. Root production access during this repair is read-only. No additional provider job, deployment or database migration is admitted by this claim.
**Next scheduled implementation run:** original cadence is preserved; the task will be re-enabled after this repair is checkpointed. Next nominal implementation slot is 2026-10-29 04:00 UTC; timing is flexible and is not proof of a run.
**Campaign hard stop:** 2026-11-05 02:00 UTC or newer explicit stop.

## Ownership and dependency registry

- Scheduled implementation writer: `6ae2a4c96bbc819182133e17e9b7f779` — Complete ingestion reliability; temporarily disabled for this bounded originating-conversation recovery.
- Read-only independent verifier: `6ae2a4df5e908191989eacee0a454141` — Verify ingestion independently.
- Read-only readiness closeout: `6ae2a4f6b4ac8191813eb27ed33c5e1b` — Close ingestion readiness gates.
- Former owner run `c256f0aa-43d8-8332-b4f1-c94d78854529` ended failed with no result message. Its former 03:45 lease is superseded only after terminal-run, paused-schedule and branch/state reconciliation. Do not blindly replay its mutations.
- Each independent task retains its own evidence; no unrelated or paused legacy schedule is changed.

- Repository `robert8p/Alpaca-Supabase-Populator`; branch `feat/astra-ingestion-service`; [PR 93](https://github.com/robert8p/Alpaca-Supabase-Populator/pull/93) remains draft, unmerged.
- Initial qualified source and both deployed Render revisions: `1c3d9e860a22ea872fd0ce3fcfce27fd44d8eebe`. Web `srv-dbh85vl9fdbs7387rucg`; worker `srv-dbh9fko473hc739an8m0`; Render workspace `tea-d562ma4hg0os73aejnfg`. Blueprint `exs-dbh5qcetlv9c73fqqen0` uses `render-ingestion.yaml`. Service auto-deploy and Blueprint Auto Sync off. Normal compute $14/month.
- Supabase `oxzabweahkoimtevbbny`, isolated schema `astra_ingestion_v1`. Reconciled at **2026-10-29T02:26:34.580541Z**: one **completed** original job, zero active partition claims, no additional job.
- Immutable canary: job `fab354f9-c8fc-4158-add9-4aff025594bf`, key `astra-ingestion-v1-canary-20261028-1c3d9e8`, scope hash `893249da7775de9e75421b185280bfb837b3e37fc0b1926b1069544560e24cf1`; AAPL/MSFT, 2025-09-02T13:30:00Z–20:00:00Z, 5Min/SIP/raw.
- Canary completed with 156 stored rows (78 per symbol), 2 provider requests, 2 retained source receipts and stored verification passed. Deadline expired `2026-10-29T01:24:10.838070Z`; do not reopen, resubmit or alter.
- Controlled pause/redeploy/resume demonstrated checkpoint persistence, but old and replacement worker instances overlapped. It did **not** demonstrate exclusive takeover, host-loss recovery or independent runtime verification.
- Additional campaign allowance: **10 total provider requests and 1,000 records** across *all* post-canary tests; consumed since initial canary: **0**. Never reset. New jobs limited to original AAPL/MSFT interval, 30-minute maximum deadline, fixed idempotency keys and retained manifest.
- New paid services/compute: **not authorised**. No trading, no bulk acquisition, no paused mission changes. Legacy services `srv-d9p2vljncjis73evkocg` and `srv-d9p2vljncjis73evkoc0` stay suspended.


## Reconciled effects of the failed scheduled run

- Preserved source candidate: `cda4177b985e3b377f2f9156dd256f20098b21d9`, based on qualified `1c3d9e860a22ea872fd0ce3fcfce27fd44d8eebe`. Both Render services remain on the original qualified revision; no candidate deployment has been observed.
- Added observer/verifier SQL and recovery fixtures. Original checkpoint version 1 was stale: observer DDL and its schedule had already been installed. Do not reapply `sql/astra_ingestion_observer_v1.sql`.
- Observer function body matches published candidate exactly. Function owner `astra_ingestion_monitor_owner_v1` is NOLOGIN, NOINHERIT, non-superuser, NOBYPASSRLS. Readback shows no job UPDATE or runtime-credential SELECT, tick INSERT allowed, and no anon/authenticated function EXECUTE.
- Existing pg_cron job **602**, name `astra_ingestion_monitor_v1`, active schedule `*/2 * * * *`, executes only `SELECT astra_ingestion_v1.monitor_tick_v1()`. Scheduler login is postgres; SECURITY DEFINER executes the body as the restricted monitor owner.
- At 02:26:34 UTC, 11 persisted monitor ticks ran from 02:06:55 through 02:26:00; all observed zero active jobs and zero new incidents. This proves installed idle observation, not live stall detection/recovery.
- Runtime independent verifier objects/role are absent. Its migration was not observed installed.
- Candidate ingestion CI failed: [PR run 40805713520](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40805713520), SQLSTATE42883 `operator does not exist: text ->> unknown`. Both key assignments need parenthesized JSON extraction.
- Static review additionally found receipt-chain/cardinality and duplicate-normalization false-pass cases. Repair and regression tests are in progress; no pass or release claim yet.
- Two bounded attempts to read cron execution history timed out. No execution-history conclusion is claimed; actual tick ledger and current cron definition provide the observations above.

## Qualification gate ledger

1. Finite hosted AAPL/MSFT canary with worker-controlled bounded delivery — **PASS for original revision/population only**.
2. Independent full retained-source/target comparison — **PASS for the original 156-row canary**. All 9 normalized fields, every key, two exact TEXT receipts, hashes, pagination and pre-dedup source occurrence counts checked; 11 negative/known-answer controls passed. AAPL78/MSFT78, zero missing/changed/extra/duplicates.
3. Independent running useful-progress monitor — **INSTALLED / ACTIVE IDLE OBSERVATION PROVED**; synthetic regression qualification and live stall/incident/fail-closed evidence must be bound to the accepted revision. Full recovery gate remains **PENDING**.
4. Crash-after-commit and stale-owner/expired-lease behavior — synthetic fixtures added, exact repaired-candidate CI **PENDING**. Exclusive hosted replacement/actual old-instance cessation remains **PENDING**.
5. Independently restricted runtime verifier — candidate present, not installed; exact-source CI, actual deployed identity/transport enforcement and bounded live attestation **PENDING**.
6. Controlled named-service deployment and final independent acceptance — **PENDING**.
7. Full historical coverage/universe/corporate actions/identity/financial research — **NOT_CERTIFIED, OUT OF THIS RELEASE**.

## Independent retained-canary evidence

- Complete report: `libfile_dcfd71df63248191ba61293c51b84921`, `ASTRA_Ingestion_Independent_Canary_Review_2026-10-29.md`.
- Report SHA256 `51c2e09b28732183ec72b0e9e32f0fad4553b7acd3e8d94675e400c18859592e`.
- Standalone verifier SHA256 `957d8a388983a9d1a3927789b693a0ce063b6b27dad556bc9f2e36c8681534d8`.
- Local full-snapshot SHA256 `faf32dd90cdaed64fac7fa78c7d0e0709d53424d85d42c1b945959efb03b15ca`.
- Read-only snapshots at 02:16:21.097565 and 02:16:21.364018 UTC; audit/controls rerun at 02:19:58.526508 UTC.
- Administrative connector evidence is distinct from restricted runtime verifier qualification. It qualifies the original canary, not later source changes, new jobs or full historical coverage. All three task prompts already reference this report.

## Next admissible step and change control

Complete this bounded repair, publish with exact-head CAS, run the required PostgreSQL and release CI, record its result and release ownership before restoring the scheduled writer. Install any later verifier migration once, in one transaction, only after baseline/schema/ACL admission and exact-candidate CI; migration replay is deliberately rejected. A failed attestation is one-shot for its partition/version and cannot be silently retried or deleted to obtain a pass. Acceptance must require result=passed plus exact scope/counts; equal empty-map hashes alone prove nothing. SQL map hashes and worker/audit array hashes use different canonical containers and must not be compared as equal digests.

Keep all original budgets, immutable-canary constraints, manual-deployment settings, legacy stops and scientific holds. No new provider allowance was consumed by this interim repair. Recheck current ownership and unresolved effects before every future mutation.
