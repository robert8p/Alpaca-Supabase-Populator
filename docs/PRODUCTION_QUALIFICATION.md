# ASTRA ingestion production qualification

Assessment date: **28 October 2026**. This document separates observed project
identity, implemented behaviour, local verification, and the evidence still
required before a production completion claim.

## Current release state

The isolated `astra_ingestion` package is an implementation candidate. No
production schema change, production ingestion or deployment has been established.
Earlier GitHub writes were interrupted. A later successful connector call created
the isolated ingestion branch; publication and CI evidence must be attached to
the exact candidate commit. Branch creation alone does not qualify the code.

The retained [local test result](../evidence/local-tests.json), observed at
**18:57:37 UTC on 28 October 2026**, records **77 tests discovered: 59 passed,
0 failures, 0 errors and 18 skipped**. The skipped tests comprise
**10 PostgreSQL qualification tests and 8 ASGI tests**.
The executed suite includes real child-process interruption against the SQLite
reference backend. SQLite results do not qualify PostgreSQL transaction,
connection, role, TLS, or hosted recovery behaviour. The production entry point
uses FastAPI/Uvicorn; the standard-library web server is a local test aid.

Keep any later test result attached to its exact source revision and command.
Do not carry these counts forward after changing the candidate without rerunning
the affected checks.

## Subsequent CI qualification

The [ingestion CI run](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40762186249)
completed successfully for commit `a0932015ff1085607d22ee6b5c33b2d3c1cc0516`.
All **77 tests passed with zero skips**, including all **10 PostgreSQL** and
**8 ASGI API** tests. Python was 3.12.15 and PostgreSQL was the disposable
PostgreSQL 17 service supplied by the workflow. Retained machine-readable
evidence is in `evidence/ci-qualification.json`.

This supersedes the missing-adapter portion of the earlier local result. It does
not establish live Supabase permissions, RLS/TLS, provider entitlement, hosting,
useful-progress monitoring or completed live ingestion.

## Verified database identity

The following metadata was returned by connected Supabase tools at approximately
**18:41 UTC on 28 October 2026**. It is identity and service metadata, not evidence
that the new ingestion schema exists or that any ingestion job completed.

| Purpose | Project reference | Observed metadata |
| --- | --- | --- |
| Project-scoped Market Data Cloud connection | `oxzabweahkoimtevbbny` | `market-data-leading-indicators`; `eu-west-1`; `ACTIVE_HEALTHY`; PostgreSQL `17.6.1.147` |
| Legacy loader project | `mnmkxjirpwbptdnvjmpw` | `Alpaca Supabase Populator`; `eu-west-1`; `ACTIVE_HEALTHY`; PostgreSQL `17.6.1.155` |

