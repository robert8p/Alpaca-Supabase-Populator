# ASTRA: complete dataset and reliable unattended ingestion

## Authority and target

Unattended operation and the previously paused Top-3,000 target are approved.
Deliver 1 August–30 September 2026 through this isolated application, all 24
original families. Preserve D06 only. Never restart the legacy controllers or
release financial/identity/data-quality/scientific holds. No research/trading.
No new services, new costs, main merge or campaign extension is admitted.
The campaign ends 2026-11-05T02:00:00Z. Main stays unmerged.

The prior practical membership is accepted for reuse, not invented anew. Its
snapshot is `2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec`;
acceptance `20b9dac759857e9b510ccaeca33e4a94d8c748d588fb0cc27740cc66c389b5f9`.
The original source acceptance event24407 references user amendment23086 and
explicitly does not certify exact global ranking, financial facts or full-period
security mapping. Preserve those distinctions; do not spend the campaign trying
to re-create an already accepted membership or quietly certify its other fields.

## Implemented slice: retained evidence, not a bulk executor

`sql/astra_ingestion_bulk_scope_v1.sql` creates two isolated immutable evidence
tables and a privileged-caller-only SECURITY INVOKER capture function. No provider
call, source update, loader restart, existing-job mutation, credential access or
new runtime grant is present. This is a one-time migration, not startup DDL.

The function requires a repeatable-read transaction, takes a nonblocking atomic
transactional lock, validates pinned original scope/cohort/acceptance/contract
hashes, root acceptance, 3,000 distinct companies/ranks and held qualifications,
42 sessions/16,380 scheduled minutes, and three existing D06 catalogue records.
It atomically retains 3,074 evidence documents and one receipt. Hashes use exact
original UTF-8 text; aggregate receipts use ordered PostgreSQL JSONB arrays of
(kind,key,source-hash). Do not compare those hashes to Python reserializations.
Reconciliation with the same capture key validates the entire existing result
and returns the original receipt without resetting its timestamp or first run.
Conflicting retained evidence fails closed; updates/deletes/truncates are blocked.

RLS defaults deny; PUBLIC and application roles cannot invoke capture or access
its evidence. It deliberately does not reuse the worker's provider identity.
An administrator performing this capture is NOT restricted runtime-verifier proof.

`astra_ingestion/bulk_scope.py` validates the exact original contract set, computes
deterministic dependency waves, represents immutable bounded partition proposals,
and keeps unknown/incomplete/unavailable counts distinct from certified coverage.
A proposal is NOT a durable reservation or permission to run acquisition.

## Exact-revision admission of this slice

1. Require the candidate's ingestion CI, including all new PostgreSQL tests with
   the existing loopback PostgreSQL service; skip-free dedicated ingestion result.
   Require existing release checks as regression evidence.
2. Reconcile sole-writer task/run, current head, checkpoint/lease, runtime and
   unresolved operations. Apply this migration once, transactionally, in the
   isolated schema. Do not reinstall existing observer/verifier migrations.
3. Call `capture_retained_top3000_scope_v1` in a repeatable-read transaction with
   a local statement timeout of 15 seconds and a stable operation run identifier.
4. Read back 3,000 company/24 contract/42 calendar/3 preservation documents and
   original cohort/membership/scope/two acceptance-event documents, compare every
   retained source digest and the aggregate receipt. Preserve NOT_CERTIFIED.
   Confirm unchanged original two jobs, requests, records, claims and old controls.
5. Publish exact results and release/advance the finite implementation lease.

## Executable successors, not reminder-only handoffs

Keep ONE code/runtime mutator (task6ae2a4c96bbc819182133e17e9b7f779), plus the
existing independent read-only verifier and closeout. No extra mutator chats.
Each run takes the highest-value admissible unfinished slice, implements and tests
it, records real outputs and dispatches its next admissible bounded operation.

A. Recover retained source manifests, source pages, dated instrument mappings and
per-family authoritative expected units. Build bounded keyset reuse readers and
per-family adapters inside ASTRA; do not copy whole legacy schemas or trust queue
completion counts. Reuse source data before buying or re-fetching anything.

B. Implement a durable per-family/per-partition ledger: original manifest and
deadline, finite cumulative provider/request/record/cost reservations, lease fence,
cancellation, attempts (maximum two identical failed attempts), uncertain-persistence
reconciliation, source receipts and verified output. No reset on a new schedule.
Prepare all test machinery before any hosted/provider job. Allow independent
families to progress; isolate a blocked provider instead of pausing everything.

C. Connect the named worker to admitted work, extend useful-progress observation
and independent verification to the bulk ledger, test postcommit loss/stale-owner/
expiry/cancellation/accounting, and qualify exact revisions before deployments.
Retain existing unproven host-eviction/non-overlap/authenticated-HTTPS gates honestly.
Do not let an unavailable hosted experiment prevent unrelated source/test work;
do not waive actual safety gates for production execution.

D. Execute bounded retained-source reuse and, when the adapter/accounting and
provider gates pass, finite missing-data batches. Cover all 24 families or record
evidence-backed exact unavailability. D06 is never an acquisition family. Shared
macro/futures/breadth evidence is not multiplied 3,000 times. No arbitrary subset,
silent denominator relaxation or false completeness.

E. Independently reconcile every family against source evidence, lifecycle and
point-in-time requirements; publish a full coverage/gap inventory and narrow
consumer-ready outputs only after their own gates pass. A successful canary,
heartbeat, passing task or this capture receipt is not complete delivery.

Existing qualified v1 jobs and their budgets are immutable and separate. Current
additional qualification consumption remains1/10 requests,78/1000 records and
$0 incremental compute. New bulk reservations must be durable and finite within
existing resources; they cannot be inferred from this evidence-capture receipt.
