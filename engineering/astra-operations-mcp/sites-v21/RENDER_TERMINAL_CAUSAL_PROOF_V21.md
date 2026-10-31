# ASTRA Operations MCP v21 — immutable original terminal causal settlement guard

31 October 2026 UTC. **Dormant source-only controller-injected caller**. No provider adapter, production operation, controller integration, new principal, app, or worker.

## Newly reproduced defect in original v20 source

A historical or initial owner receipt can already be in terminal `CONFIRMED` state but contain **invalid, absent or contradictory causal proof**. V20 checked terminal `state` consistency and the original Render `patch_ack` / GitHub dispatch `dispatch_ack`, but assessed the **success causal proof only on later readback**. The following locally executed regressions against unchanged v20 demonstrated false completion without any provider write:

- **Render PATCH:** original `CONFIRMED` record's `causal.source` was `uncorrelated_later_service_get`, while later `CONFIRMED` readback supplied `controller_captured_provider_response`; both original and later exact PATCH acknowledgements matched. V20 incorrectly returned `complete`, `causal_verified:true`, `configuration_only:true`.
- **GitHub Actions:** original `CONFIRMED` record had workflow `run_attempt:2` (not the authorized first attempt), later `CONFIRMED` readback changed it to `run_attempt:1` using the same original captured HTTP 200 dispatch run ID, immutable HEAD SHA and repo/ref. V20 incorrectly returned `complete` and `workflow_success_verified:true`. Missing or failed original terminal causal proof behaved similarly.

Both cases show later proof being used to **retroactively upgrade a purportedly immutable terminal result**. This differs materially from legitimate `ACCEPTED`/`DISPATCHING` to `CONFIRMED` progression; the latter must remain eligible for real owner-causal settlement.

## Narrow v21 source correction

In `controller-owner-port-v21.mjs`, after the existing original/readback identity and terminal-state checks, require:

```js
if(expected.state==='CONFIRMED'&&!causalProofValid(expected,request))
  return blocked('original_terminal_causal_proof_unverified_no_retry');
```

The original `expected` record comes only from controller-injected durable lookup/reservation and is **not** MCP request input; the correction cannot authenticate that source, which still awaits a genuine owner-native port. This guard blocks a terminal original lacking the required proof **even when later readback appears successful**. No provider replay, reservation, cancellation, credential, workflow or service change is performed. Already `REJECTED` terminal rows remain subject to their existing state-invariance and no-replay semantics. A nonterminal original may transition to valid completed readback only with preserved original Render PATCH/GitHub dispatch proof.

Tests cover original absent/false/uncorrelated Render causal proof; original first-attempt vs rerun discrepancy for GitHub; both historical and new reservation-shaped paths; valid terminal and legitimate pending-to-confirmed transitions; unchanged Render environment-group pre-admission hold. The test port is **synthetic** and does **not** demonstrate controller-native serialisation, transport capture, credential permissions or production integration.

## Preserved contracts and production blockers

- Existing owner still exclusively holds `lookupExact`, `admitExact`, `reserveAndDispatchUnderOwnerGuard`, `readbackExact`, durable owner change/physical-resource lock and PREPARED/DISPATCHING/UNKNOWN no-replay. No authenticated GET-only Sites status facade exists; existing Basic credential remains prohibited for Sites.
- V20 original outbound Render PATCH body must exactly hash transmitted UTF-8 `{"autoDeployTrigger":"off"}`, 27 bytes SHA256 `8525a932af773f1d2b9a91210582e00f3280c1a281fc34155d82d6b825946d2d`, and preserve original HTTP 200 and bounded identity; PATCH is configuration-only, never deploy proof.
- V18/V17 GitHub exact original HTTP 200 workflow dispatch run ID, admitted SHA, repo, workflow, ref, terminal `completed/success`, **first `run_attempt===1`**, remain required. A late provider GET or rerun cannot replace the original terminal evidence. Unknown/deleted proof stays HELD with no replay.
- New Render environment-group linking remains blocked **before** admission for inherited secrets, collision uncertainty and automatic-deploy effects. Existing worker `srv-dbh9fko473hc739an8m0` must not be duplicated; Free background worker remains unavailable, no paid plan grant. Four future write capabilities remain backlog.
- Preserve historical `v10-json-v1` = SHA256(JSON.stringify(request)), idempotency and immutable change/revision, owner stop/fence/lease/expiry, release, real effective grant, zero-cost rules.
- Render scoped-key beta entitlement unknown and available documented broad Services Read&Write, Env-group Read and Deploy Run residual powers must be disclosed; GitHub Actions:Write permits rerun/delete/cancel/enable/disable and workflow approval effects, Actions:Read logs/artifacts access. Connected GitHub installation `repository_selection:all` is **not** a Sites grant or Actions:Write verification. See immutable provider checkpoints `1afeded2b6bf965632ad194355a9a487d04f91f0`, `7e068dadac6280b783d071aca4d1408e5215f60f`, and `974507f92f94ea05af95f73b4e2bd0eb0ada7203`.
- Ingestion `feat/astra-ingestion-service` remains at last read-only `280d37ac339d780a497878af473128e78d889f0e`, existing issue #94 already acknowledged in backfill audit 96 and deferred behind repair. Do not interrupt or request redundant acknowledgement. Only ingestion owner may extend port, GET-only facade, and default-branch `workflow_dispatch` after release gates. Dot alone publishes Site/plugin and seeks specific action-time approvals.

**Qualification boundary:** This correction is an additional source-only necessary condition; no live controller-native atomic integration or provider operation has been verified.