# ASTRA Operations — native connector engineering checkpoint v8 (2026-10-30)

Implementation owner: [Assess MCP Plugin Opportunities](https://chatgpt.com/c/6ae4ce37-54f0-83eb-9e51-6447e6a4d6ba). Dot exclusively owns native Site releases and provider setup. Ingestion and scanner controllers retain all app-operation authority.

## Verified live state (read only)
- Existing owner-private Site `appgprj_6ae4dcec2034819197d448ca2eea21a3`; canonical plugin `plugin_asdk_app_sites_a5e127b6f02081918cde92d94b477c57`; endpoint `https://astra-operations.robert8p.chatgpt.site/mcp`.
- Last supplied successful deployment `appgdep_6ae4e214b77481918e5102573e560ef9` saved version `appgprj_6ae4dcec2034819197d448ca2eea21a3~appgver_122f230524348191ba47fa72f00f9461`, actual tracked source commit `3d260fbe95d3600c1519e28d49af7be36c9f4712`, env revision 0.
- This execution independently called actual `implementation_context` and `connection_diagnostics` tools: succeeded; Render/GitHub/ingestion adapters each **false**, `provider_access_verified=false`. Published `hosting_verified=false` is **stale static source metadata**, not a new failed publication. No live provider calls were made.
- Materialized and hash-checked canonical native source Library ZIP SHA-256 `fd8d34becb219c575a6f9b437993d7fa7a02fc09af9c2bfbab9aed92fcec088f` and v7 full ZIP SHA-256 `8a62aa04bc0c865459b6786ecd142d25d46644a5db81fa2c30ecb8d11a399cc6`. Reused the verified 41 baseline tests.

## v8 substantive source and tests
- Full **self-contained** ZIP Library `/ASTRA Operations/ASTRA_Operations_Native_Connector_Qualification_v8.zip`, Library ID `libfile_e3de52de56d081918497ffe3d87657e3`, SHA-256 **`ae4a6d5bdcdfa72d7339667de2154585aa3b1f505957bedd48b5c927703fac6a`**.
- Dot handoff Library `/ASTRA Operations/NATIVE_CONNECTOR_HANDOFF_v8.md`, ID `libfile_f0524164a98081919cd600c611d4a808`.
- Includes untouched native/v7 source baselines, new `lib/provider-connector-v8.mjs`, `lib/native-context-probe-v8.mjs`, shared `lib/schema-shape-v8.mjs`, tests, read-only native status/projection overlay, exact diff, hashes, README, independent test evidence.
- **103/103 Node tests passed**, including **fresh re-extraction** rerun and independent verification of all 9 manifest-listed file checksums.
- Key v7 issue repaired in source-only candidate: resolve `connectorsForRequest()` **on each tool invocation**, not at import time. Per-call trusted grant binds exact actor/Site/action/resource, read-only scope, revocation and expiry; checked before and after schema preflight to catch intervening revocation.
- Owner-only no-invoke connector-context probe emits only connector ID, policy, action and normalized structural JSON Schema; descriptions, defaults, unknown semantics and secret argument names are excluded or denied.
- Strict schema drift detection, fixed Render/GitHub target allowlists, response minimization and redaction, exact GitHub HTTPS host/branch/path/SHA verification, no uncertain retries. GitHub `fetch_file` only proves source presence, not workflow enablement.
- Source-only native overlay corrects static hosting evidence and exposes GitHub source provenance without asserting provider access. It is **NOT deployed**; existing native code remains unchanged.

## Genuine outstanding gates
1. Dot's **read-only Site-connected-app context readback** with exact connector IDs, enabled policies and safe structural input schemas for Render `get_service` and GitHub `fetch_file`. This cannot be inferred from existing ChatGPT plugin tool metadata.
2. Verify that native Sites supplies a **trusted grant decision and revocation** for each exact provider action/target. The current native starter documents `getContext` and `invoke`, **not** an independently verified `verifyHostGrant` interface. Do not replace it with a self-issued grant or unconditional true.
3. Independently validate that target Render services and GitHub workflow file are current. No provider read is authorised yet.
4. Dot obtains separate exact action-time Render and GitHub grants only after (1)–(3), then owns any approved private Site release and rollback.
5. Ingestion controller provides a proven GET-only identity/facade; its control-capable HTTP Basic is **forbidden**. Fresh end-user-chat discovery and approval/login reduction measurements remain.
6. No trades, app controllers, scanner gates, new Sites/plugin, OAuth server, credentials, persistent access or paid commitments were touched.

## Executable successor
Dot should use the existing Site and **non-invoking owner-authenticated** `connectorsForRequest().getContext()` introspection, returning only safe connector ID/policy/action/schema plus whether enforceable native grant/revocation is exposed. Use the v8 handoff. If introspection needs a Site code change/release, obtain exact action-time Site-release confirmation first; do not alter deployed service opportunistically. If unsupported, record precise capability gap and retain private hosted tools. Implementation owner then pins verified values, tests the realistic host interface, creates a reviewed minimal overlay for dot, and does not call providers before the distinct grants. Maintain existing hourly successor `6ae4d6e1e2a48191aa7edaf9464f77e5`, no duplicate executor. Stop on verified full implementation or explicit stop.

State: **LOCAL_V8_QUALIFIED_HOSTED_BOOTSTRAP_VERIFIED_PROVIDER_BINDINGS_UNGRANTED**. This is not completion.
