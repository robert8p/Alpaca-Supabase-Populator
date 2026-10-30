# Managed Massive relay: exact security review candidate

**Status: LOCAL REVIEW ONLY — ACTION-TIME USER CONFIRMATION REQUIRED.** No relay migration, Edge deployment, production worker integration, live readiness probe, provider request, or credential configuration has been performed by this agent. Independent ingestion continues through the existing controller and worker.

The candidate is concrete and locally qualified. It expands persistent permissions and introduces a new recipient for the existing worker capability token. Existing blanket approval does not authorize these actions under the user's latest boundary. The production hold must remain until the user confirms this exact reviewed change at action time.

## Existing authorization and the proposed change

Root's saved readback, `replacement-relay-existing-auth-reconciliation-v2.json`, observed at 07:26:31 UTC on 2026-10-30, establishes that the relay table/helper/worker operations were absent. The anonymous gateway role and internal RPC owner are NOLOGIN, non-superuser and do not bypass RLS. There was one valid API credential and one valid worker credential; credential values were not inspected.

Root subsequently supplied the stage3 dispatcher definition hash at 07:32:30 UTC. The normalized definition reproduced in the local PostgreSQL stage3 fixture has **exactly the same hash**:

`0616b84ec99710083681c2ed7bc2b7dd7acff9ef2f809d84b84c5f724a71fe96`

The complete before/after authorization diff is `replacement-managed-relay-rpc-auth.diff`. It adds exactly two worker operations and a dispatch branch after the existing authentication and global lock. The API allowlist, gateway/JWT checks, capability expiry/revocation checks, post-lock credential recheck, security-definer boundary, function metadata and transaction error handling remain unchanged.

| Boundary | Existing behavior | Exact proposed addition |
|---|---|---|
| Existing Edge function | `population-top3000-news-v1` accepts `{attempt_id, token}`, uses the old `massive_news_claim_v1` contract, and requires N01 / `news-published-202608-202609`. | An explicit `x-astra-replacement-relay: astra-massive-relay-v2` branch handles the replacement protocol. Requests without that header retain the original handler. |
| Worker token recipient | The worker sends its existing `X-Astra-Ingestion-Token` to the fixed ingestion RPC. | **The same token would also be sent to the existing Edge function**, which forwards it only to the fixed RPC on the same admitted Supabase origin. This is a new trust boundary even though the origin and token are unchanged. |
| RPC capability | Existing worker operations cannot invoke a managed-key relay. | Worker-only `backfill_relay_probe` and `backfill_relay_dispatch`. API capabilities remain unable to call either operation. |
| Managed provider credential | The old Edge handler uses its own existing Massive/Polygon managed key for its old pipeline. | The new branch may use that key for six admitted replacement read-only endpoints. The key remains inside Edge and is sent only in the HTTPS Authorization header to `api.massive.com`. |
| New persistent table | None. | `astra_ingestion_v1.backfill_relay_dispatches_v2`, with SELECT and INSERT granted only to `astra_ingestion_rpc_owner_v1`. RLS is enabled; UPDATE, DELETE and TRUNCATE are not granted and an immutable trigger rejects alteration. |
| New internal helper | None. | `astra_ingestion_v1.backfill_relay_v2(text,jsonb)`, SECURITY INVOKER with an empty search path, EXECUTE only for the existing internal RPC owner. PUBLIC and inherited nonowner grants are removed. |
| Approval consumption | Current production metadata is held. | One installation audit plus `candidate_applied`, `applied_at` and `applied_migration_sha256` merged into the existing approval object. Existing authority/scope/history fields are preserved. |
| Worker integration | Production worker remains byte-identical to stage3. | A separate four-line review patch would wrap the existing provider when the existing RPC deployment is configured. It is present only as a proposed file and patch. |

The old Edge handler's source is byte-identical after removing only the added import, factory initialization, and explicit header branch. Its baseline source has 15,606 characters and SHA256 `29269e3c092a3377e2ae329a3a193d87ef66dbf36655b040a8603719e9490dfe`. The exact small change is in `replacement-managed-relay-edge-handler.diff`.

## Credential and request dataflow

1. The existing worker sends the existing public project key, its own capability token, and the explicit relay header to `https://oxzabweahkoimtevbbny.supabase.co/functions/v1/population-top3000-news-v1`. No new environment credential is required.
2. The Edge branch forwards only that public key and capability token to `https://oxzabweahkoimtevbbny.supabase.co/rest/v1/rpc/astra_ingestion_rpc_v1`. It does not forward Authorization, service-role credentials, arbitrary headers, destinations or SQL.
3. An authenticated `backfill_relay_probe` must authorize the active fixed run and current security approval **before the branch reads any provider key**. Readiness returns only `{"ready": true}` or `{"ready": false}`. It proves authenticated managed-key presence, not entitlement to every dataset or coverage completeness.
4. Fetch requires a live task claim, exact current page/generation/fence/reservation, and at least one second of lease/attempt time. The RPC independently validates the frozen member/anchor pairs, mission dates and family, then regenerates and compares the entire request JSON. It inserts a unique `(task_id, generation, page_no)` dispatch marker before external acquisition.
5. Edge verifies the ticket's task, run, generation, page, request digest and finite expiry. It makes one GET to the fixed Massive origin with a maximum 25-second deadline and no redirects. The managed key goes only in `Authorization: Bearer …`; the worker token is never sent to Massive.
6. The response is bounded to 3 MiB, with exact original-byte SHA256 and a base64 envelope. Only the existing safe request/rate-limit headers may leave Edge. Credential reflection in plain text, URL encoding, base64 or JSON escapes is rejected without returning body bytes or reflected headers. No headers or credentials are logged by the new branch.
7. Python verifies the envelope, digest and request binding, then uses the existing parser and durable queue commit/defer path. Oversized pages retain an honest bounded prefix and drive the existing adaptive page policy. A Massive opaque cursor is not falsely treated as adjustable. HTTP failures preserve status and Retry-After; they never create a provider-absence conclusion.

