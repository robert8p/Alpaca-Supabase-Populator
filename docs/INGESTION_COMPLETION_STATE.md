# ASTRA ingestion completion — durable coordination state

**Checkpoint version:** 14 — 29 October 2026, user-approval handoff complete.
**Programme:** isolated ASTRA ingestion reliability and authorised unattended bulk ingestion; historical coverage NOT_CERTIFIED.
**Current owner:** none. The document-only `user-approval-handoff-20261029T0527Z` claim is **RELEASED by this CAS publication**, before its 05:45 UTC expiry. It was an originating-conversation handoff, not an automation run or a competing runtime writer.
**Active operation/deadline:** none. Approval propagation is complete; no ingestion job, provider operation, deployment or source-code mutation was initiated. A future writer must reconcile actual state and acquire a new finite CAS guard.
**Campaign hard stop:** **2026-11-05T02:00:00Z**, or a newer explicit stop; unchanged.

## Latest user instruction and its precise effect

On 29 October 2026 Rob stated: **“Unattended bulk ingestion is approved.”**

- Unattended bulk-ingestion authorisation is **APPROVED**. Earlier statements that bulk ingestion is unapproved are superseded as authorisation statements, not erased from historical evidence.
- Execution is **NOT_STARTED**. Approval does not itself prove technical readiness, waive unresolved assurance tests, supply a population/date/dataset manifest, reset qualification counters, permit new expenditure, merge main, or restart a stopped legacy mission.
- The originating ingestion-app context and current isolated ledger identify only the completed AAPL/MSFT canary and AAPL fault qualification. No distinct bulk manifest has been admitted in this app. Do not invent a population or silently import the separately paused Top 3000 remediation scope. Resolve the intended bulk target, bind it to a stable manifest and idempotency keys, and establish finite request/record/deadline accounting within existing resources before submission. No repeat approval of unattended operation is required.
- Preserve the outstanding technical gates below. Evidence-limited is not PASS. Approval and readiness must be reported separately by all three tasks.

## Completed approval handoff and registry

The finite document-only guard was acquired by CAS against checkpoint blob `f65d8dd84b0d75528fd78896088c10f83ec9ff03` at reconciled branch head `91804b86cc19376d96f85c76818ce7fce2ff6ff2`. Approval checkpoint commit **`7033fcb731095e4773a38a9536d07e106769ab6a`**, blob `d5d62a5c5c0ee7710c74cc52f418a52a735c2c9a`, was read back; branch head remained that commit before this final CAS. No newer checkpoint was overwritten.

