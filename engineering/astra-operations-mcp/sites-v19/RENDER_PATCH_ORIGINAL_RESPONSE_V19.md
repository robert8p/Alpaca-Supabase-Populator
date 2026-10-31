# ASTRA Operations v19 — owner-original Render PATCH response binding

**Scope:** Dormant source-only implementation owned by the existing ASTRA Operations MCP engineering owner. No new provider adapter, controller, Site, plugin, journal, credential or workflow. Ingestion and EQ17 application controllers alone own execution. Dot alone owns publication of the existing private Site/plugin. No actual Render PATCH was sent.

## Documented provider semantics and source defect

Render's official [Update service API](https://api-docs.render.com/reference/update-service) specifies `PATCH /v1/services/{serviceId}`, HTTP **200** with an updated service object whose `id` identifies the service and whose `autoDeployTrigger` can be `off`. Its request field `autoDeployTrigger` supersedes the deprecated `autoDeploy`; you cannot send both. **PATCH changes configuration and does not itself deploy**; a separate deploy API is required when the change must be applied to the running service. Render's [deploy documentation](https://render.com/docs/deploys) confirms separate deployment semantics.

V18's `causalProofValid()` accepted an object with `kind:'provider_ack'`, `source:'controller_captured_provider_response'`, `acknowledged:true`, the expected workspace/service and `auto_deploy_trigger:'off'`. Nothing in the source bound that acknowledgment to the **original** guarded PATCH response, HTTP status, requested field, actual response `id` or returned auto-deploy setting. A later GET showing the desired value, or a generic service-level acknowledgment from another operation, could therefore be mistakenly projected as a completed approved PATCH. The v19 regression fixture reproduces this as `state:'complete'` in v18 without any original PATCH receipt. This is a *source-level projection defect*, not a claim that the real owner has made an incorrect provider call.

## V19 correction and owner contract

The new dormant `controller-owner-port-v19.mjs` requires a **bounded owner-captured original PATCH response projection**, persisted in the original reservation or exact historical lookup and returned identically by `readbackExact`. The immutable `patch_ack` is limited to:

- `kind:'render_service_patch_http_response'`, `source:'controller_captured_render_patch_response'`, `method:'PATCH'`, `status_code:200`;
- `path:'/v1/services/<exact service id>'`, original immutable `operation_id`, `change_id`, `revision`, `digest`, exact `workspace_id` and `service_id`;
- `requested_field:'autoDeployTrigger'`, `requested_value:'off'`, `response_service_id:<same target>`, `response_auto_deploy_trigger:'off'`, `provider_effect:'configuration_updated_not_deployed'`.

No raw Render service response or nested environment/secret values may be copied into this projection. Exact original/readback mismatch, missing original ACK, GET-only observation, non-200 status, different service, unexpected setting, malformed path or extra raw-response fields **block** completion with `original_render_patch_ack_unverified_no_retry`. There is no replay or provider call to settle the uncertainty. A proven configuration-only success returns `configuration_only:true`, `deploy_verified:false`. Historical readback remains side-effect free. The owner must still establish actual durable storage and atomic stop/fence/lease/physical resource locking and provider-response capture: passing fixtures never proves those properties.

The v10 public input still uses legacy `params.auto_deploy:false` for this exact preexisting capability; the owner must explicitly map that to the current Render HTTP request `{autoDeployTrigger:'off'}` and prove its actual account/provider-enforced rights, cost, action-time approval, effective target, secure credential destination and release gate before any live operation. No new Render credential or provider request is authorised here. If the provider omits `autoDeployTrigger` in the actual update response, this source fails closed pending a controller-owned causal proof design, rather than inferring success from a subsequent GET.

## Preserved previous controls

V18 first-attempt-only GitHub run settlement, original POST 200 returned run-ID binding, immutable pinned SHA, terminal status/conclusion, v10 `v10-json-v1` digest, stop/fence/lease/expiry/release/grant/zero-cost, unknown/no-replay, blocked new Render environment group linking (secrets/collision/deploy), blocked free Render worker creation, and all four future write capability backlogs are unchanged. Existing worker `srv-dbh9fko473hc739an8m0` must never be duplicated.

## Regression evidence and ownership

V19 has 17 additional synthetic tests: v18 false-positive reproduction, direct source fix, positive bounded original PATCH response, historical no-dispatch, missing/late/changed ACK, GET provenance, status, service, request/response field, immutable identity, raw response leak, wrong method and preserved unrelated gates. Historical v18 tests remain unmodified; combined expected count is 240 (223 + 17). A fresh ZIP extraction, CRC/manifest verification and test rerun are required before treating the archive as verified.

Existing ingestion-owner issue [#94](https://github.com/robert8p/Alpaca-Supabase-Populator/issues/94) remains **already acknowledged in backfill audit 96 and deferred** behind active reliability work; the exact immutable v11 owner adoption contract is [commit `db0efa4` at this path](https://github.com/robert8p/Alpaca-Supabase-Populator/blob/db0efa4140ae6d59b4c8f36d0d0ebd39b5ff3cd0/engineering/astra-operations-mcp/sites-v11/docs/OWNER_PORT_ADOPTION_CONTRACT.md). Ingestion owner alone may implement cross-provider atomic port, GET-only Sites identity and default-branch workflow dispatch. Do not request redundant acknowledgement or interrupt reliability repair.

Independent pending provider setup: Render scoped-key beta account eligibility UNKNOWN because no exposed account entitlement tool; GitHub App installation, effective Actions:Write/Read grants, exact secure destination and token TTL/revocation unverified. Native Sites `sites_list_plugin_eligibility` action absent. No broad classic Render key substituted, no premature owner approval requested. No production provider calls or spending.
