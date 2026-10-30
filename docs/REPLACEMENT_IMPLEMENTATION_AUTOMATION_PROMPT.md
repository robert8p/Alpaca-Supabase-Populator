# Existing implementation task — replacement checkpoint v73

**The bounded v73 observation is complete and exact maintenance source has been restored.** The package at **3fddb6cf196e289e79eb9bfaef45d56965b64eca**, tree **bd41e2f106d412ebebf3e72f854c2665ae616aa8**, passed all four exact-head CI gates, was installed once, produced two immutable ordinary-monitor observations, and was restored once to exact **6c880114a645c8a9167d5260c4aeabf58a10617c4244cf0340be1d6cf4bf0ce7**, independently verified at **15:45:10.404232**. The diagnostic deadline remains **15:45 UTC**, has expired, and must not be extended or used to reinstall. Same-owner lease **16:15 UTC** remains separate.

The final accounting cutoff is **15:46:48.130167 UTC: 5,650 pages, 5,650 independent readbacks and 680,657 physical records or retained pointers**. Latest actual acquisition was **15:41:59.315192**, before restoration; post-restoration acquisition is not yet demonstrated. Shared processing dominated the first measured maintenance call, while contract processing exceeded two seconds in both. The remaining engineering step is a bounded, source-pinned read-only diagnosis of those retained inputs, plus separate review of proven55P03 rollback handling. **No further repair or deployment has been selected, and sustained reliability or mission completion is not established.**

## Scope, owner and the existing successor

Continue repository `robert8p/Alpaca-Supabase-Populator`, branch `feat/astra-ingestion-service` / PR93, project `oxzabweahkoimtevbbny`, schema `astra_ingestion_v1`, and run `fixed3000-20250901-20260731-v1-20261030`. The existing owner remains `root-replacement-20261030T042603Z`, fence1. Audit38 at **15:27:06.530532** renewed only this owner's lease to **2026-10-30 16:15 UTC**; the independent **15:27:13.806142** readback found one matching audit, unchanged cohort and ACTIVE status. The preceding15:45 owner lease remains historical evidence. This renewal does not renew an approval, extend the15:45 diagnostic window, displace another valid writer or create a new controller. Evidence: `evidence/replacement-owner-phase-observation-cleanup-lease-v73.json`.

Retain enabled hourly task **6ae2a4c96bbc819182133e17e9b7f779**, its unchanged schedule and the existing deployed worker. The v72 prompt was updated at **15:07:12.508437** and independently read back byte-exact, SHA256 **01b010fc7e35fa9b60bd7d7f4d8792834fa870ca689ac2d5c79f86b89aa6a283**. The retained successor read shows the15:00 run `f42a5e8f-3164-832a-b9ba-11d00afb2ab8` completed at **15:09:15.771228**, with latest result created15:09:14.940488; the exact v72 prompt remains installed. A fresh read bounded by **15:53:42–15:53:44 UTC** independently confirms the same enabled task, exact v72 prompt, completed15:00 run and no newer run. These observation bounds are separate from task update, run completion and result timestamps; the15:40:51 database preinstall time is not used as an automation timestamp. Delivery and future dispatch timing are not guaranteed by the read. Evidence: `evidence/replacement-existing-successor-update-v72.json`, `review/recovery-v73/independent_progress_during_phase_preparation_v73.json` and `review/recovery-v73/existing_successor_before_checkpoint_v73.json`. After publishing this concrete checkpoint, update and independently read back only this existing task. No second controller, task or worker is authorized by this checkpoint.

Keep exactly the frozen **3,000 accepted members**, all **16 families**, **2025-09-01 through2026-07-31** New York market dates, required support history and formulas, and only the existing Alpaca Algo Trader Plus and Massive Stocks Starter entitlements. Accepted `content->companies` SHA256 is **2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec**, acceptance event24407; manifest **4134b415e2c26fcde9fced749c0d54ef51376e23f0d2f8c6ce9ef562f9fab99f**. Preserve `RETROSPECTIVE_FIXED_COHORT`, its selection limitation, exclusions, aliases and unrelated data. Never invoke `ref01_practical_material_v1`, rerank, substitute, shrink or restart the cohort. Existing planning, reuse, support, derivation, registry, pacing and verification work remains retained.

## v72 continuity publication and task refresh are complete

Checkpoint v72 is published at **1f1f423e4dd1db87eff92e8687b2d9c49ba63c01**, tree **45c5b7d6410f4fba1d154d50debdb3b574c9e86d**, manifest **7d4b2dd64303c7d5a19f12634d9c09322b5a9d73223fb7a993d6e6bdad15c2ef**. Audit37 at **15:10:23.865821** and independent **15:10:25.067253** database readback bind the exact checkpoint, same-task prompt and preserved original mission. These completed writes must be reconciled, not repeated. Evidence: `evidence/replacement-published-checkpoint-v72.json`.

All **three actually triggered**1f1f workflows passed: ingestion PR41077749682 executed653 tests with zero skips/errors/failures in340.759s on PostgreSQL17.11; release PR41077749681 reported710 passed/333 skipped/one warning, and release push41077738141 reported the same counts. The PR checkout `db5f52d69fac119b0f2d0d39cbb0103e054c8ef1` has the exact published45c5 tree. No ingestion-push run was returned or claimed for this documentation checkpoint. Evidence: `evidence/replacement-checkpoint-ci-v72.json`. These checks do not replace3fddb6cf's new runtime qualification.

Preserve all existing v71 archives. The v73 continuity packet archives the exact v72 canonical documents, SHA256 **3efdf5fdced9176457d5943fd829983e0afcaf4fc43eebdaa40d143c7903b0c3** and **01b010fc7e35fa9b60bd7d7f4d8792834fa870ca689ac2d5c79f86b89aa6a283**, alongside the reviewed v73 canonical replacements. Every other existing blob remains unchanged.

## Latest verified acquisition — cutoff15:46:48.130167 UTC

| Exact-run measure | Verified value |
| --- | ---: |
| Committed pages | 5,650 |
| Physical records / retained pointers | 680,657 |
| Request reservations | 2,980 |
| Reported source bytes | 551,219,963 |
| Independent page readbacks | 5,650 |
| Planner next-member cursor | 2,359 |
| Planning complete | false |

Latest actual page commit: **15:41:59.315192**. Since the final v72 repair readback14:40:58.490017, the retained query identifies **342 pages /38,380 physical records or pointers /342 distinct tasks**, all342 with matching independent hashes and counts. That interval includes the15 pages/1,887 records already reported in v72. Compared with v72's14:46 accounting cutoff, the actual increase is **327 pages/readbacks,36,493 physical records,200 reservations and22,964,586 reported bytes**. These overlapping deltas must not be added again to run totals.

The15:28 postrestart receipt separately proved15 new pages/readbacks and1,482 records after the15:25 recovery read. From15:28 to this final cutoff, another81 pages/readbacks and7,995 records were retained. These observations establish real acquisition before cleanup, not the restart cause or sustained reliability. **The latest page predates the15:45:10 restoration; no post-restoration acquisition is claimed.** A planner cursor is not a completed-member count, and physical rows/pointers are not certified unique target-window coverage. Evidence: `review/recovery-v73/live_progress_after_phase_restoration_v73.json`, SHA256 **cf71d387ff605518252564923dc6020b151d6b9014547396ce2dbc7b8d6cf93a**, and the separately retained `review/recovery-v73/postrestart_independent_acquisition_v73.json`.

## Temporary database unavailability reconciled without manual restart

A read-only ownership/progress query around15:24 returned **FATAL57P03**, database not accepting connections, with the hot-standby-disabled detail. No write was attempted in that failed call. Control-plane ACTIVE_HEALTHY was retained as a separate observation, not proof that SQL was available. A successful **15:24:50.052808** read showed a postmaster start at **15:23:17.23156**, `in_recovery=false`, read_only off, unchanged owner/fence and exact installed maintenance6c880. Root did not initiate a restart, redeploy, credential change or counter reset.

