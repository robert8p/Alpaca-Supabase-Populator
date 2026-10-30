# ASTRA Operations v7 — native Sites connector candidate (2026-10-30)

**Implementation owner:** Assess MCP Plugin Opportunities chat. **Hosting owner:** dot. **Application controllers unchanged.**

## Verified native hosting
- Existing owner-private Site `appgprj_6ae4dcec2034819197d448ca2eea21a3`, origin `https://astra-operations.robert8p.chatgpt.site`, canonical plugin `plugin_asdk_app_sites_a5e127b6f02081918cde92d94b477c57`.
- Native publication `appgdep_6ae4e214b77481918e5102573e560ef9` succeeded; published source commit `3d260fbe95d3600c1519e28d49af7be36c9f4712`; env revision 0.
- This chat called `implementation_context` and `connection_diagnostics` successfully; Render inspect correctly returned `provider_adapter_not_provisioned`. **No real provider integration, fresh end-user-chat proof, or application control.**
- Exact native source Library `/ASTRA Operations/ASTRA_Operations_Native_Sites_Source_v1.zip` SHA256 `fd8d34becb219c575a6f9b437993d7fa7a02fc09af9c2bfbab9aed92fcec088f`; independently materialized and hash verified.

## Independent code and tests
- Full v7 archive Library `/ASTRA Operations/ASTRA_Operations_Native_Connector_Qualification_v7.zip`, SHA256 `8a62aa04bc0c865459b6786ecd142d25d46644a5db81fa2c30ecb8d11a399cc6`.
- Includes native source, v6 source, new `provider-connector-candidate.mjs`, 21 new tests, original 20 native tests, test output and action-time handoff.
- **41/41 tests passed**, source archive digest verified. Candidate is NOT bound to published route.
- Native Sites starter has request-scoped connected-app runtime `getContext()` and `invoke()`; no provider credential inheritance. Candidate validates host-enabled exact connector action, per-call host grant, owner identity, fixed target, structured response, size and target readback. No writes or retries.
- Render `get_service` and GitHub `fetch_file` are proposed supported native actions; GitHub fetch_file proves source presence, not workflow enablement. Ingestion remains unbound until controller-owned GET-only facade; existing Basic credential is control-capable and forbidden.

## Precise next step
Dot performs a **read-only native Sites connector context probe**, returning only connector ID, policy, action name and input schema for Render `get_service` and GitHub `fetch_file`. No provider call, credential, audience or Site change. If unavailable, record exact gap.
Implementation owner pins returned IDs, integrates only a reviewed grant-bound adapter and reruns tests; **no live provider call without separate exact action-time grant**. Dot alone handles any approved Site release. No duplicate Site/plugin/host.
Conditional confirmation text and rollback are in Library `/ASTRA Operations/NATIVE_CONNECTOR_HANDOFF_v7.md`.
Existing hourly successor `6ae4d6e1e2a48191aa7edaf9464f77e5` must continue independent qualification and reconcile dot's readback.
