# ASTRA: complete dataset and reliable unattended ingestion


## Exact independently reviewed unit binding — source/test slice, 29 October 2026

**New STAGED components, not installed:** `sql/astra_ingestion_bulk_unit_binding_v1.sql`, `tests/ingestion/test_bulk_unit_binding_postgres.py`, `astra_ingestion/bulk_unit_binding.py` and `tests/ingestion/test_bulk_unit_binding.py`. Exact executable/test candidate initially `610fc4a240c0cbd14bc41ed58d291ce56b2e24be`. The SQL amendment installs an append-only per-family exact-unit witness and a full unit-set seal. The distinct external reviewer must provide the independently observed ordered unit-set digest, matching **every** unit's source/provenance/identity/PIT hash; all 24 family seals must agree with the pinned original family review. A rewritten restricted claim port rejects the **entire** manifest if any queued partition/unit/source receipt is absent, mismatched, provider-mode or outside the sealed expected set. Manifest SHARE lock serialises the admission decision with the existing finite reservation UPDATE lock, preventing late unbound insertion before claim. User stops, original job deadlines, count/source holds, retry/record/request fences and lease expiry remain enforced by the underlying durable ledger.

**Python bridge:** bounded keyset enumeration produces reviewer-only candidate rows and the exact PostgreSQL JSONB unit-set digest, cross-checked in disposable PostgreSQL tests. It refuses unpinned PIT/identity/provenance/source hashes, missing/extra/duplicate keys, snapshot receipt drift and non-ASCII unit keys without separately qualified canonicalisation. It does **not** authenticate itself as the reviewer, acquire source data, mutate SQL or admit worker jobs. Its result always says `worker_admission_authorized=False`. A synthetic SQL-computed fixture hash is explicitly not independent external source evidence.

**Security:** no staged SQL installed and NO PUBLIC/application grants added. Prior generic claim and original count-only claim functions must remain ungranted to the production runtime, and no reviewer role may be impersonated by the worker. The original 24-family source review/denominator remains unresolved for real data (especially REF01); synthetic hashes, counts or the existing 4,136 retained scope documents cannot certify actual coverage. A distinct authenticated reviewer, real source-backed exact-unit hashes, actual atomic output materialiser and hosted automatic successor/old-instance cessation, JWT-over-HTTPS and physical host eviction proofs remain production hard gates.

**Scope and cost:** no production DDL/DML, provider requests, new services, paid changes, main merge, legacy controller restart, altered canary/crash job or rewritten original deadlines. The programme has no expiry; individual jobs and resources remain finite. All four joint acceptance gates remain OPEN. Deploy only after exact-candidate CI, source-backed review, transport/role rights, fencing and rollback gates.



## Restricted runtime admission/claim port — exact-source qualification (18:10 UTC, 29 October)

**Qualified executable/test revision:** `5e09e38330ccf6146828c7e6f0a16d7a71f8bcb7`. New STAGED `sql/astra_ingestion_bulk_runtime_port_v1.sql` exposes a read-only, exact-shape manifest admission snapshot for the already staged Python retained dispatcher and a pending RETAINED-ONLY claim wrapper. It is **not installed**, has **no PUBLIC grants** and gives no production principal any new rights. Every admission readback rejects an absent/stopped manifest, incomplete 24-family review, changed original contract receipt, wrong source capture or unpinned report SHA. The only claim operation delegates to `bulk_claim_retained_v1` under finite lease/original deadline/attempt/dependency constraints; it does not access provider APIs.

**Tests:** [ASTRA ingestion qualification PR run 40928124146](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40928124146) SUCCESS — **199 unit/disposable PostgreSQL tests**, including five new tests for source drift, exact dispatcher readback, synthetic successor after external simulated verification, user stop/provider exclusion and no PUBLIC EXECUTE. [Release gate 40928123963](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40928123963) SUCCESS. The first candidate's ACL test falsely matched the function owner's own `=X/` privilege; corrected at `5e09e383` to inspect ACL grantee OID 0. This was a test defect, not an ignored permission failure.

**Important newly isolated admission gap:** a valid 24-family **count-based** review does NOT yet prove that *each queued work unit* belongs to the exact independently verified expected-unit set. The present claim gate must NOT receive an application grant until immutable per-unit manifest evidence is bound to every reserved partition and independently checked. A claim plus a receipt hash also does NOT prove atomic source-to-output materialisation. A separate fully restricted materializer and independent post-commit verification are still required. CI's synthetic reviewer and successor are NOT evidence of production auto-dispatch, data completeness, actual separate authenticated reviewer, external JWT HTTPS transport, physical eviction or cross-instance cessation.