The15:22:03 worker `backfill_plan_next` failure is separately matched to55P03 at authenticated dispatcher line39 and predates the observed postmaster start. Timing does not establish the restart cause. The15:25 database read confirmed5,554 pages/readbacks and671,180 physical records; the subsequent15:28 receipt supplies the15 real new pages described above. Evidence: `review/recovery-v73/database_availability_incident_v73.json`, `database_availability_recovery_readback_v73.json` and `postrestart_independent_acquisition_v73.json`. Fresh source/ownership/permission readback still precedes any new mutation.

## Bounded phase observation — installed once, two samples retained, exact cleanup complete

The45-file additive package at **3fddb6cf196e289e79eb9bfaef45d56965b64eca**, tree **bd41e2f106d412ebebf3e72f854c2665ae616aa8**, preserves every existing1f1f blob. Publication manifest SHA256 **0c1b44fa60738665d676c73637d8c946c3b86d723fc3a2001c743b76b00ac94e**. Its candidate is **12e05b1fa5a6e59f1f626a33aaec4e30248d0cfc858917be171fd812b41c229d**, mechanically reversible to the complete installed **6c880114a645c8a9167d5260c4aeabf58a10617c4244cf0340be1d6cf4bf0ce7** definition. The earlier v72 timing prototype remains unselected and unapplied.

Audit39 at **15:33:38.322994** records the published package as **PREPARED_NOT_INSTALLED_AWAITING_EXACT_HEAD_CI**; independent **15:33:51.364909** readback confirmed one matching audit, exact source pins, unchanged controller/fence and16:15 lease. Evidence: `evidence/replacement-maintenance-phase-publication-v73.json` and `evidence/replacement-maintenance-phase-prepared-audit-v73.json`. These are preparation/publication records, not installation records.

The separately reviewed read-only preflight completed at **15:37:00.288969**, under explicit read-only/repeatable-read8s/3s bounds. It confirmed installed baseline6c880, maintenance OID16041463, the fixed3,000 members, same owner/fence/lease, all13 unchanged function pins and exact metadata/permission/index catalogs. Its `install_ready` value describes that catalog snapshot only; the exact-head CI gate is still independent. Evidence: `review/recovery-v73/live_phase_preflight_before_ci_completion_v73.json`. The late preflight independent review is `evidence/replacement-maintenance-phase-preflight-independent-review-v73.json`, SHA256 **a77af1105096cb9f239f44522980e6691b845492eab133a961545eb265571216**, and must be included in the final checkpoint packet.

| Artifact | Exact SHA256 |
| --- | --- |
| `sql/astra_backfill_maintenance_phase_observation_v73.sql` | b7bf8d2223cf7f50f9d8e5653c836c8a30517f030f8592f99a9f48dcc478c34d |
| `sql/astra_backfill_maintenance_phase_observation_restore_v73.sql` | 9a11851bcaf11a8c530575a5b1c0a83d4b9f66b650a18f47484c2c8ade8fe020 |
| Active observation test | 1744faa5fedb092991c2229dffc31de8c45a6e19c3ad614bf4d1c654f6df89fe |
| Active installer/restore test | c6b57aa7aca1b5f84037cf54eb10c54bce88e70c4c21f76636155ac493c09cbc |
| Independent review | 95600d447b131c0b67e7179201b956437a4d43c4b38129c69dfa1cac9c05e29c |
| Combined active qualification/dependency audit | 4085afa8b744a9b7b42ca58ee42aedb22295c96cc58fab243405b762e2e6ac0d |

The combined independent local run executed **26 tests:17 observation plus9 installer/restore**, with zero errors, failures or skips,16.507s. All77 actual project dependencies were accounted for; every existing dependency matched1f1f exactly. The tests exercise the actual nonsuperuser/non-BYPASSRLS owner, existing audit SELECT+INSERT and identity/sequence behavior, real RLS denial, queued READ COMMITTED commit/rollback cap races, stronger-isolation main work, deadline/lease expiry inside the optional INSERT, immutable evidence, exact cleanup and postwrite rollback. Initial failed fixture evidence is retained: direct sequence USAGE removal was incorrectly expected to stop GENERATED ALWAYS identity allocation. The corrected test proves direct `nextval`42501 separately; no production grant was added to satisfy it.

The function keeps its original gate, ten helpers/loops, readback age/failure rules, result, owner, ACL, VOLATILE classification, empty search path and8s/2s settings. It uses existing permissions to append at most **four committed** numeric observations for one fixed probe/run; the underlying measured work remains **global maintenance**. Telemetry is admitted only under READ COMMITTED after the existing gate, with the fixed owner/fence/cohort, valid lease, cap and unextended **15:45** deadline. Stronger isolation skips only telemetry. No new role, grant, credential, API operation, provider request, schedule or timeout policy is introduced.

Measurements separate gate admission, telemetry admission, all eight original helpers, readback and finalizer loops. `total_ms` ends before audit construction/append; monitor remainder and caller commit are unmeasured. Ordinary telemetry failures affect only their diagnostic subtransaction; cancellation/assertion and original helper errors propagate. NOWAIT prevents specified relation/row waits but cannot eliminate IO or commit cost. A local fault test demonstrates that the extra audit write can exhaust an otherwise sufficient caller deadline; zero observer effect is not claimed. Append-boundary checks do not guarantee commit time. Audit identity gaps can remain after rollback; they are not reset. REF03 evidence rows increase without becoming acquired-page/readback/coverage counts. Missing samples can reflect the cap, expiry, isolation, failure or caller rollback and do not prove fast maintenance.

The install forward is ACTIVE-only and fail-closed on exact source, full metadata/permissions/index/helper pins, same owner/fence/cohort/3,000 members and valid lease. Cleanup restores exact6c880 under those same guards in **any existing run status**, including PAUSED and COMPLETE, without altering status or deleting evidence. Cleanup is allowed after15:45 under the unexpired same-owner lease; installation/collection is not. Reconcile any uncertain response before retry, and never rerun the installer merely because a sample is missing.

All four exact **3fddb6cf** gates passed on their first attempts. Both dedicated ingestion jobs ran **679 tests, zero skips/errors/failures**, including all17 observation and9 installer/restore cases, on PostgreSQL17.11. The PR run41081683757 took391.266s; push41081674761 took382.028s. General-release PR41081683707 reported **712 passed /357 skipped /one warning**,11.84s; push41081674552 reported the same counts,10.77s. Both PR jobs checked out `eb78a1ddf9f1991c0c6b2b493b294f1ba45a1435`, whose tree exactly equals publishedbd41. Evidence: `evidence/replacement-maintenance-phase-observation-release-gates-v73.json`, SHA256 **6aa9e9d9d73780f39c615871ed6354fd999d7f38310622bad938b93daddf9668**. These are actual qualification results, not live performance or recovery proof.

Root then reconciled the complete live state at **15:40:51.089697**, applied the frozen forward **once**, and independently read it back at **15:41:15.953464** as exact candidate12e05. History version **20261030154059** contains one exact **46,180-byte** b7bf SQL body, confirmed at **15:41:17.079034**. Maintenance OID16041463, full metadata, audit permissions, both task-index fingerprints, all13 unchanged function pins and the remaining schema catalog fingerprints matched before and after. Owner/fence/cohort/3,000 members and16:15 lease remained exact. Evidence: `evidence/replacement-maintenance-phase-live-installation-v73.json`. No worker redeploy, provider request, schedule or timeout change accompanied installation. The install is completed work, not a retry candidate.

### Ordinary monitor observations identify expensive phases

Exactly two committed fixed-probe samples remain, audit IDs **41 and42**. Each matches a unique completed cron602 run by exact backend PID and contained time interval; the phase sum plus telemetry admission agrees with the recorded total. The separate monitor-tick rows have no backend identity and are temporal candidates only. Evidence: `review/recovery-v73/live_phase_samples_first_v73.json` and `review/recovery-v73/live_phase_samples_final_v73.json`, final SHA256 **21a831c670eed522efe527f115c43f0976b3c9315a91f50e8ac53c4df9376f05**.

