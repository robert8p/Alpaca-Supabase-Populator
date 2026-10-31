# Strict confirmed-lock-abort retry: local implementation review

## State and scope

**Locally implemented and qualified; publication and deployment are held.** The runtime change is confined to `astra_ingestion/rpc_store.py`. The existing worker, provider adapters, credentials, endpoint, SQL functions, permissions, schedules and restart policy are unchanged. This is a bounded resilience measure that complements the maintenance-cost repair; it is not evidence that the shared gate or the five-minute restart symptom has recovered.

The final active qualification passed **48 tests, zero failures, errors or skips**, in 12.496 seconds. Those comprise 16 new transport/worker cases, two new workflow-admission cases, six new actual disposable-PostgreSQL cases and 24 existing RPC boundary/observability regressions. The independent reviewer ran the 42 non-PostgreSQL cases successfully and found no static classifier or resend-scope blocker. The independent reviewer also inspected the six actual-PostgreSQL cases. A separate combined run then passed all **56 retry/shared-repair cases**, zero skips/errors/failures, in 20.576 seconds, with 82 actual dependencies and no unexpected base differences. These results do not constitute exact published-head CI or a production-positive classifier observation.

Qualification used published base `a3bc0520e624054b278e46682b04cebb33e9b677`, whose runtime retains the deployed 3ee4 source. The subsequent reporting-only head `a3e48a080c70c802a2fbb1a1bb5db29b0d7aee62` also preserves that runtime. The baseline copies in `baseline/` bind it. The actual-read dependency audit verifies 71 files against the immutable published tree: exactly one intended runtime replacement, four new actual-read dependencies and no unrelated existing-blob changes. The main workspace contains older foundation files, so publication must use the immutable remote base and the explicit replacement/addition list rather than copying the whole workspace.

## Retry admission

Only these six operation strings can enter the retry branch:

| Operation | Same-RPC boundary |
|---|---|
| `backfill_claim` | Repeat the same capability/source/kind/lease request after its transaction abort. |
| `backfill_reserve` | Repeat the same fenced reservation; do not perform the provider request here. |
| `backfill_commit` | Repeat the same retained response, hash, count, cursor and claim bytes. |
| `backfill_reuse_commit` | Repeat the same fenced retained-source transaction. |
| `backfill_verify` | Repeat the same committed-page verification request in another transaction. |
| `backfill_plan_next` | Repeat the same bounded planner request; the aborted cursor/task writes do not advance the plan. |

The planner is included because it is an actual outer-gate restart path. Its exact source closure and a native PostgreSQL gate-abort test establish the same transactional contract for this operation. An unchanged planner retry then admits one member and advances the cursor to two exactly once.

Admission requires all of the following in the **HTTPError returned by opening this exact RPC request**:

- Integer HTTP status 500 and the exact fixed HTTPS RPC URL.
- JSON content type, absent or identity encoding, unambiguous framing, and no conflicting content-length/transfer-encoding headers.
- A complete error body at EOF, no more than 8,192 bytes, matching any declared length and read before the original response deadline.
- Strict UTF-8 JSON with no duplicate fields or nonfinite constants.
- Exactly the four native fields `code`, `message`, `details`, `hint`; native string code `55P03`, string message, and string-or-null details/hint.

The implementation uses a private boolean confirmation path, rather than the earlier proposal's private typed marker. It is reachable only from the transport's `opener.open` HTTPError branch. A caller-created exception, a reason-code label, message text containing `55P03`, a provider response, an application `ok/error` envelope or a success-response stream failure cannot authorize a resend. Remote message/detail/hint values are discarded and never added to logs or exceptions.

Every other HTTP status, SQLSTATE, malformed/incomplete body, transport interruption or ambiguous successful-response failure preserves fatal handling. In particular, a native-shaped HTTPError raised while reading an already opened HTTP 200 stream is treated as `TRANSPORT_ERROR`, not rollback evidence.

## Bounds and preserved behavior

The request is serialized once into immutable bytes and one `Request` object. Retries use those identical bytes, headers, operation, endpoint, claim and provider response. There are at most **three total sends**, with 0.25-second and 0.75-second delays between attempts. All attempts and error-body reads share the existing 15-second deadline; each later socket timeout is reduced to the remaining budget. The existing urllib read model still permits one outstanding socket-timeout tail. This is not a hard 15-second wall-clock guarantee.

The retry occurs inside one persistence call. It does not repeat `BackfillWorker.run_once`, reacquire a provider page, reconstruct a cursor, reserve another provider request, change a generation, renew a lease outside the original RPC behavior, or relax a fence. Each resend traverses the unchanged authentication, capability, gate, lease, deadline, run-state, reservation and integrity checks. Normal behavior already implemented by that RPC remains in place. A later ownership/authentication rejection stops according to its existing disposition.

