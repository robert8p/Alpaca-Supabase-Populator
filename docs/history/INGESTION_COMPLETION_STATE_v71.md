# ASTRA ingestion — replacement checkpoint v71

**Progress cutoff: 2026-10-30T13:45:41.352806Z. Published through the existing root controller; source/cron observations are dated separately below.** The approved connector-compatible Massive relay and narrow claim filter repair are installed. The run has committed 515 more pages since that repair. Two exact PID correlations identify the existing cron 602 monitor as the holder blocking worker authentication at the global advisory gate. Maintenance cost isolation is the current executable step. Sustained recovery and full mission completion are not established.

## Ownership, mission and durable successor

Continue run `fixed3000-20250901-20260731-v1-20261030`, fence **1**, under `root-replacement-20261030T042603Z`. The existing implementation lease runs through **14:30 UTC**, audit **28**. Reconcile its current value, retained work and uncertain writes before any further mutation; an old checkpoint is not authority to displace an active writer.

The same enabled hourly task is `6ae2a4c96bbc819182133e17e9b7f779`. Its scheduled **13:00** run, `6c2e1bc0-2800-8328-b027-da97f8799910`, started **13:04:55.441853** and **completed at 13:10:48.548108**. Its retained result was read-only: it reported 4,276 pages as of 13:06, preserved this owner/lease, made no competing writes and requested no owner action. Its then-proposed claim repair is now installed and must not be replayed. The 13:29 task readback confirms the existing hourly schedule remains enabled; `next_run_time` was null and delivery status unknown, so no exact next dispatch or message delivery is asserted. Read the current registry before updating only this task. The deployed worker continues automatically. [Existing successor readback](../evidence/replacement-existing-successor-readback-v71.json).

Scope remains exactly the frozen **3,000 members**, all **16 families**, **2025-09-01 through 2026-07-31** using New York market dates, and required support history/formulas. Only the existing Alpaca Algo Trader Plus and Massive Stocks Starter entitlements are allowed. Keep excluded families and unrelated data intact; no new subscription, source substitution, scanner change or trading.

The accepted snapshot `content->companies` SHA-256 is `2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec`, acceptance event **24407**, cohort manifest `4134b415e2c26fcde9fced749c0d54ef51376e23f0d2f8c6ce9ef562f9fab99f`. Membership/order reconciliation and prior reuse are retained. Never call `ref01_practical_material_v1`, rerank, substitute, shrink or restart the cohort. This remains a retrospective fixed cohort.

The exact v70 documents are preserved in [checkpoint history](history/INGESTION_COMPLETION_STATE_v70.md), SHA-256 `39b71ed0c3a198391116aabe00c5bad850913b8445817001befdda445f0b06a8`, and [automation history](history/REPLACEMENT_IMPLEMENTATION_AUTOMATION_PROMPT_v70.md), SHA-256 `af93cf9ba82bc77c72d65adf8b62c28d57d18f070e17e7eccd64380becd7188b`. Their earlier relay hold and runtime pins remain historical evidence, not the current installation state. The [original ten-section mission](REPLACEMENT_BACKFILL_MISSION_20261030.md), SHA-256 `62dd1a15c5c6cf46a42340917701816c6c3b86c49e4b4fb462f8b111bcaadc45`, is unchanged; its complete bytes follow the consolidated automation prompt.

## Verified useful progress

Latest run readback at **13:45:41.352806 UTC** is **4,791 committed pages, 580,742 physical records/pointers, 2,453 reservations, 484,986,459 source bytes and 4,791 independent readbacks**. **515 pages** have committed since the 13:13 claim repair; the latest actual page commit is **13:45:34.304069**. Planner next-member cursor is **2,173**, planning remains false, and the same owner/fence remain active with lease through **14:30 UTC**. This is acquired and verified work, separate from planning timestamps. It does not establish sustained recovery or full coverage. [Latest exact run readback](../review/recovery-v71/live_committed_progress_1346.json).

