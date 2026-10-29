# ASTRA ingestion completion — durable coordination state

**Checkpoint version:** 1 (2026-10-29 01:57 UTC; initial atomic claim)
**Programme:** isolated ASTRA ingestion reliability; no bulk ingestion or scientific certification.
**Owner:** automation `6ae2a4c96bbc819182133e17e9b7f779`, run `c256f0aa-43d8-8332-b4f1-c94d78854529`.
**Exclusive implementation lease:** claimed via atomic GitHub create-file on the isolated branch; expires **2026-10-29 03:45 UTC**. Successor must compare exact current content SHA, verify no active owner, and renew by CAS. The lease is a *coordination* guard, not proof of a production-wide PostgreSQL mutex. Independently inspect all current runtime claims before production writes.
**Operation:** initial evidence inventory and implementation of independent progress monitor; no code or production mutation yet. No additional provider requests authorised until implementation and acceptance tests pass.
**Next scheduled implementation run:** no earlier than 2026-10-29 04:00 UTC. Do not treat the next schedule as proof of a run or completion.
**Campaign hard stop:** 2026-11-05 02:00 UTC or newer explicit stop.

## Ownership and dependency registry
- Only implementation writer: `6ae2a4c96bbc819182133e17e9b7f779` — Complete ingestion reliability.
- Read-only independent verifier: `6ae2a4df5e908191989eacee0a454141` — Verify ingestion independently.
- Read-only readiness closeout: `6ae2a4f6b4ac8191813eb27ed33c5e1b` — Close ingestion readiness gates.
- The other two tasks were enabled and had not yet run when this claim was made. Do not modify their evidence or schedules except upon final accepted closeout.

## Fixed scope and evidence
- Repository `robert8p/Alpaca-Supabase-Populator`; branch `feat/astra-ingestion-service`; [PR 93](https://github.com/robert8p/Alpaca-Supabase-Populator/pull/93) remains draft, unmerged.
- Initial qualified source and both deployed Render revisions: `1c3d9e860a22ea872fd0ce3fcfce27fd44d8eebe`. Web `srv-dbh85vl9fdbs7387rucg`; worker `srv-dbh9fko473hc739an8m0`; Render workspace `tea-d562ma4hg0os73aejnfg`. Blueprint `exs-dbh5qcetlv9c73fqqen0` uses `render-ingestion.yaml`. Service auto-deploy and Blueprint Auto Sync off. Normal compute $14/month.
- Supabase `oxzabweahkoimtevbbny`, isolated schema `astra_ingestion_v1`. At **2026-10-29T01:56:57.873Z**: one **completed** job, zero active partition leases, no other job.
- Immutable canary: job `fab354f9-c8fc-4158-add9-4aff025594bf`, key `astra-ingestion-v1-canary-20261028-1c3d9e8`, scope hash `893249da7775de9e75421b185280bfb837b3e37fc0b1926b1069544560e24cf1`; AAPL/MSFT, 2025-09-02T13:30:00Z–20:00:00Z, 5Min/SIP/raw.
- Canary completed with 156 stored rows (78 per symbol), 2 provider requests, 2 retained source receipts and stored verification passed. Deadline expired `2026-10-29T01:24:10.838070Z`; do not reopen, resubmit or alter.
- Controlled pause/redeploy/resume demonstrated checkpoint persistence, but old and replacement worker instances overlapped. It did **not** demonstrate exclusive takeover, host-loss recovery or independent runtime verification.
- Additional campaign allowance: **10 total provider requests and 1,000 records** across *all* post-canary tests; consumed since initial canary: **0**. Never reset. New jobs limited to original AAPL/MSFT interval, 30-minute maximum deadline, fixed idempotency keys and retained manifest.
- New paid services/compute: **not authorised**. No trading, no bulk acquisition, no paused mission changes. Legacy services `srv-d9p2vljncjis73evkocg` and `srv-d9p2vljncjis73evkoc0` stay suspended.

## Qualification gate ledger (not complete)
1. Finite hosted AAPL/MSFT canary with stored source-to-target exact verification — **PASS for worker-controlled bounded delivery only**.
2. Independent running useful-progress monitor and stall incident/recovery evidence — **PENDING**.
3. Crash-after-commit fault test; expired lease and stale-owner rejection; original instance cessation and isolated hosted replacement — **PENDING**.
4. Independently restricted runtime verifier identity and deployed actor enforcement — **PENDING**.
5. Independent fresh full 156-row source/target recheck — **PENDING**, assigned to independent verifier.
6. Exact new source CI, controlled named-service deployment and final independent acceptance — **PENDING**.
7. Full historical coverage/universe/corporate actions/identity/financial research — **NOT_CERTIFIED, OUT OF THIS RELEASE**.

**Immediate next admissible step:** inspect worker/store/RPC contracts, design isolated observer with narrowly scoped RPC and test-only deterministic recovery scenarios; implement synthetic tests before any new hosted provider-backed job. Preserve the original worker and production SQL until a reviewed candidate passes exact-source checks.

## Change-control notes
- This is a one-file CAS acquisition: create failed if another implementation owner created the checkpoint first. Any subsequent edit MUST supply the just-read blob SHA and reconcile source head/lease to avoid overwriting newer work.
- Re-verify active leases and original Render/PR revision before changing deployed state. Fail closed if another owner/active operation is discovered.
- Report only real new evidence. Never claim an automation schedule is a qualified runtime watchdog.
