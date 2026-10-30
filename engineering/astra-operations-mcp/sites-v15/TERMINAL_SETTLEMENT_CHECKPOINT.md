# ASTRA Operations v15 — original owner SHA and terminal-outcome settlement

**2026-10-30 · Implemented and source-tested; NOT live integrated.** Existing ingestion and EQ17 controlling chats retain exclusive application execution ownership. Dot alone owns publication to private Site `appgprj_6ae4dcec2034819197d448ca2eea21a3` and canonical plugin `plugin_asdk_app_sites_a5e127b6f02081918cde92d94b477c57`.

## Verified source correction
Two previously untested v14 readback defects were reproduced:
1. An **originally unpinned GitHub workflow** could receive `admitted_head_sha` only in the later readback and be marked complete, although the original owner reservation/lookup did not bind that SHA.
2. An immutable terminal `REJECTED` or `CONFIRMED` receipt could change its state between lookup/reservation and readback. A `PREPARED`, `DISPATCHING`, `UNKNOWN` or `ACCEPTED` operation could also be marked `REJECTED` without independent proof that the provider write never happened.

New dormant `controller-owner-port-v15.mjs` requires the SHA pin in the **original** owner receipt, blocks terminal-state contradiction, and holds uncertain-to-REJECTED transitions with `replay_permitted:false`. The same four owner-injected methods, historical `v10-json-v1` digest, permission/cost/release/stop/fence/lease controls, GitHub complete/success readback and Render secret/deploy holds remain unchanged. No new journal/executor/provider adapter/controller was introduced.

**Regression demonstration:** v15's ten new safety cases against archived v14: **4 passed / 6 failed**, confirming the old defects. Against corrected v15: **10/10 passed**. Full source-only suite: **189/189 passed** (179 historical v14 plus ten v15), Node 22.16.0. A fresh ZIP extraction independently reran all 189 tests and verified ZIP integrity/manifest file hashes. These synthetic checks do **not** prove real ingestion-owner locking, provider authentication, dispatch or causal settlement.

## Exact source and artifact pins
- Source GitHub blob SHA1 `01e83a01140b8c371452679f759f3a1fb3bea390`, SHA256 `1c39264f901a79609441f11b5b526acd7715a3eed931ac6eb6bee32cda86642e`.
- Test GitHub blob SHA1 `af12d8583c2cbb41ac7eea2012b88445bd08e976`, SHA256 `a3380b9a67b6767be1dfec60ffe27c3f290289a74a8e803a42afd8769b829317`.
- Documentation GitHub blob SHA1 `5b20c56c2bf3542cbf89635f2fc1d73f7ce4cf15`, SHA256 `8406b792e65167622c8696b69eb402191eb625805f46b0563c26eae5ec5c38d1`.
- All three are on existing branch `feat/astra-operations-sites-handoff-20261030`, immutable containing commit **`d16f006016d0e36abb8924e02a1855d6176d921c`**; blob SHA readback independently matched the exact archived bytes including the final newline.
- Full ZIP: Library `/ASTRA Operations/ASTRA_Operations_Terminal_Readback_Pin_Hardening_v15.zip`, ID `libfile_535c40ee9ab88191a54b85fe463b0d47`, **1,093,542 bytes**, SHA256 **`1664a1cefe5579b7fd22d515e07932d0071eaece88b7e002c50b8fdd951b37bd`**. Library rematerialization matched original bytes and SHA; ZIP CRC passed.
- Archived v14 ZIP is included **byte-identically**, SHA256 `1ec8ca48013211a20530ed3e24829efe6d74aa7122ab4a85d593bf759073ec5b`.
- Standalone archived source and tests also in Library under `/ASTRA Operations/ASTRA_Operations_Controller_Owner_Port_v15.mjs` and `...v15.test.mjs`.

