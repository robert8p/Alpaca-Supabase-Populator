# ASTRA Operations v14 — immutable owner receipt and causal settlement correction

**Date:** 2026-10-30. **State:** tested source only; NO live owner port, provider grant, Site release, controller mutation or production provider call. Dot alone owns native Site/plugin publication; the existing ingestion and EQ17 controllers alone own operational writes.

## Reconciled controller and handoff state
- Existing ingestion branch `feat/astra-ingestion-service` remains at observed head `08bea176e39174f8c39f62caebae79d5cb50cdcf`. Existing job-specific API/RPC does not expose a verified atomic cross-provider `lookupExact/admitExact/reserveAndDispatchUnderOwnerGuard/readbackExact` port.
- Existing **issue #94**: https://github.com/robert8p/Alpaca-Supabase-Populator/issues/94 . The ingestion owner **already acknowledged** it in backfill audit 96 and deferred it behind active reliability repair. Correct immutable v11 contract is linked in existing issue comment https://github.com/robert8p/Alpaca-Supabase-Populator/issues/94#issuecomment-6534994041 ; do not seek redundant acknowledgement, interrupt ingestion or add a competing controller.
- Immutable owner contract: https://github.com/robert8p/Alpaca-Supabase-Populator/blob/db0efa4140ae6d59b4c8f36d0d0ebd39b5ff3cd0/engineering/astra-operations-mcp/sites-v11/docs/OWNER_PORT_ADOPTION_CONTRACT.md ; Git blob `622d820e97b62a99a1278223bdc677972be8bf3f`, SHA256 `58b61d0026d4dc9f7a53185d0d06bd5db216dc9b50e8d575cc96377e2e65c0cb`.
- Implementation workflow `.github/workflows/astra-ingestion-qualification.yml` blob `f36b4f21874de6afb141faca74bba1cd2d84e328` lacks `workflow_dispatch`; default `main` path 404. The owner must admit and release any workflow change; none made.

## Material independent v14 correction
V11 `causalProofValid` could call a correlated **incomplete GitHub run** `complete`, without requiring completed/success or an immutable owner-pinned head SHA. Its readback could also accept a changed `change_id` or `revision` with the same operation ID. General Render provider ACK could misclassify an environment-group link as effect-complete even though group secrets are inherited and deployment still requires causal proof.

The new **dormant** v14 owner-port candidate enforces:
1. Immutable prior/intent identity (`change_id`, `revision`, `operation_id`, digest and pinned SHA) must match final owner readback; mismatch blocks/no replay.
2. GitHub completion requires exact repo/workflow/ref/event, workflow/run IDs, attempt, owner-correlated operation, admitted full head SHA, and `status:completed`/`conclusion:success`. Dispatch response or queued/failed run remains held.
3. Render PATCH acknowledgement may resolve **configuration-only**, explicitly `deploy_verified:false`. It does not prove a deployed release.
4. Render env-group link acknowledgement **never** resolves deployment or secret-access effects; preserve held/UNKNOWN without another POST until owner qualifies a true causal link/deploy readback.
5. Historical `v10-json-v1` SHA256(JSON.stringify(request)), explicit owner-grant/cost/release/stop/fence/lease gates and uncertain-write no-replay remain intact.

**Source/test exact GitHub blobs (immutable in commit `db5f2852657f3c53cdf2c693649a68bfd05029bb`):**
- [v14 owner port source](https://github.com/robert8p/Alpaca-Supabase-Populator/blob/db5f2852657f3c53cdf2c693649a68bfd05029bb/engineering/astra-operations-mcp/sites-v14/controller-owner-port-v14.mjs), Git blob `64ec5dbffe24b43aedc34fd2889b581371979aef`; SHA256 `3765624dcbd4bbd84310f097b5bef04f4f2b4f575cf18f2087f955d1c21e3da9`.
- [v14 synthetic acceptance tests](https://github.com/robert8p/Alpaca-Supabase-Populator/blob/db5f2852657f3c53cdf2c693649a68bfd05029bb/engineering/astra-operations-mcp/sites-v14/controller-owner-port-v14.test.mjs), Git blob `7274ab8e85e98041650d7e516026944eb984a461`; SHA256 `1c11fe6f543429e67191dfb8f8505cd62d49f3006ce3b7f474fe6c55457b30ba`. Both Git blobs independently matched original archive files byte-for-byte (including final newline).

**Archive, tests, independent readback:**
- Library `/ASTRA Operations/ASTRA_Operations_Causal_Settlement_Hardening_v14.zip`, ID `libfile_bb04eb59be00819186768a470cc50c6c`, size 1,034,995 bytes, **SHA256 `1ec8ca48013211a20530ed3e24829efe6d74aa7122ab4a85d593bf759073ec5b`**. Library rematerialized separately: exact byte/sha match and ZIP integrity passed.
- Embeds byte-identical v13 ZIP SHA256 `a0ba2e534b1cd4864dc414e42b3e1ee3a0136b87c39661d75a4aca324578d48f`. Contains manifest, all v13 source/tests, new v14 source/tests, official-schema notes and TAP evidence.
- `node v22.16.0`: 162/162 independent v13 baseline; 17/17 new v14 synthetic cases; **179/179 combined** including fresh ZIP extraction rerun. These prove source contract behavior only, **NOT real controller serialization, grants or live provider integration**.

## Provider/setup qualification
- Official docs: GitHub workflow dispatch API returns a run ID/URL (not success); workflow run API has `status`, `conclusion`, `head_sha` and read permission. Render PATCH does not deploy; env-group link exposes group variables/secret files to the service and can return sensitive raw values.
- Render scoped-key beta account eligibility still **UNKNOWN** (no supported entitlement tool). Native Sites `sites_list_plugin_eligibility` still unavailable. GitHub App installation and effective Actions:Write / read grants not verified. Current Basic ingestion identity controls writes and must never be passed to Sites. No credential, key or secret transfer; no speculative owner consent payload.
- Existing ingestion Render worker `srv-dbh9fko473hc739an8m0` remains the only allowed existing target, not to duplicate. Free Render background workers unsupported. Four write capabilities remain in backlog and remain blocked behind owner release/atomic port/current effective permission/cost gates.

## Next action and owner
1. **Existing ingestion controller:** only after current reliability repair admission, use issue #94 and immutable v11 contract to identify or implement the real owner-controlled durable request/outcome, logical and physical resource lock, stop/fence/lease guard and causal provider readback. Qualify 20-call concurrency, alternate keys/revisions, crash windows, unknown no replay. It owns default-branch workflow trigger decision.
2. **ASTRA implementation owner (same hourly task):** read issue #94 and ingestion branch for *real* port changes; apply stricter v14 rules to an owner-injected client only after verified semantics. Independently investigate provider schema and account-eligibility **only through approved safe tools**. No more mock-only changes claimed as live integration.
3. **Dot:** solely publish existing native Site/app/plugin after exact factual grant and release gates; consolidate routine results. Preserve native published source `3d260fbe95d3600c1519e28d49af7be36c9f4712`.

No new worker/controller/journal/Site/plugin/OAuth, no workflow/PR changes, provider calls, credential grants, trading, scanner changes, spending or production mutation. Do NOT retry interrupted N1 remote Git tree write (`feat/astra-operations-mcp-20261030` at `fb20e97`); N1 archived bundle commit `984892c6be8ddaae805ec305bf257111c196ee4b` remains non-published.

