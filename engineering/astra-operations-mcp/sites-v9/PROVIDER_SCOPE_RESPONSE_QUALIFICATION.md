# ASTRA Operations v9 — provider scope and secret-safe output qualification
**Date:** 2026-10-30. **Owner:** existing implementation-owner chat; dot alone owns native Site hosting/release. No other site, plugin, executor, controller, provider permission, or credential created.

## Baseline retained
- Private native Site `appgprj_6ae4dcec2034819197d448ca2eea21a3`; plugin `plugin_asdk_app_sites_a5e127b6f02081918cde92d94b477c57`.
- Last verified published deployment `appgdep_6ae4e214b77481918e5102573e560ef9`, source `3d260fbe95d3600c1519e28d49af7be36c9f4712`, env revision 0.
- Fresh implementation-owner plugin call: `implementation_context` release 0.4.1, writes disabled; `connection_diagnostics` render/github/ingestion all false, provider access not verified. Static `hosting_verified=false` is stale metadata, not a failed publication.
- Sites action `sites_list_plugin_eligibility` and native connector-context/schema inspection not exposed in dot's available inventory. No evidence of account denial. Native read_only is connector-wide reads, not action-specific. `getContext` is cached hints only.

## Offline source and tests
- Library archive `/ASTRA Operations/ASTRA_Operations_Provider_Qualification_v9.zip`, Library ID `libfile_c915829260648191bbc951fe1fd09d82`.
- **Archive SHA256** `04bb44fdaed6b8d23702693c5fa743442d92f34acd514a8d37d61c00372b6345` (zip integrity checked).
- Includes original v8 modules/tests, the unchanged published native source and 4 new v9 pure JS files: strict provider response projection and provider-permission classification, each with tests.
- **119/119 local Node tests passed:** 45 v8 candidate + 54 new v9 + 20 native published-source tests. No production calls, provider access, credentials, Site deployment, controller changes or cost incurred.
- New render projection requires exact service ID, workspace `ownerId` and type; returns safe allowlisted fields only, never full service config/environment/secret data. GitHub source fetch returns source presence only, not workflow active; workflow state requires a different Actions GET endpoint. Wrong URLs, hashes, resource IDs, plain-text provider responses and overlarge payloads denied. Pure test fixtures only.
- v9 permissions classifier always reports `approved:false` and `provider_call_permitted:false`, including hypothetical structurally correct inputs. V8 validator's `admissible:true` is shape-only, NOT a real action-time consent or entitlement.

## Independently checked provider permission facts, 2026-10-30
- **New: Render scoped API keys entered private beta 2026-10-27**, not verified enabled for this account. Relevant docs: https://render.com/blog/scoped-api-keys-private-beta ; https://render.com/docs/scoped-api-keys .
- Scoped `Services: Read` is **workspace-wide services access**, not service-ID-specific. The `Environment variables and secret files: Read` permission **can view secret values**; exclude it and all other secret-bearing categories. Service creation/configuration requires `Services: Read & write`, not suitable for the ASTRA read-only plugin.
- Classic Render API key carries creator's permissions across **all joined workspaces**; backend allowlisting cannot narrow credential. Docs: https://api-docs.render.com/reference/authentication .
- Render `GET /v1/services/{serviceId}` returns `ownerId` camelCase (not `owner_id` used elsewhere): https://api-docs.render.com/reference/retrieve-service .
- GitHub `Get a workflow` needs `Actions: Read` and returns workflow `state`; `fetch_file` needs `Contents: Read` but does not show workflow state. `workflow_dispatch` requires `Actions: Write`, a separate control authority outside this plugin. Docs: https://docs.github.com/en/rest/actions/workflows .
- GitHub App selected-repo installation and effective permissions still need separate verification. App installation tokens last ~one hour. No App created.
- Existing ingestion Basic is control-capable and excluded; a controller-owned GET-only facade remains required.

## Highest-value missing capabilities / successor
1. Dot checks if supported `sites_list_plugin_eligibility` can be exposed. Until then native Sites connector deployment stays blocked, not denied. Do not guess connector IDs, create OAuth servers or rely on cached hints.
2. For direct Render fallback, verify whether **this exact Render account** has scoped API key early-access, the ability to exclude all secrets and writes, credential storage/revocation and cost. A broad classic key requires explicit broad-risk disclosure, not a representation as scoped.
3. GitHub workflow status could use an app with selected repo and `Actions: Read`; workflow dispatch needs `Actions: Write` and controller-only authorization. Do not confuse source fetch with workflow state, nor request write authority by default.
4. Preserve and reuse both existing application controllers. Worker creation, env attachment, GitHub workflow dispatch and scanner operations do not belong to this read-only plugin.
5. Before even an action-time proposal, establish actual owner/provider/account, effective **provider-enforced** permissions, exact target, secure secret destination, expiry/revocation, operational/cost effects, and independently verified owner-specific consent. Not enough evidence now to send one.

No notifications from this engineering task to Rob; routine evidence for dot. Existing hourly successor `6ae4d6e1e2a48191aa7edaf9464f77e5` retains bounded scope. Full checkpoint and test evidence also inside ZIP.