| Measured phase or interval | Audit41,15:42 / PID4599 / cron4068765 | Audit42,15:44 / PID4645 / cron4068767 |
| --- | ---: | ---: |
| Entire completed cron call | 9,796.815ms | 2,741.006ms |
| Measured maintenance total | 9,778.570ms | 2,725.346ms |
| Gate admission | 0.172ms | 0.159ms |
| Telemetry admission | 3.407ms | 4.071ms |
| Shared records | 5,320.806ms | 6.202ms |
| Contract processing | 2,157.210ms | 2,355.536ms |
| Breadth | 1,124.056ms | 143.938ms |
| Minute accounting | 1,097.945ms | 19.098ms |
| Nonminute | 17.029ms | 153.285ms |
| S02 | 36.816ms | 13.991ms |
| Readback loop | 8.897ms | 23.916ms |
| Identity refresh | 9.031ms | 2.519ms |
| Identity discovery | 1.594ms | 1.004ms |
| Finalizer loop | 1.607ms | 1.627ms |
| Entire cron minus measured total | 18.245ms | 15.660ms |

Audit41 was recorded **15:42:09.813373** inside cron15:42:00.025984–15:42:09.822799. Audit42 was recorded **15:44:02.762337** inside cron15:44:00.029452–15:44:02.770458. Shared processing dominates the first call and varies sharply in the second; contract processing remains about2.16–2.36 seconds. These are actual global-maintenance timings, not exclusive per-run work or a diagnosis of every internal read/write. The existing8s/2s function settings are unchanged; the measured9.78-second elapsed call must not be presented as evidence of a hard eight-second whole-call deadline. The cron-minus-total interval includes pre-entry, telemetry append, remaining monitor and commit costs; it is not an isolated component measurement.

A live worker `backfill_reserve` error at **15:42:03.07360425** correlates with SQL55P03 at **15:42:03.054**, authenticated dispatcher line39, waiterPID3929. Its preceding wait log identifies holderPID**4599**, exactly the measured cron602 backend. This proves continued gate contention during the slow sample; other waiters and health failures must not all be counted as worker failures. Evidence: `review/recovery-v73/first_phase_live_failure_correlation_v73.json`. No retry-policy change has been applied, and the successful diagnostic transaction does not turn the failed reservation into a committed write.

### Exact restoration and durable audit are complete

The exact restore SQL was applied **once**, migration history **20261030154455**. Independent **15:45:10.404232** readback confirmed restored definition **6c880114a645c8a9167d5260c4aeabf58a10617c4244cf0340be1d6cf4bf0ce7**, unchanged OID16041463, full function metadata, audit permissions, both task-index fingerprints, all13 unchanged function pins and remaining schema catalogs. The history read contains one install bodyb7bf and one restore body9a118, not repeated operations. A separate **15:45:11.893213** read confirmed the two immutable samples41/42 remain. No audit/source/count record or run status was reset. Evidence: `evidence/replacement-maintenance-phase-exact-restoration-v73.json`, SHA256 **e0b9ef2eb07f02d205329f55ffe1cec592bb886b58d57861beb6bb90f49fe6d4**.

Audit**43**, action `MAINTENANCE_DIAGNOSTIC_RESTORED`, at **15:46:31.666108**, records `RESTORED_EXACT_BASELINE_TWO_OBSERVATIONS_RETAINED`; independent **15:46:48.130167** readback found one matching audit. It binds exact restored6c880, sample IDs41/42, same controller, unchanged approval and `reinstall_allowed=false`. Evidence: `evidence/replacement-maintenance-phase-restoration-audit-v73.json`, SHA256 **9d28782d2fa234d18680972c00e2f3c54ac7b3d8ddfb4677fabc25051a70a537**. The15:45 installation/collection window is closed. The16:15 owner lease supports ongoing authorized work; it does not reopen that window. Cleanup is complete and must not be replayed. Restoring the baseline is not a performance repair.

### Historical receipt lookup completed; focused read diagnosis is next

Fresh seven-function definitions and metadata were retained after restoration at **15:45:58.374083** in `review/recovery-v73/live_shared_nested_definitions_after_restore_v73.json`; shared maintain5da488, project78ceb and the existing refreshb18a remain unchanged. The bounded read-only historical lookup was executed once at **15:50:57**, using the exact observed cron windows. The slow15:42 window has three **temporal candidate** shared-page receipts: Alpaca news50 records/384,857 bytes, actions6 records/1,459 bytes, and option contracts1,000 records/711,481 bytes. All stored source/readback hashes and counts agree; there was no bounded-result overflow. The15:44 window has zero matching receipts, which does not imply that no shared work occurred. A temporal match does not identify the backend that projected a page.

The retained1,000-contract candidate is task `backfill-plan-e0b79e51a28872e6abbee0d1f23c340ab77857acfa36dc3fbd85dba162329bec`, page0, bodySHA256 **9adb2b2051d81b7906efd0776a2ff759912a5eda0c216a605098515b0ec1a720**. Evidence: `review/recovery-v73/shared_historical_page_receipts_readonly_v73.sql` and `review/recovery-v73/live_shared_historical_page_receipts_v73.json`. The next diagnosis is a narrowly bounded, source-pinned, read-only profile of this archived candidate's parsing, metadata, summary and refresh inputs, with explicit after-state and cache/role limitations. No mutating shared helper replay, provider call or mutation has been authorized by that lookup, and its current cursor or materialized after-state must not be mislabeled as the sampled input state.


## Retained installed work and the earlier v72 causal evidence

The following time-stamped evidence remains unchanged history. Its earlier progress cutoffs do not replace the latest accounting above, and its completed repairs are not retry candidates. The completed v73 observation/restoration and final accounting above supersede its older continuation instructions.

### Installed work remains installed

The approved connector-compatible **managed Massive relay v3** was installed once at **12:17:26.804513**, audit **23**, under the actual **12:14** action-time approval `Sentinel_17a454f266748191bfca91e4c57d99b0` and within its **12:29** installation gate. Existing Edge function `population-top3000-news-v1` is version **2**. Approved scope SHA-256 is `a40f86ad49918644c5443586644b66ca9748ede1a91ffb8a09cdca0b522963d5`; SQL is `fe0f948824771dfa673548402e5d80a076d71f0211cf24091bb11e7ef0b6b013`. The expired v2 approval and pre-DDL failure remain retained history, not authority to replay. Exact wrapper/body/history, authentication, expiry, scope, fence and integrity checks remain intact. The managed Massive key remains server-side; no new credentials, subscription or PostgreSQL configuration is needed for this installed route. Evidence: `evidence/replacement-managed-relay-approval-installation-receipt-v3.json` and `evidence/replacement-managed-relay-production-security-proof-v3.json`.

The existing worker service **`srv-dbh9fko473hc739an8m0`**, deployment **`dep-dbi8ud942hec73cpm7qg`**, became LIVE at **12:36:45.668499** on **`3ee4db2a79c081ffb65ef0d7ec2a04228d69fb1d`**, advertises all **18 supported kinds**, and has automatic source deployment disabled. Its worker file SHA-256 is `b682b2425fd226296cdc141ff5936a49a7cac336fe859a02ebbd7faa4adf49c2`. The current selected changes are SQL/tests/evidence only and need no worker redeployment. Preserve the successful 3ee4 gates and earlier d321 collection failures. Evidence: `evidence/replacement-approved-relay-worker-deployment-v71.json` and `evidence/replacement-3ee4-release-gates-v71.json`.

