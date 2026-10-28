# ASTRA ingestion service — implementation candidate

This is an additive implementation for robert8p/Alpaca-Supabase-Populator,
based on source revision 455e45646aa71605cb3e541d2c714603d89f4079.

**Release preparation checkpoint — 28 October 2026, 22:24 UTC:** restricted RPC
and its forward authentication repair are installed; 112 local tests and all ten
live HTTPS boundary checks passed. At this checkpoint, source publication, CI
and hosted runtime deployment were still ahead. This revision requires its own
exact-commit CI result; see [PR 93](https://github.com/robert8p/Alpaca-Supabase-Populator/pull/93)
for the latest publication and check state. The historical CI-qualified baseline
is commit `73f4f3e5a07cd7ae2c5d7d4b34653f3de1b84a60`.
The current working revision replaces production database logins with fixed
HTTPS RPC operations.

All 17 installed function bodies match the tested baseline plus the exact
forward dispatcher repair. Readback confirms ten RLS-enabled tables, no
anonymous table grants and the intended limited `NOLOGIN` function owner.
All four temporary qualification capabilities have been revoked; a formerly
valid token was rejected over HTTPS, and the temporary plaintext credential
file was deleted. Final readback found zero active capabilities, jobs, records
and receipts. No provider request or ingestion job was dispatched. Existing jobs
and holds remain in scope for preservation. See
[the live qualification record](docs/PRODUCTION_QUALIFICATION.md).

## What is included

An isolated astra_ingestion package with no imports from legacy app modules:
strict immutable admission, a bounded Alpaca adapter, durable database job and
partition state, page receipts and record writes committed atomically, ownership
generations and leases, shared request pacing, bounded retries and deadlines,
fresh source-to-target readback, and authenticated web controls.

Production uses a FastAPI/Uvicorn control service and `astra_ingestion/rpc_store.py`
to persist through the target project's HTTPS Data API. The fixed operations in
`sql/astra_ingestion_rpc_v1.sql` execute on PostgreSQL. Runtime services receive
no database DSN, administrator or service-role key, or project signing key.
The direct PostgreSQL/psycopg adapter, SQLite adapter and standard-library HTTP
handler remain local qualification tools, not production transports.

The first adapter accepts one to ten explicit symbols, SIP/raw bars, 1Min/5Min/
15Min/1Hour, an explicit UTC interval of at most seven days inside
2025-09-01 through 2026-07-31 inclusive. It does not infer a historical universe
from current listings or release held security identities.

The included live-canary **candidate** is AAPL/MSFT, 2 September 2025,
13:30–20:00 UTC, 5-minute SIP/raw bars, at most ten provider calls and 1,000
records, with a 30-minute deadline. This manifest has not been dispatched.

## Completion semantics

A successfully fetched task is not yet verified. A fresh read reconstructs
expected keys and values from retained original response bodies and compares
them with stored keys and values. Hash corruption, missing/extra/changed rows,
incomplete pagination and empty expected partitions prevent verification.
Blocked symbols remain visible in immutable scope. The resume control does not
release quality holds.

The RPC readback obtains retained receipts and records in one bounded statement
snapshot. It uses the worker capability and the existing Python reconciliation
code. The SQL path independently validates source-page parsing at commit, but
that does not establish independently privileged verification or an independently
qualified end-to-end verifier.

Completed execution with passed verification means exact source-response
delivery has been verified for every requested partition. It does **not**
certify full historical market coverage, historical identity resolution,
financial reconstruction, point-in-time research suitability or strategy
validity. Those remain separate mission stages.

## Qualification status

The historical baseline commit, `73f4f3e5a07cd7ae2c5d7d4b34653f3de1b84a60`, passed
[all 77 ingestion tests with zero skips](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40762636622),
including 10 PostgreSQL and 8 ASGI tests. Its
[existing release gate](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40762636513)
passed 450 tests with 10 skipped. These are historical results for that exact
commit; they do not qualify the subsequent RPC, configuration, SQL or evidence
changes. The deployment candidate pins Python 3.12.15.

The current RPC working revision passed the complete local ingestion suite:
**112 passed, zero failures, zero errors and zero skips**, completed at
22:23:43 UTC on 28 October 2026 with Python 3.12.14 and PostgreSQL 17.11.
This includes 17 PostgreSQL RPC tests, 12 HTTP boundary tests, 8 configuration
tests, the existing 10 PostgreSQL tests, 8 ASGI API tests plus import isolation,
and 3 role-admission tests.
[Machine-readable qualification](evidence/rpc-qualification.json) retains the
command and exact source hashes, unchanged during the run; the
[complete test log](evidence/rpc-tests.txt) is also retained. An initial local
run's child-process dependency issue was corrected with an isolated interpreter
before this successful full rerun.

These are local results. At the 22:24 UTC preparation checkpoint, the RPC
revision still awaited publication and exact-commit CI. Consult PR 93 for its
subsequent state; the historical CI results above belong only to `73f4f3e`.
[Live HTTPS qualification](evidence/live-rpc-https-qualification.json) passed all
ten checks: API/worker health, empty job inventory, missing/unknown/expired/
revoked capability denial, both wrong-actor denials, and rejection of the private
schema profile. Cleanup and post-revocation rejection were separately verified.
These checks qualify the ingestion authentication/schema boundary; they do not
qualify a live ingestion job or unrelated public function behaviour. Provider
entitlement, hosted deployment and recovery remain separate gates.

## Local qualification

Python 3.12 is used for the candidate. Run the suite and syntax checks with:

    python -m unittest discover -s tests/ingestion -v
    python -m compileall -q astra_ingestion
    node --check astra_ingestion/static/app.js

PostgreSQL and ASGI tests explicitly skip when their required infrastructure is
absent. A skip is not a pass. The older `evidence/local-tests.json` result records
77 discovered tests: 59 passed and 18 skipped (8 ASGI and 10 PostgreSQL); it is
retained as historical evidence, not a result for the RPC working revision.
See `docs/PRODUCTION_QUALIFICATION.md` for current gates.

For the full disposable CI suite:

    python -m pip install -r requirements-ingestion-dev.txt

Provide ASTRA_INGESTION_POSTGRES_TEST_URL only for a disposable loopback database
named astra_ingestion_qualification. The test adapter rejects remote targets.
The included GitHub workflow supplies PostgreSQL 17 locally and does not read
production secrets or deploy resources. Local PostgreSQL RPC tests exercise
the SQL and simulated gateway context; they do not establish real Supabase
gateway header handling or effective access through the deployed HTTPS endpoint.

## Production commands

- Web: python -m astra_ingestion.serve
- Worker: python -m astra_ingestion.worker
- Bounded submission:

    python -m astra_ingestion.cli submit examples/astra-ingestion-canary.json --idempotency-key astra-delivery-qualification-20261028

Do not submit against a live target before completing qualification and binding
checks. Neither web nor worker creates schema or submits a job on startup.
`python -m astra_ingestion.cli migrate` is available only in explicit test mode;
production schema changes use separately reviewed SQL through an administrative
deployment path. The original schema, restricted RPC migration and forward
authentication repair are already installed on the admitted target and must not
be rerun blindly. For a separately admitted fresh installation, apply the reviewed
schema, then `sql/astra_ingestion_rpc_v1.sql`, then the mandatory
`sql/astra_ingestion_rpc_auth_context_v1.sql` repair. The historical baseline SQL
is intentionally unchanged; applying it alone leaves the live authentication
failure unresolved. Do not restart legacy `app.worker`.

## Configuration and permissions

Every production process requires these explicit settings:

| Variable | Required value or purpose |
| --- | --- |
| `ASTRA_INGESTION_PROJECT_REF` | `oxzabweahkoimtevbbny` |
| `ASTRA_INGESTION_API_URL` | `https://oxzabweahkoimtevbbny.supabase.co` |
| `ASTRA_INGESTION_PUBLISHABLE_KEY` | The project's public publishable key or project-bound legacy `anon` key; never a secret or `service_role` key |
| `ASTRA_INGESTION_RPC_TOKEN` | A distinct, securely generated 256-bit capability for each service, encoded as exactly 64 lowercase hexadecimal characters |

Production rejects `ASTRA_INGESTION_DATABASE_URL`. HTTPS uses the system trust
store and hostname verification, pins the admitted project origin, and refuses
redirects. Neither service sets `PGSSLROOTCERT`. The downloaded public database
CA remains only as historical evidence; see
[certificate provenance](docs/PRODUCTION_QUALIFICATION.md#certificate-provenance-and-rotation).

The web service additionally requires `ASTRA_INGESTION_USERNAME` and a dedicated
`ASTRA_INGESTION_PASSWORD` of at least 32 bytes. Provider credentials belong only
on the worker (`APCA_API_KEY_ID` and `APCA_API_SECRET_KEY`). The web and worker
must use different RPC tokens, assigned to the `api` and `worker` actors:

| Actor | Allowed fixed operations |
| --- | --- |
| `api` | `health`, `list_jobs`, `get_job`, `submit_job`, `control_job` |
| `worker` | `health`, `claim_next`, `reserve_request`, `commit_page`, `verification_material`, `finish_verification`, `fail_claim` |

The public invoker wrapper calls a private dispatcher owned by a limited
`NOLOGIN`, `NOBYPASSRLS` role that does not own the tables. RLS and explicit
operation grants apply to this role. The endpoint exposes neither credential
administration nor arbitrary SQL. After the forward repair, it requires a machine
`anon` gateway/JWT context, no user subject in either the JWT claims or legacy
claim setting, and a valid `X-Astra-Ingestion-Token` header. A public
project key alone is insufficient. The private ingestion schema and its tables
must remain outside the Data API's exposed schemas.

The installed `sql/astra_ingestion_rpc_v1.sql` added the fixed operations and an
initially empty credential-digest table. Through a separately authorized administrative step,
register only the SHA-256 digest of each token's UTF-8 text, its actor, and an
explicit expiry. Supply the corresponding plaintext token only through that
service's protected environment configuration. Do not place tokens in source,
SQL files, logs, screenshots or evidence. Expired or revoked entries are denied;
runtime credentials cannot provision or rotate other credentials. No actual
runtime secrets are supplied in this bundle.

The older direct-login template `sql/astra_ingestion_roles.sql` is not the
production activation path. Its inherited-`pg_net` rejection remains evidence
of why direct database login isolation was unsuitable. The repaired API path has
installed-object readback, ten passed live HTTPS boundary checks and no ingestion
findings from scoped security advisors. This does not qualify other existing
public RPC functions, provider entitlement or hosted operation.

The current market-data target was observed as oxzabweahkoimtevbbny. The legacy
loader's different project is not an interchangeable default. The deleted and
old test targets are rejected by runtime configuration.

## Limits and recovery

- At most one configured production worker in the initial deployment.
- Database-wide advisory transaction locking serializes application writes.
- Provider pacing is shared through PostgreSQL, at most one dispatch per two
  seconds for this application.
- Every provider call is counted durably before dispatch.
- Default limit: 50 requests, 50,000 records and 30 minutes per job; admission
  has hard maximums. Retained response bodies are capped at 32 MiB per job.
- Two transient failures exhaust the partition's retry budget. Rate-limit
  not-before times persist across restart. Waits exceeding the job deadline
  terminate explicitly.
- One source page is at most 2 MiB; request timeout is 20 seconds.
- Pauses and cancellation invalidate in-flight ownership. Original deadlines,
  attempts and source evidence are preserved.
- A worker with an uncertain database outcome exits. A replacement reconciles
  the durable checkpoint after lease expiry rather than blindly repeating an
  effect.
- Each mutating RPC is a whole PostgreSQL transaction. The client does not
  replay a timed-out or otherwise uncertain HTTP mutation. Original ownership,
  generation and deadline fences still apply to its durable result.
- Raw bars are isolated ingestion records; no canonical dataset is overwritten.

There is no deployed external observer or active ongoing monitoring in this
candidate. Scheduler/host restart proof and useful-progress alerting remain
required before unattended production admission.

## Delivery and deployment

render-ingestion.yaml proposes two new services in Frankfurt with automatic
deployment disabled. It does not modify the existing render.yaml or reference
the suspended loader services. Validate it using the current Render CLI/API,
confirm current pricing and total commitments, and bind secrets before applying.
Select the custom Blueprint path render-ingestion.yaml and set Blueprint Auto Sync
to No; do not use the repository's legacy root render.yaml.
The named branch is the isolated release branch. Its presence does not establish
a successful deployment; retain the exact qualified commit and deployment result.

No financial-fact, corporate-action or identity adapter is included in this
first slice. Add those after qualifying the execution path and adopting their
exact source, provenance and point-in-time contracts.