At **13:29:06.438699 UTC**, the run had **4,423 committed pages, 538,388 physical records/pointers, 2,224 request reservations, 454,982,075 source bytes and 4,423 independent readbacks**. This is **147 new pages since the 13:13 claim repair**. Latest page commit was **13:25:59.737537**; latest worker observation **13:25:57.729834**, source `3ee4db2a79c081ffb65ef0d7ec2a04228d69fb1d`. The durable planner next-member cursor was **2,099**; planning remains incomplete. These are overlapping physical outputs, not unique observations or final coverage. [Committed progress and cursor](../review/recovery-v71/live_committed_progress_1329.json).

A separate **13:08:39** relay proof establishes **67 provider pages, 4,812 records, 67 bound dispatches and 67 independent readbacks** across **67 distinct tasks**. These pages are included in the run totals and must not be added again.

The separate **13:10:25.22716** date-classification readback divides those records as follows. The N02 source-date reconciliation accounts for all 536 records; the 12 post-window records are accounted for and are not unknown or lost.

| Relay family | Pages | Target window | Pre-window support | Post-window | Total records |
| --- | ---: | ---: | ---: | ---: | ---: |
| N01 — Massive news | 15 | 1,500 | 0 | 0 | 1,500 |
| N02 — dividends | 13 | 35 | 489 | 12 | 536 |
| N03 — executed splits | 14 | 0 | 27 | 0 | 27 |
| S01 — short volume | 12 | 2,487 | 0 | 0 | 2,487 |
| S02 — short interest | 13 | 262 | 0 | 0 | 262 |
| **Total** | **67** | **4,284** | **516** | **12** | **4,812** |

There are zero unknown-date records in this reconciliation. [Target/support readback](../review/recovery-v71/live_relay_target_support_readback_1308.json); [N02 source-date reconciliation](../review/recovery-v71/live_relay_n02_date_reconciliation_1308.json). The historical `1308` filenames do not replace the recorded 13:10 observation time.

First relay commit was **12:37:11.249618**; later distinct tasks committed without another manual trigger. This proves useful acquisition and an automatic successor through the existing worker. A live Massive reference page was not yet observed in that proof. It does not establish completion of the five observed families, all six Massive routes, all 16 mission families, sustained recovery or unique-observation coverage. [Relay acquisition and binding/readback receipt](../evidence/replacement-approved-relay-live-acquisition-v71.json).

Planning, pagination/enumeration, historical identity, derivations and field-level coverage remain unfinished. Preserve the prior status/index, member-count, fairness, pacing, reuse, aliases, shared-data, registry and readback work. The legacy canary's 234 records/3 requests and old-scope closure remain historical; do not reset them or reapply their limits to this replacement run. Refresh actual durable planning cursors rather than assuming the v70 position is still current.

## Approved relay installation and live source

The expired **09:53** v2 approval and failed pre-DDL transport attempt remain preserved; they were neither re-dated nor reused. Rob's actual **12:14 UTC** action-time approval, `Sentinel_17a454f266748191bfca91e4c57d99b0`, authorized the independently reviewed **managed-massive-relay-v3-review-20261030** package at publication `8774e059274610635111cc4e0fb2d74923c37545`. Its exact SQL was installed once at **12:17:26.804513**, within the **12:29** installation deadline, audit **23**. The existing Edge function is **version 2**. No native PostgreSQL configuration or owner-supplied code is needed for this installed route.

The connector-compatible v3 validator accepts only the two reviewed exact wrapper endings; it does not trim or generally normalize input. All body/history equality, authentication, scope, fence, expiry and integrity controls remain bound to the approved package. The existing managed Massive key remains server-side; no new provider subscription or credentials/environment configuration were created. New persistent security scope still requires specific action-time confirmation if a future proposal materially changes it. Do not reinstall this package or request renewal for work already installed under valid approval. [Approval/install receipt](../evidence/replacement-managed-relay-approval-installation-receipt-v3.json); [production security proof](../evidence/replacement-managed-relay-production-security-proof-v3.json).

