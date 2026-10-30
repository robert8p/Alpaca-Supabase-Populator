# ASTRA ingestion — replacement checkpoint v63

## Active authority and scope

Rob's full ten-section replacement instruction is adopted in [REPLACEMENT_BACKFILL_MISSION_20261030.md](REPLACEMENT_BACKFILL_MISSION_20261030.md), SHA256 `62dd1a15c5c6cf46a42340917701816c6c3b86c49e4b4fb462f8b111bcaadc45`. It replaces the old Aug–Sep2026/all24-family mission and incompatible admission/acceptance requirements. Old checkpoints are retained as history, not current scope.

New run identifier: `fixed3000-20250901-20260731-v1-20261030`.
Classification: **RETROSPECTIVE_FIXED_COHORT**.
Target: 2025-09-01 through2026-07-31 inclusive, America/New_York exchange dates.
Families: REF01,REF03,P01,P02,D01,D02,D03,D04,D05,N01,N02,N03,S01,S02,CTX02,CTX06.
Sources: existing Alpaca Algo Trader Plus and Massive Stocks Starter only.
Population: exact previously accepted practical3000 membership, now being resolved from saved records. No reranking/substitution. No scoped provider acquisition until membership is reconciled.
No programme expiry. Requests/transactions/leases/attempts remain bounded and automatically resumable. Old canary quotas/deadlines apply only to their original jobs.

## Sole current implementation ownership

Owner: originating controlling conversation `root-replacement-20261030T042603Z`.
Finite claim expires **2026-10-30T06:30:00Z**.
Prior scheduled run `b232445d-fd0c-8327-88fc-971f7562f77b` ended completed04:16:07Z; prior v61 claim RELEASED/RETIRED.
Existing implementation automation `6ae2a4c96bbc819182133e17e9b7f779` has been retargeted to the exact full replacement instruction and temporarily paused while this owner implements safe supersession. Its original hourly recurrence is retained without expiry. No second controller was created.
Local delegated agents may inspect/build independent files but have no production/repository write ownership.
Before future shared writes, reconcile actual task/run state, current head, this finite lease and database stop/fences; use exact-head CAS.

## Verified live starting state

At2026-10-30T04:32:54.468429Z, app schema has exactly two completed legacy jobs: original156-record canary and78-record crash qualification; zero active claims and no queued old job. Preserve these immutable scopes/keys/deadlines/receipts/counters.
No live bulk ledger or bulk worker exists. The current worker only processes legacy Alpaca bar jobs. Prior327-test candidate is staged source, not a running bulk ingestion pipeline.
Existing worker is Render `srv-dbh9fko473hc739an8m0`, web `srv-dbh85vl9fdbs7387rucg`, workspace `tea-d562ma4hg0os73aejnfg`. Existing branch remainsfeat/astra-ingestion-service; manual deploy; no new service/cost.
The old runtime dispatcher uses real api/worker capabilities and advisory transaction lock706314020261028. Extend that existing authenticated runtime; do not fabricate a hosted user principal or treat a synthetic callback as provider evidence.

## Current implementation work

1. Old-scope admission is now closed at the authenticated database boundary. Persist a distinct replacement run and freeze the exact saved cohort.
2. Extend the existing application queue/worker with family-aware bounded tasks, receipts, truthful dispositions, retries and automatic continuation.
3. Reuse verified equivalent existing source observations by mapped reference where practical. Do not count direct SEC/FINRA/other sources in two-plan completion.
4. Connect the first useful provider/reuse batch, verify readback and successor, then keep full-scope work running while implementing remaining adapters/calculations.
5. Keep raw acquisition independent of per-unit identity/research-quality gaps. Operational failures remain operational failures, never provider absences.
6. Retarget all app continuation/supervision paths; preserve unrelated scanners/controllers and excluded datasets.

All16 families remain in accounting. F01–F06,CTX07,CTX14 are outside acquisition; D06preservation-only. Current full backfill state is **IMPLEMENTING / NOT_YET_RUNNING**, not complete. Database admission supersession is verified; the new-run deployment is not yet claimed.

## Evidence and continuation

Current source before replacement: `b3e2912f00812dd11122be116f98be9499a4908f`; old checkpoint archived at [history/INGESTION_COMPLETION_STATE_v61.md](history/INGESTION_COMPLETION_STATE_v61.md).
The implementation owner is active in this conversation and will publish concrete queue/run/release receipts and restore this same scheduled writer after establishing safe resumption. Never restore the old24-family/Aug–Sep scope from archived docs or former automation prompts.
Existing disabled independent reviewer/closeout have unresolved requires_user_action states; do not impersonate their acceptance or bypass actual platform restrictions. Independent local/source/readback work continues meanwhile.

## Verified replacement milestone — 2026-10-30T05:03:57Z

Migration `astra_ingestion_supersede_gate_v2` applied successfully and read back. Original `submit_job` now returns SUPERSEDED_BY_SCOPE_CHANGE after normal capability authentication; original `claim_next` returns null after the shared transaction lock. Existing completed job counters remain 156/2 and78/1; zero active claims. No queued original work required relabeling.
The gate was qualified against disposable PostgreSQL16 with existing capability authentication, queued-task preservation, repeated application, and invalid-token rejection.
Actual Alpaca calendar has230 target sessions. Minimum60-session daily support begins2025-06-05;20-session intraday support begins2025-08-04. Retain support separately.
Actual Render deployment reconciliation confirms both services still LIVE on `2c809b69e131f84e1778486e74c2f89a273f59f9`; no replacement bulk execution is claimed.