After three confirmed aborts or an exhausted shared deadline, the worker receives a fixed sanitized `LOCK_ABORT_RETRY_EXHAUSTED` fatal reason. An unknown outcome after an earlier confirmed abort still terminates immediately. Interrupts are not caught. Existing signal/current-call behavior is unchanged; no new cancellation mechanism is claimed.

The bounded database error can avoid a process restart only if the real gateway produces the qualifying response and a later attempt succeeds within these bounds. Persistent contention, mismatched gateway responses and all excluded failures still follow the existing restart/reconciliation behavior.

## Actual transaction evidence and its limits

The six database cases execute the authenticated SQL RPC with its actual disposable gateway role and capability checks. Each attempt uses a new real PostgreSQL transaction. The test adapter converts a native database exception **after connection rollback** into the documented PostgREST four-field HTTP error. That HTTP layer is simulated. No PostgREST server, production RPC, provider endpoint or production credential was used.

The fixture loads the six freshly captured RPC roots and 18 freshly captured callees. All 24 sources reverse their established disposable identifier substitutions exactly to the captured hashes. Published planner/batch and adaptive-page migrations supply the fixture's original schema dependencies. The broader callable closure is matched independently to the fresh live function catalog.

| Actual PostgreSQL case | Observed result |
|---|---|
| Outer advisory gate blocks claim | Native `55P03`; first transaction rolled back; second claim commits generation 1/page attempt 1. |
| Late lock after commit-path writes | Task/page/run/probe rows roll back; a sequence value is consumed; identical second commit succeeds; provider fetch count stays one. |
| Commit succeeds but its ACK is lost | One page and one record remain committed; exactly one commit send; no automatic readback or resend; fatal transport reason. |
| Reservation succeeds but ACK is lost | One reservation remains; no second reservation send; zero provider fetches. |
| Authority changes after the aborted attempt | Owner, generation, run fence, expired claim lease, paused run, revoked credential and expired credential are rechecked; no page is committed and no provider refetch occurs. |
| Planner waits on the native gate | First transaction aborts without tasks/cursor progress; identical retry plans one member once and makes no provider request. |

Sequence gaps and emitted database logs can survive rollback. The proof is about transactional domain rows/counters/receipts; it does not claim all observable effects disappear.

Local PostgreSQL was **16.15**. The current production compatibility gate uses PostgreSQL 17.11, but the earlier a3bc or 3fdd CI results do not qualify this changed runtime. New exact published-head CI is required before deployment. The dedicated ingestion workflow must run all 24 new cases with zero skips. Without a DSN, that workflow errors; other contexts explicitly skip the six PostgreSQL cases. Both admission paths are directly tested without opening a database connection.

## Exact source and catalog closure

`retry_source_closure.json` and `retry_closure_sources.json` bind **73 callable functions, 44 write tables and 31 noninternal triggers** for the six selected operations. The outer/private/delivery wrapper branch edges are explicit; all other reachable helper bodies are conservatively traversed. Unrelated relay, maintenance-entry and legacy operations are not admitted by the client allowlist.

The public SQL wrapper only selects the authenticated dispatcher. The dispatcher authenticates before its transaction advisory gate, rechecks credentials after the gate, and wraps ordinary outcomes in the controlled `ok/result` or `ok/error` envelope. Its expected-error handler catches the named AI/data-conversion errors, not `55P03`. The selected closure contains no network invocation, dynamic SQL execution, session advisory lock or response-status customization. A caught error returned as an ordinary HTTP 200 envelope cannot trigger this retry.

The feature summary's `compute_feature_sessions_remediated_v1` and `feature_grid_remediated_v1` strings are source-hash references passed to `pg_get_functiondef`, not invocations. Its actual external call is the exact immutable SQL `compact_output_hash_remediated_v1`, guarded by source hash `3d2af9589f2171964f77ecb2a5739e7417d12775833c0b3c884a61438689dae5`; the retained definition only hashes its supplied binary values. Regex matches for INSERT target column lists are table syntax, not external function calls.

The fresh 16:33–16:41 catalog receipts close the scoped database expression boundary. All 44 write relations are ordinary persistent tables. Their 82 defaults are literals, `CURRENT_USER`, `clock_timestamp` or identity generation; 50 checks contain built-ins and the already closed page-limit-cap helper. All 44 foreign keys are nondeferrable `NO ACTION` for update and delete; there are no rewrite rules. The 64 current write-table policies have only literal `true` or absent `USING/WITH CHECK` expressions and zero function dependencies. All 84 indexes use eight standard `pg_catalog` B-tree/hash operator classes; the 16 expression/partial indexes use built-in JSON/text operators, `lower`/`coalesce`, literals and boolean comparisons, with no custom function dependency. The external hash function's exact source and full metadata are freshly captured.

The 11 retained read roots resolve to an 18-relation recursive closure containing two views, plus 12 ordinary bar partitions captured separately. There are no foreign relations. Both exact view definitions use built-in casts, projections, hashes and joins. The three applicable retained-read policy expressions contain literal/provider-array checks and have zero function dependencies. This closes the concrete view/FDW/RLS paths without expanding to an unrelated estate inventory. The remaining effective-gateway configuration visibility limit is separate and explicit.

