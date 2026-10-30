# Controller-owned atomic port qualification — exact boundary

**No new controller runtime or journal is provided.** `candidate/lib/controller-owner-port-v11.mjs` is a source-only caller/parser to be used with a controller-injected port only after the existing application owner qualifies that port. Four abstract methods are required:

| Method | Owner-side requirements |
| --- | --- |
| `lookupExact({idempotency_key,request_digest})` | Durable historical lookup by authenticated principal and exact key; mismatched digest, changed revision or another principal must refuse; lookup allowed after stop/expiry but cannot trigger mutation |
| `admitExact({request,request_digest})` | Resolve **owner-stored** immutable change/revision and action-time confirmation; verify real provider effective grants, zero incremental cost, release gate, allowed exact target and workflow eligibility. Trust neither MCP caller-supplied permission flags nor caller-derived resource labels |
| `reserveAndDispatchUnderOwnerGuard({...})` | One atomic existing-owner transaction: compare current stop/owner/lease/fence/expiry and immutable admission; reserve logical change (reject alternate-key/revision replay); reserve physical resource; persist PREPARED and DISPATCHING before possible provider write; hold an owner guard across the dispatch boundary, send at most once; preserve unknown, never infer absence of a write from timeout or desired state |
| `readbackExact({idempotency_key,operation_id,request_digest})` | Historical immutable receipt; no mutation; return exact change_id/revision/digest, safe operation ID, known state and **causal evidence** as applicable. PREPARED/DISPATCHING cannot be swept into retry permission before executor settlement; UNKNOWN locks remain held until causally resolved |

No single external provider API can join a database transaction. The existing controller must reconcile crash windows with its legitimate mutex/fence/locking discipline and durable operation store, and independently qualify whether a side effect may still be in flight. A fixture calling a callback cannot prove real serialization. The tool only projects a *bounded* receipt and never echoes secrets or full provider responses.

### N1 scenario mapping

- Same key concurrent x20 -> exactly one dispatch; repeated lookups same operation ID.
- Different idempotency key for same logical owner change or revision of same change -> no second dispatch.
- Physical resource aliases and environment attachments -> same canonical service lock, irrespective of caller label.
- Stop/owner/fence/lease/expiry changes between admission and guarded dispatch -> no provider write.
- DISPATCHING surviving crash/restart -> read-only lookup returns held; no automatic takeover or replay.
- Lost response or provider readback unavailable -> UNKNOWN with lock; identical request is readback only.
- Render desired state visible without owner-captured provider acknowledgement -> NOT a causal settlement.
- GitHub run matching only timestamp or ID -> NOT a causal settlement; exact controller correlation, repository, full SHA, workflow, ref and event must match.
- Historical readback survives owner stop/admission expiry without restoring write authority.

### N1 provenance vs this implementation

N1's SQLite/D1 tests genuinely exercise its isolated journal and local operation harness, but are **not** integrated with the ingestion controller's durable store. The v11 pure-source harness demonstrates the required caller behavior using a test-only in-memory synthetic owner port, not a deployed controller. Do not adopt `source/src/journal.mjs` or N1 Sites route as a second durable ledger, provider executor, lease owner or alternate ingress. The N1 remote branch write interrupted without a commit; preserve archived bundle commit `984892c6be8ddaae805ec305bf257111c196ee4b` and do not automatically retry that write.

### Versioned hashing

Historical v10 request digest is `SHA256(JSON.stringify(request))`, including idempotency key and key order. A future canonical sorted change digest would need a **new version**, immutable owner-mapped change identity and tests for old receipts; it must never silently reinterpret v10 keys or admit an alternate-key replay. `hash_version:'v10-json-v1'` is passed as a contract label and must be checked owner-side against the admitted immutable record, not accepted as caller authority.

### Limited source gate

The v11 helper blocks `render_create_worker` as `worker_creation_plan_and_cost_unqualified` because the prior free background-worker plan is unavailable. This does not retire the capability; the owner must first qualify actual provider schema, a real price, no incremental cost or explicit spend approval, and no duplicate worker. Group attachment also requires verified group workspace/project membership and current effective permissions; matching ID syntax is insufficient.
