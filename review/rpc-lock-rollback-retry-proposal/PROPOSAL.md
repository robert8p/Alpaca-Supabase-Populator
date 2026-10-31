# Confirmed PostgreSQL lock-abort retry proposal

Status: local analysis only; unselected, unimplemented, unqualified and undeployed. No production requests, runtime changes, permission changes, provider requests, or workflow mutations were made for this analysis.

## Recommendation

A narrowly scoped retry can avoid some worker exits after transient global-gate contention, provided the client receives a complete, trusted PostgREST PostgreSQL error response with exactly SQLSTATE `55P03`. Retry only that failed database RPC, in a fresh request transaction, with the same serialized operation and payload. Keep every uncertain transport/write outcome fatal. Keep the existing database authentication, capability, task/run fencing, live-lease and integrity checks authoritative on every attempt.

This is complementary resilience. It does not reduce maintenance's gate hold, establish sustained recovery, or replace the measured-cost repair. A finite retry limit also means persistent contention can still reach the existing fatal/reconciliation path.

## Exact deployed source inspected

The retained deployment receipt identifies revision `3ee4db2a79c081ffb65ef0d7ec2a04228d69fb1d`, deployment `dep-dbi8ud942hec73cpm7qg`, live at `2026-10-30T12:36:45.668499Z`. The current local bytes below match the immutable Git blob pins recorded for that exact revision in `evidence/replacement-3ee4-release-gates-v71.json`.

| File | SHA-256 | Git blob |
| --- | --- | --- |
| `astra_ingestion/rpc_store.py` | `323140a1a26314a23d9c620d2f47cd03a5dca1cd9028290f77af8fee75c2f6ea` | `b66962c2a4dec7427e8373a2aa79624ec7217c10` |
| `astra_ingestion/worker.py` | `c137839bee667ad34bf974b7edb6ba95ed2462c19e7def273a7c0a6d5d26cde1` | `2c4b10b6f2cf5f39e20ad70179ddc94fc0f3c58f` |
| `astra_ingestion/backfill_worker_v2.py` | `b682b2425fd226296cdc141ff5936a49a7cac336fe859a02ebbd7faa4adf49c2` | `e6c75bfbe0ec11198af39229edb49b662f19ed24` |
| `astra_ingestion/backfill_massive_relay_v2.py` | `76a6eb68f543afdd9637fcafc7d5900cd6e27a802de5ba61b0ea4965cc7b8841` | `9f97aa492261c85eae54af5f3162430ff588b4a6` |

`RpcStore._call_once` currently closes `HTTPError` without reading its body. It maps 401/403 to `RpcAuthenticationError`; other HTTP errors become `RpcPersistenceError` with the fixed reason `HTTP_ERROR`. Transport failures remain `TRANSPORT_ERROR`. `RpcStore._call` attaches only a safe local operation label and rethrows. `worker.main` logs a bounded record and returns 1. There is no 300-second sleep in this code; the observed five-minute delay is external restart behavior, not a timer this proposal would change.

`BackfillWorker.run_once` reserves, fetches once, constructs a page payload, calls `backfill_commit`, then calls `backfill_verify`. Therefore a retry confined to the commit RPC can retain the already fetched provider page. Retrying `run_once`, the provider method, or the whole reserve/fetch/commit sequence would be the wrong boundary.

Source references: `evidence/replacement-approved-relay-worker-deployment-v71.json`; `evidence/replacement-3ee4-release-gates-v71.json`; the four source files above; `tests/ingestion/test_rpc_store.py`; `tests/ingestion/test_rpc_failure_observability_v71.py`.

## Transaction evidence and the trust boundary

PostgreSQL identifies `55P03` as `lock_not_available`; its documentation recommends using SQLSTATE rather than localized message text. `lock_timeout` aborts a statement waiting too long to acquire a lock. An unhandled PL/pgSQL error aborts the function and surrounding transaction. An error caught by a function is different: the function may continue and the request may commit.

PostgREST documents that each API resource request runs in a transaction, database failures roll that transaction back, PostgreSQL error fields are forwarded as JSON, and class `55` maps to HTTP 500. Thus a genuine unhandled database `55P03` returned by this endpoint is positive evidence that this request's transactional writes did not commit. This does not roll back a previously successful reservation or provider request; those must remain intact.

HTTP 500 alone is insufficient. PostgREST also permits SQL to set `response.status` and return an ordinary value without aborting. A JSON object containing `code: "55P03"` is therefore not a universal rollback certificate for arbitrary HTTP endpoints. The classification must be tied to this fixed HTTPS RPC and its reviewed source contract. Normal application outcomes here use `{ok, result}` or `{ok, error}` envelopes; those must never become rollback evidence. The staged SQL source scan found no `response.status` / `response.headers` override or HTTP/dblink side-effect call. Retained live readback binds the authenticated dispatcher to `a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520` and private backfill dispatcher to `28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44`. Before any implementation is selected, source qualification should explicitly bind the complete dispatch/eligible-operation closure and its exception/response contract; an old excerpt is not a substitute for that closure.

