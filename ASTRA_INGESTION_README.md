# ASTRA ingestion service — implementation candidate

This is an additive implementation for robert8p/Alpaca-Supabase-Populator,
based on source revision 455e45646aa71605cb3e541d2c714603d89f4079.

**Release state: implementation candidate awaiting production qualification.**
The isolated ingestion branch contains this candidate. Qualify its exact commit
using the packaged CI workflow before deployment. No live database schema,
provider ingestion, hosting service, scanner setting or existing suspension
has been changed by this implementation.

## What is included

An isolated astra_ingestion package with no imports from legacy app modules:
strict immutable admission, a bounded Alpaca adapter, durable database job and
partition state, page receipts and record writes committed atomically, ownership
generations and leases, shared request pacing, bounded retries and deadlines,
fresh source-to-target readback, and authenticated web controls.

Production uses PostgreSQL with psycopg and a FastAPI/Uvicorn control service.
The standard-library HTTP handler and SQLite adapter are local reference
transports for qualification. They are not production substitutes.

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

The readback uses a fresh database snapshot with the same runtime credential
and normalization code. It does not provide independently privileged
verification or a second independently implemented parser.

Completed execution with passed verification means exact source-response
delivery has been verified for every requested partition. It does **not**
certify full historical market coverage, historical identity resolution,
financial reconstruction, point-in-time research suitability or strategy
validity. Those remain separate mission stages.

## CI qualification

The ingestion workflow passed all 77 tests with zero skips on commit
`a0932015ff1085607d22ee6b5c33b2d3c1cc0516`, including 10 PostgreSQL and 8 ASGI API
tests. See [the retained CI evidence](evidence/ci-qualification.json) and
[the successful run](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40762186249).
The disposable CI database is not evidence of live Supabase role, TLS, provider
or hosted recovery qualification. The deployment candidate pins Python 3.12.15,
the interpreter version used by that successful run.

## Local qualification

Python 3.12 is used for the candidate. The reference suite needs no third-party
dependencies:

    python -m unittest discover -s tests/ingestion -v
    python -m compileall -q astra_ingestion
    node --check astra_ingestion/static/app.js

PostgreSQL and ASGI tests explicitly skip when their required infrastructure is
absent. A skip is not a pass. The retained evidence/local-tests.json result
records 77 discovered tests: 59 passed, zero failures/errors, and 18 skipped
(8 ASGI and 10 PostgreSQL). Those production-backend checks remain NOT_RUN.
See docs/PRODUCTION_QUALIFICATION.md for outstanding gates.

For the full disposable CI suite:

    python -m pip install -r requirements-ingestion-dev.txt

Provide ASTRA_INGESTION_POSTGRES_TEST_URL only for a disposable loopback database
named astra_ingestion_qualification. The test adapter rejects remote targets.
The included GitHub workflow supplies PostgreSQL 17 locally and does not read
production secrets or deploy resources.

## Production commands

- Web: python -m astra_ingestion.serve
- Worker: python -m astra_ingestion.worker
- Explicit migration: python -m astra_ingestion.cli migrate
- Bounded submission:

    python -m astra_ingestion.cli submit examples/astra-ingestion-canary.json --idempotency-key astra-delivery-qualification-20261028

Do not run the migration or submission against a live target before completing
qualification and binding checks. Neither web nor worker creates schema or
submits a job on startup. Do not restart the legacy app.worker for this path.

## Configuration and permissions

Every production process requires ASTRA_INGESTION_DATABASE_URL and
ASTRA_INGESTION_PROJECT_REF. The URL must match the explicit Supabase project
binding, and the driver verifies TLS hostnames. Direct connections and
project-qualified Supabase pooler usernames are supported. Prepared statements
are disabled for pooler compatibility.

The web service additionally requires ASTRA_INGESTION_USERNAME and a dedicated
ASTRA_INGESTION_PASSWORD of at least 32 bytes. Provider credentials belong only
on the worker (APCA_API_KEY_ID and APCA_API_SECRET_KEY). Configure separate web
and worker database identities; never use administrator credentials at runtime.

Run the explicit migration with an authorised migration identity, then review
and apply sql/astra_ingestion_roles.sql. It creates NOLOGIN roles, applies
schema-specific grants and row-level security, and grants neither service access
to existing scanners or canonical market data. Enable login/set credentials
through the platform secret workflow; no credentials are supplied in this bundle.

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