The scoped connection returned
`https://oxzabweahkoimtevbbny.supabase.co`. The provider dashboard for this project
is [market-data-leading-indicators](https://supabase.com/dashboard/project/oxzabweahkoimtevbbny).

`xdponktobhosycdhbcrr` is an invalid deleted target. The historical test reference
`syokddbfiecauakwqygv` is not a production default. Neither appeared in the
returned project list. The implementation requires an explicit project binding
and rejects those two references in production configuration.

A subsequent bounded, read-only catalog request was interrupted before returning
results. Consequently the current business control tables, schema permissions,
RLS configuration, active holds, workload backlog, and database performance were
**not verified by that request**. No mutation was requested by this inventory.

## Admission for the first live canary

Use this exact finite workload only after the deployment and database checks
below pass. Retain the submitted canonical manifest, its scope hash, the
idempotency key, the source revision, and the resulting job ID together.

```json
{
  "name": "ASTRA ingestion production canary 2026-10-28",
  "symbols": ["AAPL", "MSFT"],
  "start": "2025-09-02T13:30:00Z",
  "end": "2025-09-02T20:00:00Z",
  "timeframe": "5Min",
  "feed": "sip",
  "adjustment": "raw",
  "max_requests": 10,
  "max_records": 1000,
  "deadline_seconds": 1800
}
```

The start is inclusive and the end is exclusive. Preserve both requested symbols
even when a provider rejects one or returns no data. No feed substitution,
automatic expansion of the date range, financial-factor work, identity release,
or full-universe certification is included in this canary.

Resolve current parent stops and business holds from the authoritative control
state before admission. A new app, package version, retained test receipt, or
general approval does not silently release an existing identity or quality hold.
Complete independent permitted work while those affected units remain held.

## Release gates and required evidence

| Gate | Required evidence | Current status |
| --- | --- | --- |
| Exact source publication | Repository commit and readback of the complete diff, followed by checks for that exact commit | Candidate published; successful ingestion CI linked above |
| PostgreSQL behaviour | All ten PostgreSQL tests run without skips against the explicit disposable local test database; CI job URL and complete result | Passed in the linked disposable CI run |
| ASGI behaviour | All eight production API tests run without skips with the pinned runtime dependencies | Passed in the linked disposable CI run |
| Target and scope | Explicit binding to the intended current project, exact manifest and retained current holds | Project identity observed; current business controls unverified |
| Schema and role admission | Review and execution of the new isolated schema migration; schema-scoped runtime role; positive and negative permission probes | Not run against production |
| Provider connectivity | Dedicated valid Alpaca credentials, SIP entitlement, bounded successful real API request, no secret disclosure | Not run |
| Hosted deployment | Exact web and worker deploy revisions, terminal successful deploy states, authenticated endpoint and database readiness | Not deployed by this task |
| Browser operation | Actual authenticated desktop/mobile workflow, job submission, status refresh and controls; no fabricated UI evidence | Not run |
| Useful-progress monitoring | A verified hosted observer/watchdog with ownership, stall threshold, bounded response and successful fault exercise | Not established |
| Live bounded completion | The exact canary reaches successful source-to-target verification; every admitted partition and exception reconciled | Not run |
| Host and observer recovery | Host replacement and observer loss exercises with retained state, no duplicate effect and preserved stop behaviour | Not run |
| Scanner protection | Baseline and during-canary database/scanner metrics remain within the agreed resource limits | Not measured in this task |

### PostgreSQL qualification

The packaged PostgreSQL tests accept only an explicitly supplied loopback
database named `astra_ingestion_qualification`; they never select a production
database through the app defaults. Each test owns a fresh schema and may remove
only that schema. Run the suite through the supplied CI workflow or a correctly
configured local PostgreSQL server. A missing database URL or missing runtime
dependency is not a passing production test.

At minimum, retain evidence for atomic receipt/record/checkpoint commit, exact
readback from another connection, idempotent submission, scope immutability,
expired-lease takeover, denial of stale-owner writes, persisted rate-limit delay,
quality holds, budget exhaustion, and process interruption after commit.

### Database access, RLS and TLS

The migration is explicit; web and worker startup must not run it automatically.
Inspect the target before applying it and retain its reviewed SQL and source
revision. Keep the new `astra_ingestion_v1` schema isolated from scanner tables
and from the legacy `rd_*` queue.

Use a dedicated non-administrator runtime role. Confirm its effective grants,
schema access, ability to perform the required ledger operations, and rejection
of reads/writes outside the ingestion schema. Migration ownership and runtime
ownership should be separate. Verify that neither `anon` nor `authenticated`
has unintended direct grants, and that the schema is not inadvertently exposed
through the Data API. If exposed, RLS and suitable policies are mandatory; for a
private schema, evaluate RLS as additional protection with explicit tests.

The implementation revokes public schema/table/function access, but those
statements alone do not prove the live role or Data API configuration is correct.
Run the provider security advisors after applying the reviewed migration and
resolve any newly introduced issue. Confirm certificate-verified PostgreSQL TLS
with the deployed connection configuration; do not weaken TLS verification to
make a connection succeed.

### Hosting and controls

Deploy the isolated web and worker entry points. Do not resume the suspended
legacy loader or start `app.worker` as a shortcut: that entry point can include
old queued work and unrelated scanner/audit loops. The prior live inventory
identified the legacy loader web service `srv-d9p2vljncjis73evkoc0` and worker
`srv-d9p2vljncjis73evkocg` as suspended, and C11 as active in a separate repository.
Refresh service state immediately before any deployment action.

Use the production ASGI entry point, HTTPS at the hosting boundary, a dedicated
owner credential, and protected environment variables. Verify authentication,
origin/control-header checks, rejection of oversized bodies and conflicting
idempotency keys, health/readiness behaviour, and safe error output on the actual
deployment. A successful `/healthz` response proves database/schema readiness
only; it does not prove worker activity or useful ingestion progress.

Keep one bounded ingestion worker for this release. Confirm real connection,
rate and concurrency limits against shared provider/database usage, including
the active scanner. Local per-process tests do not establish aggregate account
limits or financial headroom. Record the exact hosting plan, estimated incremental
commitment and current applicable budget before provisioning.

### Recovery and monitoring

The ledger uses database time, durable claim generations and transaction
ownership checks. Demonstrate those invariants on the deployment backend after
process termination, deployment restart and whole-host replacement. Confirm that
pause/cancel wins against a late worker and that a quality-held partition cannot
be released through a generic resume control.

The current worker records durable progress when work commits, but a stopped
worker cannot observe its own outage. Before claiming unattended operation,
establish a separately running observer or provider mechanism that can detect
stalled useful progress, report the exact blocked job and take only bounded,
authorised recovery actions. Record its owner, active state, checks and stop
behaviour. Do not equate a process heartbeat with useful progress.

## Meaning of a successful result

Successful verification means that every retained, validated source record in
the admitted partition matches the stored record by exact key and value, with a
complete retained pagination chain. The implementation keeps source-to-target
verification distinct from historical dataset certification and returns
`coverage_certification: NOT_CERTIFIED`.

The current verifier reads through a fresh database snapshot using the same
runtime credential and normalization code. Its evidence establishes fresh
source-to-target readback. An independently privileged verifier and a second
independently implemented parser remain unqualified. It does not establish that
the provider returned every historically expected bar, resolve dated equity identities, or certify financial
information as available at the historical decision time.

Full ASTRA certification must retain its original expected population, identity,
provenance, financial point-in-time and quality gates. Do not convert the bounded
canary's success into a full-universe, financial-factor, trading or profitability
claim.

## Release evidence to retain

Keep the exact source revision, manifest/hash and idempotency key; migration and
role test results; CI and deployment references; provider request IDs and receipt
hashes; each partition's result; exact reconciliation outputs; interruption and
recovery observations; cost/resource measurements; preserved holds; and the
remaining unqualified gates. Report `implemented`, `tested`, `published`,
`deployed`, `live-canary-verified` and `historically-certified` separately.