The closure includes the current `backfill_shared_refresh_v2` source (`b18…`). The separately prepared field-cache optimization (`7f538…`) is still a separate selected/installed-state decision. If it installs before this retry, the final closure must explicitly bind and review the resulting source. A source pin from before that installation cannot silently serve as current evidence.

## Gateway visibility limitation

At 16:18:52, the retained connector-session and allowlisted PostgreSQL role/database catalogs contained no selected `pgrst.db_pre_request`, `pgrst.db_tx_end`, `response.status` or `response.headers` settings. The connector ran as `postgres`; this is **not a live gateway-session observation**. No available connector exposes all effective PostgREST environment/file configuration.

The documented Supabase pre-request configuration uses `ALTER ROLE authenticator SET pgrst.db_pre_request` and reload. The negative catalog observation is relevant evidence, but does not establish that an external override is impossible. A pre-request hook with nontransactional effects could be outside the RPC function closure. Do not convert missing visibility into proof that every request-level side effect rolls back. Final deployment review must retain this explicit boundary assumption or obtain effective configuration evidence through an already authorized route; no new credential, service, bypass or configuration change is proposed here.

## Remaining fatal paths

Every operation outside the exact six remains nonretryable. The deployed replacement worker can still encounter fatal RPC failures in `backfill_defer`, `backfill_material`, `backfill_reuse_read`, `backfill_reuse_verify`, `backfill_breadth_material`, `backfill_identity_material`, `backfill_identity_source_read`, `backfill_identity_source_commit`, `backfill_massive_archive_commit`, and `backfill_feature_reuse_commit`. Startup `health`, the legacy worker operations, and relay operations are also outside this change. These are explicit remaining restart paths, not implicitly covered operations.

All operations, including the six selected ones, still stop on ambiguous transport/success responses, authentication rejection, unrecognized SQL errors, retry exhaustion or violated integrity/ownership rules. Provider retries remain governed by the existing worker/database policy.

## Evidence and reproduction

- `qualification_final.json`: final 48-case producer run and actual opened/imported dependencies.
- `independent_unit_qualification_v74.json`: independent 42-case non-PostgreSQL run and static scope review.
- `review/recovery-v74/combined-release/combined_active_dependency_qualification_v74.json`: separate combined 56-case actual-read/import run for retry plus the shared-field repair.
- `dependency_audit.json`: 71 actual dependencies compared to the immutable published tree; one runtime replacement, four additions, no unrelated blob changes.
- `retry_source_closure.json` / `retry_closure_sources.json`: exact operation routes, sources, catalog pins, write tables, triggers and resolved syntax markers.
- `baseline/manifest.json` and baseline source copies: deployed runtime derivation.
- `qualification_attempt_*.json`: retained unsuccessful fixture/loader attempts and the earlier successful 46-case run. Their failures are not hidden or represented as production/runtime regressions.
- `runtime.patch`: the exact runtime delta from the deployed baseline.

The local runner is `qualify_rpc_lock_abort_retry.py --root <exact staged repository> --output <receipt>`. It follows the repository's `ASTRA_INGESTION_POSTGRES_TEST_URL` convention. The staged tree must supply the unchanged immutable-base dependencies; the audit rejects accidental stale foundation overwrites. A second actual-PG run requires coordination with the other local fixture author.

## Primary transaction references

- PostgreSQL 17 error codes: https://www.postgresql.org/docs/17/errcodes-appendix.html — SQLSTATE `55P03` is `lock_not_available`; classify by code, not localized message.
- PostgreSQL 17 PL/pgSQL error handling: https://www.postgresql.org/docs/17/plpgsql-control-structures.html#PLPGSQL-ERROR-TRAPPING — unhandled errors abort the transaction; caught errors have different continuation semantics.
- PostgREST 13 errors: https://docs.postgrest.org/en/v13/references/errors.html — native four-field database error format and default `55*` HTTP 500 mapping.
- PostgREST 13 transactions: https://docs.postgrest.org/en/v13/references/transactions.html — request transactions, rollback on database failure, and response customization. Documentation version is explicit; the effective production server version/configuration was not observed by this qualification.
- PostgreSQL sequence behavior: https://www.postgresql.org/docs/17/functions-sequence.html — consumed sequence values are not reclaimed on rollback.
- Supabase pre-request configuration: https://supabase.com/docs/guides/api/securing-your-api and https://supabase.com/docs/guides/database/debugging-performance — documented role-setting hook configuration, without proof that all external configuration is visible.

**Release hold:** root's independent final boundary decision must retain the gateway visibility limitation; selected source/catalog pins must be current; the exact candidate must be published and pass every actual exact-head gate with explicit new-test execution. Deployment then remains root's decision under the existing mission. The earlier independent unit receipt must not be relabeled as full boundary approval. This local work makes no production change.