The existing Render worker service `srv-dbh9fko473hc739an8m0` was manually deployed **once**, deployment `dep-dbi8ud942hec73cpm7qg`, and became **LIVE at 12:36:45.668499** on `3ee4db2a79c081ffb65ef0d7ec2a04228d69fb1d`. Subsequent registration advertises all **18 supported kinds**. Automatic source deploy remains disabled. [Deployment](../evidence/replacement-approved-relay-worker-deployment-v71.json); [3ee4 CI gates](../evidence/replacement-3ee4-release-gates-v71.json).

The earlier `d321` publication/collection failures are preserved. The `3ee4` correction published the seven exact approved active files and the scoped historical-review collection boundary, with active binding tests; no frozen review artifact or security validation was weakened. Both ingestion jobs passed **627 tests**, and both repository jobs reported **708 passed/309 skipped**. The worker diagnostics add only fixed, allowlisted RPC operation/reason labels; exception bodies, payloads, headers and secrets remain excluded. Those labels do not, by themselves, identify the cause of an `HTTP_ERROR`.

## Installed performance repair and current pins

Latest qualified source is **`b434f4575f5d6656b176b006857a655e4bf703c9`**, tree **`b35471f7db32d197c8d0012b42976fb6bb4e4d0f`**. It adds SQL, tests and evidence without changing existing worker, Edge or workflow files. Keep the live worker on `3ee4`; this SQL-only publication requires no redeploy.

| Binding | SHA-256 |
| --- | --- |
| Approved v3 scope | `a40f86ad49918644c5443586644b66ca9748ede1a91ffb8a09cdca0b522963d5` |
| Installed v3 SQL | `fe0f948824771dfa673548402e5d80a076d71f0211cf24091bb11e7ef0b6b013` |
| Live worker file | `b682b2425fd226296cdc141ff5936a49a7cac336fe859a02ebbd7faa4adf49c2` |
| Claim-filter SQL | `25427b992aebe5c81ae6c4b9e4cb44b560c8201b044476ea1ea937a933fed10c` |
| Current private dispatcher | `28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44` |
| Current approved authenticated dispatcher | `a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520` |
| Unchanged status branch | `cee8f62d034a88e3fb5166fce2b4b4903cdd1aee802e2efebfc3f08cf6c0a5de` |

The claim repair changes only the supported-kind membership predicate in the normal and recovery candidates. The controller applied SQL `25427…` **once at 13:13:00**, audit **27**. **13:13:22.722702** readback confirmed private dispatcher `28ae…`, the same OID **16040232** and metadata, unchanged authenticated dispatcher `a9a7…`, and exactly one migration-history row with the reviewed body. Authentication retains its **10-second statement/3-second lock configuration**. No grant, credential, trust, source, cost, scope, retry or runtime timeout change accompanied this repair. [Live installation/readback](../evidence/replacement-claim-capability-filter-live-installation-v71.json). Never replay either this installed repair or the retained v70 index maintenance after an uncertain response; read back first.

All four `b434` gates passed on attempt 1. PR checkout used a synthetic merge with the exact same tree as `b434`.

| Gate | Run | Actual result |
| --- | --- | --- |
| Ingestion PR | 41060461986 | 636 passed, zero skips, 331.572 s |
| Ingestion push | 41060453205 | 636 passed, zero skips, 321.780 s |
| Release PR | 41060461822 | 709 passed, 317 skipped, one warning, 11.44 s |
| Release push | 41060453000 | 709 passed, 317 skipped, one warning, 13.14 s |

Both ingestion jobs passed all nine new repair tests. The independent local review passed eight focused tests with zero skips; the scale benchmark was already qualified separately. Initial fixture errors remain recorded and were corrected without disabling monotonic-fence or frozen-member triggers. [Qualification](../evidence/replacement-claim-capability-filter-qualification-v71.json); [independent review](../evidence/replacement-claim-capability-filter-independent-review-v71.json); [exact-head CI and file pins](../evidence/replacement-claim-capability-filter-release-gates-v71.json).

## What the diagnostics establish

