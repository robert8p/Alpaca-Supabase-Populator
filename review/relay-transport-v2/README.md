# Exact-byte native PostgreSQL transport preparation

## Current state

**Production readiness: false.** The native transport is qualified only against
the existing disposable loopback PostgreSQL database. No production native
connection is established or assumed. The existing controller retains ownership
and the production relay hold remains in place.

This directory contains a fixed **read-only probe**, its restricted runner, and
guard tests. It contains **no relay migration activation runner**. Nothing here
renews approval, creates a connection profile, installs software, or changes the
reviewed relay package.

The unchanged migration is `sql/astra_backfill_massive_relay_v2.sql`:

- SHA-256: `4be1c6d145949f4cda35a1cef7772da93137e3f102f045f1a7507ea66a16652d`
- Size: 21,525 bytes; final byte LF (ASCII 10)
- Review: `managed-massive-relay-v2-review-20261030`
- Scope SHA-256: `7e253852f3173c9c3b7ba6d919e4d8abe82cb949424096beee56ddc0e2c20fbe`

## What the probe does

`native_readonly_probe.sql` starts a read-only transaction, sets bounded local
statement/lock timeouts, selects only transport metadata, and rolls back. It does
not inspect application tables, roles, grants, keys, or credentials. Its receipt
includes the SHA-256 and UTF-8 length of PostgreSQL's actual `current_query()`,
the final character, and the effective read-only transaction setting.

The runner verifies the fixed probe hash before connecting, decodes the file
without trimming or newline conversion, and passes the whole string as one
`psql --command` argument through `subprocess.run(..., shell=False)`. It disables
psql startup files and password prompts. It permits only a simple existing
libpq service name or the fixed disposable local qualification target. It does
not accept a DSN, arbitrary SQL, an alternate SQL path, or migration content.
There is no automatic retry. Connection errors are summarized without echoing
their raw diagnostic text.

The application does not inspect or export authentication material. When the
owner selects an existing service, libpq uses that service's normal existing
authentication configuration. This is not a way to establish a new relationship
or to retrieve its credentials.

## Owner-operated read-only command

Use this only on an owner-controlled machine that already has Python, `psql`,
and the intended authorized libpq service configured. Do not create or modify a
service, install software, log in, obtain a token, copy a credential, or grant
access to run this preparation. If no such existing service is available, stop
and retain the transport blocker.

From the repository root, replace `EXISTING_SERVICE_NAME` with the name of that
already configured service:

```bash
python3 review/relay-transport-v2/native_readonly_probe.py \
  --service EXISTING_SERVICE_NAME \
  --owner-confirms-existing-authorized-connection
```

This command executes **only the fixed read-only probe**, once. The owner can
return the resulting JSON to the existing controller; it contains no connection
string, account name, password, or application records.

A pass requires all of the following values to match exactly:

| Receipt field | Required value |
| --- | --- |
| `status` | `READ_ONLY_EXACT_BYTE_PROBE_PASSED` |
| `observed.query_sha256` | `2a292e5b12394f0c5b4ddc455f7c04291ff61956c5b2565e302e8e9d526b526e` |
| `observed.query_utf8_bytes` | `712` |
| `observed.final_byte_ascii` | `10` |
| `observed.transaction_read_only` | `on` |
| `migration_executed` | `false` |
| `approval_recorded` | `false` |
| `production_ready` | `false` |

`production_ready` deliberately remains false even on a pass: transport equality
does not establish that the selected service is the intended production target,
reconcile any intervening writes, or supply current action-time approval. A
failure is a stop condition. Do not change the probe or relay validator to make
it pass, and do not retry an unresolved production action.

## Subsequent unchanged relay application: controller gates

After an owner-operated probe passes, the existing controller must complete the
following before asking for a fresh 15-minute renewal:

1. Reconcile the intended production target, ownership, current relay hold, and
   any uncertain writes through already-authorized read-only access. The
   owner's service name alone is not target-identity evidence.
2. Verify the unchanged 19-file review manifest and the exact migration hash,
   length, final LF, and current approved runtime/auth prerequisites.
3. Prepare the final application action against that same confirmed existing
   native transport. Preserve the entire file as one query string. Do not use a
   statement-splitting file runner, trim or reformat the body, synthesize an
   alternative wrapper, append statements, or substitute `current_query()`.
   In particular, shell command substitution strips trailing newlines and must
   not be used to load this file into a `psql -c` argument.
4. Present the exact unchanged package and concrete prepared action for the
   user's fresh action-time renewal. The old approval is expired. Only the
   existing controller records and verifies the renewal under the existing
   15-minute guard.
5. Apply once only after those gates succeed. Independently read back the
   result before any retry or later deployment. If the action's outcome is
   uncertain, preserve the hold and reconcile it first.

The executable in this directory intentionally does not implement steps 3–5.
It will reject any attempt to replace the fixed probe with migration SQL.

## Local qualification

These commands need no new installation or production credentials:

```bash
python3 review/relay-transport-v2/test_native_readonly_probe.py
python3 review/relay-transport-v2/native_readonly_probe.py --local-qualification
```

The second command uses only the existing disposable database at loopback
`127.0.0.1:55432`, database `astra_ingestion_qualification`, user `postgres`.
Both `host` and `hostaddr` are explicit, so inherited libpq routing defaults
cannot redirect the disposable qualification connection.
It performs no schema changes. Its success is local evidence only.

## Primary references

- [PostgreSQL psql](https://www.postgresql.org/docs/current/app-psql.html): each
  SQL string passed through `-c` is sent as one server request.
- [PostgreSQL libpq command execution](https://www.postgresql.org/docs/current/libpq-exec.html):
  `PQexec` accepts a complete multi-statement command string.
- [Supabase native PostgreSQL clients](https://supabase.com/docs/guides/database/psql):
  native connections are supported. This runbook uses an existing authorized
  connection and does not reproduce connection-setup or credential steps.
