# ASTRA: complete dataset and reliable unattended ingestion

## Authority and target

Unattended operation and the previously paused Top-3,000 target are approved.
Deliver 1 August–30 September 2026 through this isolated application, all 24
original families. Preserve D06 only. Never restart the legacy controllers or
release financial/identity/data-quality/scientific holds. No research/trading.
No new services, new costs or main merge are admitted. The programme has NO expiry under the direct 29 October 2026 user amendment; the former 2026-11-05T02:00:00Z cutoff is historical, not an operating stop. Every new job still has an immutable finite original deadline and explicit budgets, cancellation and retry limits. Main stays unmerged.

The prior practical membership is accepted for reuse, not invented anew. Its
snapshot is `2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec`;
acceptance `20b9dac759857e9b510ccaeca33e4a94d8c748d588fb0cc27740cc66c389b5f9`.
The original source acceptance event24407 references user amendment23086 and
explicitly does not certify exact global ranking, financial facts or full-period
security mapping. Preserve those distinctions; do not spend the campaign trying
to re-create an already accepted membership or quietly certify its other fields.

Joint completion requires DATA_ACCEPTED AND EXECUTION_ACCEPTED AND
INDEPENDENT_REVIEW_ACCEPTED AND DELIVERY_ACCEPTED for compatible exact revisions,
manifests and complete applicable populations. None is implied by this capture.
The three existing tasks are governed by SHARED EXECUTION AND ACCEPTANCE CONTRACT v2; disabled task states are not proof of acceptance or permission to restart.


## Forward-only pending migrations (source tested separately; not installed by documentation)

The historical one-time capture and catalogue-repair SQL remain unchanged and MUST NOT
be replayed. The prepared new `sql/astra_ingestion_bulk_scope_no_campaign_cutoff_v2.sql`
performs a single exact-source preimage check against the installed capture
function, requires the immutable 4,136-document receipt and RLS/ACL invariants,
then replaces only the withdrawn programme-cutoff conditional. Repeating the
migration or observing drift fails closed. A passing synthetic/CI test DOES NOT
prove that this new SQL is installed in production. Database application requires
the normal admitted connector operation and exact production preflight.

The prepared `sql/astra_ingestion_bulk_restricted_reader_v1.sql` defines a
NOLOGIN, NOBYPASSRLS reader principal with EXECUTE on a single bounded keyset
SECURITY DEFINER function, no direct table grants, no provider rights and no
credential provisioning. It remains a staged component: the actual external
read-only actor/transport and deployed runtime integration are NOT qualified.
Tests on disposable Postgres do not establish production actor enforcement.

These independent infrastructure slices do not constitute a complete 24-family
manifest, durable bulk queue, source acquisition, data acceptance or automatic
successor execution. Installation, transport, adapter, worker and hosted
recovery gates remain separately OPEN.

## Implemented slice: retained evidence, not a bulk executor

`sql/astra_ingestion_bulk_scope_v1.sql` creates two isolated immutable evidence
tables and a privileged-caller-only SECURITY INVOKER capture function. No provider
call, source update, loader restart, existing-job mutation, credential access or
new runtime grant is present. This is a one-time migration, not startup DDL.

The function requires a repeatable-read transaction, takes a nonblocking atomic
transactional lock, validates pinned original scope/cohort/acceptance/contract
hashes, root acceptance, 3,000 distinct companies/ranks and held qualifications,
42 sessions/16,380 scheduled minutes, and the retained D06 catalogue inventory.
The corrected source candidate `13cc5b0d6294c052333178031816a5ab764bd280`
retains 1,065 D06 preservation entries, not the previously assumed three.
It atomically retained 4,136 evidence documents and one receipt. Hashes use exact
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

## Installed capture and fresh readback

The one-time migration and capture already exist. Do not reinstall or recapture.
Capture key: `top3000-augsep2026-retained-scope-v1`; captured at
`2026-10-29T09:22:03.127374Z`, first run `origin-steps12-20261029-0853`.
State remains `CAPTURED_NOT_ADMITTED`, with zero provider requests/cost.

At `2026-10-29T10:07:30.325148Z`, an explicit READ ONLY transaction through
`Supabase_Market_Data_Cloud.execute_sql` recomputed every retained content hash
and the ordered aggregate hash: 4,136 rows, zero content-hash failures,
receipt count and hash both matched. Aggregate SHA256:
`ba13899b530288b6aae8d4af3a429efa3f4bd5ec305a7dc698f98c9d552f4496`.
Composition:3,000 company,24 contract,42 calendar,1,065 preservation,
2 acceptance-event,1 cohort,1 membership and1 scope documents.
Original two jobs remain completed,234 records/3 requests,zero active claims.

This validates retained scope evidence, NOT source-to-target completeness of
all 24 research datasets, restricted-runtime verification or bulk admission.
Review the exact published candidate and its regression results before new
executable deployment. Do not carry source qualification to changed code.

## Connector refusals: bounded diagnosis, not a permission bypass

The scheduled writer reported blocked GitHub writes and read-only SQL in run
`f4d582dd-258c-8328-ab9c-b4b43b7c015a`, completed10:04:12.155847Z.
The subsequent user-requested diagnosis found both connectors already set to
app-specific Allow all actions. No permission, OAuth, RLS or credential change
was made. The ordinary SQL route passed two finite READ ONLY calls; GitHub
`update_file` acquired checkpoint v20 using its current blob SHA, commit
`575131f11c3492d3e0cf4d04884b19749fbfe5ee`, and the new blob was read back.

These results prove current interactive access, not permanent scheduled-context
recovery. Read the current checkpoint and actual task status before proceeding.
If a new task-context operation is denied, preserve the exact error, task/run,
operation, target and time; reconcile any uncertain destination effects. Do not
cycle connectors, change identities, loosen policies or encode a request to
circumvent an explicit safety block. Preserve prior failures and the maximum
two materially identical failed attempts. A confirmed auth/approval requirement
needs its supported flow; a safety refusal needs precise evidence/escalation,
not another general request for authority already granted.

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