The performance finding was narrow: an earlier Alpaca-only N01 candidate traversed about **22,121 unsupported Massive tasks** before supported work. The original read-only custom candidate exceeded 8 seconds; the reviewed predicate returned one candidate in **5,604.352 ms**, with **11,896 physical block reads**. A later generic candidate took **82.039 ms** with a warm cache and zero physical reads. These are different cache states, not a controlled speed ratio. The diagnostic SELECTs omitted `FOR UPDATE` and did not execute the authenticated RPC or the full multi-family loop. They do not prove all subsequent claim failures fixed.

For the later full 18-kind worker, one original D03 read-only custom probe returned one row in **6.571 ms** (planning **5.342 ms**, 161 hit/9 read blocks). D03 was the next retained family, not a proven failed family. No candidate comparison was dispatched after that fast result. The probe was dispatched before explicit transaction-setting assertions were added: retain its exact SQL/result and do not claim independently verified read-only/repeatable-read settings or replay it merely for stronger assertions. Its source guard pins old `1368…` and is now stale; do not execute it against `28ae…`. [Retained D03 result](../review/recovery-v71/live_full18_d03_current_custom_result.json).

The post-install worker blocker is **SQLSTATE 55P03** in approved outer `rpc_dispatch` **line 39**, the existing `pg_advisory_xact_lock(706314020261028)` acquisition. The live credential recheck at line 40 is unchanged. Two exact PID/time correlations identify **cron job 602, `monitor_tick_v1`**, as the gate holder during worker failures:

| Worker failure UTC | Worker waiter PID | Gate-holder PID | Cron 602 run | Cron start UTC | Cron end UTC |
| --- | ---: | ---: | ---: | --- | --- |
| 13:16:03.335 | 1242184 | 1242938 | 4068588 | 13:16:00.034976 | 13:16:03.949088 |
| 13:26:03.224 | 1243169 | 1244016 | 4068598 | 13:26:00.045168 | 13:26:04.085217 |

[Safe initial errors](../review/recovery-v71/live_postrepair_sql_errors_1317.json); [second holder correlation](../review/recovery-v71/live_monitor_second_holder_correlation_1326.json); [cron run/PID proof read at 13:31](../review/recovery-v71/live_ingestion_cron_run_pid_proof_1331.json). This establishes the holder and the worker overlap, not which maintenance helper accounts for the duration. Cron elapsed includes its initial gate wait, and the transaction lock remains held through the monitor's remaining work until transaction end.

The 13:14:44.497 lock error and frequent **35-byte health failures** are separate evidence; do not attribute every lock error to ingestion. Other sanitized `HTTP_ERROR` records remain unattributed without independent correlation. This gate wait is distinct from the older private normal-candidate line-123/57014 failure; it does not implicate CTX06. No CTX06 probe is justified or recorded. Worker planner and claim calls are sequential, and relay SQL authorization returns before external HTTP.

The **13:18:52** off-failure lock snapshot was empty and remains inconclusive. Existing `log_lock_waits=on` supplied the later holder evidence without a configuration change. The qualified bounded capture `capture_gate_lock_contention_readonly_v71.sql`, SHA-256 `7d0c61e69cb677cff9531c88e29a39a4d9b955883b7eeb5b5add2c112d63af59`, passed three local holder/waiter/redaction tests but **was not executed in production and is no longer needed for this attribution**. Preserve it as prepared evidence; do not dispatch it merely to repeat a resolved observation. [Off-failure snapshot](../review/recovery-v71/live_advisory_lock_snapshot_1318.json); [capture qualification](../review/recovery-v71/gate_lock_capture_qualification_v71.json).

Later source observations retain `backfill_maintain_v2` SHA-256 `cd10046d9c9aa15e8bc66724d1258d95151364ffeee9070d761c4f7d930b5859` and `monitor_tick_v1` SHA-256 `875c017ecf73df15163d15d3f9129b4507235dc893ccb4233d0a435154389057`. The 13:35 helper read has `track_functions=none`; tracking and logging configuration were unchanged. [Maintenance body](../review/recovery-v71/live_backfill_maintain_1332.json); [monitor body](../review/recovery-v71/live_cron_functions_1331.json); [ten helper definitions](../review/recovery-v71/live_maintenance_helpers_1335.json).

