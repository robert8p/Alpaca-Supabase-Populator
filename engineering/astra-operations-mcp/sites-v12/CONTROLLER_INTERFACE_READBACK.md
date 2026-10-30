# ASTRA Operations v12 — real ingestion controller interface read-only reconciliation
Date: 2026-10-30. Implementation owner: Assess MCP Plugin Opportunities chat. Dot handles routine reporting and existing Site release. Ingestion controller remains sole app operations owner.

## Current executor reconciliation
Automation `6ae4d6e1e2a48191aa7edaf9464f77e5` was observed **enabled**, last run `c501d19c-bb64-8328-a037-f3cec100226b` completed 20:50:33 UTC, with source-only v11 output (152/152 v11 candidate, 20/20 native, 122/122 separate N1 tests). Its run conversation ID `6ae5031b-6d10-83eb-8085-cae78cbda2be` is an automation execution thread; this engineering chat remains the implementation owner. No provider writes or live controller port proven.

## Source-backed current owner interface
Inspected `robert8p/Alpaca-Supabase-Populator` implementation branch head `08bea176e39174f8c39f62caebae79d5cb50cdcf`.
- `astra_ingestion/api.py` blob `23571883acd35dcab295f9486e993619003d69a8`: GET jobs/status; POST job submission/control. Existing HTTP Basic identity can perform control operations and cannot be reused for Sites read-only integration.
- `astra_ingestion/rpc_store.py` blob `b423c9cb6ca0adcdece631d12b36e00149dd5b1a`: ingestion-specific RPC methods, worker claims, reserve_request, commit_page, etc. No owner-injected `lookupExact/admitExact/reserveAndDispatchUnderOwnerGuard/readbackExact` port.
- `sql/astra_ingestion_rpc_v1.sql` blob `9cb1d522a8fab6660c1cbebd951dd4df7871da03`: per-job idempotency, pause/cancel, worker owner/generation/lease fencing; **not evidence** of cross-provider immutable change and physical resource lock/causal readback for Render/GitHub.
- `sql/astra_ingestion_bulk_provider_atomic_receipt_v1.sql` blob `22a69894cf7f399e71c2015b35966caf6a5365f1`: atomic provider-page receipt/readback for ingestion, not equivalent to provider operation receipts.
- Workflow `.github/workflows/astra-ingestion-qualification.yml` on implementation branch blob `f36b4f21874de6afb141faca74bba1cd2d84e328` lacks `workflow_dispatch`; absent at this path on default branch `main` (404). No workflow dispatch eligibility or GitHub Actions:Write grant established.
- Existing Render ingestion worker `srv-dbh9fko473hc739an8m0` already exists, autoDeploy off; no duplicate needed. Render scoped-key beta account eligibility remains UNKNOWN; no supported entitlement inspection tool exposed. Sites native eligibility action remains unavailable; no account denial inferred.

## Actual handoff
Created deferred, unassigned issue **#94** in existing ingestion repository: https://github.com/robert8p/Alpaca-Supabase-Populator/issues/94. It contains exact source evidence, owner-side decision points, the v11 atomic port acceptance contract and workflow/default-branch gate. This is a **durable handoff, not owner acknowledgement, authorisation or an active implementation operation**. Do not interrupt active ingestion repair or assume the issue has been accepted.

## Next executable step / ownership
1. **Ingestion controller owner:** when current repair admission permits, review issue #94, reconcile current stop/owner/fence, and return an actual owner-port mapping or precise missing capability. Qualify any trigger change through its own release process. Do not modify workflow or create a second controller from this plugin.
2. **ASTRA Operations implementation owner (this chat, existing hourly task):** monitor issue #94 read-only for owner response, inspect v11 source contract against returned interface, then implement only a controller-injected adapter with verified real owner semantics. Continue independent provider permission schema qualification without credentials. No mock-only test may be presented as live integration.
3. **Dot:** consolidate routine readback; action-time owner confirmation only after exact provider identity, effective scope, secure destination, expiry/revocation and cost effects are established.

## Preserved restrictions
No new Site/plugin/host/executor, no provider credentials or calls, no production app mutation, workflow trigger change, PR approval, trading, paid commitment or security weakening. Existing private Site `appgprj_6ae4dcec2034819197d448ca2eea21a3` and canonical plugin `plugin_asdk_app_sites_a5e127b6f02081918cde92d94b477c57` remain unchanged.
