# Read-only transaction hotfix (v1.0.3)

This release prevents the background worker from rerunning schema DDL on every restart and adds an explicit database write-state diagnostic.

## Required connection

Use the **primary Supabase Session Pooler** URI for both Render services. It must use port `5432`. Do not use a read replica or the transaction pooler on port `6543`.

## Render settings

- Web: `AUTO_MIGRATE=true` for initial installation, then it may be changed to `false` once the schema exists.
- Worker: `AUTO_MIGRATE=false`.

After changing `DATABASE_URL`, restart the worker. It will recover stale `running` tasks to `pending` and stale `loading` tasks to `staged` after the configured stale threshold.