A later bounded **13:41:02.252092–13:41:02.985638** selector profile completed all ten components in about **733 ms**, with read-only and repeatable-read settings verified. Breadth selection took **445.102 ms** and minute-account selection **181.387 ms**, each returning zero candidates. Cursor selectors took under 1 ms and returned 2 nonminute, 8 S02, 4 shared and 32 contract rows; contract enumeration returned one row in **0.585 ms**, and missing-readback selection returned zero in **11.117 ms**. No maintenance helper or provider was invoked and no production mutation occurred. These current no-work results do not establish what was pending during the earlier failures. The profile measures direct-role read paths, not cached cron plans, mutating helper execution or gate wait. This earlier diagnostic does not supersede the separately verified run progress above; a global table count from a plan is not this run's progress. [Exact selector profile](../review/recovery-v71/live_maintenance_selector_profile_1341.json).

A separate compact candidate read completed once at **13:42:25.319181**, under the same source/owner and enforced read-only/repeatable-read bounds. The current shared/S02 candidates take their early non-applicable-kind returns; the two nonminute candidates contain five action records and one reference record. Contract enumeration has one selected **1,000-record/705,542-byte** page. The **13:43:15.874347** read confirms `seed_complete=true` and S02 seed cursor **46**, so contract admission passes its seed gate and retained S02 seeding is exhausted. Planning remains false, with no pending identity discovery/refresh at that observation. These later snapshots do not identify which page was selected during the 13:16/13:26 failures. The next bounded diagnosis is the selected contract page's read-only parsing/key/join cost and a disposable local full-admission fixture. No maintenance repair has been applied. [Candidate metadata](../review/recovery-v71/live_maintenance_candidate_metadata_1342.json); [seed state and helper definitions](../review/recovery-v71/live_contract_seed_state_helpers_1344.json).

## Current executable continuation

1. Reconcile current ownership/lease, the completed existing hourly run, live worker, exact installed `28ae…`/`a9a7…` sources and uncertain outcomes. Preserve one controller and all retained work. Do not replay installed SQL or redeploy the unchanged worker.
2. Continue cost isolation for the proven monitor within existing maintenance/authentication/schedule. The selector profile `review/recovery-v71/maintenance_selectors_readonly_v71.sql`, SHA-256 `462cd183dc28fd0c963b7bd014fb6a63164937cc624b9e023c26c3a8e74d3cf1`, completed once at 13:41:02. The independently reviewed compact candidate probe, SHA-256 `0d16861b7deff8eb54c5632922935c6a4f2e63c1a204994ab55afba800d78105`, completed once at 13:42:25. Preserve both results; do not replay resolved observations. Next isolate the selected contract page's pure-SELECT parsing/key/join cost and qualify the full admission path in a disposable local fixture against retained exact definitions. Avoid invoking mutating production helpers merely for timing. These direct-role read paths do not measure original cached cron plans, mutation-body duration or gate-holding duration.
3. Qualify the smallest demonstrated maintenance correction. Preserve authentication, post-lock credential validation, the global lock, all scope/stop/fence/integrity controls, current runtime timeout budgets and the existing schedules. Do not extend timeouts, cancel an unidentified backend or claim the earlier N01 filter resolves this blocker. Any materially expanded persistent security scope still requires a prepared exact diff/tests and specific action-time confirmation.
4. Keep the deployed worker and existing recovery path running. Verify new committed pages and independent readbacks after any targeted repair; progress counters, passing CI and LIVE status each prove different things.
5. Continue fixed-cohort planning, entitled acquisition/reuse, pagination/enumeration, identity/support/alias work, derivations and per-family field accounting. Keep unknown denominators and provider/quality gaps explicit; operational timeouts are not provider absence.
6. Publish this reconciled v71 checkpoint durably before any v72 repair and retarget only the existing hourly task with the consolidated prompt and byte-identical original mission. Record the actual owner, task outcome, genuine progress and next bounded executable step. No new controller, routine approval request, artificial mission expiry or completion claim.
