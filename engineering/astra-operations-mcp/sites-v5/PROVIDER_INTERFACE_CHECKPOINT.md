# ASTRA Operations provider-interface qualification v5 — 2026-10-30

Owner: Assess MCP Plugin Opportunities implementation chat. No duplicate hosting executor, Site or plugin. Dot alone is the bounded native Sites publishing operator.

## Artifact
- Persisted complete source/test ZIP in Library: `/ASTRA Operations/ASTRA_Operations_Provider_Qualification_v5.zip`.
- SHA-256: `3072901d1c5a1a7983ccaeef5a368ef9d7db16102e21e46f5fbfaaa4128b0031`.
- Contains unchanged v4 Sites MCP handler and tests, new `provider_contract.mjs` and `test_provider_contract.mjs`, test-results, checkpoint, README, source digests.
- `node --test test.mjs test_provider_contract.mjs` passed 29/29 (13 original v4 + 16 new contract tests).

## Substantive work
- Added dependency-injected provider contract, not a network client or secret broker.
- Four fixed read-only operations: Render two allowlisted ingestion services, GitHub one qualification workflow, ingestion backfill status and job lookup.
- Verified fail-closed mock tests for wrong target/action/scope, broader permissions, control-capable ingestion Basic, untrusted source, absent owner, extra token fields, oversized responses, provider exceptions, redacted output and end-to-end mocked MCP status.
- Controller source contract checked: `astra_ingestion/api.py` GET `/api/backfill/status`, GET `/api/jobs/{id}`; `astra_ingestion/backfill_status.py` yields bounded `runs` list with `id`, `status`, `pages_committed`. The existing Basic credential also permits POST controls and must not be provisioned to Sites.
- No credentials attached; no provider live access verified; no app controllers modified.

## Next executable step
Await dot's actual Sites Site/project/plugin IDs, published revision and authenticated caller/tool-discovery readback. Reconcile against v4 source, run fresh-chat identity/status/tool discovery and unprovisioned-provider failure tests. Then, only with separate action-time grants, bind one host-native read-only provider integration at a time and verify target scopes, secret-free outputs/logs, and readback. Do not create another Site/plugin or a standalone OAuth server.

Hourly continuation remains `6ae4d6e1e2a48191aa7edaf9464f77e5`. Existing ingestion/scanner controllers retain sole app-operation authority.