The **claim capability predicate repair** was installed once at **13:13:00**, audit **27**, SQL SHA-256 `25427b992aebe5c81ae6c4b9e4cb44b560c8201b044476ea1ea937a933fed10c`. Readback at **13:13:22.722702** confirmed the exact private dispatcher, unchanged OID/metadata, authenticated dispatcher, status branch and one matching migration row. Published source **`b434f4575f5d6656b176b006857a655e4bf703c9`** passed both ingestion gates (**636 tests each, zero skips**) and both release gates (**709 passed / 317 skipped / one warning**). No worker, Edge, grant, credential, trust, scope, retry or runtime-timeout change accompanied it. Evidence: `evidence/replacement-claim-capability-filter-live-installation-v71.json` and `evidence/replacement-claim-capability-filter-release-gates-v71.json`.

At the **14:27:55 preinstallation** source read, private dispatcher was **`28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44`**, authenticated dispatcher **`a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520`**, maintenance **`cd10046d9c9aa15e8bc66724d1258d95151364ffeee9070d761c4f7d930b5859`**, monitor **`875c017ecf73df15163d15d3f9129b4507235dc893ccb4233d0a435154389057`**, and recheck **`0ccd4018d16e3ed3932176d2886fe78c2c1b442d70473d71e137d86e7b6dfb37`**. The two task indexes were absent then and in the **14:33:51** exact inventory; all 15 prior indexes were valid and their new migration histories were absent. These are retained preinstallation states, superseded by the separate successful readbacks below. Do not replay installed relay/claim work or old v70 maintenance after an uncertain response; reconcile exact source/catalog/history first. Evidence: `review/recovery-v72/preinstall_exact_index_history_inventory_v72.json`.

### Exact transaction-race page and preventive correction verified

The already committed Massive N01 task **`backfill-plan-28241a0a18d98d6b64c6a8e4a14027c1fe08a945048b089a02522b9cb52f42e2`**, page **0**, contains **100 records**, **246,966 bytes**, SHA-256 **`255ec70d01487893dfeeaaccf5dc9638adc325ad71c0fc13986fa7187b600a9b`**, committed at **14:00:00.061968** under generation/fence **1**. Original audit **30**, **14:00:04.16716**, records AI005: `Independent readback requires a subsequent transaction`. The verifier correctly rejected a page committed after the maintenance transaction started; the old selector then retained a permanent failure exclusion.

Root performed the separately guarded exact-page reconciliation once. The unchanged verifier produced the independent readback at **14:14:56.525507**, and audit **31** at **14:14:56.91516** links the original failure **30**, which remains present. Fresh readback at **14:16:14.826418** confirmed **100 expected / 100 actual**, matching hashes, exactly one original failure and one reconciliation marker. No source page, task status, counters, attempts or original audit were reset. This verifies already committed records; it is not another 100-record acquisition. Do not repeat this resolved reconciliation blindly. Evidence: `review/recovery-v72/readback_transaction_race_actual_reason_1410.json`, `exact_readback_transaction_reconciliation_result_v72.json`, and `exact_readback_transaction_reconciliation_committed_v72.json`.

The preventive correction adds exactly **`AND pg.committed_at<transaction_timestamp()`** to the missing-readback selector. It leaves the real verifier's `>=transaction_timestamp()` guard, other failure exclusions, helper order, limits, gate, exceptions, return and function metadata unchanged. Two actual local connections reproduce the old failure after a real advisory wait; the candidate defers the page without a failure marker and verifies all 100 records in the next transaction. Equality and newer timestamps, the 1–8 page bound, retained failure exclusions, owner/source guards and atomic rollback are tested. It is now **installed once and independently read back at 14:40:58.490017**, with maintenance source **6c880…**. This is separate from audit 31's earlier reconciliation and does not erase any old failure marker.

### What the maintenance evidence does and does not establish

Exact retained PID/time correlations identify existing cron **602**, `monitor_tick_v1`, as the holder during the **13:16** and **13:26** worker failures at authenticated `rpc_dispatch` line **39**, the existing global gate `pg_advisory_xact_lock(706314020261028)`. The post-lock credential recheck remains unchanged. Evidence: `review/recovery-v71/live_monitor_second_holder_correlation_1326.json` and `review/recovery-v71/live_ingestion_cron_run_pid_proof_1331.json`. These correlations identify the holder for those earlier failures, not each helper's cost or the holder for every later error. The old private-candidate timeout and unrelated 35-byte health failures remain distinct; no CTX06 attribution or probe is established.

The bounded read-only/repeatable-read **13:41** profile executed ten SELECT components in about **733 ms**. Breadth selection used **445.102 ms**, minute-account **181.387 ms**, both returning zero candidates; repeated rejected task-primary-key probes demonstrate avoidable selection work. The selected partial hash indexes address that work and preserve the original selector SQL. Local scale, visibility, positive-result, collision-recheck, preservation and bounded-forward tests are evidence about selector results/plans and index behavior. They do **not** measure cached cron plans, complete helper bodies, the monitor remainder, exclusive gate-holding duration, or sustained worker recovery. The rejected btree/fixture attempts and earlier receipts remain retained. The timing instrumentation contingency is **not selected**.

Fresh preinstallation observation remains adverse: the bounded Render query over **14:06–14:28** found `RpcPersistenceError` / `HTTP_ERROR` for `backfill_claim` at **14:14:03.175676642** and `backfill_commit` at **14:20:04.014779768**. The safe database context contains matching-time **55P03** at outer dispatcher line **39**; those particular safe rows have no holder field, so they do not independently establish the holder for each new failure. There was no manual restart and no blind commit retry. Evidence: `review/recovery-v72/preinstall_runtime_failures_1429.json` and `review/recovery-v72/preinstall_safe_rpc_errors_1430.json`.

| Cron 602 start UTC | Whole cron elapsed seconds | Recorded outcome |
| --- | ---: | --- |
| 14:10 | 6.132759 | succeeded |
| 14:14 | 3.226782 | succeeded |
| 14:16 | 5.918673 | succeeded |
| 14:20 | 6.299384 | succeeded |
| 14:22 | 15.070636 | succeeded |
| 14:24 | 1.811898 | succeeded |
| 14:26 | 2.022736 | succeeded |

These whole-cron times include initial admission wait and remaining monitor work. A succeeded cron can overlap a worker gate timeout. The first time-only cron-history query hit the unchanged **8-second** read bound; one corrected query using the known lower run ID **4068620** returned **24 rows**. Retain both attempts. **No timeout setting was increased.** These observations precede the installations and cannot be described as their outcome.

### All three v72 forwards installed once, in the reviewed order

| Order | Exact active SQL path | SHA-256 | Independent readback UTC |
| --- | --- | --- | --- |
| 1 | `sql/astra_backfill_breadth_pending_hash_index_v2.sql` | `8ff7824557d19d6981e036acc9228d148b460de50c38ec33017b7f628037fad9` | 14:40:13.523470 — installed and verified |
| 2 | `sql/astra_backfill_minute_pending_hash_index_v2.sql` | `1355b571ffd60602bee67e525dc687535b31e5c7c69ea3ac058551fc0c591203` | 14:40:42.164060 — installed and verified |
| 3 | `sql/astra_backfill_readback_transaction_race_v2.sql` | `f729d5be47cb9d09d8f6db1423fcab1364592b376878bfeb782218d078a1195b` | 14:40:58.490017 — installed and verified |

Root applied **breadth → minute → race**, exactly once per forward, with no uncertain result. Both indexes were installed and reconciled while maintenance still matched **cd100…**; the race forward then changed only its selector predicate to **`6c880114a645c8a9167d5260c4aeabf58a10617c4244cf0340be1d6cf4bf0ce7`**. Exact migration versions are **20261030144006**, **20261030144035**, and **20261030144057**, each with one matching reviewed SQL body. Breadth index OID is **16638529**, minute OID **16638569**; both are valid, ready, live, owned by the existing table owner, with no ACL. All 15 old indexes, table owner/ACL/RLS, all function metadata including the maintenance OID, authenticated/private dispatch, verifier and monitor were preserved. No worker redeployment occurred. Evidence: `review/recovery-v72/breadth_hash_index_installation_readback_v72.json`, `minute_hash_index_installation_readback_v72.json`, and `readback_transaction_race_installation_readback_v72.json`; consolidated `evidence/replacement-maintenance-combined-live-installation-v72.json`. Audit **35**, **14:42:49.389602**, records the installation in `evidence/replacement-maintenance-installation-audit-v72.json`.

