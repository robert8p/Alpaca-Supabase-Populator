## Additional verified September P01/P02 source-reuse assessment — 29 October 2026, 22:00 London

**Original source view is not independent:** Read-only `pg_get_viewdef` confirmed `market_fixed_20250901_20260831.us_equities_bars_1m` reads from `alpaca_sip_bars_1m_enriched`, which itself joins the *same* `market_fixed_20250901_20260831.alpaca_sip_bars_1m` parent to `reference.alpaca_fixed_window_instruments_v1`. The P01 view does not supply a separate September replacement. P02's original contract only declares the base parent.

**Protected legacy Top-3,000 retained price rows (READ ONLY; no mutation/restart):** `population_top3000_202608_202609_v1.retained_price_observation_v2` contains **13,406** rows for **4** distinct companies, earliest 2026-08-03, latest 2026-08-31, **zero September rows**. `working_retained_price_observations_v2` also contains **13,406** rows for the same four-company cardinality, with **zero September rows** and **all 13,406 rows marked `family_accepted=false`**; all 13,406 rows have NULL `expected_minute_bars`. Do not assume these two stores are disjoint, accepted, complete, eligible or independent. These are read-only, narrow source diagnostics, not a source-backed complete denominator, a licensed price export or a new bulk job.

**Actual original P01/P02 contract checks:** The retained `P01` contract SHA256 is `9eda239c37522ec884e090279220fd701b41f6140bf0a66674b2a3a4798fe387`; its expected unit is "eligible security-session-minute and required bar field", dependencies REF01/N03. The retained `P02` SHA256 is `ba96c9a04d15e88f0674278dd9ea789d61a7e62cd2e10da754d2c3426655c8bb`; expected unit is "eligible security-extended-session-minute and bar field", dependencies REF01/P01/N03. The original contracts demand provider-eligible trade/calendar validity and bar/field checks. Neither observed bars nor an empty source can prove eligible no-trade or non-applicability. Historical identity, source-feed, raw adjustment and publication/availability need separately verified evidence.

**Next admissible source work:** Use a finite, read-only instrument-key plus timestamp keyset probe on the original SIP parent to reuse actual rows and record source receipt hashes, but keep the September denominator UNKNOWN and acquisition BLOCKED until a fully sealed, finite provider request manifest, verified historical identities and eligible calendar are in place. The existing 4-company August retained data may be considered only with independent verification and preserved holds. No provider request, cost, production DDL/DML or legacy restart was made in this inspection.

---

# ASTRA Missions 1+2 — source-backed gap evidence, 29 October 2026

**Evidence version:** ref01-and-p01-temporal-gap-v1 (source-only; not ingestion or acceptance).  
**Source:** connected Supabase project `oxzabweahkoimtevbbny`, read-only metadata and aggregate SQL on 29 October 2026, approximately 21:04–21:19 Europe/London. Queries were separate reads, not one transactionally frozen cross-source snapshot.  
**Mutation/financial effects:** NONE. No source/table alteration, new provider requests, charges, migration, role grants, deployment, job submissions or revived legacy controllers. No licensed price records, credentials or full security listings are in this file.

## Exact frozen programme context

Original retained source capture: `top3000-augsep2026-retained-scope-v1`; 3,000 distinct accepted companies; **24 original families**, **42 trading sessions**, **1,065 D06 preserved catalogue entries**, and **4,136 retained scope documents** according to independently recorded previous capture evidence. Membership is accepted only as practical membership, NOT proof of financial ranking, exact historical security identities or complete source data. D06 is preservation-only.

The exact REF01 original retained contract was read from the immutable capture (`kind='contract', evidence_key='REF01'`), source hash `84087d66fa8a16426d45f5d25c856eaa9627d42e98c5da2e069d0d495e769553`. It declares expected units **company and effective-dated eligible US security/listing episode** and status `DENOMINATOR_UNRESOLVED`. Its declared routes are precisely:

- `reference.alpaca_fixed_window_instruments_v1`
- `market_reference.instrument_classification`
- `reference.equity_identity_resolution_day_v5`
- `reference.equity_resolved_security_v5`
- `reference.massive_security_master_observation_v1`

All five relation names resolved and their native columns/indexes were inspected. **Relation existence is not temporal, identity, point-in-time or numerical coverage proof.** None of the five by itself supplies independently verified complete historical ranking cap, issuer identity, ADR adjustment and listing interval, so no complete REF01 denominator can be certified.

## Actual cohort-source reconciliation

| Evidence checked | Read-only result | Interpretation |
| --- | ---: | --- |
| Accepted original company rows in capture | **3,000** | Membership present, not security mapping certified |
| Anchors with composite FIGI / share-class FIGI / ticker | **3,000 / 3,000 / 3,000** | Anchor fields are present, not independently qualified aliases |
| Accepted companies matching at least one `equity_resolved_security_v5` security using exact composite OR share-class FIGI | **9** | Only nine mappings found *in this specific original route*, not nine historically eligible securities globally |
| Companies unmatched by either FIGI in that particular relation | **2,991** | Missing route correspondence; must use other lawful evidence, not ticker guesses or fabricated N/A |
| Companies matching multiple securities in that particular relation | **0** | No conflict observed on this narrow equality test; not a full lifecycle clearance |

