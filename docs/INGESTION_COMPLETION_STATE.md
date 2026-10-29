# ASTRA ingestion completion — durable coordination state

**Checkpoint version:** 5 (2026-10-29 03:22 UTC; scoped implementation verified and writer lease released)
**Programme:** isolated ASTRA ingestion reliability; no bulk ingestion or scientific certification.
**Owner:** none after verified completion of this bounded run; previous sole writer run `8e5a5ad2-2570-8322-97bd-a1e22b9a8857` has released its finite CAS mutation lease.
**Exclusive implementation lease:** released at this checkpoint. Next writer must inspect current task runs, branch head, deployed services and active claims and acquire a new atomic finite CAS lease; never assume schedule ordering proves ownership.
**Operation:** completed one-time independent SQL verifier migration and scheduled cron603; original 156-row AAPL/MSFT attested PASS under restricted role; monitored fail-closed synthetic deadline incident durably recorded; hosted post-rollout new worker verification-only AAPL fixture PASS; fixture cleaned fully; both named services deployed and live on exact tested `bd7b5bed`. Remaining forced physical crash/zero-overlap and external HTTPS gateway actor acceptance stay open. This is not bulk-ingestion admission.
**Next run:** scheduled implementation remains enabled but unowned until a fresh CAS lease; review the newest machine evidence and independent acceptance first. Do not needlessly replay the already installed migration, completed synthetic tests or existing canary.
**Campaign hard stop:** 2026-11-05 02:00 UTC or newer explicit stop.

## Ownership and dependency registry

- Scheduled implementation writer: `6ae2a4c96bbc819182133e17e9b7f779` — Complete ingestion reliability; enabled; no continuing lease after this checkpoint.
- Read-only independent verifier: `6ae2a4df5e908191989eacee0a454141` — Verify ingestion independently.
- Read-only readiness closeout: `6ae2a4f6b4ac8191813eb27ed33c5e1b` — Close ingestion readiness gates.
- Former owner run `c256f0aa-43d8-8332-b4f1-c94d78854529` ended failed with no result message. Its former 03:45 lease is superseded only after terminal-run, paused-schedule and branch/state reconciliation. Do not blindly replay its mutations.
- Each independent task retains its own evidence; no unrelated or paused legacy schedule is changed.

## Fixed scope and evidence

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
- Repaired both key expressions, rejected receipts after terminal pages and repeated continuation tokens, required exact receipt/page-count and terminal partition checkpoint, rejected within-page source duplicates before deduplication and rejected duplicate target JSON keys before jsonb conversion. The original successful verification, actor ACL, unchanged dispatcher and one-shot attestation tests are preserved.
- Existing SQL verifier integration test now includes seven precise rejection subcases (value tamper, wrong page count, nonterminal checkpoint, receipt after terminal, repeated token, identical source duplicate, target duplicate JSON key), each rolled back independently, plus a valid three-page success case. Every negative case requires its intended SQLSTATE/message. Local Python AST/compile validation passed; PostgreSQL acceptance is the exact new GitHub workflow result, not a local execution claim.
- Repaired SQL SHA256 `82038c484a0bc26234650fd087899353f2be09915702473760636ddf12a0cb8c`; regression file SHA256 `8146b3a8c06952954a988d08de2b7d292b4c1acefc5924144f8d12241dc99d96`. Candidate source is the commit containing this checkpoint, descended from original failed candidate cda4177.
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

Read the exact commit's PostgreSQL and release CI results; no deployment is admitted on failure or missing evidence. The originating conversation restores the scheduled writer after recording the result in its task handoff. The next writer acquires its own finite CAS lease, accepts the original-canary report, and completes the remaining deployed verifier and hosted recovery gates. Install any later verifier migration once, in one transaction, only after baseline/schema/ACL admission and exact-candidate CI; migration replay is deliberately rejected. A failed attestation is one-shot for its partition/version and cannot be silently retried or deleted to obtain a pass. Acceptance must require result=passed plus exact scope/counts; equal empty-map hashes alone prove nothing. SQL map hashes and worker/audit array hashes use different canonical containers and must not be compared as equal digests.