**Current live readback:** the original capture remains 4,136 retained documents (3,000 company rows, 24 original contracts, 42 calendars, 1,065 preserved D06 catalogue items, plus scope/acceptance/membership); live Render web/worker deployments are still `2c809b69e131f84e1778486e74c2f89a273f59f9`. No bulk manifest, SQL migration, hosted automatic successor, acquisition, new provider requests, production DB writes, additional costs, or changed legacy systems in this slice. Joint acceptance remains OPEN in all four parts and full-market coverage NOT_CERTIFIED. The reviewer and closeout automations remain disabled with unexplained user-action flags; do not re-enable silently. The programme has **no expiry**, but all new work must have finite immutable job deadlines, budgets, fencing and stop controls.

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


## Bounded retained-only executor and REF01 episode normalizer (17:15 UTC, 29 October)

**Exact qualified executable source:** `ea996c1ae0145da87af4e33141f27ce1fb86da44`. Both ASTRA ingestion and general release-gate workflows, push and PR, completed SUCCESS ([ingestion PR](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40919334276), [ingestion push](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40919320580), [release PR](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40919334175), [release push](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40919320643)); **189 ingestion unit/PostgreSQL tests passed**. Source and tests were read back after qualification.

`astra_ingestion/bulk_reuse_dispatch.py` is a bounded **source-only restricted-runtime component** for an eventual admitted, server-fenced retained-source store. It refuses absent independent full-24-family admission, stopped/mismatched manifest, provider-mode work, invalid owner/fence, request budget above zero, expired original job/lease and uncertain receipt; it never attests its own work or requests provider data. Synthetic tests demonstrate a committed retained page followed by a dependent successor **only once a separate simulated reviewer releases the predecessor**, plus a post-2026-11-05 job with a *fresh finite* deadline, while an expired job stays refused. This is NOT actual hosted unattended dispatch: the restricted store method, SQL review admission and real separate verifier have not been installed or qualified.

`astra_ingestion/bulk_ref01.py` is the first domain-specific REF01 **normalised-source episode compiler**, constrained to its five exact original declared routes. It handles all 3,000 accepted company identifiers as **candidates only**, effective-dated listed security episodes, explicit held/missing required fields, evidenced exclusions, overlapping security identity conflicts and records published after the specified as-of instant. It fingerprints ranked membership and pinned scope receipt. Ten source tests passed as part of the 189-suite. It does NOT read the five live tables, prove the REF01 complete historical-security denominator, prove licence/source coverage or issue a `DenominatorEvidence` or admission credential. Actual source-backed projection and independent historical closure remain BLOCKED and must be built, not assumed from accepted company membership.

**Current reality:** production SQL ledger/reader/admission not installed; both named Render services still LIVE on clean `2c809b69e131f84e1778486e74c2f89a273f59f9`; 4,136 retained scope documents remained present on a fresh READ ONLY count; zero bulk acquisitions/deployments/provider requests/additional costs. The separate read-only review and closeout tasks remain disabled with unexplained user-action flags; no silent reactivation. All four acceptance gates OPEN and historical/full-market NOT_CERTIFIED. Next: source-backed REF01 projector and approved independent review, restricted SQL store plus complete 24-family admission, then actual automatic successor/fault/security/hosted evidence before protected ingestion.

## Independently reviewed retained-only SQL claim gate (17:21 UTC, 29 October)

**Executable source candidate:** `4e2cffd2146161a9a027704a43e0a73ae409b671`. New **STAGED, NOT INSTALLED** `sql/astra_ingestion_bulk_retained_gate_v1.sql` adds immutable per-family review evidence for the exact 24 families (not D06); explicit expected/observed equality; pinned source contract, source receipt, provenance, identity and PIT digest fields; a distinct manifest review record; source-contract matching against the immutable retained capture; and `bulk_claim_retained_v1` which will not claim until all 24 family reviews are recorded, manifest un-stopped, predecessors verified, original job deadline valid, and work mode strictly provider-free. No default PUBLIC function/table grants and RLS enabled on review tables. Legacy generic ledger functions MUST NOT be granted to an eventual retained worker; actual separate reviewer role and actor/transport need qualification before any production grant or record. The gate deliberately cannot certify provenance merely from metadata hashes or untrusted operator assertions.

