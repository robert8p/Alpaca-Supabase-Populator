# v73 proposal: bounded observation of global maintenance costs

Status: **local proposal; no production activation by the producer.** Independent review, complete publication, exact-head qualification and root selection remain required. The observation window ends at **2026-10-30 15:45:00 UTC**. This document does not renew or move that deadline.

## Purpose and current evidence

The v72 changes reduced demonstrated selector work and prevented the readback transaction-age race, but did not remove every maintenance blocker. The retained 14:46 observation matches the worker's claim lock timeout to the existing cron602 monitor backend: holder1252500, run4068678, 14:46:00.035583–14:46:08.025139. That identifies the monitor transaction as the blocker. Its 7.989556-second elapsed time includes gate waiting and surrounding monitor work; it does not identify an expensive helper. Fifteen new committed pages and matching readbacks were independently verified in the same progress receipt. Both findings remain true.

Evidence: `review/recovery-v72/postrepair_progress_and_residual_failure_v72.json`, SHA256 `a4b4ec8726f18275c0fd5cc31308fce5f761b6ea500cf80622f97f09b4314d62`. No restart, counter reset, manual provider fetch or helper replay is proposed.

This proposal adds a maximum of four committed observations to the existing immutable audit relation, using the existing monitor invocation and existing privileges. It measures the unchanged **global** maintenance work. The fixed run is the audit attachment and authorization boundary; the helper selections themselves are not exclusive to that run.

## Exact source and scope

The base is published checkpoint `1f1f423e4dd1db87eff92e8687b2d9c49ba63c01`, tree `45c5b7d6410f4fba1d154d50debdb3b574c9e86d`. The installed maintenance definition is SHA256 `6c880114a645c8a9167d5260c4aeabf58a10617c4244cf0340be1d6cf4bf0ce7`; the proposed definition is `12e05b1fa5a6e59f1f626a33aaec4e30248d0cfc858917be171fd812b41c229d`. Removing only the marked `PHASE_OBSERVATION_V73` additions recovers the complete installed definition byte for byte.

The existing global advisory gate706314020261028, BUSY return, ten original helper/loop statements, helper arguments, readback transaction-age predicate, readback failure handling, finalizer selection and returned JSON remain unchanged. The function remains VOLATILE, SECURITY DEFINER with its existing owner, empty search path, 8-second statement setting and 2-second lock setting. The outer authentication function, its post-lock credential validation and 3-second lock budget remain untouched. Both v72 task indexes remain installed and unchanged.

The fixed attachment is run `fixed3000-20250901-20260731-v1-20261030`, owner `root-replacement-20261030T042603Z`, fence1, cohort SHA256 `2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec`. The probe ID is `maintenance-global-phase-observation-v73-20261030T1545Z`; the action is `MAINTENANCE_PHASE_OBSERVATION_V73`. It cannot be redirected by a request payload or runtime parameter.

## Admission and sample cap

Telemetry admission occurs only after the original global gate has been acquired. It requires READ COMMITTED, the fixed run and owner/fence/cohort, an eligible existing run status, an unexpired owner lease, the fixed 15:45 deadline and fewer than four matching committed audit rows. REPEATABLE READ and SERIALIZABLE continue the original maintenance work and skip only telemetry. No isolation setting is changed.

Before the optional audit append, the function obtains the ordinary audit INSERT relation-lock mode with NOWAIT, obtains the fixed run row's SHARE lock with NOWAIT, and repeats scope, time and count checks. It checks time and ownership again after the INSERT. If the optional INSERT itself crosses the deadline or lease boundary, a controlled ordinary exception rolls back only that diagnostic subtransaction. The pre-existing main work remains outside that exception block. These are append-boundary protections; the function cannot guarantee that its caller commits before the deadline.

The existing gate serializes cooperating maintenance calls. Within READ COMMITTED, the existing VOLATILE function obtains fresh snapshots for its queries. The two-connection tests begin both transactions before the waiting caller acquires the gate: after three existing observations, the first caller appends the fourth and commits; the waiting caller then sees four and adds none. A rollback variant proves that the waiting caller may use a rolled-back slot while the final committed total stays four. Repeated calls in one transaction also see their own inserts and stop at four.

The cap counts committed matching audit rows. Failed or rolled-back attempts can exceed four until the fixed window closes. Identity sequence values may have gaps after a rolled-back attempt; no sequence reset is permitted. After four observations, the function still performs bounded eligibility/count work until the deadline. After the deadline, it skips the telemetry queries. Exact restoration removes the additions altogether.

## What is measured

| Field or phase | Meaning |
|---|---|
| `gate_admission_ms` | Entry to successful acquisition of the original global gate |
| `telemetry_admission_ms` | The bounded owner/scope/cap checks immediately after the gate |
| `breadth_ms` | Original pending breadth projector |
| `minute_ms` | Original minute accounting helper |
| `identity_discover_ms` | Original identity discovery helper |
| `identity_refresh_ms` | Original identity refresh helper |
| `nonminute_ms` | Original nonminute projector |
| `s02_ms` | Original S02 maintenance helper |
| `shared_ms` | Original shared-record maintenance helper |
| `contract_ms` | Original contract maintenance helper |
| `readback_ms` | Complete original bounded readback loop, including its existing error branch |
| `finalize_ms` | Complete original global finalizer loop |
| `total_ms` | Function entry through finalizer completion, before audit construction/append |