Keep all original budgets, immutable-canary constraints, manual-deployment settings, legacy stops and scientific holds. No new provider allowance was consumed by this interim repair. Recheck current ownership and unresolved effects before every future mutation.


## Most recent verified implementation results — 29 October 2026, 03:21 UTC (supersedes older gate status above)

- Candidate verifier repair `8f7463c9`; exact deployed web/worker `bd7b5bed714ef0afbd2015e6f6c1c0fd54b7d9fb`. Both GitHub exact-release ingestion and release workflows passed; both Render deploys LIVE. No main merge or auto-deploy change.
- Independent restricted verifier migration installed **once**, not replayed. Actual `pg_cron` job603 ran at **03:12:00.176** and **03:14:00.165** UTC, independently verifying AAPL78/78 and MSFT78/78, one receipt each, hashes equal and zero exceptions. Role is NOLOGIN/NOBYPASSRLS; actual `SET LOCAL ROLE anon` and `authenticated` attempts to invoke were denied SQLSTATE42501. External HTTPS gateway test is still separate.
- Independent observer `pg_cron` job602 continues every two minutes. **39** durable ticks through **03:20:00.031** UTC. A bounded, uncommitted synthetic expired job invoked the installed observer and produced **one durable fail-closed deadline incident** at **03:12:22.881** UTC, zero records or requests. This demonstrates function behaviour; the synthetic injection was *not* asynchronously detected by cron, so autonomous real-stall recovery remains pending.
- Hosted new worker `srv-dbh9fko473hc739an8m0-svxfw` (Render exact `bd7b5bed`) verified a *synthetic verification-only* AAPL source-copy fixture at **03:16:53.030** UTC, after deployment and >60-second old-instance shutdown grace. Worker event and canonical hashes passed; independent cron603 additionally verified the fixture at **03:18:00.165**. Render metrics show **one worker instance** from 03:14 to 03:17 UTC. This supports post-rollout exclusive processing, **not** a physically forced host crash or zero-overlap rollout.
- Entire synthetic fixture removed atomically at **03:18:40.520** UTC (one job, one partition, one copied receipt, 78 copied records, two events and two verifications). **03:21:34.072** readback: only the original completed canary remains, 156 original records, two original receipts, two independent restricted attestations, zero active claims. Original request_count remains **2**; no new provider requests or paid resources were used. Synthetic fixture request_count=1 was a pre-reserved accounting *test marker*, not a real request.
- Durable report: Library file `libfile_9b466ad815b48191ae49fd30233bd6c8`, `/ASTRA Ingestion/ASTRA_Ingestion_Reliability_Qualification_20261029.md`, SHA256 `0e03620134a0e96d0d1bbacc227363ec46233cfbcacc34b60af0488f4dedaa4d`. Machine evidence: `evidence/astra_ingestion_reliability_20261029.json` in this revision. Earlier independent 156-row report remains `libfile_dcfd71df63248191ba61293c51b84921`.
- Remaining specific gates: *physical forced process death immediately after fresh atomic receipt commit*, *explicit old-instance cessation before successor startup rather than post-rollout only*, *external HTTPS restricted actor execution denial*, and *final independent release closeout*. Separate tasks are read-only and must not silently waive these.
- **Next admissible action:** independently reconcile current deployed/source IDs, the report, actual role grants and cron ledger. Safely design a one-shot failpoint with bounded AAPL/MSFT provider scope only if it can meet the existing 10-request/1000-record cumulative allowance, ownership fencing, unchanged original deadline and no cost. Otherwise close the qualifying bounded result honestly with the remaining physical test unproven. No blanket bulk ingestion, trading or other mission resumes. Campaign stops 5 November as originally authorised.
