# Retained preservation catalogue correction — 29 October 2026

This correction supersedes the three-entry/3,074-document counts in the first
bulk-delivery specification. The initial production capture failed closed at its
D06 boundary; immediate readback confirmed zero capture receipts and zero evidence
rows. The base migration did succeed and must NOT be reinstalled.

A complete bounded aggregate at 09:14:08 London found 1,065 unique scoped D06
preservation catalogue entries, all with valid raw metadata hashes, catalogue state
CATALOGUED_SOURCE_UNMODIFIED. Catalogue-set SHA256:
`87e623c92ea90cc14c8ead2e6141184978542ba0876a9f603317f99f7e3daf4f`.
The earlier three-entry result was not a complete catalogue; never use it as the
full denominator. No underlying preserved relation is acquired, reopened or changed.
Only the existing catalogue evidence is copied to the isolated ASTRA schema.

After its own exact-revision CI passes, apply only
`sql/astra_ingestion_bulk_scope_catalogue_fix_v1.sql`. It requires an empty reconciled
destination, replaces only the capture function, validates all 1,065 catalogue
entries and their pinned ordered relation/metadata-hash set, and expects 4,136
retained evidence documents. It does not loosen original company/family/calendar
or source-hash requirements. Missing/re-keyed catalogue entries fail closed.

The PostgreSQL qualification applies the original base migration followed by this
correction, tests complete retention, immutable/idempotent receipts, actual RLS
actor denial, rollback on 15 distinct source-corruption cases, and postcommit
client-loss reconciliation. Client loss remains a simulation, not physical host
replacement. The migration rejects reapplication after a committed capture.

Preserve the first failed attempt in the completion checkpoint. Perform fresh
writer/head/lease/operation reconciliation before migration and capture. Read back
the complete count/hash, source equivalence, unchanged old qualification jobs and
stopped legacy control. Keep CAPTURED_NOT_ADMITTED and historical NOT_CERTIFIED;
this is retained scope evidence, not completion of the 24-family research dataset.
