# ASTRA Operations v15 — terminal settlement and original pinned-SHA integrity

**Date:** 2026-10-30. **Implementation:** source-only client qualification, no provider adapters, tokens, production calls, controller mutation or Sites publication. This is **not live integration**. Existing ingestion owner remains sole application executor.

## Actual material defects reproduced in frozen v14
1. `projectReadback` compared the readback workflow head SHA to the original reservation **only if** `expected.admitted_head_sha` was present. An unpinned immutable admission could therefore acquire a newly supplied `admitted_head_sha` on a later readback and incorrectly report a successful workflow. A completion claim must be pinned to the original owner admission.
2. A prior terminal `REJECTED` owner row could become `CONFIRMED` at readback and be presented as `complete`; a prior `CONFIRMED` could become `REJECTED` and be presented as a rejection. This is conflicting immutable finality, not valid settlement.
3. A PREPARED/DISPATCHING/UNKNOWN/ACCEPTED operation could become `REJECTED` without negative causal proof and be presented as rejected, misleading consumers about possible side effects. No replay was permitted, but outcome classification was unsafe.

A ten-case **synthetic regression suite** against archived v14 failed 6 cases / passed 4, reproducing these problems. They are source-contract defects, **not observed production incidents**.

## Smallest correction
`controller-owner-port-v15.mjs` extends v14, without editing old source or changing port operations. The original workflow reservation/lookup must already contain a valid 40-character lowercase pinned SHA before readback may claim anything. The previously recorded terminal state must not change. Uncertain-to-REJECTED without owner-designed causal negative proof stays `held`, not `rejected`; all results prohibit replay. Historical v10-json-v1 digest, scope/cost/release/stop/fence/lease gates, Render secrets/deploy holds and no new controller policy unchanged.

Node v22.16.0: **189/189** total source-only tests (179 previous + 10 v15) passed. `node --check` passed. New source/test standalone Git blobs and SHA-256 recorded in manifest. The original v14 input ZIP was preserved **byte-identically**, SHA256 `1ec8ca48013211a20530ed3e24829efe6d74aa7122ab4a85d593bf759073ec5b`. New fresh-ZIP extraction test must also pass before release of this artifact.

## Read-only owner/status reconciliation
- Issue #94: OPEN with prior acknowledged/deferred handoff in ingestion audit 96; existing corrected contract issue comment 6534994041. No redundant acknowledgement requested.
- Ingestion branch observed HEAD `f5cd20baaac9e42b2074afc1d459b4968e8b3306` (one commit beyond v14-observed `08bea176e39174f8c39f62caebae79d5cb50cdcf`). The intervening v78 work modifies planner seal and evidence, **not** ASTRA cross-provider owner-port methods. No actual `lookupExact/admitExact/reserveAndDispatchUnderOwnerGuard/readbackExact` ingestion port verified.
- v78 durable queue payload `review/recovery-v78/plugin-handoff/deferred_issue94_queue_payload_v78.json` states `DEFERRED_BEHIND_BACKFILL_RELIABILITY`. Its retained issue snapshot predates the published corrected contract and references old `fb20e97` branch; use immutable contract in existing issue comment, not stale payload. Do not alter ingestion evidence or interrupt active reliability work.
- Current GitHub workflow still not dispatchable from default branch. No GitHub App Actions:Write grant or installation verified.

## Independently documented provider/setup constraints
- GitHub official workflow dispatch endpoint requires `workflow_dispatch` trigger and Actions:Write; its response HTTP 200 may provide run ID/URL but does not prove run completion. Workflow run GET may require Actions:Read; on public repos it can be read unauthenticated. Sources: https://docs.github.com/en/rest/actions/workflows ; https://docs.github.com/en/rest/actions/workflow-runs .
- Render `PATCH /v1/services/{id}` updates settings without deploying; `autoDeployTrigger:'off'` is the supported form. Source: https://api-docs.render.com/reference/update-service .
- Render `POST /v1/env-groups/{groupId}/services/{serviceId}` may return envVars.value and secretFiles.content and confers access to group secrets. Do not call without narrowly authorised secret/deploy effect; no raw response storage. Source: https://api-docs.render.com/reference/link-service-to-env-group .
- Render Scoped API Keys are private beta; effective scope also depends on original account rights. No supported account-beta eligibility inspection is available in exposed tools. UNKNOWN, not denied. Source: https://render.com/blog/scoped-api-keys-private-beta .
- Connected GitHub tool inventory contains installation listing actions, but this run did **not** invoke any account/installation/provider calls because credential/provider production calls are outside current authority; effective installation and Actions:Write remain unverified. Native Sites plugin eligibility inspection absent from exposed inventory. No action-time confirmation payload ready.

## Owner and next action
- **Ingestion controller:** keep work deferred after current reliability repair. When owner admission permits, map existing controller's durable immutability, logical/physical locks, stop/fence/lease, crash/UNKNOWN no-replay and causally proven negative outcomes. Only its own release path decides workflow_dispatch/default-branch and GET-only status identity.
- **ASTRA implementation owner (existing hourly):** inspect #94, ingestion HEAD/source and owner queue, qualify real port if implemented against immutable v11 contract plus v15 terminal/SHA rules; separately research provider public scope/schema as feasible. No repeated synthetic-work result as live integration.
- **Dot:** routine consolidated reporting; owns existing private Site/plugin and publication exclusively. Owner confirmation only for a real exact identity/scope/target/destination/expiry/revocation/cost/secret/deploy/release package. No credential grant now.

No new Site/plugin/OAuth/host/worker, durable journal, provider account or token, production write, GitHub workflow/PR, paid commitment, scanner or trading action. N1 interrupted branch write remains unmodified.