Each installation used the existing gate and exact owner/cohort/fence/lease, **8-second statement / 3-second lock installation bounds**, source/catalog/metadata checks and transactional rollback. Runtime timeout policy, gates, credentials and schedules are unchanged. The ordinary builds temporarily lock the task table and add ongoing index maintenance for qualifying task inserts; they are not zero-cost operations. Each live index occupies **20,987,904 bytes**, a combined **41,975,808 bytes** (about **40 MiB**), matching the reviewed grown-pair scale. The project was `ACTIVE_HEALTHY` at **14:31:04**, with only retained scoped INFO advisor findings; existing connectors exposed no disk-headroom metric. The **646,994,263,187-byte** database size observed at **14:04** is not a free-capacity measurement. That uncertainty remains documented; no plan change, new storage route or owner action was required or authorized. Evidence: `review/recovery-v72/preinstall_health_advisors_v72.json` and the index qualification/install receipts. Do not rerun installed forwards, weaken their pins, or treat completed installation as worker recovery.

The final additive packet was published at activation commit **`d06c13f30a0bed8da6366f124101b59d21a450fa`**, tree **`3dc2c6d5541d1e911ab12192cea3d10de7eddfef`**, with **66 additive files** and every existing **`536bb850cf5c5653b4865e63db3f20f50a6769a1`** blob preserved. Frozen publication manifest: `evidence/replacement-maintenance-combined-publication-manifest-v72.json`, SHA-256 **`7e0c1bee91271dd58cdce629d19b4f297c35821e3706813a01682bdb6b040312`**. This activation-source publication is distinct from the v71 continuity checkpoint. Publication/audit 34 evidence is retained in `evidence/replacement-maintenance-repair-publication-v72.json`.

All four required **d06** gates passed on their first attempts. The PR merge checkout **ecd55be1ad8de7929d1e420fb3476b27b6fa236f** has the exact published **3dc2c6…** tree. Both ingestion gates executed the nine active index cases and eight active readback cases, with **653 tests and zero skips/errors/failures**, on actual PostgreSQL **17.11**. Both general-release jobs reported **710 passed / 333 skipped / one warning**; the separate zero-skip ingestion jobs supply the database proof.

| Gate | Run ID | Actual result |
| --- | ---: | --- |
| Ingestion PR | 41072428344 | 653 tests, zero skips, 340.219 s |
| Ingestion push | 41072418435 | 653 tests, zero skips, 348.618 s |
| General release PR | 41072428347 | 710 passed, 333 skipped, one warning, 7.06 s |
| General release push | 41072418656 | 710 passed, 333 skipped, one warning, 10.97 s |

Evidence: `evidence/replacement-maintenance-combined-release-gates-v72.json`, SHA-256 **`9ac9811ea29dbbc2b3c93e4d45e51d9bb5d8a46910e556a356ef894c723aeb71`**. The PostgreSQL 17 runs qualify actual-forward compatibility on that major version; they do not prove production performance or sustained recovery. The active race module SHA-256 remains **04312d34e94331fb79981b7b0032560a3128a84aab01d1a32c9efbb53021ae83**. The retained local eight-case receipt is **e09b8fa26a9c062a88ed401bc8ac69fbc7ee0a2bf21acf7faa56fea74d1ef855**. The separate four-case admission check preserves general-release explicit skips while making a missing database an error in the dedicated ingestion gate; no workflow was changed.

Retain `evidence/replacement-maintenance-task-hash-index-qualification-v72.json`, `evidence/replacement-maintenance-task-hash-index-independent-review-v72.json`, `evidence/replacement-readback-transaction-race-independent-review-v72.json`, and every initial/corrected qualification receipt. Local development used PostgreSQL **16.15**; actual CI subsequently executed PostgreSQL **17.11**, and production **17.6** installation was separately read back. Those distinct proofs must not be collapsed into a production-throughput claim.

### Completed postinstallation selector profile

Root executed the independently reviewed **59ab433babf8fcc30b9f09b9c4aafb9747685f852a9961c6e0c7c913be39e6e5** probe once, **14:41:35.342815 → 14:41:35.442793 UTC**. The exact two original SELECTs completed under explicit read-only/repeatable-read **8-second / 3-second** bounds, verified final maintenance/source/index pins, and returned the named bounded P0001 result. No maintenance helper, provider, verifier or advisory gate was invoked. Both plans naturally selected their intended partial hash index; no planner setting was forced.

| Selector | Execution ms | Candidate rows | Task-node loops | Task-node hit blocks | Task-node physical reads |
| --- | ---: | ---: | ---: | ---: | ---: |
| Breadth | 20.380 | 0 | 4,821 | 4,822 | 0 |
| Minute account | 39.745 | 0 | 4,752 | 4,754 | 0 |

The zero physical-read values apply to the task-index nodes, not a claim about every relation in each query. These are current cache/state-dependent direct read plans. Candidate populations and cache state differ from the earlier profile, so no controlled speedup ratio, original cached cron-plan latency, complete helper duration or gate-hold duration follows. Evidence: `review/recovery-v72/live_postinstall_selector_profile_v72.json`, SHA-256 **de0a587e60e29f748114e89ef61ce31625688876d1851dd4734862fde68f462c**. Preserve the one completed profile; do not repeat it merely to restate a resolved observation.

The **initial** postinstallation run read at **14:42:50.454026** contains **5,308 pages / 642,277 physical records or pointers / 2,771 reservations / 527,043,172 bytes / 5,308 readbacks**, planner **2,285**, planning **false**. The latest page is **14:40:05.812895**, which precedes the final repair readback at **14:40:58.490017**: there were **zero new pages, zero distinct committing tasks and zero new readbacks after the final repair** at that first check. This does not establish resumed acquisition.

Ordinary cron **602** at **14:42** succeeded in **1.102713 seconds**. The **14:40** cron took **2.033068 seconds** before the installations and is not a post-repair sample; **14:38** took **7.116255 seconds**. The first bounded **14:38–14:43** worker query found one `backfill_reuse_commit` / `HTTP_ERROR` at **14:40:09.546334932**, overlapping the breadth build; timing alone does not establish its exact cause. It found no post-final-repair worker errors through **14:43**, with `has_more=false`. One ordinary cron and a short error-free interval with no new commits do not prove recovery. No manual restart, deployment or blind replay was performed. Evidence: `review/recovery-v72/initial_postinstall_runtime_observation_v72.json`.

### Automatic work resumed; residual monitor gate contention is proven

The later **14:46:31.629652** read supersedes the initial zero-progress observation: **15 new committed pages / 1,887 physical records or pointers / 15 distinct tasks** appeared after the final repair, from **14:45:20.376251** through **14:45:58.440381**. All **15** have independent readbacks with matching hashes and counts. No manual restart, deployment or blind replay was used; worker capability evidence at **14:45:57.350763** still reports source **3ee4db2a79c081ffb65ef0d7ec2a04228d69fb1d** and **18** supported kinds. This establishes actual automatic resumption of committed work, with the following bounded population:

| Family | Provider / path | New pages | Physical records / pointers | Matching readbacks |
| --- | --- | ---: | ---: | ---: |
| CTX02 | Alpaca | 1 | 888 | 1 |
| D01 | DERIVED | 2 | 2 | 2 |
| D02 | Alpaca | 2 | 580 | 2 |
| D03 | DERIVED | 1 | 22 | 1 |
| D04 | DERIVED | 1 | 19 | 1 |
| D05 | DERIVED | 1 | 22 | 1 |
| N01 | Massive | 1 | 100 | 1 |
| N02 | Massive | 1 | 0 | 1 |
| N03 | Massive | 1 | 0 | 1 |
| P01 | REUSE | 1 | 1 | 1 |
| REF01 | Alpaca | 1 | 1 | 1 |
| S01 | Massive | 1 | 230 | 1 |
| S02 | Massive | 1 | 22 | 1 |
| **Total: 13 families** | | **15** | **1,887** | **15** |