- Sole scheduled implementation writer: **`6ae2a4c96bbc819182133e17e9b7f779`** — Complete ingestion reliability. Its prompt was successfully updated and returned with the approval addendum at **2026-10-29T05:29:06.996473Z**. The entire preceding mission and historical addenda were retained, explicitly overridden only where the new user approval conflicts. Original schedule `DTSTART;TZID=Europe/London:20261029T020000` / `RRULE:FREQ=HOURLY;INTERVAL=2;COUNT=83`, flexible timing and enabled state remained unchanged. The task was not manually launched. Latest recorded run remains `602a52aa-f638-8320-832c-3b20edb1d6f4`, completed **04:29:24.537677 UTC**; no in-progress implementation run was returned by the pre-write lookups.
- Read-only independent verifier: **`6ae2a4df5e908191989eacee0a454141`**. Run `8d96e57c-0a70-832e-adcf-a85ce3771e4b` completed **05:03:14.120969 UTC**. Recorded result: bounded qualification passed, full programme acceptance open; independent comparison of all 78 crash-test records at 05:00:50 found zero discrepancies. Report identity **`libfile_0386ef92720c8191b7aead77f686b5cc`**, `ASTRA_Ingestion_Independent_Release_Review_20261029.md`. Its actual recorded result was read; this handoff does not claim a fresh full-file audit.
- Read-only readiness closeout: **`6ae2a4f6b4ac8191813eb27ed33c5e1b`**. Run `6c9f40ac-21b0-8327-b21b-e299cb4a6594` completed **05:07:18.813630 UTC**. Recorded verdict: bounded release passes; full programme acceptance remains open, with three assurance gaps. Report filename `ASTRA_Ingestion_Readiness_Closeout_20261029.md`; Library ID was not present in the returned result, so none is invented here.
- Neither reviewer schedule was changed. No unrelated automation was changed. Approval was also published in [PR93 comment 6488822185](https://github.com/robert8p/Alpaca-Supabase-Populator/pull/93#issuecomment-6488822185), linked to this current checkpoint. Prior reports saying unapproved are historical, not evidence that approval is still missing.
- Future writers must re-read actual runs, branch/checkpoint, ownership and unresolved effects, then acquire their own finite CAS guard; schedule staggering never establishes exclusivity.

## Exact source, deployments and preserved scope

Repository **`robert8p/Alpaca-Supabase-Populator`**; branch **`feat/astra-ingestion-service`**; [PR 93](https://github.com/robert8p/Alpaca-Supabase-Populator/pull/93) remains draft/unmerged. Application candidate is **`2c809b69e131f84e1778486e74c2f89a273f59f9`**. Checkpoint-only commits are not claimed to be deployed or newly regression-tested.

Render workspace `tea-d562ma4hg0os73aejnfg`; web `srv-dbh85vl9fdbs7387rucg`, worker `srv-dbh9fko473hc739an8m0`; Blueprint `exs-dbh5qcetlv9c73fqqen0`, custom path `render-ingestion.yaml`. Recorded exact deployments: worker `dep-dbhcihe7bikc73e8qad0` live 04:19:53 UTC and web `dep-dbhcilgm7kps73ehkv3g` live 04:20:22 UTC, both `2c809b69`. Latest worker deployment was freshly read back unchanged during this handoff. Auto-deploy and Blueprint Auto Sync must remain off; one configured instance each, existing **$14/month** compute; no additional paid resource authorised here.

Exact-candidate CI previously passed: ingestion PR `40816993392`, ingestion push `40816988828`, release PR `40816993388`, release push `40816988677`. These qualify that exact application candidate, not arbitrary later code. Temporary crash/gateway probes were removed; worker module blob `9cfefdde070538f2fa26f5ab562efc1c8c63a253` matches the original qualified worker.

Supabase project **`oxzabweahkoimtevbbny`**, schema **`astra_ingestion_v1`** only. Fresh read-only ledger snapshot **2026-10-29T05:25:34.424703Z** found exactly the two completed jobs below, no errors and **zero outstanding partition owners/claims**. No bulk job was queued or running.

1. Original immutable canary **`fab354f9-c8fc-4158-add9-4aff025594bf`**; key `astra-ingestion-v1-canary-20261028-1c3d9e8`; scope hash `893249da7775de9e75421b185280bfb837b3e37fc0b1926b1069544560e24cf1`. AAPL/MSFT, 2025-09-02T13:30:00Z–2025-09-02T20:00:00Z, 5Min/SIP/raw. Completed **156 records, 2 requests, 2 receipts**, verified. Original deadline **2026-10-29T01:24:10.838070Z**. Never reopen, resubmit, change its key/scope/deadline or treat completion as full coverage.
2. Completed fault qualification **`astra-postcommit-crash-20261029-0410-job`**; key `astra-postcommit-crash-20261029-0410`; scope hash `769d3b7d73e48778926e7467fc587e8c0e72e300d2fe5cc5dca7f3264d6f3d47`. AAPL only, same interval/5Min/SIP/raw. **78 records, 1 request, 1 receipt**, verified; original deadline **2026-10-29T04:23:30.240014Z**. Preserve this evidence and original counters.

## Gate ledger — authorisation is not assurance

- Original full retained-source comparison: **PASS**, all 156 records/two receipts and 11 negative/known-answer controls; do not repeat without evidence drift or concrete defect.
- Exact-candidate bounded release and complete retained qualification populations: **PASS within recorded scope**, including the independent review of the 78 crash-test rows; no certification of a bulk population.
- Independent restricted monitor: installed cron **602**, every two minutes; useful-progress observations, correct idle handling and independently detected stale-claim fail-closed incident proved. Incidents remain durable. A ChatGPT schedule is not the watchdog.
- Independent restricted verifier: installed cron **603**, every two minutes; all **3/3 partition attestations PASS**. NOLOGIN/NOBYPASSRLS restricted runtime role, read-only ingestion evidence and insert-only attestations. Administrative SQL review is separate evidence.
- Hosted post-atomic-commit worker-process death and automatic same-instance restart: **PASS**. Exit 87; successor verified without provider replay, doubled records or receipts. Synthetic CI covers separate expiry, stale-owner, cancellation and missing-ack cases.
- Physical host eviction: **UNPROVEN**; observed Render event had `evicted=false`.
- Strict non-overlapping replacement across distinct hosted instances: **UNPROVEN**; same-instance process restart is not cross-instance proof.
- Genuine authenticated-user JWT enforcement over external HTTPS: **UNPROVEN**. Valid-public-key anonymous HTTPS denial and SQL role denial passed, but are not a signed-user transport test.
- Full programme acceptance: **OPEN**; do not invent waivers or repeat already passing tests to suggest progress.
- Unattended bulk operation authorisation: **APPROVED BY USER**; executable bulk manifest and admission: **NOT_YET_DEFINED / NOT_STARTED**.
- Historical/full-universe coverage: **NOT_CERTIFIED**. No research, trading, held-identity release or changes to unrelated schemas.

## Cumulative limits, attempts and immutable provenance

Qualification campaign consumption remains **1/10 additional provider requests**, **78/1000 additional records**, **$0 incremental compute**; original canary usage is separate and unchanged. This approval handoff made **0** provider requests, **0** job submissions, **0** data/schema/deployment changes. No counter resets across schedules. New qualification jobs remain confined to original AAPL/MSFT interval, maximum **1800 seconds**, stable manifest-bound keys; prepare all machinery first. Prefer synthetic tests. Never retry uncertain submission with another key. A future bulk manifest needs its own explicit finite accounting; do not relabel qualification traffic to evade its limits.

At most two materially identical failures across runs. Preserve failed-run, first-probe defect and cron-history timeout evidence in the immutable history below; reconcile uncertain effects before retry. Never delete failed one-shot attestations or replay installed observer/verifier migrations. Do not compare SQL map digests with worker/audit array digests; require passed status plus exact scope/counts.

- Complete prior engineering checkpoint/history (ownership, failed run, CI repairs, admitted test manifests, incident/recovery details and failure history): [version 12 at 91804b86](https://github.com/robert8p/Alpaca-Supabase-Populator/blob/91804b86cc19376d96f85c76818ce7fce2ff6ff2/docs/INGESTION_COMPLETION_STATE.md). This immutable archive is part of this coordination record; its historical no-bulk statements are superseded only by the new user instruction.
- Exact approval-claim checkpoint: [version 13 at 7033fcb7](https://github.com/robert8p/Alpaca-Supabase-Populator/blob/7033fcb731095e4773a38a9536d07e106769ab6a/docs/INGESTION_COMPLETION_STATE.md). Its temporary ownership is released by version 14; do not treat its old lease as active after this release.
- Clean release report: **`libfile_34450bd336048191bd29df8786cd4d40`**, SHA256 `4c8545791743f2d3709ba1172ea20cc2b68115a9f51115aaef8d4cc21cce7300`; local supplied copy read during this handoff. Machine evidence `evidence/astra_ingestion_final_release_20261029.json` at `91804b86`.
- Original independent audit: **`libfile_dcfd71df63248191ba61293c51b84921`**, report SHA256 `51c2e09b28732183ec72b0e9e32f0fad4553b7acd3e8d94675e400c18859592e`; verifier SHA256 `957d8a388983a9d1a3927789b693a0ce063b6b27dad556bc9f2e36c8681534d8`; snapshot SHA256 `faf32dd90cdaed64fac7fa78c7d0e0709d53424d85d42c1b945959efb03b15ca`.
- Interim report **`libfile_4a96895339c08191aa7c2ee6ce296116`**, SHA256 `5c35a1a9cc401dd142b73b0b8ab6034b8a40aee7cf2a42b6086db77fd5cb6157`; earlier runtime report **`libfile_9b466ad815b48191ae49fd30233bd6c8`**, SHA256 `0e03620134a0e96d0d1bbacc227363ec46233cfbcacc34b60af0488f4dedaa4d`.

## Unchanged boundaries and next admissible action

Keep legacy loaders **`srv-d9p2vljncjis73evkocg`** and **`srv-d9p2vljncjis73evkoc0`** suspended; paused Top 3000 remediation and all unrelated schedules/services/schemas/identity/financial/data-quality/scientific holds remain untouched. No main merge, automatic deployment, cost increase, credential disclosure or bypass of platform authentication/approval.

Approval propagation is complete and the document-only claim is released. The existing implementation task is enabled with the updated prompt; this is evidence of saved scheduled instructions, **not** evidence of a new run or active bulk ingestion. The next implementation run must recognise approval, work on independently feasible assurance gaps, and resolve a manifest from actual authorised target evidence rather than guessing. Where a target decision is genuinely absent, ask only for that decision, not renewed permission for unattended execution. Once target and safe admission are established, advance the authorised isolated bulk work without routine reapproval. No repeated unchanged notifications or gratuitous code/deployment mutations. Disable only the implementation task after current-candidate final closeout accepts, campaign end or newer stop; preserve other task roles and schedules.
