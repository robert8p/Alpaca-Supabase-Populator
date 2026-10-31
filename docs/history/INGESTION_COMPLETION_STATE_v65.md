# ASTRA ingestion — replacement checkpoint v65

## Current execution and ownership

Updated 2026-10-30T06:38:08Z (01:38 America/Cancun). Status: **ACTIVE — USEFUL BACKFILL RUNNING; FULL DELIVERY INCOMPLETE**.

The same originating owner `root-replacement-20261030T042603Z` retains a finite implementation lease through **2026-10-30T07:15:00Z**. The database and this checkpoint now agree on that lease. Existing implementation automation `6ae2a4c96bbc819182133e17e9b7f779` is enabled with its original hourly recurrence and no expiry. It must reconcile current ownership before implementation writes. No replacement controller or service has been created.

Run: `fixed3000-20250901-20260731-v1-20261030`, fence1. Existing PR93/branch `feat/astra-ingestion-service` in `robert8p/Alpaca-Supabase-Populator`. Deployed executable revision: `13ae192ef28b26f4f658f9c16a4992f4ed73cb2e`. Exact revision passed both GitHub ingestion qualification and release gates.

## Fixed authority and cohort

All ten sections of [the replacement instruction](REPLACEMENT_BACKFILL_MISSION_20261030.md) remain active, SHA256 `62dd1a15c5c6cf46a42340917701816c6c3b86c49e4b4fb462f8b111bcaadc45`.

Target: 2025-09-01–2026-07-31, America/New_York exchange dates. Families: REF01, REF03, P01, P02, D01, D02, D03, D04, D05, N01, N02, N03, S01, S02, CTX02, CTX06. Sources: existing Alpaca Algo Trader Plus and Massive Stocks Starter only. F01–F06/CTX07/CTX14 preserved outside acquisition; D06 preservation-only. No programme expiry; bounded calls, transactions, task leases and attempts.

The accepted saved snapshot `population_top3000_202608_202609_v1.ref01_practical_snapshot_v1.content->companies` was directly reconciled with frozen membership and selection order at06:19:01Z: **3000 saved, 3000 frozen, zero differences**. Root acceptance event24407 governs membership. The immutable snapshot's older false acceptance flag does not supersede the later accepted receipt.

- Snapshot SHA256: `2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec`.
- Acceptance receipt SHA256: `20b9dac759857e9b510ccaeca33e4a94d8c748d588fb0cc27740cc66c389b5f9`.
- Ordered member-ID SHA256: `a83310df6a6465ce8d37ffd5352095f6e38d91a3204afd8807fff39092cfd85e`.
- Evidence: [saved cohort reconciliation](../evidence/replacement-saved-cohort-reconciliation.json).
- Never invoke `ref01_practical_material_v1`; never rerank, substitute or shrink members.
- Classification remains RETROSPECTIVE_FIXED_COHORT, not contemporaneous or survivorship-free.

Actual calendar:230 target sessions; daily60-session support starts2025-06-05; intraday20-session support starts2025-08-04. Formula manifest SHA256 `e0b0835ad53ef7b71d072184bbb1576b3cd8f514c523361fa31865f71a0c8a65`.

## Verified deployment, useful data and continuity

Existing worker `srv-dbh9fko473hc739an8m0` deployed revision13ae at06:29:50Z. Existing web `srv-dbh85vl9fdbs7387rucg` deployed the same revision at06:30:04Z. Workspace `tea-d562ma4hg0os73aejnfg`; no new paid instance.

Useful source began with NVDA reference and two 290-record daily series (raw and split-adjusted), then AAPL and further fixed members. Each complete initial series includes230 target+60 support sessions. Retained SIP source references progressed automatically, including20,018 NVDA September and21,951 October minute observations. Missing retained support creates genuine acquisition children; it is not labelled provider absence.

At06:38:08Z:
-134 physical committed pages,15,258 physical records/pointers,84 provider reservations.
-133 pages independently read back; all133 hashes matched. The newest live page was awaiting its subsequent readback at that instant.
-768,136 retained minute observations were referenced, provenance-qualified and source-usable in completed readbacks.
-Planner cursor29 (next frozen selection order), planning_complete=false.
-No operational task error had been observed in the preceding reconciliation; identity limitations remain explicit.
-These are different units. Do not sum raw/split variants, shared P01/P02 data or retained pointers into one unique-observation total.