This table reports committed page evidence across **13 families**, including zero-record pages and derived/reuse paths. It establishes no completed family, member, endpoint enumeration or target-window coverage. The N01 page here is a new post-repair commit; audit 31's earlier reconciliation of the 14:00 page remains separate and is not counted as a new acquisition.

Ordinary cron **602** continued without a schedule change:

| Start UTC | Run ID | Cron PID | Whole cron elapsed seconds | Outcome |
| --- | ---: | ---: | ---: | --- |
| 14:42:00.023088 | 4068674 | 1252376 | 1.102713 | succeeded |
| 14:44:00.023163 | 4068676 | 1252402 | 2.583934 | succeeded |
| 14:46:00.035583 | 4068678 | 1252500 | 7.989556 | succeeded |

At **14:46:03.942414189**, the worker reported a new `backfill_claim` / `RpcPersistenceError` / `HTTP_ERROR`. The safe database evidence records **55P03** at **14:46:03.925000**, authenticated `rpc_dispatch(text,jsonb)` line **39**, for waiter PID **1252046**. Its lock-wait row identifies holder PID **1252500**, exactly matching cron **602**, run **4068678**, active from **14:46:00.035583** to **14:46:08.025139**. This is fresh, exact holder/time evidence of residual contention at the unchanged outer advisory gate. The bounded worker error window is **14:46–14:48**, with `has_more=false`; it is not an unbounded error count.

**Sustained reliability recovery is not established: the residual monitor gate failure is proven despite genuine resumed commits.** The **7.989556-second** whole-cron duration includes admission wait and the monitor remainder and does not identify which helper or phase consumed the time. The successful hash-index selection plans and transaction-age correction remain valid installed results; they do not resolve that remaining cause. Preserve the exact receipt `review/recovery-v72/postrepair_progress_and_residual_failure_v72.json`, SHA-256 **a4b4ec8726f18275c0fd5cc31308fce5f761b6ea500cf80622f97f09b4314d62**. Its retained read-only query correction changed only an ambiguous `page_no` join to explicit task/page equality after a pre-execution **42702** rejection; neither attempt mutated data.

## Current executable continuation

1. Reconcile the same controller, existing enabled task, owner/fence1 and audit38 lease through16:15, current branch/head, unchanged3ee4 deployed worker, both installed task indexes and every uncertain write. Reuse completed v72 publication, v73 exact-head CI, installation, samples, restoration and audit43. Do not create another controller, task or worker or replay any installed repair.
2. Reconcile whether this reviewed v73 checkpoint and same-task refresh are already published. If complete, retain their exact publication/task readbacks and proceed without replay. Otherwise publish the reviewed concrete v73 packet against the reconciled3fddb tree, with exact v72 history copies and only the two canonical replacements, then update and independently read back only task6ae2a4c96bbc819182133e17e9b7f779 before extending diagnosis. Retain its unchanged schedule and controller.
3. Read back restored maintenance6c880 and unchanged outer authenticationa9a72/inner dispatcher28ae plus the fresh nested shared definitions. Keep the exact global advisory gate, post-lock live credential check, permissions and timeout budgets. The15:45 diagnostic window is closed and the two samples are retained; do not reinstall or silently extend it.
4. Continue the source-pinned, explicitly read-only diagnosis of the retained1,000-contract temporal candidate identified above. Preserve its task/page/body/readback identity, bounded result size and8s/3s diagnostic limits. Profile only pure read components after review; no mutating helper replay or provider calls. Any pure read function used must be expressly admitted and source-pinned by that reviewed diagnostic. Treat after-state, role, plan/cache and timestamp-only attribution limits explicitly. The historical receipt lookup is already complete and is not a retry candidate. Contract-phase cost remains a separate measured component requiring causal proof.
5. Separately review a narrow55P03 rollback-handling proposal against the exact worker transport and transaction semantics. A specific server-confirmed rolled-back failure is distinct from an uncertain transport outcome. No change is selected or active. Preserve fail-closed behavior for uncertain writes, full authentication, scope/fence/dependency/fairness/lease/reservation/count integrity and existing pacing; never generalize retryability from HTTP_ERROR alone.
6. Select a repair only after concrete causal evidence, meaningful local qualification, independent review, publication and required exact-head CI. Reconcile current state before any mutation and read back uncertain results before retry. No deployment, schema, grant, credential, subscription, timeout, schedule or security-policy change is selected by this checkpoint. Continue independent ingestion under existing permissions and record actual pages/readbacks, rather than process restarts or planner timestamps. Continue fixed-cohort planning, entitled acquisition/reuse, pagination/enumeration, historical identity/options/support, derivation and field-level accounting. Operational failures remain operational failures, not provider absence or legitimate completion gaps. Full mission completion and sustained reliability remain unproved.

## Original ten-section mission — exact unchanged bytes follow

# REPLACE THE CURRENT INGESTION MISSION — COMPLETE THE FIXED 3,000-EQUITY BACKFILL

This is my direct instruction to the existing ingestion application's controlling engineering agent. Execute the replacement mission below using my connected tools and deployed application. Implement, deploy, run, recover, verify and deliver it. Do not return another proposed plan for me to approve.

My priority is a finished database backfill that runs without routine intervention. Missing or unavailable provider data must be recorded honestly and must not stop other ingestion.

## 1. Authorisation and exact replacement scope

I explicitly approve all implementation, database migrations, job/scheduler changes, scoped code merges, deployments, restarts, recovery and validation reasonably required in the existing ingestion application and its supporting infrastructure for this mission. Use these approvals without repeatedly asking me to continue. Use existing accounts, credentials, infrastructure and paid provider plans. Optimise request, storage and compute use.

This instruction replaces the ingestion application's current mission priorities and incompatible scope/acceptance requirements. It does not authorise bypassing real platform access controls, fabricating data, deleting unrelated data, changing scanners or placing trades.

The new scope is:

- Target dates: 1 September 2025 through 31 July 2026 inclusive, using America/New_York market dates and the actual exchange calendar.
- Population: exactly the already selected and frozen practical 3,000-company/equity cohort from the August–September 2026 population work. Reuse those members; do not choose a new 3,000.
- Families: REF01, REF03, P01, P02, D01, D02, D03, D04, D05, N01, N02, N03, S01, S02, CTX02 and CTX06.
- External data sources: Alpaca Algo Trader Plus and Massive Stocks Starter only, using currently entitled endpoints. No add-ons, plan upgrades, new data subscriptions or silent substitutions from other sources.
- Derivations and audit records calculated from those inputs are included.
- Acquire and retain the minimum extra history needed for the agreed formulas, including sufficient earlier trading-session observations for 60-session returns and intraday/20-session rolling calculations. Mark these as support history outside the target period.
- F01–F06, CTX07 and CTX14 are outside this replacement mission. Preserve their existing data. D06 remains preservation-only.
- No artificial programme expiry. Individual requests, transactions, leases and attempts must remain bounded and automatically resumable.

The objective is to finish all achievable acquisition and calculation within this scope, with explicit accounting for genuine provider limitations. Perfect historical research certification is not a prerequisite for acquiring and preserving available data.

## 2. Stop and replace the current work safely

Immediately stop admitting new tasks for the superseded mission. Bring in-flight operations to a safe checkpoint; reconcile uncertain writes before retrying. Preserve source responses, completed records, counters, audit history and reusable code.

Mark superseded queued tasks as SUPERSEDED_BY_SCOPE_CHANGE. Do not label them completed, delete them, reopen completed jobs or rewrite old evidence.

