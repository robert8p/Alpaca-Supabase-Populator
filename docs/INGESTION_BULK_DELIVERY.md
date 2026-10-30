## Bound provider HTTPS transport and immutable page observation — 30 October 2026, 04:09 London

**Exact source/test candidate:** [`2e69a5480c79b6d29629c97ec1128f9be9d87b0a`](https://github.com/robert8p/Alpaca-Supabase-Populator/commit/2e69a5480c79b6d29629c97ec1128f9be9d87b0a). [ASTRA ingestion qualification](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/41001271240) SUCCESS **323 tests**; [release gate](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/41001271175) SUCCESS **609 passed, 97 skipped, one warning**. Source and test blobs fetched and read back at the exact branch head after CI. This is **STAGED SOURCE-ONLY ENGINEERING, NOT A PRODUCTION DEPLOYMENT**.

**Completed engineering slice:** `astra_ingestion/bulk_authenticated_provider_transport.py` implements a strict one-page P01/P02 Alpaca historical bars HTTPS adapter. It reconstructs the original manifest/contract/identity/calendar/entitlement-bound SIP 1Min/raw/USD request and a previously reserved immutable provider pre-call candidate, refuses stopped/expired/stale/fenced/mismatched claims, and binds continuation only to a separately consistent prior source-page receipt. The destination is fixed to the Alpaca historical bars endpoint; query shape and page-token URL have an independent request-URL digest. The transport uses a system-verifying TLS context with no ambient proxies, redirects or automatic retries, finite timeout and response size, credentials passed only in HTTPS headers, and sanitized transport errors. Response validation rejects URL/status/media/encoding mismatches, duplicated JSON keys, nonfinite numeric data, foreign symbols, invalid bars and budget overflows. Accepted source bytes remain immutable in a private, repr-excluded field; every requested JSON copy is freshly decoded to avoid post-validation mutation. Regresions cover these safety conditions and the inclusive-end source budget rule. No licensed records or credentials are written into repository artifacts.

**AUTHENTICATION LIMIT:** the transport's `verified_admission` injection is **not** a production security boundary and test authorizers and HTTP openers are synthetic. There is **NO independently authenticated SQL ticket readback, HTTPS provider session proven in hosted production, service principal/JWT acceptance, source entitlement proof, independent provenance attestation or worker integration** from these tests. `HTTPSPageObservation.provider_provenance_accepted` and `bulk_output_committed` remain explicitly false. Future production integration MUST install a separately authenticated restricted admission/attestor linked to original ticket, expense reservation, valid leased owner and original job deadline before exposing this transport as an executable worker step. No hosted request was issued. No provider call should occur solely on a fabricated true callback.

**Current live disposition (read-back):** Render web and worker both remain on clean `2c809b69e131f84e1778486e74c2f89a273f59f9` (latest LIVE deployment, auto-deploy OFF), and the bulk tables are not installed in `astra_ingestion_v1`. Existing 4,136 captured source documents are previously verified and preserved, not newly ingested. Original canary/crash jobs are untouched; additional provider qualification remains previously recorded one request/78 records with no increment in this run. No paid resource, new acquisition request, production write, source migration or legacy restart. All 24-family source/PIT/security expected denominators and historical REF01 identity remain unaccepted. **DATA_ACCEPTED=OPEN; EXECUTION_ACCEPTED=OPEN; INDEPENDENT_REVIEW_ACCEPTED=OPEN; DELIVERY_ACCEPTED=OPEN; full-market NOT_CERTIFIED.** Registered writer remains enabled without a programme cutoff; disabled verifier and closeout were not enabled or awoken.

**Next genuine engineering dependency:** authenticate the actual restricted worker admission role and real provider transport at a hosted endpoint, bind HTTPS observation/transport provenance to the original atomic quarantine/receipt ledger, and prove successor execution under real fences and recovery. In parallel, acquire/refine original-source historical REF01 episodes and contract-specific expected-unit keysets across the 24 families; do not substitute current ticker candidates. Hosted safety gaps may not block independent source/test engineering but prohibit production bulk admission until resolved. No programme end date; finite individual job/lease/budget/attempt safeguards remain intact.

---

## Provider response atomic output/receipt and observed-budget closure — 30 October 2026, scheduled 03:04 London run

**EXACT TESTED EXECUTABLE SOURCE:** [`39cf0fea98240d87d775445a2c78a933097eaac2`](https://github.com/robert8p/Alpaca-Supabase-Populator/commit/39cf0fea98240d87d775445a2c78a933097eaac2). [ASTRA ingestion qualification 40996227987](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40996227987) **SUCCESS, 312 tests**, including PostgreSQL disposable fixtures. [Release gate 40996228007](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40996228007) **SUCCESS, 598 passed / 97 skipped / one warning**. The staged source and test blobs were separately fetched and read back after CI. Intermediate candidate [`4c33609e`](https://github.com/robert8p/Alpaca-Supabase-Populator/commit/4c33609e8b9577c39f3f317530ab830d60f75b0c) independently passed **311** ingestion tests and release gate. No provider, production or costly retry attempts occurred.

**NEW QUALIFIED STAGED IMPLEMENTATION, NOT DEPLOYED:** `sql/astra_ingestion_bulk_provider_atomic_receipt_v1.sql` adds a separate immutable restricted provider-transport proof slot, private append-only output table and one-transaction, fenced quarantine-to-output/receipt/counter commit function. The worker supplies no market records or source hashes. All committed output is checked against the immutable P01/P02 quarantine, original pre-call ticket, exact reviewed unit/request, stop, lease, original deadline and cumulative budgets. A source-only post-crash readback compares the output digest and receipt without exposing licensed prices. The test suite covers missing/mismatched transport proof, exact atomic commit, duplicate replay rejection, stale claims, explicit stop, source/output immutability, empty eligible response (consumes one observed provider record and one request but cannot falsely verify data) and private privileges. These tests use *synthetic* attestor evidence, never authenticated remote transport.

**CLOSED SOURCE-LEVEL SAFETY DEFECTS:** The prior accounting considered only eligible committed bars, potentially ignoring an excluded, valid provider inclusive-end observation. Both the pre-call and response-stage gates now count all observed source records across committed pages against the original finite budget. The next-page pre-call requires a nonterminal predecessor backed by a separate transport pin, matching immutable output, and consistent atomic receipt; a forged generic ledger receipt does not authorize provider continuation. The quarantine readback now accurately indicates whether a matching output receipt exists, while the separate atomic reader recomputes source/output consistency. The old two immutable 156/78 jobs and all accounting remain untouched.

**IMPORTANT PRODUCTION HOLD:** A test fixture or a database proof row does **NOT** establish genuine Alpaca HTTPS response provenance, real authenticated-user JWT, separately qualified transport role, historical identity/calendar coverage, independent review or hosted eviction and old-instance cessation. No production SQL schema was installed; all new functions remain without PUBLIC grants. Render web/worker remain LIVE at prior clean `2c809b69e131f84e1778486e74c2f89a273f59f9`, auto-deploy OFF. No live provider calls, production ingress, legacy activity, new resources, charges or bulk automatic-successor proof. Existing retained capture 4,136, 24-family unknown applicable denominators, D06 catalogue and qualification cumulative one request/78 records are preserved as **previously verified evidence**, not falsely refreshed. All four joint acceptance gates remain OPEN; broader full-market coverage NOT_CERTIFIED.

**NEXT ADMISSIBLE ENGINEERING:** implement and qualify a genuinely separate HTTPS provider transport/authentication attestor and role-restricted worker service integration; prove source truth and independent 24-family effective-dated expected-unit/calendar reviews (including REF01), then only after hosted identity/fencing/eviction authorization install exact SQL candidate, deploy and observe an actual useful commit followed by an automatic successor. Reconcile actual provider entailments and finite reservations; do not substitute synthetic provenance. The registered hourly writer remains enabled, reviewer and closeout disabled with unresolved user-action flags. No programme cutoff, but all new job deadlines/budgets/stops remain finite.

---

## Provider-response quarantine bridge — qualified staged candidate, 30 October 2026, 02:12 UTC

**Exact executable/test candidate:** [`d1baf0d3fc04cd66145b21d81a31569887fc365f`](https://github.com/robert8p/Alpaca-Supabase-Populator/commit/d1baf0d3fc04cd66145b21d81a31569887fc365f). [Dedicated ingestion qualification 40990249207](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40990249207) **SUCCESS — 304 tests**, including disposable PostgreSQL provider pre-call/quarantine cases. [General release gate 40990249288](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40990249288) **SUCCESS — 598 passed, 89 skipped, one warning**. Direct readback: `astra_ingestion/bulk_provider_quarantine_bridge.py`, `sql/astra_ingestion_bulk_provider_response_quarantine_v1.sql`, `tests/ingestion/test_bulk_provider_quarantine_bridge.py`, `tests/ingestion/test_bulk_provider_precall_postgres.py`. Intermediate test correction at the exact candidate adjusted a synthetic stale-fence fixture to supply the already reserved ticket; no production state or historical test evidence was rewritten.

**Implemented but NOT deployed:** A bounded P01/P02 request/response bridge revalidates the original immutable request, pre-call ticket, fenced work claim, finite budget, parsed September SIP/raw 1Min price response, original inclusive end rule, continuation predecessor and source-page witness before constructing a private JSON quarantine candidate (prices never logged). A staged PostgreSQL response quarantine provides atomic, immutable page storage and source-array digest, strict shape/type/sequence checks, original ticket binding, independent review-pin predicates, stop/job-deadline/fencing checks, read-only uncertain-stage reconciliation, RLS and no PUBLIC grants. It expressly returns `QUARANTINED_UNAUTHENTICATED_NOT_BULK_COMMITTED`: it does **not** certify true provider transport, source provenance, independent reviewer identity, actual bulk output/receipt, calendar completeness or coverage.

**Current readback:** Render web and worker latest LIVE deployments remain clean revision `2c809b69e131f84e1778486e74c2f89a273f59f9`, auto-deploy OFF. This SQL migration is uninstalled, no provider request was issued for this candidate, no protected legacy state changed, and neither original completed 156/78 job was reopened. Qualification usage remains prior **one request/78 records**, zero incremental. All four joint acceptance gates remain OPEN; historical/full-market coverage NOT_CERTIFIED. Distinct authenticated HTTPS user JWT, genuine 24-family source-backed expected populations (especially REF01 dated listings), entitlement, authenticated provider-response provenance, production principal/hosted loss-recovery, automatic useful-output successor, independent review and consumer delivery remain gating.

**Executable successor:** create and qualify the *distinct authenticated source-transport and immutable provider-provenance gate*, then an **atomic quarantined-provider to receipt/output commit** bound to original ticket and cumulative accounting. Do not grant the staged quarantine actor a generic existing receipt writer or promote synthetic source hashes as truth. Separately continue REF01 historical security-episode source reconciliation and all-family expected-unit construction. No programme cutoff; individual new jobs, budgets, stop/fence/attempt restrictions remain finite. Reviewer and closeout tasks remain disabled and must not be reenabled without resolving their explicit task states.

---

## Inclusive Alpaca end-boundary correction — 29 October 2026, 23:06 London

**Exact qualified source/test revision:** [`aec91d24b00030a54ef3cb0334ec4dbadcd7e653`](https://github.com/robert8p/Alpaca-Supabase-Populator/commit/aec91d24b00030a54ef3cb0334ec4dbadcd7e653). [Ingestion PostgreSQL qualification 40970638582](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40970638582) **SUCCESS, 263 tests**; [release-gate 40970638544](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40970638544) **SUCCESS**. Source/test readback blobs: `23ab11a0ee2fcf21090afd84b0b7fa0e98ef799d` / `bcf26d76020f02a6d6c3990f320f7e5072712a30`. An intermediate unpaired source-only change failed release-gate run `40970594944` because its existing regression still expected the provider inclusive end to be rejected; it was not hidden, retried blindly, or released. The final paired source/test revision passed.

**Corrected defect:** [Alpaca's own 2026 Historical Bars reference](https://docs.alpaca.markets/us/reference/stockbars) explicitly defines the provider `end` timestamp as **inclusive**, while the source-eligible original security-session minute window is **[start,end)**. The previous parser would abort a valid response containing the boundary minute. The corrected adapter now validates the inclusive-boundary bar's native price and monotonically increasing timestamp, counts it against the original finite provider response reservation, captures its exact content hash in an immutable page witness, and **excludes it from eligible output**. It rejects truly out-of-window timestamps, repeats and forged values. It never counts a boundary-only/empty response as no-trade evidence, a complete expected calendar or data acceptance. One new synthetic regression proves the excluded boundary changes the source-page hash without producing an eligible bar.

**Scope and disposition:** source/test code only; no provider request, new ingestion rows, source admission, production migration, deployment, cost, legacy restart, changed original jobs or main merge. Cumulative additional qualification remains 1 request/78 records and zero increment in this operation. The full 24-family expected populations and REF01 historical security mapping, independent reviewer/JWT, immutable staging/ledger, hosted eviction/automatic successor and delivery still require separate evidence. No programme expiry; all original per-job deadlines, finite budgets, stops and claims remain binding.

---

## P01/P02 September SIP response integrity — 29 October 2026, 23:00 London

**Verified executable/test source** [`5f040043c47508d989b2fd971ed1748400a16d19`](https://github.com/robert8p/Alpaca-Supabase-Populator/commit/5f040043c47508d989b2fd971ed1748400a16d19), [ingestion qualification 40969956678](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40969956678) SUCCESS (**262 tests, including 10 new synthetic SIP parser tests**) and [release gate 40969956694](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40969956694) SUCCESS. Corresponding push workflow runs 40969951994 and 40969952053 SUCCESS. Both new source and test files were fetched and read back after CI. This is **source-only qualification, NOT production deploy, source provenance or data acceptance**.

**New substantive implementation:** `astra_ingestion/bulk_p01_p02_alpaca_response.py` and `tests/ingestion/test_bulk_p01_p02_alpaca_response.py`. The response inspector reconstructs and revalidates the original, immutable September P01/P02 1Min/SIP/raw/USD request candidate, requires the exact one-symbol price-bar response shape, bounds every page by the finite 1,000-record request limit, excludes foreign symbols/currencies, validates aligned UTC half-open time bounds (Alpaca provider end may be inclusive), strictly increasing minute keys, OHLC/VWAP relationships and numeric volume/trade counts, and generates immutable per-record/source-page SHA256 witnesses. It tracks continuation tokens and predecessor page hashes; empty pages and terminal pages never assert source-eligible calendar closure, PIT, independently verified identity or contract-defined N/A. The inspector cannot acquire/submit data or reserve resources; token continuation is NOT itself an admitted new request. A transport-authenticated provider receipt, separately verified exact calendar, atomic cumulative budget/staging ledger, actual restricted worker, and independent evidence remain missing.

**Independent current production readback (read-only):** source capture 4,136 rows, comprising 3,000 practical companies, 24 contracts, 42 calendar records, 1,065 D06 preservation-only entries and 5 other documents. `astra_ingestion_v1.bulk_manifest_v1` is NOT installed. Both Render web and worker latest LIVE deployed revision remains `2c809b69e131f84e1778486e74c2f89a273f59f9`; auto-deploy stays OFF. No provider request, production SQL DDL/DML, deployment, charge, original job amendment, legacy restart or main merge was made. Additional provider qualification usage remains 1 previously recorded request / 78 records, increment zero this slice. All four joint acceptance gates remain OPEN. Original September P01/P02 source gap and REF01 historical mapping still unresolved.

**Safe executable successor:** independently authenticated, immutable response-page source staging tied to original identity/session/minute witnesses and the per-manifest SQL ledger; enforce cumulative per-page request+record budgets, continuation identity, original deadline, stop and fence in one transaction. Then integrate restricted provider worker and independent review and verify hosted automatic successors without changing protections. Complete the other family source populations separately. Verifier and closeout automations remain DISABLED with unexplained `requires_user_action=true`; do not silently enable or call them. There is NO programme expiry, but every new job/lease/request remains finite.

---

## P01/P02 September acquisition guard and read-only source adapter — 29 October 2026, 22:04 London

**Verified executable/test revision** [`086f3b635059718b10847f92288067fa390898a9`](https://github.com/robert8p/Alpaca-Supabase-Populator/commit/086f3b635059718b10847f92288067fa390898a9): [ingestion qualification run 40963193143](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40963193143) SUCCESS, **252 tests**, including 11 bounded P01/P02 retained-source tests and 8 finite September Alpaca request-candidate tests, and [release gate 40963193144](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40963193144) SUCCESS. Both are *source/test* acceptance, NOT installed production or 24-family population acceptance. A prior pre-immutability candidate `6fd8399d` also passed 252 tests; exact later candidate adds regressions against mutable provider request and source array parameters.

**New STAGED source-only implementations:** `astra_ingestion/bulk_p01_p02_source_probe.py` and `astra_ingestion/bulk_p01_p02_alpaca_request.py` with matching test modules. Original P01/P02 contracts pinned to SHA256 `9eda239c37522ec884e090279220fd701b41f6140bf0a66674b2a3a4798fe387` and `ba96c9a04d15e88f0674278dd9ea789d61a7e62cd2e10da754d2c3426655c8bb`. The retained-source probe creates finite, fixed-schema, read-only instrument/timestamp keyset SQL with 128-unit key/page caps, 24-hour maximum interval, original family session labels and OHLCV/trade-count validation. Source array parameters are copied fresh to prevent a caller widening a sealed read. The original P01 enriched view derives from the same SIP parent and is NOT an independent September source.

The new September *provider request candidate*, never a submitted provider call, validates original family SHA, one symbol/dated identity, separately evidenced calendar/entitlement/manifest hashes, one finite reserved request, at most 1,000 reserved one-minute records, 1Min/SIP/raw/USD/asof, finite original job deadline and safe UTC boundaries; request parameters are frozen after validation. The result is explicitly **`REQUEST_CANDIDATE_NOT_RESERVED_NOT_AUTHORIZED`**: it does NOT commit ledger reservations, prove hashes came from genuine evidence, confer hosted JWT/reviewer rights, debit any provider budget or authorize a request. Alpaca connector parameter shapes were inspected, but the connector was NOT called. A response parser, full source staging/receipt linkage, bounded paging and actual ledger/worker integration are still outstanding.

**New live read-only source findings:** The original `market_fixed_20250901_20260831.us_equities_bars_1m` view is derived from `alpaca_sip_bars_1m_enriched` which joins the SAME original `alpaca_sip_bars_1m` parent; it does not replace missing September. Protected legacy `population_top3000_202608_202609_v1.retained_price_observation_v2` and `working_retained_price_observations_v2` each have 13,406 August rows for 4 companies, zero September rows. The working rows all have `family_accepted=false` and null `expected_minute_bars`; overlap/deduplication and actual source semantics remain unverified. Separate `market_governance.remediation_listed_price_release_v2` (120,186 rows) and `research_eq5_20261014_1319.supplemental_bars` (118,862 rows) both end 31 July 2026, with no September observations. No alternate full September SIP source is established by these examined routes. See `docs/INGESTION_SOURCE_GAP_EVIDENCE_20261029.md` for contract and SQL evidence. These narrow source findings do NOT assert broader provider unavailability, contract N/A, complete missing calendar, or any full-cohort gap denominator.

**Live production reconciliation:** fresh read-only scope inventory verified exactly **4,136** original documents: 3,000 companies, 24 contracts, 42 calendar documents, 1,065 D06 preservation entries, and 5 other immutable scope/membership/acceptance documents. Render web and worker remain LIVE at `2c809b69e131f84e1778486e74c2f89a273f59f9`; auto-deploy OFF. Original two jobs and cumulative qualification usage remain frozen. No new production SQL, hosted code deployment, provider request, acquired record, approval bypass, paid resource, legacy restart or main merge occurred. All four joint acceptance gates remain OPEN. Physical eviction, distinct cross-instance cessation and authenticated user JWT over HTTPS are still not proven for this new release; neither is admitted automatic successor execution.

**NEXT EXECUTABLE ENGINEERING HANDOFF:** complete response staging/validation with independently evidenced source identity and minute calendar, per-partition cumulative budget reservation, restricted worker integration and durable auto-successor; separately recover REF01 historical security episodes and contract-eligible source population for all 24 families. Do not submit bulk provider jobs until full exact-unit manifest, reviewer/JWT/host gates and finite accounting are qualified. Continue safe source/reliability engineering under the existing enabled writer schedule. The verifier and closeout automations remain disabled with `requires_user_action=true` and no explanatory result, so do not silently reactivate. No programme campaign expiry; every new job still finite.

---

# ASTRA: complete dataset and reliable unattended ingestion

## Verified REF01 source-schema adapter and actual missing-window evidence — 29 October 2026, 21:16–21:20 London

**Exact executable/test candidate:** `0210822ec93d314fb57575839212f97a67a63f85`, [ingestion qualification 40956071443](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40956071443) and [40956081502](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40956081502) SUCCESS with **233 tests**, including the new 11 `test_bulk_ref01_route_probe` tests; [release gates 40956071242](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40956071242) and [40956081459](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40956081459) SUCCESS. Exact source/test GitHub blob readback verified (`d6511b61faf4ec7193b7028d0134e9652e4b9f4c` and `90f2d667181e50bf1cefdc87fc7973bdd43ce082`). No deployment, migration or granted runtime principal.

**NEW TESTED SOURCE/TEST SLICE:** `astra_ingestion/bulk_ref01_route_probe.py` and `tests/ingestion/test_bulk_ref01_route_probe.py`. Fixed, allowlisted source routes identical to the original five REF01 declarations, exact native columns/unique cursor keys, bounded 1–128-row parameterised read-only keysets, Massive 2026 Aug–Sep FIGI-scoped date filter, no raw licensed provider payloads/prices. Refuses out-of-window, unselected FIGI, duplicate/non-advancing, malformed keys/hash, unknown/late PIT dates. Returns only `OBSERVED_SOURCE_PAGE_NOT_POPULATION_CLOSURE`, never a verified historical listing denominator, independent reviewer decision, user JWT, database grant or admission. Native route metadata is project-inspected; the tests are synthetic and do not certify hosted source access.

**FRESH SOURCE READ-ONLY RESULTS:** original 3,000 accepted company rows all carry anchor composite/share-class FIGI; original `reference.equity_resolved_security_v5` links only **9 distinct accepted company identifiers** across either exact FIGI, leaving **2,991 unmatched in that particular route**. Original `reference.massive_security_master_observation_v1` has 2,844,997 rows whose `requested_as_of` ranges 2025-09-02–2026-07-31, and **0 Aug–Sep 2026 target-window observations**. Original P01/P02 Alpaca SIP 1-minute source is partitioned through August only; direct September 2026 `count(*)` is **0**, even though August's partition exists. Do **NOT** infer absent global source coverage, eligible N/A, rank-cap validity, session calendars or securities from these narrow route results. The full read-only evidence, exact queries, 24-family UNKNOWN denominators and D06 preservation are saved at `docs/INGESTION_SOURCE_GAP_EVIDENCE_20261029.md`, whose GitHub blob was read back as `415c0fc4888c840ec455c901070e60139460cc08`. No credentials or licensed records in report.

**NEXT EXECUTABLE HANDOFF:** build contract-equivalent, lawful/source-entitled historical REF01 episode and P01/P02 September read/acquisition adapters against the actual existing provider rights, with independent expected calendar and identity/availability evidence. Never turn missing source into completeness. Before any provider request, prepare and qualify the finite manifest, budget reservation and durable restricted worker; install nothing until independent authenticated role/JWT-over-HTTPS, physical host eviction/cross-instance cessation and full source-unit seals pass. 24-family bulk ingestion remains NOT RUNNING, no programme cutoff, original jobs closed, all joint gates OPEN. Sole writer remains the existing enabled implementation task; verifier/closeout remain disabled with unexplained user-action flags.

---


## Exact-source atomic retained materializer and restricted HTTPS integration — 29 October 2026, 20:19 London

**Qualified executable/test revision:** `1d0841cc0903d6b37daeea296af306f8a2c1ee7a`. [Ingestion PostgreSQL qualification 40947813464](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40947813464) completed SUCCESS with **222 tests**, including the actual disposable-PostgreSQL-to-Python-dispatcher bridge and a synthetic independently released successor. [Release gate 40947813470](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40947813470) completed SUCCESS. Executable/test file contents and blob hashes were fetched back.

**STAGED, NOT DEPLOYED OR GRANTED:** `sql/astra_ingestion_bulk_atomic_materializer_v1.sql` atomically inserts immutable output rows and their durable receipt/accounting under an exact owner/fence, original job deadline, manifest stop, independent 24-family seal and finite record/request budget. A stored, immutable retained source page is separately required. The restricted worker supplies only work/fence/page, never licensed content, an output digest, source proof, reviewer decision or provider request. Transaction errors roll back output and accounting together; existing receipts are read back without replay. Source provenance still depends on separately qualified immutable staging and actual original external source evidence.

**SQL tests:** zero extra provider requests; first committed source page followed by claimable dependent successor **only after a separate synthetic reviewer verification**; atomic budget rollback, immutable source and target rows, wrong-instance and wrong-fence refusal, manifest stop, no PUBLIC function grant and read-only postcommit receipt comparison. Newly added `test_python_dispatcher_to_real_disposable_postgres_automatic_successor` uses the existing `RetainedOnlyDispatcher` against actual disposable ledger/port/materializer functions, not just an in-memory mocked queue. It demonstrates code integration, **not hosted unattended operation or genuine independent reviewer authorization**.

**Staged HTTPS adapter:** `astra_ingestion/bulk_http_store.py` with `tests/ingestion/test_bulk_http_store.py` supports exactly the four fixed restricted PostgREST functions (admission, claim, atomic materialize and readback) at the pinned Supabase HTTPS origin/schema; has explicit bounded request/response/time, no redirects, no service-role credentials, no generic SQL, provider, review, recovery, budget changes or administrative rights. It demands an authenticated-user JWT shape and rejects expired/anonymous tokens before each call. JWT parsing is NOT signature proof, tests use deliberately fake tokens and no live request; real gateway-verified HTTPS user identity, database rights, PostgREST schema exposure and separate reviewer still need independently demonstrated acceptance. Do not put a JWT into repository documentation, and do not enable this adapter in the deployed old worker before gates pass.

**Test chronology retained:** first materializer candidate at `6b6103e6` failed only because a test queried `information_schema.routine_privileges.grantee` as integer. The exact non-PUBLIC ACL regression was corrected at `0194381f` to use `pg_catalog.aclexplode`, then CI succeeded. Restricted port source/test revisions were qualified through `1d0841cc`. No failed test was silently discarded or retry counter reset.

**Fresh production readback, 20:10–20:19 London:** retained scope remains 4,136 documents with `CAPTURED_NOT_ADMITTED`; bulk manifest/ledger absent. Render web and worker still live on `2c809b69e131f84e1778486e74c2f89a273f59f9`, auto-deploy off. Zero production ingestion, migrations, deployment, provider requests, new chargeable resources or protected legacy changes. All four joint acceptance gates remain OPEN, historical/full-market NOT_CERTIFIED. Two immutable original jobs and cumulative qualification counters remain unchanged. Reviewer and closeout tasks remain disabled with blank user-action reasons. No programme cutoff; individual job deadlines, stop/budget/lease/attempt rules still enforce.

**Executable successor:** obtain genuine source-backed REF01 historical security/listing evidence for its five original declared routes and all remaining family populations, then separately authenticate production reviewer and worker roles; establish restricted immutable source staging, full 24-family independent seals, physical host eviction and old-instance cessation/HTTPS JWT gates before installing/admitting any new production bulk job. Continue independent adapter/source/verification engineering without a global pause. This is an INCOMPLETE source/test delivery and is not a claim of autonomous bulk execution.



## Exact independently reviewed unit binding — source/test slice, 29 October 2026

**Exact candidate verified in CI:** [ASTRA ingestion qualification run 40937362007](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40937362007) completed SUCCESS with **210 ingestion/disposable PostgreSQL tests**, including independent Python-versus-PostgreSQL JSONB unit-set digest equality. [Release gate 40937361985](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40937361985) completed SUCCESS. The first review candidate failed solely because one negative test expected the word 'page' rather than the actual fail-closed 'bounded family/source plan' diagnostic; corrected without weakening validation. Exact executable source/test files were fetched back. These checks are not hosted role/source/completeness proof.

**New STAGED components, not installed:** `sql/astra_ingestion_bulk_unit_binding_v1.sql`, `tests/ingestion/test_bulk_unit_binding_postgres.py`, `astra_ingestion/bulk_unit_binding.py` and `tests/ingestion/test_bulk_unit_binding.py`. Exact executable/test candidate initially `610fc4a240c0cbd14bc41ed58d291ce56b2e24be`. The SQL amendment installs an append-only per-family exact-unit witness and a full unit-set seal. The distinct external reviewer must provide the independently observed ordered unit-set digest, matching **every** unit's source/provenance/identity/PIT hash; all 24 family seals must agree with the pinned original family review. A rewritten restricted claim port rejects the **entire** manifest if any queued partition/unit/source receipt is absent, mismatched, provider-mode or outside the sealed expected set. Manifest SHARE lock serialises the admission decision with the existing finite reservation UPDATE lock, preventing late unbound insertion before claim. User stops, original job deadlines, count/source holds, retry/record/request fences and lease expiry remain enforced by the underlying durable ledger.

**Python bridge:** bounded keyset enumeration produces reviewer-only candidate rows and the exact PostgreSQL JSONB unit-set digest, cross-checked in disposable PostgreSQL tests. It refuses unpinned PIT/identity/provenance/source hashes, missing/extra/duplicate keys, snapshot receipt drift and non-ASCII unit keys without separately qualified canonicalisation. It does **not** authenticate itself as the reviewer, acquire source data, mutate SQL or admit worker jobs. Its result always says `worker_admission_authorized=False`. A synthetic SQL-computed fixture hash is explicitly not independent external source evidence.

**Security:** no staged SQL installed and NO PUBLIC/application grants added. Prior generic claim and original count-only claim functions must remain ungranted to the production runtime, and no reviewer role may be impersonated by the worker. The original 24-family source review/denominator remains unresolved for real data (especially REF01); synthetic hashes, counts or the existing 4,136 retained scope documents cannot certify actual coverage. A distinct authenticated reviewer, real source-backed exact-unit hashes, actual atomic output materialiser and hosted automatic successor/old-instance cessation, JWT-over-HTTPS and physical host eviction proofs remain production hard gates.

**Scope and cost:** no production DDL/DML, provider requests, new services, paid changes, main merge, legacy controller restart, altered canary/crash job or rewritten original deadlines. The programme has no expiry; individual jobs and resources remain finite. All four joint acceptance gates remain OPEN. Deploy only after exact-candidate CI, source-backed review, transport/role rights, fencing and rollback gates.



## Restricted runtime admission/claim port — exact-source qualification (18:10 UTC, 29 October)

**Qualified executable/test revision:** `5e09e38330ccf6146828c7e6f0a16d7a71f8bcb7`. New STAGED `sql/astra_ingestion_bulk_runtime_port_v1.sql` exposes a read-only, exact-shape manifest admission snapshot for the already staged Python retained dispatcher and a pending RETAINED-ONLY claim wrapper. It is **not installed**, has **no PUBLIC grants** and gives no production principal any new rights. Every admission readback rejects an absent/stopped manifest, incomplete 24-family review, changed original contract receipt, wrong source capture or unpinned report SHA. The only claim operation delegates to `bulk_claim_retained_v1` under finite lease/original deadline/attempt/dependency constraints; it does not access provider APIs.

**Tests:** [ASTRA ingestion qualification PR run 40928124146](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40928124146) SUCCESS — **199 unit/disposable PostgreSQL tests**, including five new tests for source drift, exact dispatcher readback, synthetic successor after external simulated verification, user stop/provider exclusion and no PUBLIC EXECUTE. [Release gate 40928123963](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40928123963) SUCCESS. The first candidate's ACL test falsely matched the function owner's own `=X/` privilege; corrected at `5e09e383` to inspect ACL grantee OID 0. This was a test defect, not an ignored permission failure.

**Important newly isolated admission gap:** a valid 24-family **count-based** review does NOT yet prove that *each queued work unit* belongs to the exact independently verified expected-unit set. The present claim gate must NOT receive an application grant until immutable per-unit manifest evidence is bound to every reserved partition and independently checked. A claim plus a receipt hash also does NOT prove atomic source-to-output materialisation. A separate fully restricted materializer and independent post-commit verification are still required. CI's synthetic reviewer and successor are NOT evidence of production auto-dispatch, data completeness, actual separate authenticated reviewer, external JWT HTTPS transport, physical eviction or cross-instance cessation.

**Current live readback:** the original capture remains 4,136 retained documents (3,000 company rows, 24 original contracts, 42 calendars, 1,065 preserved D06 catalogue items, plus scope/acceptance/membership); live Render web/worker deployments are still `2c809b69e131f84e1778486e74c2f89a273f59f9`. No bulk manifest, SQL migration, hosted automatic successor, acquisition, new provider requests, production DB writes, additional costs, or changed legacy systems in this slice. Joint acceptance remains OPEN in all four parts and full-market coverage NOT_CERTIFIED. The reviewer and closeout automations remain disabled with unexplained user-action flags; do not re-enable silently. The programme has **no expiry**, but all new work must have finite immutable job deadlines, budgets, fencing and stop controls.

## Authority and target

Unattended operation and the previously paused Top-3,000 target are approved.
Deliver 1 August–30 September 2026 through this isolated application, all 24
original families. Preserve D06 only. Never restart the legacy controllers or
release financial/identity/data-quality/scientific holds. No research/trading.
No new services, new costs or main merge are admitted. The programme has NO expiry under the direct 29 October 2026 user amendment; the former 2026-11-05T02:00:00Z cutoff is historical, not an operating stop. Every new job still has an immutable finite original deadline and explicit budgets, cancellation and retry limits. Main stays unmerged.

The prior practical membership is accepted for reuse, not invented anew. Its
snapshot is `2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec`;
acceptance `20b9dac759857e9b510ccaeca33e4a94d8c748d588fb0cc27740cc66c389b5f9`.
The original source acceptance event24407 references user amendment23086 and
explicitly does not certify exact global ranking, financial facts or full-period
security mapping. Preserve those distinctions; do not spend the campaign trying
to re-create an already accepted membership or quietly certify its other fields.

Joint completion requires DATA_ACCEPTED AND EXECUTION_ACCEPTED AND
INDEPENDENT_REVIEW_ACCEPTED AND DELIVERY_ACCEPTED for compatible exact revisions,
manifests and complete applicable populations. None is implied by this capture.
The three existing tasks are governed by SHARED EXECUTION AND ACCEPTANCE CONTRACT v2; disabled task states are not proof of acceptance or permission to restart.


## Bounded retained-only executor and REF01 episode normalizer (17:15 UTC, 29 October)

**Exact qualified executable source:** `ea996c1ae0145da87af4e33141f27ce1fb86da44`. Both ASTRA ingestion and general release-gate workflows, push and PR, completed SUCCESS ([ingestion PR](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40919334276), [ingestion push](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40919320580), [release PR](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40919334175), [release push](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40919320643)); **189 ingestion unit/PostgreSQL tests passed**. Source and tests were read back after qualification.

`astra_ingestion/bulk_reuse_dispatch.py` is a bounded **source-only restricted-runtime component** for an eventual admitted, server-fenced retained-source store. It refuses absent independent full-24-family admission, stopped/mismatched manifest, provider-mode work, invalid owner/fence, request budget above zero, expired original job/lease and uncertain receipt; it never attests its own work or requests provider data. Synthetic tests demonstrate a committed retained page followed by a dependent successor **only once a separate simulated reviewer releases the predecessor**, plus a post-2026-11-05 job with a *fresh finite* deadline, while an expired job stays refused. This is NOT actual hosted unattended dispatch: the restricted store method, SQL review admission and real separate verifier have not been installed or qualified.

`astra_ingestion/bulk_ref01.py` is the first domain-specific REF01 **normalised-source episode compiler**, constrained to its five exact original declared routes. It handles all 3,000 accepted company identifiers as **candidates only**, effective-dated listed security episodes, explicit held/missing required fields, evidenced exclusions, overlapping security identity conflicts and records published after the specified as-of instant. It fingerprints ranked membership and pinned scope receipt. Ten source tests passed as part of the 189-suite. It does NOT read the five live tables, prove the REF01 complete historical-security denominator, prove licence/source coverage or issue a `DenominatorEvidence` or admission credential. Actual source-backed projection and independent historical closure remain BLOCKED and must be built, not assumed from accepted company membership.

**Current reality:** production SQL ledger/reader/admission not installed; both named Render services still LIVE on clean `2c809b69e131f84e1778486e74c2f89a273f59f9`; 4,136 retained scope documents remained present on a fresh READ ONLY count; zero bulk acquisitions/deployments/provider requests/additional costs. The separate read-only review and closeout tasks remain disabled with unexplained user-action flags; no silent reactivation. All four acceptance gates OPEN and historical/full-market NOT_CERTIFIED. Next: source-backed REF01 projector and approved independent review, restricted SQL store plus complete 24-family admission, then actual automatic successor/fault/security/hosted evidence before protected ingestion.

## Independently reviewed retained-only SQL claim gate (17:21 UTC, 29 October)

**Executable source candidate:** `4e2cffd2146161a9a027704a43e0a73ae409b671`. New **STAGED, NOT INSTALLED** `sql/astra_ingestion_bulk_retained_gate_v1.sql` adds immutable per-family review evidence for the exact 24 families (not D06); explicit expected/observed equality; pinned source contract, source receipt, provenance, identity and PIT digest fields; a distinct manifest review record; source-contract matching against the immutable retained capture; and `bulk_claim_retained_v1` which will not claim until all 24 family reviews are recorded, manifest un-stopped, predecessors verified, original job deadline valid, and work mode strictly provider-free. No default PUBLIC function/table grants and RLS enabled on review tables. Legacy generic ledger functions MUST NOT be granted to an eventual retained worker; actual separate reviewer role and actor/transport need qualification before any production grant or record. The gate deliberately cannot certify provenance merely from metadata hashes or untrusted operator assertions.

**Disposable Postgres evidence:** [ingestion push run 40920326277](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40920326277) completed SUCCESS with **194 tests**, including five new tests covering absent review, 23/24 review rejection, original retained-contract hash binding, immutable review rows, dependent retained-only successor, provider exclusion and stop preservation. [release push 40920326250](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40920326250) and [release PR 40920333272](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40920333272) also SUCCESS. The synthetic administrative fixture is not a genuinely independent production review or credential/HTTPS/RLS qualification. All real 24 denominators remain unverified; the reviewer and closeout automations are disabled; no full-data admission or actual hosted successor evidence exists.

**Required next engineering:** integrate the independently qualified SQL store with the staged Python retained dispatcher under a restricted database principal (without provider rights); produce actual REF01 normalized projections from lawful, date-valid source routes and evidence-backed complete security episodes; establish a separate independent review principal/transport, read back its full 24-family source evidence, and qualify hosted restart/old-instance/non-overlap before admitting any production job. Do not weaken safety gates, recreate old jobs, reset budgets or treat CI as deployed ingestion.

## Forward-only pending migrations (source tested separately; not installed by documentation)

The historical one-time capture and catalogue-repair SQL remain unchanged and MUST NOT
be replayed. The prepared new `sql/astra_ingestion_bulk_scope_no_campaign_cutoff_v2.sql`
performs a single exact-source preimage check against the installed capture
function, requires the immutable 4,136-document receipt and RLS/ACL invariants,
then replaces only the withdrawn programme-cutoff conditional. Repeating the
migration or observing drift fails closed. A passing synthetic/CI test DOES NOT
prove that this new SQL is installed in production. Database application requires
the normal admitted connector operation and exact production preflight.

The prepared `sql/astra_ingestion_bulk_restricted_reader_v1.sql` defines a
NOLOGIN, NOBYPASSRLS reader principal with EXECUTE on a single bounded keyset
SECURITY DEFINER function, no direct table grants, no provider rights and no
credential provisioning. It remains a staged component: the actual external
read-only actor/transport and deployed runtime integration are NOT qualified.
Tests on disposable Postgres do not establish production actor enforcement.

These independent infrastructure slices do not constitute a complete 24-family
manifest, durable bulk queue, source acquisition, data acceptance or automatic
successor execution. Installation, transport, adapter, worker and hosted
recovery gates remain separately OPEN.

## Implemented slice: retained evidence, not a bulk executor

`sql/astra_ingestion_bulk_scope_v1.sql` creates two isolated immutable evidence
tables and a privileged-caller-only SECURITY INVOKER capture function. No provider
call, source update, loader restart, existing-job mutation, credential access or
new runtime grant is present. This is a one-time migration, not startup DDL.

The function requires a repeatable-read transaction, takes a nonblocking atomic
transactional lock, validates pinned original scope/cohort/acceptance/contract
hashes, root acceptance, 3,000 distinct companies/ranks and held qualifications,
42 sessions/16,380 scheduled minutes, and the retained D06 catalogue inventory.
The corrected source candidate `13cc5b0d6294c052333178031816a5ab764bd280`
retains 1,065 D06 preservation entries, not the previously assumed three.
It atomically retained 4,136 evidence documents and one receipt. Hashes use exact
original UTF-8 text; aggregate receipts use ordered PostgreSQL JSONB arrays of
(kind,key,source-hash). Do not compare those hashes to Python reserializations.
Reconciliation with the same capture key validates the entire existing result
and returns the original receipt without resetting its timestamp or first run.
Conflicting retained evidence fails closed; updates/deletes/truncates are blocked.

RLS defaults deny; PUBLIC and application roles cannot invoke capture or access
its evidence. It deliberately does not reuse the worker's provider identity.
An administrator performing this capture is NOT restricted runtime-verifier proof.

`astra_ingestion/bulk_scope.py` validates the exact original contract set, computes
deterministic dependency waves, represents immutable bounded partition proposals,
and keeps unknown/incomplete/unavailable counts distinct from certified coverage.
A proposal is NOT a durable reservation or permission to run acquisition.

## Installed capture and fresh readback

The one-time migration and capture already exist. Do not reinstall or recapture.
Capture key: `top3000-augsep2026-retained-scope-v1`; captured at
`2026-10-29T09:22:03.127374Z`, first run `origin-steps12-20261029-0853`.
State remains `CAPTURED_NOT_ADMITTED`, with zero provider requests/cost.

At `2026-10-29T10:07:30.325148Z`, an explicit READ ONLY transaction through
`Supabase_Market_Data_Cloud.execute_sql` recomputed every retained content hash
and the ordered aggregate hash: 4,136 rows, zero content-hash failures,
receipt count and hash both matched. Aggregate SHA256:
`ba13899b530288b6aae8d4af3a429efa3f4bd5ec305a7dc698f98c9d552f4496`.
Composition:3,000 company,24 contract,42 calendar,1,065 preservation,
2 acceptance-event,1 cohort,1 membership and1 scope documents.
Original two jobs remain completed,234 records/3 requests,zero active claims.

This validates retained scope evidence, NOT source-to-target completeness of
all 24 research datasets, restricted-runtime verification or bulk admission.
Review the exact published candidate and its regression results before new
executable deployment. Do not carry source qualification to changed code.

## Connector refusals: bounded diagnosis, not a permission bypass

The scheduled writer reported blocked GitHub writes and read-only SQL in run
`f4d582dd-258c-8328-ab9c-b4b43b7c015a`, completed10:04:12.155847Z.
The subsequent user-requested diagnosis found both connectors already set to
app-specific Allow all actions. No permission, OAuth, RLS or credential change
was made. The ordinary SQL route passed two finite READ ONLY calls; GitHub
`update_file` acquired checkpoint v20 using its current blob SHA, commit
`575131f11c3492d3e0cf4d04884b19749fbfe5ee`, and the new blob was read back.

These results prove current interactive access, not permanent scheduled-context
recovery. Read the current checkpoint and actual task status before proceeding.
If a new task-context operation is denied, preserve the exact error, task/run,
operation, target and time; reconcile any uncertain destination effects. Do not
cycle connectors, change identities, loosen policies or encode a request to
circumvent an explicit safety block. Preserve prior failures and the maximum
two materially identical failed attempts. A confirmed auth/approval requirement
needs its supported flow; a safety refusal needs precise evidence/escalation,
not another general request for authority already granted.

## Executable successors, not reminder-only handoffs

Keep ONE code/runtime mutator (task6ae2a4c96bbc819182133e17e9b7f779), plus the
existing independent read-only verifier and closeout. No extra mutator chats.
Each run takes the highest-value admissible unfinished slice, implements and tests
it, records real outputs and dispatches its next admissible bounded operation.

A. Recover retained source manifests, source pages, dated instrument mappings and
per-family authoritative expected units. Build bounded keyset reuse readers and
per-family adapters inside ASTRA; do not copy whole legacy schemas or trust queue
completion counts. Reuse source data before buying or re-fetching anything.

B. Implement a durable per-family/per-partition ledger: original manifest and
deadline, finite cumulative provider/request/record/cost reservations, lease fence,
cancellation, attempts (maximum two identical failed attempts), uncertain-persistence
reconciliation, source receipts and verified output. No reset on a new schedule.
Prepare all test machinery before any hosted/provider job. Allow independent
families to progress; isolate a blocked provider instead of pausing everything.

C. Connect the named worker to admitted work, extend useful-progress observation
and independent verification to the bulk ledger, test postcommit loss/stale-owner/
expiry/cancellation/accounting, and qualify exact revisions before deployments.
Retain existing unproven host-eviction/non-overlap/authenticated-HTTPS gates honestly.
Do not let an unavailable hosted experiment prevent unrelated source/test work;
do not waive actual safety gates for production execution.

D. Execute bounded retained-source reuse and, when the adapter/accounting and
provider gates pass, finite missing-data batches. Cover all 24 families or record
evidence-backed exact unavailability. D06 is never an acquisition family. Shared
macro/futures/breadth evidence is not multiplied 3,000 times. No arbitrary subset,
silent denominator relaxation or false completeness.

E. Independently reconcile every family against source evidence, lifecycle and
point-in-time requirements; publish a full coverage/gap inventory and narrow
consumer-ready outputs only after their own gates pass. A successful canary,
heartbeat, passing task or this capture receipt is not complete delivery.

Existing qualified v1 jobs and their budgets are immutable and separate. Current
additional qualification consumption remains1/10 requests,78/1000 records and
$0 incremental compute. New bulk reservations must be durable and finite within
existing resources; they cannot be inferred from this evidence-capture receipt.


## CI-qualified retained-only claim recovery (STAGED, NOT INSTALLED)

Exact tested source revision: abef74e25dd1b5bb80618e5083658d22230467a0. The staged
`sql/astra_ingestion_bulk_ledger_v1.sql` now contains
`bulk_recover_retained_v1(work, expected_fence, new_owner, lease_seconds)`.
It only reclaims previously claimed, expired `retained_source_reuse` work
with zero provider requests. It preserves immutable original job deadlines,
retained receipts, costs and cumulative attempt count; requires an expected
fence and changed owner; takes a manifest lock before a work lock; and fails
closed on stop, deadline, stale fence, attempt limit or provider acquisition.

Lease expiry **does not** prove the former instance stopped. DB fencing protects
the retained-only commit path, not hosted cross-instance cessation. Provider
acquisition never automatically retries through this function. Independent
review, restricted runtime rights, exact 24-family coverage, automatic
successor execution, old-host cessation and hosted eviction are still OPEN.

Disposable PostgreSQL regression passed: 163 ingestion tests, including two
new retained-only recovery/stop/expiry cases and no-duplication evidence.
CI: [ingestion PR qualification](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40898001985),
[release PR gate](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40898002041)
and [release push gate](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40897993666), all successful.
This is source/disposable-database validation, NOT production installation or data acceptance.

## Full-24-family source-witness preflight (CI-qualified, NOT runtime admission)

Added `astra_ingestion/bulk_manifest_admission.py` and
`tests/ingestion/test_bulk_manifest_admission.py` at executable candidate
`10a755efa91b722a819c1ec457e10d563b7fabdd`. Both ingestion workflows
[push](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40908820282)
and [PR](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40908830654)
PASS; both release gates
[push](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40908820390)
and [PR](https://github.com/robert8p/Alpaca-Supabase-Populator/actions/runs/40908830668)
PASS. The source and test use only synthetic evidence, have no provider/database
writes and create no executable work.

The preflight reconstructs all 24 expected family populations from the pinned
4,136-record receipt, accepted company membership, original contract set and
independent eligibility/keyset bindings. It refuses substituted or forged
`ExpectedUnitPlan` objects; requires source snapshot/contract/expected-manifest
hash bindings for each family; reads sorted, finite source-witness keyset pages;
checks all expected versus witnessed keys; and distinguishes absent denominator,
missing source proof, missing/extra units, duplicate rows and invalid provenance,
identity or point-in-time witness metadata. D06 never becomes a work family.
All-family structural reconciliation produces only
`INDEPENDENT_REVIEW_REQUIRED`, NEVER permission to reserve, claim, fetch or
certify full dataset coverage. The `worker_admission_authorized` property
remains false by construction, and actual source bytes/point-in-time truth need
independent external evidence and restricted runtime checks.

This is one tested **engineering slice**, not the durable production admission
barrier: the existing staged SQL ledger does not yet consume this fingerprint
or enforce independent reviewer/manifest-source/worker admission. No real
24-family source denominators or per-family proof records have been supplied;
therefore none of the research families is DATA_ACCEPTED.
Read-only production evidence at 2026-10-29T16:11:27Z still has 4,136 scope
documents; Render web and worker still run revision
`2c809b69e131f84e1778486e74c2f89a273f59f9`.
No acquisition, migration, deployment, paid service or original-job mutation
accompanied this slice.

**Executable successor:** bind independently acquired exact 24-family source
unit/temporal/identity proofs to this tested preflight and staged ledger;
implement a restricted, fail-closed durable admission transition and retained
reuse worker dispatch (with verified automatic successor). Develop against
disposable PostgreSQL without assuming production RLS grants or bypassing any
previous explicit source introspection refusal. Qualify the exact revised
source/deployment before any production admission. The independent reviewer
and closeout automations remain disabled with unexplained user-action flags,
so neither review nor closeout acceptance may be presumed.

