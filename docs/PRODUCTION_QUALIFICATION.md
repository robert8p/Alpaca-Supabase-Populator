# ASTRA ingestion production qualification

Assessment date: **28 October 2026**. This document separates observed project
identity, implemented behaviour, local verification, and the evidence still
required before a production completion claim.

## Release preparation checkpoint

Checkpoint: **2026-10-28T22:24Z**. The historical published baseline is commit
`73f4f3e5a07cd7ae2c5d7d4b34653f3de1b84a60`. See
[PR 93](https://github.com/robert8p/Alpaca-Supabase-Populator/pull/93) for the latest
publication and check state; this document records the preparation evidence.
The current working revision implements restricted HTTPS persistence in
`astra_ingestion/rpc_store.py`, the original RPC SQL, and a narrowly scoped
forward authentication-context repair. Both RPC migrations are installed on the
intended Supabase project. All 17 function bodies and their access metadata
match the tested baseline plus that exact dispatcher repair.

**At the preparation checkpoint, the working source had passed 112 local tests
and ten actual HTTPS boundary checks and still awaited publication and CI.**
This revision requires its own exact-commit CI result. No hosting service or
provider ingestion was activated by these checks. Final database readback
shows ten RLS tables, zero anonymous table grants, zero active credentials and
zero jobs, records and receipts. All four temporary qualification digest rows
are revoked; a formerly valid capability was rejected again over HTTPS, and the
temporary plaintext credential file was deleted. Persistent runtime capability
provisioning and hosted deployment remain separate steps.

Direct database logins would inherit the shared `pg_net` privileges described
below; they are no longer the production runtime transport. Live HTTPS boundary
qualification is not a claim that an ingestion job completed or that unrelated
public functions have been audited.

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

## Historical CI qualification

The [ingestion CI run](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40762186249)
completed successfully for commit `a0932015ff1085607d22ee6b5c33b2d3c1cc0516`.
All **77 tests passed with zero skips**, including all **10 PostgreSQL** and
**8 ASGI API** tests. Python was 3.12.15 and PostgreSQL was the disposable
PostgreSQL 17 service supplied by the workflow. Retained machine-readable
evidence is in `evidence/ci-qualification.json`.

This supersedes the missing-adapter portion of the earlier local result. It does
not establish live Supabase permissions, RLS/TLS, provider entitlement, hosting,
useful-progress monitoring or completed live ingestion.

The later published commit `73f4f3e5a07cd7ae2c5d7d4b34653f3de1b84a60` also passed
[all 77 ingestion tests](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40762636622)
with zero skips and the
[existing release gate](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40762636513)
with 450 passed and 10 skipped. The equivalent PR-triggered workflows passed.
Those CI runs predate the CA, role-admission, live-schema evidence and restricted
RPC changes. They do not qualify any of those later changes or substitute for
CI attached to the exact subsequent publication commit.

## Current RPC qualification

The final complete local ingestion suite finished at **22:23:43.724005 UTC on
28 October 2026** with **112 passed, 0 failures, 0 errors and 0 skips** using
Python **3.12.14** and disposable PostgreSQL **17.11**. The suite includes
17 PostgreSQL RPC tests, 12 HTTP boundary tests, 8 configuration tests, the
existing 10 PostgreSQL tests, 8 ASGI API tests plus an import-isolation test,
and 3 role-admission tests. This rerun includes the forward authentication
repair and its regression checks.

The [machine-readable result](../evidence/rpc-qualification.json) retains the
exact command, 31 source-file SHA-256 values, interpreter/database versions,
timestamps and counts. It records that source files did not change during the
run. The [complete test output](../evidence/rpc-tests.txt) is retained alongside
it. An earlier full-run attempt failed because a crash-recovery child process
could not import `psycopg`; supplying the pinned dependencies through a dedicated
test interpreter corrected that environment issue. The earlier failure logs
were retained separately, and the final result above is a complete rerun.

The tested source was an unpublished working revision at the preparation
checkpoint. These local results do not confer CI qualification; consult PR 93
for the subsequent exact-commit result. Historical CI results belong to the
specific commits identified above. The proposed deployment remains pinned to
Python 3.12.15, while this local run used 3.12.14.

Local RPC tests use the isolated loopback `astra_ingestion_qualification`
database and a simulated gateway context. They do not prove real Supabase HTTPS
routing, gateway claim/header handling, effective public API access or hosted
deployment. The subsequent live boundary probes below provide separate HTTPS
evidence. State flags in the local test receipt describe that earlier test-time
snapshot; later installation and cleanup receipts supersede those live-state
flags without changing the local test result.

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

### Live schema installation and readback

Authenticated dashboard SQL subsequently succeeded on the intended project.
Before the mutation, `astra_ingestion_v1` and both proposed runtime role names
were absent. The 75 unsuperseded job-control records comprised 17 cancelled,
55 complete and 3 rejected jobs. The three inspected older full-window ingestion
controls were disabled. Those jobs, counters, holds and permissions were not
changed or resumed by this work. The separate September 2025 canary was undispatched at this check and cannot
release a historical-identity or protected-outcome hold.

Only the reviewed schema transaction was submitted. Its exact UTF-8 payload was
9,374 bytes with SHA-256
`8980049b20238a937a38865453821432664056f2772a5671b2a4f3aadf9d24c8`.
The schema SQL is retained in `sql/astra_ingestion_schema_v1.sql` and the complete
bounded readback is in `evidence/live-schema-verification.json`.

Readback confirmed schema version 1, nine tables with RLS enabled, zero
non-owner ACL entries, zero RLS policies, two invoker trigger functions and two
scope guards. `anon`, `authenticated` and `service_role` had no schema usage.
There were zero runtime roles, jobs, records and receipts. The only seeds were
schema version 1 and the initial `alpaca:0` pacing row. Administrative ownership
remains privileged. This is private schema installation evidence, not runtime
permission, TLS, hosting or ingestion qualification.

### Live RPC installation and readback

The separate migration `astra_ingestion_rpc_v1_20261028` was applied successfully
to `oxzabweahkoimtevbbny`. Its exact reviewed SQL SHA-256 is
`eac2550cab52917ffd1ad7c884cd6bf97c40512a2090ee71912d81eb602ada2a`, matching the
baseline source included in the local test receipt. Do not rerun this one-time
migration blindly; the required forward repair below is a separate migration.

[Live RPC readback](../evidence/live-rpc-verification.json) records all
17 installed function bodies and confirms that their hashes match the tested
source. It also records ten tables with RLS enabled, zero table grants to
`anon`, and the expected function owner: `NOLOGIN`, `NOINHERIT`, no superuser,
no bypass-RLS, no database/role creation, no table ownership, no schema creation
and no credential-write access. At this installation readback there were zero
credentials, jobs, records and receipts.

The scoped post-migration security-advisor check returned no ingestion findings.
This is not a clearance of unrelated project objects or the existing public
function surface. This baseline receipt predates the authentication repair and
HTTPS qualification below; retain it as the installation history, not the final
installed dispatcher or credential state.

### Forward authentication repair and live HTTPS qualification

The initial actual HTTPS probes exposed a provider-owned `auth` schema mismatch:
the intended function-owner USAGE grant had not taken effect, so the original
`auth.uid()` call could not execute. The first failed result is preserved in
[evidence/live-rpc-https-initial-failure.json](../evidence/live-rpc-https-initial-failure.json).
Its pending-cleanup field describes that initial stage and is superseded by the
completed cleanup receipt below.

The baseline `sql/astra_ingestion_rpc_v1.sql` is intentionally unchanged.
`sql/astra_ingestion_rpc_auth_context_v1.sql` is a separate, required forward
migration with SHA-256
`81f4258b8a492dfa3a1186cd92c08da49773bc0e81bb49e05659738107e83631`.
It replaces only the hash-bound dispatcher's `auth.uid()` predicate with direct
checks that the gateway/JWT role is `anon` and neither the JWT claims nor the
legacy claim setting contains a user subject. It adds no schema privileges or
credentials and preserves ownership, function attributes and ACLs. The function
owner still has no `auth` schema USAGE after repair.

[Forward-migration readback](../evidence/live-rpc-auth-context-verification.json)
confirms all 17 function bodies and access metadata against the reviewed
baseline plus this one dispatcher replacement. Ten tables retain RLS, the owner
remains limited and `NOLOGIN`, and anonymous table grants remain zero. Scoped
security advisors report no ingestion findings.

**Fresh installations must apply the baseline RPC migration and then this
forward repair.** Applying only the historical baseline leaves the observed
live authentication failure unresolved. Both are already installed on the
current target; their admission guards deliberately reject blind replay.

The [final live HTTPS receipt](../evidence/live-rpc-https-qualification.json)
records all ten checks passing between **22:24:06 and 22:24:08 UTC on
28 October 2026** through the production client and exact project origin, with
TLS verification enabled, redirects refused and no service-role key:

| Live check | Observed result |
| --- | --- |
| API and worker health | Both capabilities returned validated schema/RPC readiness |
| API job inventory | Empty |
| Missing, unknown, expired and revoked capabilities | HTTP 401 for all four cases |
| Worker using API operations; API claiming worker jobs | HTTP 403 for both cases |
| Private ingestion schema requested as an API profile | HTTP 406 / `PGRST106` |

The **22:24:27.754808 UTC** cleanup readback confirms all four temporary
qualification digest rows revoked, zero active ingestion capabilities, and zero
jobs, records and receipts. A formerly valid API token was tested again and
returned HTTP 401. The temporary plaintext credential file was deleted; revoked
digest records remain for audit. No provider request or ingestion job was
submitted during qualification.

This proves the tested ingestion authentication and schema boundary. It does not
prove live ingestion transactions against Alpaca, provider SIP entitlement,
hosted service recovery, or authorization correctness of unrelated public RPCs.

### Direct-login isolation blocker

The catalog showed `PUBLIC` usage on `net`, plus all table privileges on
`net.http_request_queue` and `net._http_response`; both tables have RLS disabled.
Any newly created direct-login role would receive that access in addition to
its explicit ingestion grants. No queue rows, headers, response bodies or
credentials were read to establish this finding.

Supabase documents that these objects are provider-owned, the project `postgres`
role cannot remove their grants, and individual roles cannot be excluded from
`PUBLIC`. `NOINHERIT` does not remove this access. See
[Supabase's pg_net privilege constraint](https://supabase.com/kb/troubleshooting/revoking-access-to-pg_net-objects-has-no-effect)
and [inherited custom-role privileges](https://supabase.com/kb/troubleshooting/custom-role-inherits-privileges-that-were-not-explicitly-granted).
Do not attempt global revocation, extension removal or another route around
these provider-owned permissions as part of this ingestion deployment.

The role template now fails atomically when this inherited queue access is
present. It also rejects pre-existing runtime-role names and removes unintended
ACLs only within the new ingestion schema before granting its intended access.
It remains a NOLOGIN template, and has not been applied to production.

The adopted working revision uses narrowly scoped Data API/RPC operations
without distributing database logins. The older direct-role template is retained
as evidence and is not the new production activation path. The RPC implementation
preserves whole-operation transactions, lease fencing, durable request
reservation, original budgets and deadlines, and one bounded statement snapshot
for verification. Its client never replays an uncertain HTTP mutation. Local
qualification is recorded above; actual HTTPS and hosted recovery qualification
remain separate requirements.

### Restricted Data API design and observed exposure

The runtime is pinned to project `oxzabweahkoimtevbbny` and HTTPS origin
`https://oxzabweahkoimtevbbny.supabase.co`. The only added public endpoint is the
invoker wrapper `public.astra_ingestion_rpc_v1(operation, payload)`. It invokes a
private dispatcher with a closed list of operations; callers cannot supply SQL,
schema names, destinations or function names to execute.

The private functions are owned by `astra_ingestion_rpc_owner_v1`, a new
`NOLOGIN`, `NOINHERIT`, `NOBYPASSRLS` role with neither superuser privileges nor
table ownership. Explicit table grants and RLS policies allow the required
ledger operations. The migration grants no credential-writing, deletion,
truncation or schema-creation privilege for runtime use. A fixed definer function,
not a distributed database
credential, is the entry point to these privileges. The design does not claim
that PostgreSQL `PUBLIC` privileges have disappeared from this role.

After the forward repair, admission requires the gateway role and JWT role to
be `anon`, no user subject in the JWT claims or legacy claim setting, the HTTP
method to be POST, and an exact 64-lowercase-hex-character
`X-Astra-Ingestion-Token`. The dispatcher hashes that token and checks its actor,
expiry and revocation state before dispatch and again after obtaining the
application transaction lock. An ordinary user session or a public project key
alone is insufficient. Separate `api` and `worker` capabilities have disjoint
operation sets except for `health`.

The Data API settings UI was observed with only `public` and `graphql_public`
selected as exposed schemas; `astra_ingestion_v1` was unchecked. The extra
search path displayed `public, extensions`, the maximum row setting was 1,000,
and the UI reported 0 tables and 36 functions. A subsequent catalog privilege
inventory found **0 anonymously reachable tables and 37 anonymously callable
functions** across `public` and `graphql_public`: **24 SECURITY DEFINER and
13 SECURITY INVOKER** functions. The earlier UI count and later catalog count
are separately retained observations. The final ingestion evidence addresses
its own installed function bodies and HTTPS boundary; those counts alone do
not establish the behaviour of unrelated functions.

The ten ingestion HTTPS boundary probes passed as recorded above. They do not
turn this inventory into an authorization audit of existing public functions.
Do not treat these counts, local SQL tests or the new wrapper as proof that all
existing anonymous API access is appropriately restricted. Unrelated callable
definer functions are outside the claims of this ingestion qualification.

Keep the ingestion schema outside the exposed schema list. The wrapper requires
schema usage and dispatcher execution for `anon`, but grants no direct table
access to that role. Applying the migration therefore changes some schema and
function grants from the historical owner-only installation; retain and review
that exact difference rather than carrying forward the earlier zero-ACL claim.

### Secure capability provisioning

Both services require `ASTRA_INGESTION_PROJECT_REF`,
`ASTRA_INGESTION_API_URL`, `ASTRA_INGESTION_PUBLISHABLE_KEY` and
`ASTRA_INGESTION_RPC_TOKEN`. The project reference and origin must match the
exact admitted values above. The project key must be a public publishable key
or the project-bound legacy `anon` key. Production configuration rejects a
database DSN; runtime receives no `service_role` key or project signing key.

The RPC migration initially left `astra_ingestion_v1.runtime_credentials` empty.
All four temporary HTTPS test capabilities have now been revoked with database
and HTTP readback, leaving zero active capabilities. For persistent runtime
access, generate
independent 256-bit random tokens for the API and worker through an approved
secure provisioning channel, encode each as 64 lowercase hexadecimal characters,
and store plaintext only in the corresponding service's protected environment.
A separately authorized administrator records only SHA-256 of the token's
UTF-8 text, its `api` or `worker` actor, and a finite expiry in the private table.
No actual token, password or provider secret belongs in this document, SQL
source, source control, logs, screenshots or test evidence. Do not reuse the web
owner password as an RPC capability.

Only the administrator provisions, rotates or revokes these digest records;
runtime cannot write them. Revocation uses `revoked_at`, and requests after
expiry or revocation are denied. The initial empty table admits no runtime
capability. Registering digests, binding runtime secrets and proving the live
allowed/denied paths remain separate activation steps.

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

| Gate | Required evidence | Status at preparation checkpoint |
| --- | --- | --- |
| Exact source publication | Repository commit and readback of the complete diff, followed by checks for that exact commit | Historical baseline `73f4f3e` qualified; RPC source awaited publication and exact-commit CI at 22:24 UTC; see PR 93 for subsequent state |
| PostgreSQL behaviour | All current store, role and RPC tests run without skips against the explicit disposable local test database, with exact source hashes | Full local 112-test suite passed, including 17 RPC, 10 existing PostgreSQL and 3 role-admission tests; exact-commit CI still required at the checkpoint |
| ASGI and HTTP behaviour | Current ASGI, HTTP persistence and configuration suites with pinned dependencies; uncertain-outcome and credential-boundary cases | Full local suite passed, including 8 ASGI API tests plus import isolation, 12 HTTP boundary and 8 configuration tests; exact-commit CI still required at the checkpoint |
| Target and scope | Explicit binding to the intended current project, exact manifest and retained current holds | Project and bounded control inventory verified at the last live check; refresh before canary admission |
| Schema and RPC admission | Reviewed one-time RPC migration over the installed private schema; limited definer owner and RLS; credential lifecycle; catalog and real HTTPS positive/negative probes | Baseline and forward repair installed; 17 function bodies/ACLs matched, ten RLS tables and zero anonymous table grants; all ten HTTPS boundary probes passed; temporary capabilities revoked; evidence is confined to the ingestion endpoint |
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
database through the app defaults. Use an isolated disposable qualification
database and let each test clean up only its own admitted test objects. Run the
suite through the supplied CI workflow or a correctly configured local
PostgreSQL server. A missing database URL or missing runtime dependency is not a
passing production test.

At minimum, retain evidence for atomic receipt/record/checkpoint commit, exact
readback from another connection, idempotent submission, scope immutability,
expired-lease takeover, denial of stale-owner writes, persisted rate-limit delay,
quality holds, budget exhaustion, and process interruption after commit. For the
RPC path, also retain actor separation, unauthenticated/expired/revoked-token
denial, direct table-access denial, response validation, bounded payloads and
refusal to replay uncertain HTTP mutations. A simulated gateway context must be
labelled as such and followed by real HTTPS probes.

### Database access, RLS and HTTPS

Production migration is explicit and administrative; runtime cannot migrate.
The original schema transaction, baseline RPC migration and mandatory forward
authentication repair are already installed and must not be rerun blindly. Retain the exact reviewed SQL bytes,
source revision and installed-object readback. Inspect the target and review a
new migration for any subsequent change; do not bypass the current migration's
existing-object or changed-grant admission guards.
Keep the private schema separate from scanner tables and the legacy `rd_*`
queue, and outside the Data API's exposed schemas.

Confirm the definer owner remains `NOLOGIN`, `NOBYPASSRLS` and distinct from
table ownership. Verify all effective function/table grants, explicit RLS
policies, actor restrictions and credential-table protections. Test missing,
invalid, expired and revoked capabilities, authenticated-user contexts,
wrong-actor operations and attempts to access tables or unrelated functions.
The project's existing public API surface needs its own catalog and endpoint
review; adding a guarded wrapper does not automatically secure older functions.

The post-repair scoped security-advisor result and actual HTTPS checks are
recorded above. Repeat the affected checks after a future migration or credential
boundary change and resolve any newly introduced finding before activation.
The client uses Python's default trusted HTTPS context, exact-project origin
binding and redirect refusal. Do not disable certificate or hostname validation.
No live PostgreSQL connection is part of the production runtime design.

### Certificate provenance and rotation

This subsection preserves evidence from the earlier direct-PostgreSQL candidate;
the restricted Data API runtime does not use this certificate or set
`PGSSLROOTCERT`. It uses the operating system's HTTPS trust store instead.

On **28 October 2026**, the target project's authenticated Supabase dashboard
confirmed session-pooler endpoint `aws-0-eu-west-1.pooler.supabase.com:5432` for
`oxzabweahkoimtevbbny`. This endpoint was observed in the Connect dialog, not
constructed from the region. The dialog's direct-connection username format was
`[ROLE].oxzabweahkoimtevbbny` and its database name was `postgres`; those are not
instructions to provision runtime database logins.

The same project's Database Settings linked the
[public Supabase CA certificate](https://supabase-downloads.s3-ap-southeast-1.amazonaws.com/prod/ssl/prod-ca-2021.crt).
The browser-downloaded bytes are retained unchanged at
`astra_ingestion/certs/supabase-project-ca.crt`. OpenSSL parsed it as one X.509 CA
certificate with critical `CA:TRUE`, certificate-signing/CRL-signing key usage,
and a valid self-signed trust anchor. The PEM contains no private key.

| Property | Verified value |
| --- | --- |
| Subject and issuer common name | Supabase Root 2021 CA |
| Valid from | 28 April 2021, 10:56:53 UTC |
| Valid until | 26 April 2031, 10:56:53 UTC |
| File size | 1,367 bytes |
| SHA-256 of exact PEM file bytes | `700723581420dd1ac98fd7e9ac529f0ef210eadcaf87fc868a3ad7d114c2f3b7` |
| SHA-256 X.509 certificate fingerprint | `80:70:25:AD:50:D4:ED:21:9D:2C:9C:7D:29:9C:00:4F:82:4E:B0:0C:F7:F6:5A:FE:F6:07:D0:7B:72:E6:CA:FA` |

The file hash measures the exact PEM encoding; the X.509 fingerprint measures
the certificate's DER encoding. They intentionally differ.

The former candidate used this public CA with libpq `sslmode=verify-full`.
The current `render-ingestion.yaml` removes that configuration and supplies only
the public project API key and each service's separate RPC capability for
persistence. PostgreSQL documents the former trust-root setting
in its [SSL client guidance](https://www.postgresql.org/docs/current/libpq-ssl.html),
and Supabase documents verification with its downloaded CA in the
[PSQL connection guide](https://supabase.com/docs/guides/database/psql).

The retained file is historical evidence, not an active runtime trust override.
Any future separately admitted use of direct PostgreSQL must recheck the
authoritative certificate source, validity and server chain, including announced
CA rotations. Do not reactivate database logins or weaken TLS merely because a
certificate file is present. This repository does not automatically refresh
that historical trust root.

This validation establishes the downloaded trust anchor's identity and integrity.
It does not establish the current server certificate chain, successful runtime
role authentication, RLS/grants, or a completed live TLS connection. It also does
not establish successful HTTPS RPC authentication or qualification.

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

The RPC verifier obtains receipts and records through one bounded statement
snapshot using the worker capability and existing Python normalization code.
The SQL commit path independently validates source-page parsing, but a second
independently qualified end-to-end verifier and an independently privileged
verifier remain unqualified. Source-to-target readback does not establish that
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
