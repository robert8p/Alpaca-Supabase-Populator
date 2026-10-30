# Defer-only confirmed lock-abort retry candidate

The prepared runtime adds only `backfill_defer` to the installed strict native
HTTP 500 / SQLSTATE `55P03` retry allowlist. The inverse of that one literal
addition is byte-identical to deployed `rpc_store.py` SHA
`1deb7051d4311b22c09d7245a36d751dd10c843192207aaefc0a2d4cf1291403`.
The candidate is SHA
`7614f7bf1094afbb552e657683726b7549c0b84d45cd3756ced79617042d3e11`.
No other operation becomes eligible. The held identity-material candidate is
excluded.

## Base and exact scope

The publication parent is `a71e9df014a4f0b66818ff47b2f85f1adbf6623e`, tree
`cc1c8702b0f9b43c52952736ed47566d8189e155`. That revision retains all 1,063
e694 blobs and adds the 32-file claim-cursor repair. The running worker still
uses e694 Python bytes; the database private dispatcher is the installed
`dbe8eb5a563eaf9e8e00678045f8a28da65c8c4b83b4a3295c4eb32c05f50fbf` source.
Its defer branch remains byte-identical to the earlier reviewed branch. The
installed shared refresh source remains `7f538bf4…`.

The archive contains three explicitly named active payloads: the runtime
replacement, the existing strict-policy test with its exact expected set
changed from six to seven, and one new defer-specific test module. Original
bytes for both replaced files are retained in the archive. The additional
source-bundle JSON is the new test's only non-base fixture input. No active
workspace file has been replaced. Raw duplicate test modules are not published
under `review/`.

The source boundary contains nine functions and four direct write tables.
The earlier six-operation callable closure has 73 functions; updating its
private/shared pins and adding the existing adaptation function yields 74.
`backfill_adapt_page_v2` SHA `10a17158…` is the sole newly selected callee.
There is no new table, trigger, policy, grant, role, provider, schema or database
function change in this runtime candidate.

## Retry and unknown-write behavior

The existing classifier still requires the fixed endpoint, integer HTTP 500,
complete bounded JSON body, exact four native error keys, exact `55P03`, valid
field types, and acceptable framing/content headers. Response customization
or an arbitrary application reason cannot independently authorize retry.
Authentication errors, controlled application envelopes, SQLSTATE `57014`,
truncated or malformed responses, transport failures and uncertain writes
remain outside this branch.

Only the already serialized RPC request is resent. The existing budget remains
three sends, backoffs of 0.25 and 0.75 seconds, and one 15-second RPC deadline.
The worker's provider fetch, prior reservation, cursor, attempt count and
attempt deadline are not reset or repeated by that resend.

A successful defer is **not idempotent**: it moves the task away from RUNNING
and clears task ownership and lease. There is no successful-defer ACK replay
branch. A committed defer whose acknowledgement is lost remains fatal after
one send. Native rollback may leave identity-sequence gaps and logs; those
effects are not treated as committed business rows or permission to reset
state.

## Qualification

The final local receipt records **51 tests, zero errors, failures or skips,
16.291 seconds**, using actual disposable PostgreSQL 16.15. The 42 inherited
strict-classifier, RPC boundary, safe-observability and admission cases remain
enabled; the new module adds nine methods with substantive subcases.

- A real global advisory-gate wait produces native `55P03`, leaves the complete
  selected business snapshot unchanged, and then permits one identical defer
  resend.
- A test-only trigger checks the real pacing, credential-dependency or adaptive
  page-limit effects and exception append before waiting on a second held
  advisory lock. All three native late aborts roll back those effects, including
  task status/lease/page limit. An identity-sequence gap proves the late trigger
  was reached; the retried disposition commits once.
- In all three effect variants, an acknowledgement is dropped only after the
  actual PostgreSQL commit. The worker fails with `TRANSPORT_ERROR`, makes one
  defer send, and fetches the synthetic provider exactly once.
- Seven authority changes between an aborted attempt and its resend reject the
  stale request: owner, generation, run fence, task lease, paused run, revoked
  credential and expired credential. These transition cases use an explicitly
  test-raised SQLSTATE; the independent native lock-wait cases establish the
  native-abort path.
- An invalid scoped adaptive receipt stays a controlled, single-send error.
  The dedicated ingestion workflow still rejects missing PostgreSQL DSN; other
  workflows explicitly skip the PostgreSQL class.

HTTP is a **simulated PostgREST envelope** over real isolated PostgreSQL
transactions. No actual PostgREST server, production RPC, external provider or
provider credential was used. Disposable schema, role, endpoint and retained
source relation names are explicit fixture adaptations; all nine selected
function definitions normalize to their exact captured production hashes.
Ordinary local test sleeps are suppressed; separate fake-clock assertions
verify the unchanged backoff and whole-RPC deadline.

The actual read/import audit contains 76 dependencies: 72 byte-identical a71
files, two reviewed replacements and two additions. There are zero unexpected
base differences. Both earlier import-only failures are retained. They were
resolved by staging missing exact parent fixture files, with no weakened
runtime or SQL guard.

## Admission and executable next step

Root can extract only the archive's three target payloads into an isolated
checkout of the exact current parent, verify their UTF-8 byte counts and
SHA256 values, and include the unchanged source bundle and selected evidence.
The publication builder must preserve every unrelated a71 blob and the held
checkpoint/identity packages. Do not publish the authoring fixture directory.

Activation remains subject to the independent hash-bound review, actual
exact-head CI including all nine new methods and zero dedicated PostgreSQL
skips, current source/metadata/catalog and owner/fence/lease confirmation, and
root-controlled deployment with independent revision/readback. Existing
gateway configuration visibility is incomplete: retained role/catalog
settings do not prove the absence of external PostgREST overrides. No actual
production-positive classifier observation is claimed.

This change handles a strictly proven transaction abort. It does not remove
the remaining maintenance gate-holder cost, extend a timeout or retry budget,
or establish sustained acquisition stability. Further evidence must retain
that distinction.

Authoritative execution evidence is in `qualification_final_v77.json`, the
source/table/callee bindings in `defer_source_effect_closure_v77.json`, and the
complete payload mapping in `candidate_files_v77.json`.