Create a distinct, versioned replacement run in the existing application. Persist its scope, cohort reference, family list, date range and instruction revision. Drain or fence old writers so they cannot commit under the new scope. Reuse the existing queue, worker, supervisor and recovery mechanisms; do not create a competing controller.

Reconcile and retarget the existing scheduled implementation task, application supervisor and any continuation instructions so they cannot restore the old August–September/all-24-family mission. The previously recorded implementation task is 6ae2a4c96bbc819182133e17e9b7f779; verify the actual current registry before changing it. Preserve unrelated scheduled tasks.

Old canary deadlines and 10-request/1,000-record limits stay attached to their original jobs. They are not limits on this newly authorised full backfill. Establish a separate full-scope run with honest cumulative usage accounting. Do not reset old counters or stop after a pilot-sized allowance.

If a platform requires an account-owner action or refuses an operation, respect that boundary, identify the exact issue and continue all independent work. Do not invent approval evidence or bypass a restricted task through a disguised replacement.

## 3. Locate and freeze the existing cohort; reuse the estate

Use the current connected state, not an assumption that an earlier checkpoint remains current.

Known entry points to verify:
- Application repository: robert8p/Alpaca-Supabase-Populator.
- Existing ingestion branch/PR: feat/astra-ingestion-service / PR 93.
- Application checkpoint: docs/INGESTION_COMPLETION_STATE.md.
- Supabase project: oxzabweahkoimtevbbny.
- Existing Render ingestion services: astra-ingestion-web-v1 and astra-ingestion-worker-v1.
- Earlier population repository: robert8p/market-data-leading-indicator-lab.
- Earlier population schema: population_top3000_202608_202609_v1.
- Retained scope capture: top3000-augsep2026-retained-scope-v1.
- Practical membership policy: PRACTICAL_US_EQUITY_COHORT_20261024_V1.

Resolve the actual accepted membership artifact, version/hash and 3,000 distinct member IDs. Record its source in the new run. A policy document or an assertion of “3,000” is not the member list. Retrieve and reconcile the saved membership through available records before making scoped provider requests; do not ask me to reconstruct it.

Do not rerank market capitalisations, prove an exact global top-3,000 cutoff, substitute members to improve coverage, or reopen the selection exercise. Historical securities, share classes, aliases and listing episodes belong beneath the fixed company membership.

Label this as a RETROSPECTIVE_FIXED_COHORT because its selection occurred after the requested historical period. Preserve that limitation without delaying ingestion or claiming a contemporaneously selected, survivorship-free universe.

Inventory retained data with bounded, indexed reads. Reuse equivalent verified observations and calculations for these members/dates before refetching. Preserve original provenance and formula versions. Reuse immutable source data through a mapping/view when practical rather than duplicating hundreds of millions of rows.

Keep existing direct SEC, direct FINRA and other non-qualifying-source records intact, but outside this two-plan completion accounting. An old record's existence does not prove that its source and licence meet this mission.

## 4. Populate these 16 families

Implement every required adapter and calculation. Do not count a registered adapter, enabled flag, sample request or empty table as a populated family.

1. REF01 — Reference and historical identity.
   Use entitled Alpaca and Massive reference data to retain original provider identifiers, names, symbols, exchanges, eligible instrument types, dated aliases and supported listing episodes for the fixed cohort. Record mapping confidence and uncertainty. Do not force historical ticker-only matches.

2. REF03 — Provenance and data quality.
   Continuously retain request/page receipts, source timestamps, identifiers, lineage, counts, deduplication, validation results, gaps and remediation history. Produce this alongside ingestion, rather than making it a separate project that blocks collection.

3. P01 — Regular-session one-minute bars.
   Prefer entitled Alpaca SIP history. Retain raw OHLCV, trade count and provider VWAP where supplied, plus session and source identifiers. Use actual market dates and early closes. Preserve adjustment semantics.

4. P02 — Premarket and after-hours one-minute bars.
   Retain available extended-session OHLCV, trade count and VWAP with correct session labels. Reuse P01 source retrieval when a request contains both sessions; avoid duplicate requests.

5. D01 — Intraday technical features.
   Apply the existing agreed feature dictionary and formulas to usable inputs, including required return horizons, volatility, relative volume, moving averages, ranges and agreed liquidity primitives. Freeze the actual formula/version manifest. Compute incrementally by security/session.

6. D02 — Daily closing price and volume.
   Populate the agreed daily close, volume and dollar-volume fields from entitled daily bars or verified minute aggregation. Identify the actual source and regular-session/adjustment basis. Do not silently mix incompatible daily-volume definitions.

7. D03 — Daily returns.
   Calculate the agreed 1/5/20/60-session returns and raw/adjusted variants, with sufficient support history, identity continuity and supported split mechanics.

8. D04 — Daily volatility and volume measures.
   Calculate the agreed realised-volatility, relative-volume and volume-z-score measures from the frozen formulas and qualifying inputs.

9. D05 — Daily Amihud illiquidity.
   Calculate the agreed rolling return-to-dollar-volume measure, preserving its input and adjustment conventions.

10. N01 — News and article/security links.
    Exhaust the entitled provider archive and pagination for the selected companies and required dates. Prefer the existing Massive route; use Alpaca news only where entitled and equivalent. Preserve article IDs, publication/update times and deduplicated links. Include weekends and holidays. Scope completeness to the available provider archive.

11. N02 — Dividends and other supported corporate actions.
    Use entitled Massive and Alpaca action data. Preserve announcement/declaration, ex, record, payment and effective dates separately where available. Log unavailable action types or dates without stopping other event ingestion.

12. N03 — Executed splits and share-unit adjustments.
    Retain supported executed events, ratios, effective dates and identities from the permitted providers. Apply mechanical adjustments only where supported. Keep unresolved mechanics explicit.

13. S01 — Daily short-sale volume.
    Use the entitled Massive route. Preserve its reporting coverage and short/total-volume definitions. Do not substitute direct FINRA downloads, treat a shortable flag as volume, or claim total-market coverage beyond the provider's stated scope.

14. S02 — Twice-monthly short interest.
    Use the entitled Massive route. Preserve settlement dates, reporting/publication times, retrieval times and availability policy separately. Include in-window settlement observations even if published afterward, clearly marking that they were unavailable for earlier trading decisions.

15. CTX02 — Daily individual-security options prices and volume.
    Use entitled Alpaca OPRA historical data and contract reference capabilities. Enumerate relevant historical contracts for the selected underlyings, including expired/adjusted contracts where supported; do not substitute today's chain or a convenience sample. Acquire applicable daily prices/volume and retain contract/underlying identities. Record historical enumeration or field limitations. IV, Greeks and open-interest surfaces are not added to this family.

16. CTX06 — Cohort breadth.
    Derive the agreed breadth measures using an explicit, consistent company voting/representative-security rule. Prevent multiple share classes from unintentionally overweighting a company. Report eligible, observed, missing and excluded constituents per session; do not automatically divide by 3,000.

Shared archives and cohort-level datasets should be stored once and related to the cohort. They do not require 3,000 identical copies.

## 5. Acquire now; qualify and derive progressively

Persist each family's governing date/filter: market session for bars and derivations; publication time for news; settlement and publication separately for short interest; and the relevant announcement/effective/action dates for corporate events. Retain boundary-crossing events and necessary pre-window states that govern in-window observations. Trading calendars must not exclude weekend/holiday disclosures. Retrieve later-published reports when needed for retrospective records, preserving their actual availability and labelling out-of-window supporting records separately.

Begin eligible reference, stock-price, news, action, short-reporting and options acquisition in parallel as soon as the fixed membership and usable provider anchors permit it. Govern concurrency and pacing by the providers' actual limits.

Historical identity uncertainty, missing publication timestamps, incomplete research qualification or an unresolved universal denominator must not become an all-family admission gate.

Persist original provider records and request provenance even when attribution is uncertain. Quarantine only the affected company mapping or derived use. Resolve REF01 incrementally; recompute affected derivatives when mappings or source inputs improve.

