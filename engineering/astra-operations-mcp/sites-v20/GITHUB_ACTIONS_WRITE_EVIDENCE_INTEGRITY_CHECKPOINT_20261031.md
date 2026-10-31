# ASTRA Operations MCP — GitHub Actions evidence-integrity and residual-grant checkpoint

**31 October 2026 UTC | Independent public API documentation/read-only repository reconciliation; NO v21 source change, controller integration, credential request or provider write.**

## Read-only owner state and provenance

- Existing ASTRA operations implementation branch prior checkpoint: `1afeded2b6bf965632ad194355a9a487d04f91f0`, `sites-v20/PROVIDER_SCOPE_RESIDUAL_RISK_CHECKPOINT_20261031.md`, blob `e43d3d9f25c3da6e32db5671f18f802b51bf8a5a`. Preserve its full Render scoped-key and GitHub Actions:write residual-risk inventory.
- Existing ingestion branch `feat/astra-ingestion-service` still at `280d37ac339d780a497878af473128e78d889f0e` in this run; `astra_ingestion/rpc_store.py` blob `b423c9cb6ca0adcdece631d12b36e00149dd5b1a` and `sql/astra_ingestion_rpc_v1.sql` blob `9cb1d522a8fab6660c1cbebd951dd4df7871da03` remain **job-specific**, not a verified cross-provider owner-native four-method atomic port. The implementation workflow blob `f36b4f21874de6afb141faca74bba1cd2d84e328` lacks `workflow_dispatch`, and the workflow path returned 404 on `main`. No live port, owner physical-resource reservation or GET-only Sites identity verified.
- Issue [#94](https://github.com/robert8p/Alpaca-Supabase-Populator/issues/94) is OPEN and already acknowledged in ingestion owner's backfill audit 96, deferred behind active reliability repairs. [Issue comment 6534994041](https://github.com/robert8p/Alpaca-Supabase-Populator/issues/94#issuecomment-6534994041) provides the immutable v11 contract at `db0efa4140ae6d59b4c8f36d0d0ebd39b5ff3cd0`. No redundant acknowledgement or owner interruption.
- Source-only v20 remains latest tested source: immutable `a04eba6336ed83554ae92c7957bfdefee70715de`, source blob `bf412614550ff93970264e5a3bdc4fabde716448`, previously verified **260/260 synthetic tests**. No fresh test run or v21 source revision is represented by this factual checkpoint.

## Newly verified GitHub provider-enforced Actions permission effects

Official [GitHub workflow-runs REST API](https://docs.github.com/en/rest/actions/workflow-runs), accessed 31 October 2026, explicitly lists **repository Actions: write** as the fine-grained token permission for all of these operations (subject to endpoint-specific access/context checks):

1. **Delete an entire workflow run** (`DELETE /repos/{owner}/{repo}/actions/runs/{run_id}`) and **delete all logs for a workflow run** (`DELETE .../actions/runs/{run_id}/logs`). These are materially destructive to provider-hosted audit/evidence availability.
2. **Re-run a workflow / failed jobs** (`POST .../actions/runs/{run_id}/rerun` and `.../rerun-failed-jobs`). A new attempt can share the original run ID, ref and SHA; v18's first-attempt-only causal guard must remain, and a later rerun cannot be silently accepted as proof of the original action.
3. **Cancel** and **force-cancel a workflow run**, the latter bypassing conditions that would normally keep a workflow running (e.g. `always()`).
4. **Approve eligible fork pull-request workflow runs** via the Actions endpoint, subject to the applicable GitHub trust/approval rules; this is an authorization effect beyond dispatch.

Official [GitHub Actions artifacts REST API](https://docs.github.com/en/rest/actions/artifacts) separately confirms **Actions: write** can **delete workflow-run artifacts**. **Actions: read** includes downloading workflow logs and artifacts. A write token therefore has evidence-destruction capability and also broader read capability; workflow logs/artifacts may contain sensitive data if producers mishandle output. This is a **capability inventory**, not evidence that this particular repository has such artifacts/secrets, or that an installation or token has been granted.

**Security consequence:** Even a repository-restricted, one-hour installation token with Actions:write is **not dispatch-only**, **not workflow-only** and **not evidence-immutable**. A controller allowlist does not reduce the provider-enforced rights of the underlying credential. This expands the residual risk already recorded for enabling/disabling workflows; dot must disclose run/log/artifact deletion, rerun, cancellation, and fork-approval effects in any future exact action-time grant assessment.

## Qualification and execution policy

- No new GitHub App installation, token, permission, provider write, workflow change or approval is authorized by this research. Actual installation, effective scope and secure secret destination remain UNKNOWN.
- Preserve the original owner-captured GitHub workflow dispatch HTTP 200 run ID, exact first-attempt `run_attempt === 1`, immutable pinned SHA, completion/success, and readback provenance. If run/log/artifact evidence is unavailable, deleted or contradictory, return HELD/UNKNOWN without replay; do **not** infer success or safely retriable absence.
- The existing ingestion controller alone, after its reliability/release admission, may implement the native `lookupExact/admitExact/reserveAndDispatchUnderOwnerGuard/readbackExact`, durable protected receipt/physical resource locks and a GET-only status interface, and may consider default-branch `workflow_dispatch`. Historical v10 `v10-json-v1` digest and all stop/fence/lease/expiry/grant/cost gates remain.
- A future action-time grant must explicitly disclose these broader provider privileges and verify exact account/installation, effective rights, repo/workflow/ref, secure credential destination, expiry/revocation, operation, owner release/fence and side effects. Dot alone owns the Site/plugin publication and any narrowly scoped user confirmation.
- Keep all four missing provider write capabilities in backlog; existing ingestion worker `srv-dbh9fko473hc739an8m0` must not be duplicated. Render environment-group linking remains blocked before admission for unqualified secret inheritance/collisions/deploy; Render service PATCH remains configuration-only, not deployment.
- **No Site/plugin/OAuth/host/controller/journal/executor/worker creation, production provider call/write, credential access, workflow/default-branch/PR mutation, paid commitment, scanner/trading action or security weakening.** No retry of N1's unpublished interrupted Git tree write.

**Disposition:** A materially broader, documented GitHub Actions:write destructive and audit-evidence capability inventory is preserved. No v21 code/archive change is justified; latest v20 source tests remain historical synthetic 260/260, not live integration. Continue read-only owner issue/HEAD reconciliation and non-disruptive research until ingestion owner releases the deferred interface.