The audit JSON contains only the fixed probe ID and scope label, backend PID and numeric durations under fixed phase names. It contains no source records, ticker lists, request payloads, SQL text, error bodies, headers, credentials or dynamic application strings. It labels its scope `GLOBAL_MAINTENANCE_BEFORE_TELEMETRY`. Negative rounded phase durations or reversed admission time omit the observation. Timings use the database wall clock and are approximate durations, not monotonic profiler measurements.

The measurement excludes audit construction/append, the rest of the calling monitor function, and outer commit. It includes the telemetry admission checks in `total_ms`, separately reported as `telemetry_admission_ms`. Missing observations do not establish that maintenance was fast or successful: the window, cap, isolation, lease, errors or caller rollback can all omit them.

## Exact security diff

No new table, role, grant, policy, index, credential, operation, endpoint, subscription, provider request, schedule or timeout setting is introduced. Only the maintenance function body is temporarily replaced; its OID, owner, ACL, SECURITY DEFINER status and configuration must remain exact. Existing source acquisition and ownership rules remain in force.

The retained 15:08:46 permission inventory proves that the function owner is a non-login, non-superuser, non-BYPASSRLS role. It does not own the audit table. The audit table has RLS enabled with existing permissive SELECT and INSERT policies for that role; the role has SELECT and INSERT, no UPDATE or DELETE, and sequence USAGE without sequence UPDATE. It already has run SELECT and UPDATE. Standard anon/authenticated/service_role identities lack audit and maintenance/monitor access. The immutable audit trigger prohibits update/delete/truncate and is unchanged.

PostgreSQL17 documents that INSERT permits the ROW EXCLUSIVE table-lock mode used here. The actual-role tests exercise it without broadening privileges. They also distinguish direct sequence access from the audit's GENERATED ALWAYS identity: direct `nextval` is denied when USAGE is removed in a disposable fixture, while automatic identity generation for an otherwise permitted INSERT remains possible. That corrected an initial false fixture assumption; no production grant was added to make the test pass.

## Observer risks and error behavior

The added checks, timestamps and audit INSERT consume real time. NOWAIT avoids waiting for the specified relation/row locks; it does not eliminate buffer, storage, sequence, foreign-key or commit latency. A successful main operation that previously fit its caller's deadline can exceed that deadline because of telemetry. The fixture demonstrates this risk by delaying only the audit INSERT: the baseline succeeds under a controlled 150ms caller budget, while the candidate propagates57014. This is a disclosed limitation, not a promise of zero perturbation.

Only ordinary errors inside the telemetry admission/append blocks are suppressed. No exception body is exported. `query_canceled` and `assert_failure` are explicitly rethrown. Every original helper error and the original readback exception policy remain intact. An ordinary telemetry constraint/RLS/INSERT denial rolls back only the diagnostic block and leaves real independent readback work committed. The delayed-INSERT test proves that both deadline and lease expiry discard the diagnostic row while preserving real readback; nontransactional identity gaps prove the INSERTs were actually reached.

Each observation also appears in the existing REF03 evidence view. Its evidence-row count increases; that is diagnostic evidence, not a newly acquired page, provider record, coverage result or readback. Acquisition counters and source rows are unchanged by the observation code.

## Installation, restoration and release requirements

Installation must remain ACTIVE-only and require exact current source, complete metadata/permissions/catalog, original auth and helper pins, existing v72 index definitions, fixed owner/fence/cohort/3,000 members and unexpired lease. Its transaction uses the existing global-gate-before-run-row order with an 8-second statement and 3-second lock bound. Unexpected source/catalog drift, expiry, failed qualification or uncertain application holds the operation for reconciliation; no blind retry is permitted.

Restoration is authorized cleanup to exact6c880. It requires the exact candidate source and the same owner, unexpired lease, fence, cohort, complete membership and other source/permission/catalog guards, but may run in any existing run status. It must not alter that status, reactivate work, delete audit evidence or reset source/counter records. The fixed observation deadline does not prevent cleanup; the ownership lease still applies. No automatic self-replacement or new scheduler is introduced.

The producer's active tests use controlled disposable future/past deadlines, so future CI remains meaningful after15:45. Static source tests remain pinned to the exact production deadline and definition. Qualification uses local PostgreSQL16.15, while current production is17.6; exact-head CI and subsequent production readback remain required. The first failed fixture and all corrected qualification attempts are retained distinctly. Independent review and the exact publication tree must bind the final SQL, tests, evidence and all fixture dependencies before root selection.

## Primary references

- [PostgreSQL17 function volatility and snapshot behavior](https://www.postgresql.org/docs/17/xfunc-volatility.html)
- [PostgreSQL17 transaction isolation](https://www.postgresql.org/docs/17/transaction-iso.html)
- [PostgreSQL17 LOCK privileges and NOWAIT](https://www.postgresql.org/docs/17/sql-lock.html)
- [PostgreSQL17 exception handling](https://www.postgresql.org/docs/17/plpgsql-control-structures.html)
- [PostgreSQL17 explicit locking](https://www.postgresql.org/docs/17/explicit-locking.html)

The live permission inventory and local actual-role tests are the direct evidence for this application's permissions. These references explain the underlying PostgreSQL behavior and do not substitute for application-specific qualification.