Use the existing agreed feature formulas. If definitions are genuinely missing, recover them from retained code/contracts; persist a versioned, clearly named conventional definition only for an undefined field. Do not silently change an existing formula to inflate completeness.

Preserve raw and adjusted values distinctly. Do not double-adjust splits, forward-fill prices to hide gaps, invent bars/events, replace unknowns with zero, or invent publication/receipt times. Missing inputs produce NULL plus a reason.

A successful empty minute query is not automatically proof of no eligible trade. A security with evidenced pre-listing dates or no applicable options can be NOT_APPLICABLE. Unknown listing or contract history stays explicitly unknown.

## 6. Make provider gaps non-blocking and truthful

Record exceptions at the smallest practical company/security, family, field and date/period unit. Each exception needs its reason, provider/endpoint, request parameters or reference, response evidence, attempts, affected scope and downstream impact.

Distinguish at least:
- INGESTED: available source data committed.
- NO_DATA_RETURNED: a valid query completed and all pagination was exhausted, but the provider returned no observations.
- NOT_APPLICABLE: evidence establishes that the requested item does not apply.
- PROVIDER_LIMITATION: documented history, endpoint, field or entitlement limitations under the two permitted plans.
- IDENTITY_OR_QUALITY_UNRESOLVED: source data retained, with uncertain attribution or analytical use.
- RETRY_WAIT: a transient failure with a persisted retry time.
- OPERATIONAL_ERROR / BLOCKED_EXTERNAL: a genuine application, authentication, storage, access or infrastructure problem.

The last four must retain their actual meaning. A timeout, unfinished page, invalid credential, denied database write, unimplemented adapter or exhausted retry budget is not proof of provider absence. Diagnose it and repair it where authorised.

Test actual endpoint entitlements and historical reach. A 403 alone does not prove a subscription limitation; distinguish an account/configuration failure from a documented unavailable entitlement. Do not repeatedly call an endpoint already proven unavailable under the permitted plan.

For missing provider data, retain the exception, advance the queue and continue every unaffected task. Exhaust relevant permitted alternatives within Alpaca/Massive when they can genuinely supply the same required field. Do not purchase an add-on or widen sources.

After available source routes are exhausted, retain unresolved identity/quality limitations honestly. They may restrict research use without blocking the completion of raw acquisition.

## 7. Establish durable unattended execution

Use the deployed worker, persistent database queue and actual recovery process, independent of this conversation remaining open. Extend and deploy the existing application where necessary. A scheduled chat or health check alone is not the ingestion executor.

Persist run/task IDs, scope/version, family, member/security or shared scope, date window, cursor/page, state, attempts, next retry time, lease, source receipt, committed counts and last substantive progress.

Make writes idempotent. Atomically commit data/receipt/checkpoint state, or use a recoverable equivalent. A successful page must leave its next eligible page/task durably runnable or record a legitimate terminal outcome. Recover an uncertain commit by readback before repeating it.

Use bounded requests/transactions, adaptive batch sizes, provider-aware pacing, Retry-After and exponential backoff. Select and persist sensible finite attempt/recovery limits. Defer transient failures, isolate repeated failures and continue healthy partitions. Never sleep indefinitely, spin on the same failed call, or use an endless retry loop as “running”.

Recover expired claims and failed processes through the existing infrastructure. Preserve stop requests and reject stale writes. Account for credential expiry and refresh through already authorised mechanisms; never log secrets.

Monitor useful output: committed pages/records, completed units, advancing cursors and resolved exceptions. A heartbeat, passing CI or a live but idle worker is not useful ingestion progress.

Detect a stall against the expected batch runtime, diagnose its cause, repair feasible defects, and resume affected work automatically. If no task is runnable, the state must explain why, identify the next persisted retry/recovery action, or show reconciled terminal completion.

Keep one coherent implementation/recovery owner. If this chat execution ends, the existing persisted implementation controller must retain an executable next task while the deployed ingestion worker continues admitted work.

## 8. Verify practical correctness without recreating a global deadlock

Reuse valid existing tests and evidence for unchanged components. Perform meaningful checks for the changed scope, parsers, persistence, duplicate prevention, permissions and calculations. Deploy the exact tested revision through the existing authorised process.

Before claiming unattended operation, demonstrate on this new run:
- A real provider acquisition commits useful target-window data or verified reuse.
- The next eligible task starts automatically, without another user message.
- Checkpoint recovery works across a controlled worker restart without duplication or skipped work; reuse applicable prior recovery proof where the execution path is unchanged.
- Deferred retries have a working scheduled execution path.
- Source-to-database readback verifies the actual committed result.

Continue bulk work after this bounded proof. Do not stop at a canary or restart an open-ended certification programme. Keep necessary authentication, access control and write-integrity checks; separate them from research-quality and historical-universe qualifications that can be recorded per affected unit.

Run acquisition and independent readback/calculation checks concurrently where dependencies allow. A source gap must not fail unrelated partitions.

## 9. Define and deliver completion honestly

Track two separate results:
1. Work completion: every planned acquisition/enumeration/page/calculation unit has a truthful terminal disposition.
2. Data coverage: actual available/usable observations and fields, with provider gaps, non-applicability and unresolved quality shown separately.

Maintain the full fixed cohort and all 16 families in the accounting. Do not improve percentages by dropping members, difficult fields, dates or contract enumeration. Use actual expected populations where supported; keep unknown denominators unknown. Planned provider-query completion is not proof that every possible market observation exists.

Finish and publish automatically when:
- All 16 family workflows and their pagination/enumeration are processed.
- All obtainable entitled data is persisted and verified.
- Required derivations are calculated wherever their inputs allow, with explicit NULL/reason values elsewhere.
- Reusable data, new data, support history, gaps and quality limitations are reconciled.
- No silently abandoned queue item, retryable task, unimplemented adapter or repairable technical failure is hidden in a provider-gap category.
- Stable database tables/views and the final coverage report are available to downstream analysis.

Use COMPLETE only where applicable data coverage is established. Use COMPLETE_WITH_DOCUMENTED_GAPS when acquisition is finished but evidenced provider limitations or exhausted source/quality limitations remain; distinguish each class and do not call this “100% data present”.

Unresolved operational failures mean PARTIAL_OPERATIONAL_FAILURE or BLOCKED_EXTERNAL, with useful data published, exact remaining work and a real recovery/escalation path. They must never be disguised as successful completion.

Publish a per-family report containing: scope/unit, sources, dates, expected count where known, acquired/reused/usable counts, missing fields, no-data/N/A/provider-limit counts, quality limitations, unresolved technical failures, and queryable destination.

Also publish the exact cohort reference, support-history range, formula versions, gap register, request/storage/compute usage, latest substantive progress and final run/release identifier. Avoid adding overlapping store or shared-output counts together.

Stop acquisition and routine recovery only after COMPLETE or COMPLETE_WITH_DOCUMENTED_GAPS has verified final accounting and delivery. PARTIAL_OPERATIONAL_FAILURE, BLOCKED_EXTERNAL and exhausted transient retries are not successful completion: preserve their checkpoint and executable recovery path, continue independent work, and schedule bounded rechecks where automatic recovery is possible. Do not repeatedly retry a confirmed account-owner dependency without new evidence. Preserve all results and leave unrelated tasks untouched.

## 10. Start now and carry the work through

Your first execution must safely supersede old-scope admission, resolve the saved cohort, persist the replacement mission and begin or deploy the first feasible useful backfill batch. Perform necessary engineering in the same workflow; do not leave prose “next actions” without an assigned executable successor.

Report briefly after verified milestones: what actually committed, which families are progressing, what is retrying or limited, and what runs next automatically. Alert me only when an external account-owner action is genuinely unavoidable, while continuing independent work.

Do not end with “ready to proceed”, ask for approvals already granted here, claim completion from monitoring or test counts, or require me to keep prompting. Execute this authorised replacement mission through verified delivery, with missing provider data recorded rather than allowed to stop the ingestion.