The actual gate uses `pg_advisory_xact_lock`, whose lock is released at transaction end. This is not the session-level advisory-lock behavior, which can survive rollback. Sequence values are another qualification limit: PostgreSQL can consume sequence numbers even when a transaction aborts. The guarantee should concern committed application rows, budgets and receipts, not gapless identity values or absence of server error logs.

Primary documentation inspected:

- [PostgreSQL 17 error codes](https://www.postgresql.org/docs/17/errcodes-appendix.html), `55P03` and the SQLSTATE guidance.
- [PostgreSQL client connection defaults](https://www.postgresql.org/docs/18/runtime-config-client.html), `lock_timeout`. The documented behavior is the relevant statement-abort rule; this is not a claim that production runs PostgreSQL 18.
- [PostgreSQL 17 PL/pgSQL error handling](https://www.postgresql.org/docs/17/plpgsql-control-structures.html#PLPGSQL-ERROR-TRAPPING), unhandled error versus exception recovery.
- [PostgREST 13 transactions](https://docs.postgrest.org/en/v13/references/transactions.html), request transactions, aborts and custom response status.
- [PostgREST 13 errors](https://docs.postgrest.org/en/v13/references/errors.html), four error fields and HTTP status mapping. The stable PostgREST transaction documentation was also checked; no deployed PostgREST version was identified in the retained local receipts.
- [PostgreSQL 17 explicit locking](https://www.postgresql.org/docs/17/explicit-locking.html), transaction versus session advisory locks.
- [PostgreSQL sequence behavior](https://www.postgresql.org/docs/16/functions-sequence.html), nontransactional sequence allocation.

## Narrow initial behavior

Use an explicit local retry allowlist of `backfill_claim`, `backfill_reserve`, `backfill_commit`, `backfill_reuse_commit`, and `backfill_verify`. This covers the observed claim/commit/reuse-commit failure positions plus their reservation and verification boundaries. Keep every other operation unchanged initially, including planner, maintenance, API control, relay dispatch and provider/Edge Function calls. The allowlist is a client resilience policy, never an authorization mechanism.

At the fixed transport boundary, recognize a confirmed lock-abort only when all of these conditions hold:

1. The failed request is the existing POST to the exact admitted project HTTPS origin and RPC path, using the existing TLS validation, headers and redirect refusal. The error response URL must match that endpoint exactly, with no other host, path, query or fragment.
2. The actual HTTP status is 500; content type is JSON and content encoding is absent or identity. Do not inspect bodies for 401/403, redirects, other status codes, or a foreign URL.
3. Read at most a separate small error bound, proposed 8 KiB, under the same request deadline. Require complete framing/EOF and a matching declared length when present. A read exception, oversized/truncated/trickling body, incompatible encoding or malformed framing remains uncertain and fatal.
4. Decode strict UTF-8 JSON with the existing duplicate-key and non-finite-number rejection. Require exactly the four PostgREST error keys `code`, `message`, `details`, `hint`, with ordinary string/null field types, and native string `code == "55P03"`. Do not use text search, exception messages, SQL context strings, a nested provider field, SQLSTATE class matching, or a success/application envelope.
5. Discard the body after classification. A private typed internal result may carry a fixed local label, but must not retain or log the remote message, details, hint, URL, request, headers, payload, exception chain or credentials. Continue using bounded local enum labels in logs. Merely attaching a reason-code string to an arbitrary exception must not make it retryable.

The retry loop should be inside the RPC transport call, below `BackfillWorker.call`, and limited to that allowlist. Serialize the request once before the first send; every retry sends byte-identical operation/payload data and the same existing capability through the usual authentication boundary. The provider result, raw body, digest, request descriptor, cursor, generation, fence and reservation stay unchanged. There is no new claim, provider fetch, reservation, lease extension or deadline reset to make a retry succeed.

Proposed starting bound: at most three total sends (two retries), delays 0.25 seconds then 0.75 seconds, and one shared 15-second monotonic logical-call deadline beginning before the initial send. Do not reset the deadline after each `55P03`; cap each subsequent network timeout by the remaining allowance and the current 15-second transport maximum. Check the deadline before and after every read and before sleeping/sending. Do not retry a request whose response is lost or whose deadline expires. These values are a qualification proposal, not an implemented or performance-qualified setting.

The existing urllib reader documents a deadline plus one outstanding socket-timeout tail. Reusing that mechanism cannot honestly promise a hard 15-second wall bound. Qualification must measure/verify the bound under a trickling/blocking read, retain at most that existing bounded tail, and launch no further request after expiration. A hard wall-clock cancellation design would be separate work; do not conceal it inside this small change.

Every fresh RPC transaction repeats server-side capability validation and the existing ownership/fence/lease checks. If credentials are revoked, the run is stopped, a generation/fence changes, or a lease expires during backoff, return the current authentication/ownership outcome and stop retrying. Do not extend an attempt deadline or add a readback lease requirement where the existing verifier deliberately permits verification of a committed page after lease expiry. An expired caller budget is also a stop condition, never a reason to reconstruct a new claim.

After the third confirmed abort, propagate a fixed sanitized persistence failure through the current fatal/reconciliation path. After any ambiguous response on any attempt, stop immediately, even if earlier attempts were confirmed aborts. Do not automatically issue a compensating `defer`, `recover`, or another mutation.

## Expected benefit and limits

Three ordinary 3-second gate-wait attempts separated by 0.25 and 0.75 seconds can span a roughly 8-second gate hold; this is arithmetic, not a production latency promise. If an attempt succeeds within the budget, the worker continues its existing stack and avoids that process exit. The extra cost is at most two additional database requests/waits per eligible logical call, with no additional provider request or committed reservation for the failed transactions.

The first aborted claim can later select a different task; that is valid because no first claim result committed. A failed reservation must consume no durable reservation counter or pacing update. A commit retry must keep the already committed reservation and already fetched page. A verification retry must repeat only verification after the page's successful commit. Retained-reuse commit may re-read database source material in its fresh transaction under its unchanged validation contract; it is not a provider re-fetch.

No current worker log contains a parsed positive `55P03` classification because the deployed client never reads error bodies. Database/worker timing correlation does not reconstruct the HTTP body. The design can therefore be supported by the documented transaction contract, but actual successful classification on the managed path remains unobserved. Unknown writes remain fatal even where database commit functions have duplicate-receipt branches; this proposal does not use those branches as a general timeout-retry license.

## Required meaningful qualification before selection/publication

1. **Positive transport classification:** genuine HTTP-error response objects with complete bounded PostgREST `55P03` JSON, followed by success; verify two/three sends only, identical encoded bytes, no repeated serialization, closed responses, unchanged headers/endpoint and bounded sanitized logs.
2. **Fail-closed matrix:** 401/403/429/502/503/504; 500 with HTML, foreign URL, redirect, unsupported encoding, duplicate fields, unknown/missing/extra keys, wrong code type/case, nested `55P03`, localized message containing the code, `57014`, `40001`, `40003`, `40P01`, `PGRST003`, malformed JSON, oversized/truncated bodies and stream errors. Each must make exactly one send for that outcome and no retry. A custom status/application envelope is ineligible.
3. **Budget and retry transitions:** repeated confirmed aborts exhaust at three sends; backoff and reads share one monotonic deadline; no send after deadline or cancellation; a timeout/reset/decode failure after a confirmed abort terminates immediately. Preserve the existing unknown-write exception and logging behavior, including hostile string subclasses and concurrent independent calls.
4. **Real PostgreSQL rollback:** two disposable connections; hold the existing transaction advisory gate in one and call the exact authenticated RPC path in the other to produce native `55P03`. Verify rollback and fresh-transaction success after release. Add a controlled late lock failure after an application-row/budget write to prove that response-level abort classification is not limited to errors occurring before the first write. Assert application rows/counters/receipts are unchanged after the failure; allow sequence gaps.
5. **End-to-end worker counts:** with the real worker call order, fail claim, reservation, commit, reuse commit and verification separately. Assert one successful claim generation/page attempt; at most one successful reservation; one provider fetch; one final committed page/count increment; one matching independent readback. Commit retries must reuse the exact fetched raw body/hash, and verify retries must never invoke commit or fetch again.
6. **Unknown committed outcome:** commit successfully on the test server, then lose/drop the HTTP response. Verify immediate fatal propagation, zero resend, zero provider re-fetch and preserved durable receipt for the existing reconciliation path. Also test unknown reservation response causes no provider call.
7. **Authority changes between attempts:** credential revocation/expiry, owner/generation/fence changes, run pause/stop, expired task lease and attempt deadline. The next genuine server check must reject, with no client lease renewal, reset or bypass. Successful-postcommit verification retains its existing lease-independent contract.
8. **Endpoint provenance/contract:** bind the exact complete public/auth/private/eligible-function source closure; prove no successful custom-status error-shaped response can enter this classification. Where a compatible disposable PostgREST service already exists, exercise actual native-error HTTP mapping and rollback through it. Mock HTTP responses and direct PostgreSQL tests prove different layers and must not be reported as a managed production-path test. Do not create a production endpoint, provision new credentials or install a new service as part of this proposal.

Retain existing uncertain-outcome and observability tests. Amend the older “never read any error body” invariant only for the new tightly gated 500/error-parser case; all other no-read and zero-secret-log cases stay enforced. After any selected implementation: independent review, complete ingestion qualification with zero unexpected skips, and exact published-head CI are required before a separately authorized deployment. No such implementation or activation is selected by this document.