A repeated dispatch ticket cannot cause another provider GET. An uncertain pure read can be deferred into a new generation with a new counted reservation; it is never replayed under the consumed reservation. An uncertain dispatch acknowledgment reports consumption as unknown instead of falsely reporting it unused.

Official Massive REST documentation explicitly supports the proposed Bearer header form, as an alternative to query-string API-key authentication. The relevant primary reference is [REST API Quickstart — Authenticate Your Request](https://massive.com/docs/rest/quickstart), verified 2026-10-30. Its example uses `Authorization: Bearer YOUR_API_KEY`. This was documentation verification only; no live provider request was made.

## Exact mission scope admitted by the relay

The run remains `fixed3000-20250901-20260731-v1-20261030`, with the accepted cohort hash `2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec` and manifest hash `4134b415e2c26fcde9fced749c0d54ef51376e23f0d2f8c6ce9ef562f9fab99f`. A live task alone is insufficient authorization: the relay also checks exact frozen member IDs and retained anchor ticker pairs. It does not admit new members or aliases.

| Family / kind | Read-only path | Independent date/scope restriction |
|---|---|---|
| REF01 / `massive_reference` | `/v3/reference/tickers/{frozen_anchor}` | One frozen anchor; exact as-of date within 2025-09-01 through 2026-07-31. |
| N01 / `massive_news` | `/v2/reference/news` | One frozen anchor; publication start at or after 2025-09-01 04:00 UTC, end before 2026-08-01 04:00 UTC, start no later than end. These are the full target's New York calendar boundaries. |
| N02 / `massive_dividends` | `/stocks/v1/dividends` | Frozen anchors; explicit `UNBOUNDED_PROVIDER_EVENT_HISTORY`, `retain_boundary_crossing_events=true`, and unchanged target dates. |
| N03 / `massive_splits` | `/stocks/v1/splits` | Same explicit all-history event policy and frozen anchors. |
| S01 / `massive_short_volume` | `/stocks/v1/short-volume` | Reporting dates within the inclusive target, ordered start/end. |
| S02 / `massive_short_interest` | `/stocks/v1/short-interest` | Settlement dates within the inclusive target, ordered start/end; no invented publication cutoff. |

The two corporate-action requests deliberately fetch all entitled event history for their fixed anchors. Declaration, ex-dividend, record, payment, execution and effective dates can straddle the target. Restricting the request to only one of those date fields would lose relevant boundary-crossing evidence. This all-history acquisition is an explicit part of the proposed approval; returned events remain source observations and do not automatically become target-period research coverage.

The existing planner admits fixed scopes; there is no general-purpose worker enqueue operation in the reviewed RPC. The added checks independently reject a mismatched anchor, a valid member paired to a different ticker, out-of-window dates, the wrong family, or an action task lacking its explicit event-history policy. Pagination still relies on the existing immutable source-page/continuation contract and the exact current task cursor.

## Installation approval gate and exact transport binding

The current production object under `metadata.massive_relay_security_confirmation` remains `state=AWAITING_ACTION_TIME_CONFIRMATION`. Root's 07:30:30 readback also records the latest controlling user instruction and `independent_ingestion=CONTINUE_WITH_EXISTING_PERMISSIONS`. **This current hold cannot pass the candidate preflight.**

Only a newly recorded explicit action-time confirmation can satisfy the gate. The required fields bind the following exact values:

| Approval field | Required value |
|---|---|
| `state` | `APPROVED_AT_ACTION_TIME` |
| `review_id` | `managed-massive-relay-v2-review-20261030` |
| `scope_sha256` | `7e253852f3173c9c3b7ba6d919e4d8abe82cb949424096beee56ddc0e2c20fbe` |
| `confirmation_source` | `EXPLICIT_USER_ACTION_TIME_CONFIRMATION` |
| `confirmation_ref` | The actual new user-confirmation reference; no synthetic or prior blanket approval. |
| `approved_at` | Actual approval timestamp, at most 15 minutes old and no more than one minute in the future at installation. |
| `candidate_applied` | `false` before first application; consumed to `true` by the migration. |
| `approved_migration_sha256` | `4be1c6d145949f4cda35a1cef7772da93137e3f102f045f1a7507ea66a16652d` |
| `approved_rpc_dispatch_sha256` | `0616b84ec99710083681c2ed7bc2b7dd7acff9ef2f809d84b84c5f724a71fe96` |
| `approved_edge_index_sha256` | `d1cf7bd54392ad834682249cfc33e00cbdcef343fc88053a98c2134330308f97` |
| `approved_edge_module_sha256` | `bb13314362122485c0f755664ee9e5bd035157df4f03e4984c295ae04b099a83` |
| `approved_python_adapter_sha256` | `76a6eb68f543afdd9637fcafc7d5900cd6e27a802de5ba61b0ea4965cc7b8841` |
| `approved_worker_base_sha256` | `90d048a6c535f7f768050c25e396a923e0e4e211457016757e30af16daface3e` |
| `approved_worker_integration_sha256` | `4427fe549e86922e0a01afde4aad632fd6d2d7c44225dc7ec0ee5dba3eb17a6e` |
| `approved_worker_source_sha256` | `b682b2425fd226296cdc141ff5936a49a7cac336fe859a02ebbd7faa4adf49c2` |

These are review requirements, **not a populated approval record**. Only synthetic records were used in the disposable test database. The live approval object has not been changed by this agent.

The Supabase migration tool wraps submitted SQL and repeats its exact body inside a dollar-quoted history insert. The final gate therefore hashes the exact sentinel-delimited original migration bytes, then reconstructs and compares the complete known wrapper. It accepts either the exact raw file or that exact wrapper, with the fixed migration name, a safe 20-letter delimiter and bounded account identifier. The history body must be byte-identical to the executable body. Unknown prefix/trailing SQL, an altered history copy, repeated executable sentinels, wrong migration name, invalid delimiter or account syntax are rejected. It does not strip arbitrary SQL or silently normalize whitespace.

The existing dispatcher definition must also match the approved stage3 hash. A later independent RPC change requires a fresh reconciled candidate and approval; it cannot silently inherit this approval. Installation is single-use: the new table/helper must be absent, the approval must be unconsumed, and the successful transaction adds one audit record and marks the exact approved migration applied.

## Qualification and independent review

The final exact candidate passed **33 focused Python-suite tests** in 5.357 seconds: 15 actual PostgreSQL cases, 14 adapter cases, 3 proposed-integration cases and the JS-suite wrapper. The JS suite separately passed **16 handler cases**. Without a PostgreSQL DSN, 33 tests were discovered, 18 executed and 15 database cases intentionally skipped. Six Python compilation units and two Node syntax checks passed.

The PostgreSQL fixture reproduces the qualified stage3 runtime, including feature reuse, identity, nonminute coverage, retained S02, planning, adaptive pages, canonicalization, family fairness and recovery. It proves exact current reservation admission, concurrent replay exclusion, all six native request shapes, immutable dispatch evidence, unchanged source counters, successful native page commit/readback, adaptive oversized-page recovery, revoked-approval denial, ten approval mismatches, and seven malformed wrapper variants. The real wrapper's history copy is verified byte-for-byte.

An independent agent reviewed the frozen scope and reported no remaining blocking finding within it. That review found two earlier issues, both fixed and rechecked: JSON escapes could hide a printable punctuation credential, and invalid UTF-8 could produce changed text with an original-byte hash. The final escape scanner checks between decoding layers. Invalid UTF-8 now retains the original-byte count/hash and a bounded original prefix, with no fabricated complete `raw_body`; HTTP and Retry-After semantics remain intact.

The tests do not prove live key availability, provider entitlement, live Edge startup or actual provider service behavior. Those remain gated live validations after explicit confirmation. A readiness response alone is not coverage evidence.

## Revocation and rollback requirements

The runtime probe and dispatch re-read the approval state. A reviewed revocation can return that state to held/revoked while preserving the audit and unrelated metadata; subsequent relay authorization then fails. An external GET already admitted before revocation may finish within its bounded deadline. Existing queue lease/fence checks still govern any result commit.

A code rollback should restore only the reviewed four-line worker integration and the three Edge branch insertions, using the recorded base hashes. It must preserve queue state, original response receipts and retained completed work. A permission rollback should remove only the two added worker operations and relay dispatch branch from the then-current RPC, revoke the relay helper/table grants, and retain immutable dispatch/audit evidence. Restoring an old whole dispatcher definition would risk discarding later independent work and is not the proposed rollback.

No rollback action has been executed. Any future reapplication remains subject to a fresh exact review and confirmation; controller automation must not clear or fabricate the hold.

## Review files

- `replacement-managed-relay-qualification-v2.json`: exact file hashes, tests and limits.
- `replacement-managed-relay-review-scope-v2.json`: canonical scope whose SHA256 is pinned above.
- `replacement-managed-relay-rpc-auth.diff`: exact before/after RPC authorization change.
- `replacement-managed-relay-edge-handler.diff`: original-handler preservation and branch insertion.
- `../review/massive-relay-v2/worker-integration.patch` and the proposed worker file: root-owned integration review only.
- `replacement-managed-relay-review-manifest-v2.json`: frozen review package; it is not a production publish/apply manifest.
