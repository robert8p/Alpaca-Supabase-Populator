# ASTRA Operations v13 — provider side-effect qualification and deferred owner-port handoff

**Date:** 2026-10-30. **Maturity:** tested source only. No live app-controller port integration, no provider credentials/calls, no Site/plugin publication, no new host/controller, no paid operation and no workflow change.

## Verified source/test artifact
- Library: `/ASTRA Operations/ASTRA_Operations_Provider_Effect_Qualification_v13.zip`
- Library file: `libfile_3b9c14e0c52c8191a2b892803fa04dbd`
- **SHA-256:** `a0ba2e534b1cd4864dc414e42b3e1ee3a0136b87c39661d75a4aca324578d48f`
- Size: 977,361 bytes; independent Library rematerialization matched original SHA and exact bytes; ZIP CRC clean.
- Contains exact v11 source/test archive SHA-256 `1e44c4de036ca565d4aaad669f2621d6e358b73c616c2edb25415a8e7775696f`.
- **162/162 source-only tests pass:** original v11 152 + v13 ten new; v11 native 20 and N1 122 remain distinct historical test populations, not added to this new total.
- New source `v13/candidate/lib/provider-effects-v13.mjs` and tests `provider-effects-v13.test.mjs`. See `v13/docs/PROVIDER_EFFECTS_AND_OWNER_HANDOFF.md`.

## New, material official provider findings
1. `render_link_environment_group` is security-impacting: linking grants recipient service access to **all environment variables and secret files** in the group, may include `envVars.value` and `secretFiles.content` in API response, and triggers a service deployment. No raw response logging/echo; no link without exact owner-authorised group contents *metadata*, project/environment membership, protected-environment and secret/deploy effects. Official: https://api-docs.render.com/reference/link-service-to-env-group and https://render.com/docs/configure-environment-variables .
2. `render_update_worker`: `PATCH /v1/services/{serviceId}` updates configuration but **does not deploy**; a separate deploy operation would require its own release/authorisation. `autoDeployTrigger:'off'` replaces deprecated `autoDeploy:'no'`. Existing worker `srv-dbh9fko473hc739an8m0` was already off in previous verified readback; owner must freshly reconcile for no-op and avoid redundant writes. Official: https://api-docs.render.com/reference/update-service .
3. `github_workflow_dispatch`: current API returns a run ID/URL (not proof of completed workflow). Requires separate real controller correlation and run/head SHA readback. Official: https://docs.github.com/en/enterprise-cloud@latest/rest/actions/workflows .
4. Render Free background workers unsupported; `render_create_worker` remains backlog until exact real plan and cost authority established.

The new pure-source module exposes bounded *safe projections* of hypothetical provider responses, but cannot authorize any operation or establish real causal settlement. All four missing capabilities remain scoped, blocked and assigned to existing application controller.

## Read-only ingress owner and handoff status
- Existing owner: ingestion controller https://chatgpt.com/c/6ae206a6-9524-83ed-b103-7c23bcfe51e5; implementation branch head at inspection `08bea176e39174f8c39f62caebae79d5cb50cdcf`.
- Existing deferred issue **[#94](https://github.com/robert8p/Alpaca-Supabase-Populator/issues/94)** remained open without comments/owner acknowledgement. No active controller handoff execution assumed; do not interrupt its independent repair.
- Existing source shows job-specific RPC/idempotency, worker stop/lease/fence and ingestion provider-page receipt, **not** evidenced atomic cross-provider `lookupExact/admitExact/reserveAndDispatchUnderOwnerGuard/readbackExact` port.
- Implementation workflow `.github/workflows/astra-ingestion-qualification.yml` lacks `workflow_dispatch`; same path absent on default `main`. No GitHub App installation or Actions:Write verification.
- Existing Basic ingestion credential is control-capable and forbidden for Sites. Real GET-only controller identity/facade absent.
- Render scoped API-key private beta account entitlement **UNKNOWN** (no supported read-only entitlement/permission tool exposed). Sites native `sites_list_plugin_eligibility` absent from dot's available inventory; not a denial.

## Exact executable successor — existing hourly task, same owner
1. **ASTRA Operations implementation owner:** check issue #94 and ingestion implementation branch read-only for actual owner acknowledgement/new port. Compare any *real* controller interface to v11 owner-port contract plus the v13 provider-effects controls; do not report synthetic tests as live integration.
2. **Ingestion controller owner:** when its existing admission/repair schedule permits, respond to #94 with durable receipt/idempotency/physical resource lock/stop-generation/lease/guard/readback mapping, or precise missing interface. Decide independently whether default-branch `workflow_dispatch` is useful and authorised. No new journal/executor or workflow change from ASTRA.
3. **Dot:** routine consolidation and sole release ownership of private Site `appgprj_6ae4dcec2034819197d448ca2eea21a3` and canonical plugin `plugin_asdk_app_sites_a5e127b6f02081918cde92d94b477c57`. Preserve successful native source commit `3d260fbe95d3600c1519e28d49af7be36c9f4712`.
4. Only after verified exact provider identity/effective permissions/secure destination/revocation/expiry/resource/cost/secret and deploy effects should dot seek a **specific** action-time consent. Neither `getContext` nor scope-shaped proposals establish access.

Existing hourly task: `6ae4d6e1e2a48191aa7edaf9464f77e5`, Europe/London schedule unchanged. N1 archived bundle commit `984892c6be8ddaae805ec305bf257111c196ee4b` was not published; do not retry remote interrupted mutation. Preserve v10 historical SHA256(JSON.stringify(request)) / `v10-json-v1` digest records.