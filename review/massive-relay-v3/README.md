# Managed Massive relay v3 preparation

This directory contains a versioned connector-compatible installer proposal. It is **not approved or installed**. The original v2 approval expired; all v2 files and evidence remain intact.

Read [the security review](../../evidence/replacement-managed-relay-security-review-v3.md), [exact SQL diff](installer-security-v2-to-v3.diff) and [scope](../../evidence/replacement-managed-relay-review-scope-v3.json). Runtime Edge/Python/worker artifacts remain pinned to the existing v2 candidates; only the installer and its approval bindings are revised.

## Existing connector route

The controller uses the project-scoped Supabase Market Data Cloud `apply_migration` connector. Its exact generated wrapper may end with `commit;` or `commit;` plus one LF. V3 admits exactly those two full wrapper strings while requiring unchanged executable-body hashing and a byte-identical history copy. No native PostgreSQL connection or new credential setup is required.

Before owner approval, the controller may execute [the read-only probe packet](transport_readonly_probe_action_v3.json). The probe explicitly sets transaction read-only and intentionally raises `ASTRA_RELAY_V3_TRANSPORT_PROBE_ACCEPTED` before any history write. The expected tool result is an error containing a safe bounded JSON receipt. A generic error is not a pass. Reconcile unchanged hold, object absence and history after the probe.

After independent review and verified transport, [the installation action packet](installation_action_packet_v3.json) supplies exact apply arguments and required pins. Its approval template contains placeholders and cannot satisfy the installation gate. Only a fresh explicit user action-time approval of this v3 package can do so. Preserve the original v2 expiry and never re-date it.

## Local qualification

The tests accept only the existing disposable loopback database through the inherited fixture. They never accept a production target. Run the source checks without a database:

```bash
python3 -m unittest discover -s review/massive-relay-v3/tests -p 'test_managed_relay_v3_source.py' -v
```

Run the actual PostgreSQL cases only against the already available disposable test database:

```bash
ASTRA_INGESTION_POSTGRES_TEST_URL=postgresql://postgres@127.0.0.1:55432/astra_ingestion_qualification \
PYTHONPATH=.:tests/ingestion \
python3 -m unittest discover -s review/massive-relay-v3/tests -p 'test_managed_relay_connector_v3.py' -v
```

The fixture creates unique local schemas/roles and removes those exact objects on cleanup. No provider request, production service call or credential read occurs. See [the qualification receipt](../../evidence/replacement-managed-relay-qualification-v3.json) and [independent review](../../evidence/replacement-managed-relay-independent-review-v3.json) for recorded results and limits.