**Disposable Postgres evidence:** [ingestion push run 40920326277](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40920326277) completed SUCCESS with **194 tests**, including five new tests covering absent review, 23/24 review rejection, original retained-contract hash binding, immutable review rows, dependent retained-only successor, provider exclusion and stop preservation. [release push 40920326250](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40920326250) and [release PR 40920333272](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40920333272) also SUCCESS. The synthetic administrative fixture is not a genuinely independent production review or credential/HTTPS/RLS qualification. All real 24 denominators remain unverified; the reviewer and closeout automations are disabled; no full-data admission or actual hosted successor evidence exists.

**Required next engineering:** integrate the independently qualified SQL store with the staged Python retained dispatcher under a restricted database principal (without provider rights); produce actual REF01 normalized projections from lawful, date-valid source routes and evidence-backed complete security episodes; establish a separate independent review principal/transport, read back its full 24-family source evidence, and qualify hosted restart/old-instance/non-overlap before admitting any production job. Do not weaken safety gates, recreate old jobs, reset budgets or treat CI as deployed ingestion.

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


## CI-qualified retained-only claim recovery (STAGED, NOT INSTALLED)

Exact tested source revision: abef74e25dd1b5bb80618e5083658d22230467a0. The staged
`sql/astra_ingestion_bulk_ledger_v1.sql` now contains
`bulk_recover_retained_v1(work, expected_fence, new_owner, lease_seconds)`.
It only reclaims previously claimed, expired `retained_source_reuse` work
with zero provider requests. It preserves immutable original job deadlines,
retained receipts, costs and cumulative attempt count; requires an expected
fence and changed owner; takes a manifest lock before a work lock; and fails
closed on stop, deadline, stale fence, attempt limit or provider acquisition.

Lease expiry **does not** prove the former instance stopped. DB fencing protects
the retained-only commit path, not hosted cross-instance cessation. Provider
acquisition never automatically retries through this function. Independent
review, restricted runtime rights, exact 24-family coverage, automatic
successor execution, old-host cessation and hosted eviction are still OPEN.

Disposable PostgreSQL regression passed: 163 ingestion tests, including two
new retained-only recovery/stop/expiry cases and no-duplication evidence.
CI: [ingestion PR qualification](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40898001985),
[release PR gate](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40898002041)
and [release push gate](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40897993666), all successful.
This is source/disposable-database validation, NOT production installation or data acceptance.

## Full-24-family source-witness preflight (CI-qualified, NOT runtime admission)

Added `astra_ingestion/bulk_manifest_admission.py` and
`tests/ingestion/test_bulk_manifest_admission.py` at executable candidate
`10a755efa91b722a819c1ec457e10d563b7fabdd`. Both ingestion workflows
[push](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40908820282)
and [PR](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40908830654)
PASS; both release gates
[push](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40908820390)
and [PR](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40908830668)
PASS. The source and test use only synthetic evidence, have no provider/database
writes and create no executable work.

The preflight reconstructs all 24 expected family populations from the pinned
4,136-record receipt, accepted company membership, original contract set and
independent eligibility/keyset bindings. It refuses substituted or forged
`ExpectedUnitPlan` objects; requires source snapshot/contract/expected-manifest
hash bindings for each family; reads sorted, finite source-witness keyset pages;
checks all expected versus witnessed keys; and distinguishes absent denominator,
missing source proof, missing/extra units, duplicate rows and invalid provenance,
identity or point-in-time witness metadata. D06 never becomes a work family.
All-family structural reconciliation produces only
`INDEPENDENT_REVIEW_REQUIRED`, NEVER permission to reserve, claim, fetch or
certify full dataset coverage. The `worker_admission_authorized` property
remains false by construction, and actual source bytes/point-in-time truth need
independent external evidence and restricted runtime checks.

This is one tested **engineering slice**, not the durable production admission
barrier: the existing staged SQL ledger does not yet consume this fingerprint
or enforce independent reviewer/manifest-source/worker admission. No real
24-family source denominators or per-family proof records have been supplied;
therefore none of the research families is DATA_ACCEPTED.
Read-only production evidence at 2026-10-29T16:11:27Z still has 4,136 scope
documents; Render web and worker still run revision
`2c809b69e131f84e1778486e74c2f89a273f59f9`.
No acquisition, migration, deployment, paid service or original-job mutation
accompanied this slice.

**Executable successor:** bind independently acquired exact 24-family source
unit/temporal/identity proofs to this tested preflight and staged ledger;
implement a restricted, fail-closed durable admission transition and retained
reuse worker dispatch (with verified automatic successor). Develop against
disposable PostgreSQL without assuming production RLS grants or bypassing any
previous explicit source introspection refusal. Qualify the exact revised
source/deployment before any production admission. The independent reviewer
and closeout automations remain disabled with unexplained user-action flags,
so neither review nor closeout acceptance may be presumed.