## Current controlling handoff, without interruption
- Existing issue **[#94](https://github.com/robert8p/Alpaca-Supabase-Populator/issues/94)** open, already acknowledged by ingestion owner in backfill audit 96, deferred behind reliability work; do not request another acknowledgement.
- Correct immutable v11 contract is in [existing issue comment 6534994041](https://github.com/robert8p/Alpaca-Supabase-Populator/issues/94#issuecomment-6534994041), commit `db0efa4140ae6d59b4c8f36d0d0ebd39b5ff3cd0`, blob `622d820e97b62a99a1278223bdc677972be8bf3f`, SHA256 `58b61d0026d4dc9f7a53185d0d06bd5db216dc9b50e8d575cc96377e2e65c0cb`.
- Latest ingested branch `feat/astra-ingestion-service` observed HEAD `f5cd20baaac9e42b2074afc1d459b4968e8b3306`. Compare vs `08bea176e39174f8c39f62caebae79d5cb50cdcf`: one additional v78 planner SEAL/evidence commit, **not a verified atomic Render/GitHub owner port**. Its deferred queue `review/recovery-v78/plugin-handoff/deferred_issue94_queue_payload_v78.json` still contains a *pre-contract-fix* snapshot referencing stale branch `fb20e97`; do not rely on it for contract location. Use corrected immutable link in issue #94.
- Workflow still lacks `workflow_dispatch` on implementation branch and file was absent at inspected path on `main`. Only ingestion owner may decide workflow change and release.
- Current Basic ingestion identity is control-capable and forbidden to Sites. No GET-only identity or four real owner-native port operations evidenced.

## Provider/setup qualification (no credential/account calls)
- Official GitHub workflow dispatch requires Actions:Write and a trigger configured on the default branch; HTTP 200 and run ID/URL are **not workflow success**. Workflow-run GET uses Actions:Read, or public read where allowed: https://docs.github.com/en/rest/actions/workflows and https://docs.github.com/en/rest/actions/workflow-runs .
- Official Render service PATCH does not deploy; `autoDeployTrigger:'off'` replaces the deprecated `autoDeploy` parameter: https://api-docs.render.com/reference/update-service .
- Official Render environment-group linking inherits group env values and secret files and can return raw secrets: https://api-docs.render.com/reference/link-service-to-env-group . No owner-approved group/secret/deployment effect exists.
- Render scoped-key beta eligibility remains UNKNOWN: no supported account entitlement inspection exposed. No native Sites `sites_list_plugin_eligibility`. No provider credential or production call performed. GitHub installation and effective Actions:Write/Read, secure destination, TTL/revocation, operation/cost/secret effects remain unverified; no scoped action-time consent payload ready.

## Next executable action, existing owners
1. **Existing ingestion controller owner:** continue reliability work; only when its current release admission permits, review deferred issue #94, bind real owner port to its durable immutable change/physical resource locks, stop/fence/lease, PREPARED/DISPATCHING crash handling, terminal/unknown causal settlement including v15's original SHA requirement. Qualify 20-call concurrency and alternate keys/revisions **inside actual existing owner**. No second controller.
2. **ASTRA Operations implementation owner / existing hourly task:** read issue #94, owner HEAD and exact port source read-only; only when a real port exists, qualify v15 controls against owner-native results. Meanwhile perform independent factual provider/schema/account setup research; do not call providers or create credentials. Do not churn mocks and claim integration.
3. **Dot:** consolidate routine reporting, owns Site/plugin publication. Only request exact grant at action time when provider/account, effective permissions, target, secure destination, expiration/revocation, effects/cost, controller release and stop/fence are all independently verified.

No new Site/plugin/OAuth/host, journal/worker, production provider or app-controller mutation, workflow trigger, PR approval, payment, scanner or trading change. Existing worker `srv-dbh9fko473hc739an8m0` is not to be duplicated; no Render Free worker creation. Preserve N1 remote interrupted branch as-is and published native Site source `3d260fbe95d3600c1519e28d49af7be36c9f4712`.