Controlled restart `dep-dbi3ki4s728c73c8fnrg` was triggered once at06:33:44Z and became LIVE06:34:28Z on the same revision13ae. Old worker3874b7b4-3693-472d-a386-fa979c417a32 was replaced by2952b01e-7c23-48e8-9947-2fa1f5c058f6. All75 pre-restart page keys/hashes remain unchanged; zero duplicates;34 pages committed after the old worker's final heartbeat by06:37:23Z. Automatic successors are executing from the same durable queue.

Evidence: [first useful batch](../evidence/replacement-first-useful-batch.json), [restart proof](../evidence/replacement-controlled-restart-proof.json), [live accounting](../evidence/replacement-live-progress-v65.json).

## Installed work and retained engineering

Installed runtime, exact fixed cohort, planner, retained-source read/commit/verification, delivery views/finalizer, breadth projection/material, performance extension, paid-provider pacing, retained/fresh source deduplication, and retained D01 feature reuse. Applied migrations remain immutable.

Forward source-dedup SHA256 `f535e4cde061f1123efd09f2a248cb0a4097c97d1a04ae93521f2312a3a4d6a5`; feature-reuse SHA256 `28361e30c10eb696f8e7beaf0ac9c788b1700b77a36ffcc8929be7f3f2ecba61`; pacing SHA256 `50f1e3fd4dd0b7ac6c891de5d7dfaa850d75297af2c0c1255a03acceeb14d501`. Their source publication is included in the next tested forward release; do not reapply because a local output was interrupted.

Optional worker cache wiring is locally qualified, not yet deployed: full449-test PostgreSQL suite passed; actual worker cache-hit/fallback paths passed. Additional family fairness and adaptive-page changes are being qualified under this same owner. These test counts are engineering evidence, not ingestion completion.

Original legacy canary/restart jobs and their234 records/3 requests remain immutable and outside new-run usage. Old admission remains closed.

## Genuine remaining dependencies and executable continuation

1. Publish and deploy the exact tested forward release: wire retained D01 cache reuse, make persisted family rotation prevent a price/reference backlog from starving news/actions/options, and persist adaptive execution page limits without changing immutable scope/cursors. Verify exact deployed commit and actual family progress.
2. Demonstrate the new run's persisted deferred-retry execution path. A heartbeat or unit test alone is insufficient; retain actual scheduled deferral and later progress evidence.
3. Implement progressive historical-identity reconciliation and affected derivation recomputation. Current provider anchors remain unresolved; raw acquisition continues. Missing resolution logic is an implementation issue, not an exhausted provider gap.
4. Improve non-minute per-field coverage accounting: distinguish source variants, derived rows, usable values and NULL reasons; do not add overlapping raw/split/derived counts. Keep unknown expected denominators unknown.
5. Expose replacement-run status in the existing app, and continue the full bounded planner, acquisition, independent readbacks and finalizer. Do not stop after this first useful batch.
6. **Massive worker credential remains BLOCKED_EXTERNAL**: actual heartbeat advertises Alpaca kinds only; `MASSIVE_WORKER_CREDENTIAL / RUNTIME_CAPABILITY_UNAVAILABLE` is persisted. Massive connector historical probes succeeded, but do not supply a deployable secret. Use the existing Massive account API key as `MASSIVE_API_KEY` in this worker environment through an authorised owner setup when available. Do not request a new plan or infer provider absence. Keep Alpaca, reuse and calculations active; the admitted Alpaca-news alternative is planned.
7. At safe handoff, refresh this same task's executable prompt and release the root implementation lease. The enabled task must reconcile remote state before taking the next bounded repair step. Preserve disabled independent reviewer/closeout platform states and unrelated scanners.

No full-family completion or unattended-proof completion is claimed yet. Full delivery requires all3000 members, all16 workflows, sealed complete plan, pagination/contract enumeration, truthful terminal outcomes, independent readbacks, actual data coverage and stable outputs. Operational failures must remain operational. Continue healthy bulk work while repairing affected units.

Previous checkpoint retained at [v64](history/INGESTION_COMPLETION_STATE_v64.md).