The 9/2,991 result was computed from **both exact FIGI columns** and a UNION of matches, with distinct security keys. No ticker-only matching, cap inference or speculative historical listing dates were used.

## Temporal evidence — important new blocker

`reference.massive_security_master_observation_v1` was read for historical `requested_as_of` coverage. Its **2,844,997 observed rows** range from **2025-09-02 to 2026-07-31**, with **ZERO observations for 2026-08-01 through 2026-09-30**. Hence this original route has **no target-window observations to reuse** for REF01. Research publication times and source-observed timestamps must be independently evaluated on any new equivalent source; `requested_as_of` itself is not a publication time. This is not evidence that no company listed in the window.

The original P01/P02 source `market_fixed_20250901_20260831.alpaca_sip_bars_1m` is partitioned through **August 2026**. August's partition exists (optimizer statistics estimate 38,600,616 source rows, not a measured completeness denominator). **No September partition** was returned in the inspected partition inventory and a direct date-pruned `count(*)` confirmed **ZERO September 2026 one-minute bar rows** in this parent relation. The other P01 route `us_equities_bars_1m` is a VIEW and was not independently certified as a September replacement. Actual eligible instrument-session-minute expected coverage remains unknown and must come from the original date-valid calendar, not from observed bar counts.

## Original 24-family unresolved coverage

The original retained contracts for **every family** still report `DENOMINATOR_UNRESOLVED` as read from the captured 24 contract documents. The following is a **gap inventory**, not a completed or independently reviewed 24-family reconciliation:

| Family/coverage area | Evidence disposition |
| --- | --- |
| REF01 | 3,000 practical members pinned, full effective-dated security universe UNKNOWN; narrow resolved-FIGI route has 2,991 unmatched; original Massive source has no Aug–Sep as-of observations |
| P01, P02 | September 1-minute source partition absent and exact September rows zero in original Alpaca SIP parent; full expected instrument-session calendar unproved |
| D01, D02, D03, D04, D05 | Original expected/observed denominator and target-window date validity not established |
| N01, N02, N03 | Original expected/observed denominator and event-publication coverage not established |
| F01, F02, F03, F04, F05, F06 | Original expected/observed denominator and PIT fundamentals/event mapping not established |
| S01, S02 | Original expected/observed denominator and short-volume/short-interest reporting coverage not established |
| CTX02, CTX06, CTX07, CTX14, REF03 | Original expected/observed shared or security-applicable populations not established; no 3,000-fold duplication of shared sources |
| D06 | 1,065 original entries preserved/catalogued only; NEVER ingestion |

**No family is DATA_ACCEPTED.** Unsupported/new acquisition sources remain blocked until lawfully entitled, contract-equivalent, finite and proven. A source absence is a data gap, not a contract-defined N/A. Coverage in unrelated historical/full-market datasets remains NOT_CERTIFIED.

## Executable source/test response

`astra_ingestion/bulk_ref01_route_probe.py` provides five literal-allowlisted, keyset-paginated, max-128-row **read-only** query plans. Its Massive plan binds the selected FIGI set and exactly the Aug–Sep date window, excludes raw provider payload/prices and rejects foreign rows, duplicate/out-of-order keys, malformed native IDs and uncertain research-availability timestamps. Its page witnesses are deliberately `NOT_POPULATION_CLOSURE`, never reviewer permission or worker admission. No source query is dynamically interpolated with caller-controlled table names. This is staged source engineering; its successful disposable tests do NOT establish deployed source access or held-identity resolution.

Required subsequent work: source-backed, date-valid REF01 security-episode evidence from lawful existing or entitled adapters, explicit P01/P02 September acquisition/reuse with per-session calendar checks, then the remaining contracts' exact independently evidenced unit sets. Keep SQL production admission and worker/reviewer role gates closed until authenticated separate principals, actual source unit seals and hosted recovery/successor guarantees are verified. No campaign expiry; all new jobs individually finite. The existing sole-writer recurrence is the continuing engineering controller; no new controller.

## Query reproducibility notes (read only)

1. Obtain original REF01 declaration and SHA from `astra_ingestion_v1.bulk_scope_evidence_v1` filtered by the exact capture key, `kind='contract'` and `evidence_key='REF01'`.
2. For company anchors, select `source_text::jsonb` only for `kind='company'`, aggregate presence of the exact anchor FIGI fields and compare exact FIGIs to `reference.equity_resolved_security_v5` using **UNION** of composite/share-class joins. Return **counts only**; no identifiers in reports.
3. For massive security-master temporal availability, aggregate `min(requested_as_of)`, `max(requested_as_of)`, `count(*)` and `count(*) FILTER (WHERE requested_as_of >= DATE '2026-08-01' AND requested_as_of < DATE '2026-10-01')`. Inspect `research_available_at` separately before any PIT claim.
4. For P01/P02, inspect `pg_inherits` bounds of `market_fixed_20250901_20260831.alpaca_sip_bars_1m`; then exact September `count(*)` with `bar_ts >= TIMESTAMPTZ '2026-09-01T00:00:00Z'` and `bar_ts < TIMESTAMPTZ '2026-10-01T00:00:00Z'`. A partition or observed count is NOT an expected-session calendar.

**Versioning:** append corrections rather than overwriting raw historical evidence. This document has no executable ownership or admission authority.
