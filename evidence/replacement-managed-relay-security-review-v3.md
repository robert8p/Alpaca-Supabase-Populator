# Managed Massive relay v3 — connector-compatible security proposal

**Preparation only. No v3 production installation or deployment is authorized by this document.** The original v2 approval at 2026-10-30 09:53 UTC expired at 10:08 UTC without installation. That approval and its failed pre-DDL attempt remain evidence; neither its timestamp nor its scope is reused for v3.

The executable route is the **existing project-scoped Supabase Market Data Cloud `apply_migration` connector**. It needs no native PostgreSQL connection, new credential, new connection profile, or owner-run command. The previous route failed because the connector's generated wrapper ends at `commit;`, while v2 admitted only an otherwise identical wrapper with a final line-feed byte. V3 explicitly reviews that second exact byte string. The controller must retain a passing intentionally aborting transport-probe receipt and an independent review before asking for the new action-time approval.

## Package identity

| Item | Pin |
| --- | --- |
| Review ID | `managed-massive-relay-v3-review-20261030` |
| Canonical scope SHA-256 | `a40f86ad49918644c5443586644b66ca9748ede1a91ffb8a09cdca0b522963d5` |
| Proposed installer SHA-256 | `fe0f948824771dfa673548402e5d80a076d71f0211cf24091bb11e7ef0b6b013` |
| Proposed installer size | 21,825 bytes, including its final LF |
| Connector migration name | `astra_backfill_massive_relay_v3` |
| Existing project | `oxzabweahkoimtevbbny` |
| Existing run | `fixed3000-20250901-20260731-v1-20261030` |
| Frozen cohort snapshot | `2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec` |

The separate installer is [the v3 candidate](../review/massive-relay-v3/candidates/sql/astra_backfill_massive_relay_v3.sql). The v2 SQL, scope, review, manifest and all 19 manifest payloads remain byte-identical. Runtime protocol and object names remain `v2` deliberately: their behavior and interface are unchanged apart from binding runtime approval checks to the new v3 review ID and scope digest.

## Exact security diff from the reviewed v2 package

| Boundary | V2 | V3 proposal |
| --- | --- | --- |
| Wrapper terminal bytes | Exactly `commit;` followed by one LF | Exactly that existing string **or** exactly `commit;` without that final LF |
| Wrapper/body validation | Exact prefix, full reconstructed suffix, exact duplicate history body, exact body hash, bounded safe delimiter/account | Same checks; only the two explicitly enumerated terminal strings are accepted |
| Approval identity | V2 review ID, canonical scope and migration bytes | New v3 review ID, scope digest and exact v3 migration hash; v2 approval cannot qualify |
| Migration identity | V2 name and V2 sentinels | V3 name and V3 sentinels |
| Runtime approval binding | V2 review ID and scope digest | V3 review ID and scope digest |
| Authentication and runtime authorization | Existing gateway/capability validation plus two reviewed worker-only operations | Byte-identical authorization extension; no additional operation or grant |
| Time, scope and integrity | 15-minute installation gate, same cohort, request/fence/reservation/lease/cursor/response rules | Unchanged |
| Credential and service changes | Existing worker token sent to existing Edge function; existing server-side Massive key; existing worker/Edge deployment | Same explicit trust expansion, requiring fresh approval; no added credentials or services |

[The complete installer diff](../review/massive-relay-v3/installer-security-v2-to-v3.diff) is small and exact. A source equality test reconstructs the entire v3 SQL from v2 using only the declared substitutions and exact second suffix comparison. There is **no `trim`, `rtrim`, arbitrary whitespace acceptance, ignored suffix, SQL normalization, or body-hash substitution**. Two trailing LFs, CRLF, trailing spaces, tabs, comments, SQL, changed wrapper fields and changed history copies are rejected.

The existing exact raw-file mode remains unchanged, but is not the execution dependency for this proposal. The supported operational route is the already connected migration tool.

## Persistent security action being requested

Approval would permit these same bounded changes originally reviewed for v2:

1. Send the existing ingestion worker capability token to the **existing** `population-top3000-news-v1` Edge function. The function forwards it only to the fixed same-project ingestion RPC. It never forwards the token to Massive.
2. Add worker-only `backfill_relay_probe` and `backfill_relay_dispatch` operations behind existing gateway, capability expiry/revocation, post-lock revalidation and authorization checks. API capabilities cannot invoke either operation.
3. Create the private append-only `astra_ingestion_v1.backfill_relay_dispatches_v2` ledger with RLS, granting only SELECT and INSERT to the existing internal RPC owner. Create the invoker helper with an empty search path and EXECUTE only for that owner. No new role, broader public access, UPDATE, DELETE or TRUNCATE grant is included.
4. Deploy the pinned explicit relay branch in the existing Edge function and the pinned four-line integration in the existing worker. The old Edge handler remains intact for requests without the replacement relay header.
5. Use the existing server-side Massive/Polygon managed key for exactly the six reviewed read-only routes. The key stays in Edge and is sent only in the Authorization header to `https://api.massive.com`; no key is returned, exported or configured anew.

Giving the Edge function the worker token is a persistent trust expansion: compromise or misuse of that recipient could authorize requests within the token's allowed operations. This is the principal credential-handling risk the owner is approving. Reuse of a token or managed key does not itself grant this permission.

## Preserved acquisition scope

| Family | Read-only endpoint | Preserved boundary |
| --- | --- | --- |
| REF01 | `/v3/reference/tickers/{frozen_anchor}` | One frozen anchor, as-of date within 2025-09-01 through 2026-07-31 |
| N01 | `/v2/reference/news` | One frozen anchor, original New York publication boundaries |
| N02 | `/stocks/v1/dividends` | All entitled event history for fixed anchors, retaining boundary-crossing events |
| N03 | `/stocks/v1/splits` | Same explicit all-history event policy |
| S01 | `/stocks/v1/short-volume` | Reporting dates within the target |
| S02 | `/stocks/v1/short-interest` | Settlement dates within the target; no invented publication cutoff |

The fixed 3,000 members, existing provider plans and cost restrictions remain unchanged. Redirects remain disabled. Each provider GET retains the 25-second and 3-MiB limits. Current counted task/generation/page reservation, member/anchor consistency, run fence, owner, lease, attempt deadline, current cursor and adaptive page limit remain required. A durable immutable dispatch record precedes each external GET; uncertain effects require reconciliation and a new counted reservation/generation when the existing policy permits it. The existing source-body hashes and independent readbacks remain mandatory.

## Connector proof and qualification

The prepared [read-only probe](../review/massive-relay-v3/transport_readonly_probe_v3.sql) uses the **same parser bytes** as the candidate, changing only its named probe sentinel prefix and migration name. It explicitly sets transaction read-only and always raises a fixed P0001 acceptance receipt before the connector's history insert. The receipt reports only the probe hash/size, wrapper variant, verified duplicate copy and read-only/no-write flags. It does not return the connector account field, current query, credential or secret.

The producer's actual local PostgreSQL suite passed **17 tests in 5.258 seconds**. It includes 23 rejected approval variants, 25 rejected wrapper/body variants, all three admitted exact transport formats, a full no-final-LF wrapped installation with byte-identical history, the unchanged authentication/ACL and scope/fence/reservation/replay/integrity tests, runtime rejection of old/held approval, and the read-only probe's intentional rollback in all three formats. Four exact source/probe/preservation tests also passed. [Qualification receipt](replacement-managed-relay-qualification-v3.json).

An independent reviewer separately checks the final source and adversarial transport cases. Its receipt is [the independent review](replacement-managed-relay-independent-review-v3.json). Root owns the distinct live connector probe and target/ownership/hold readback; local test success does not stand in for that receipt. The package manifest binds the final review and action artifacts.

These tests do not establish live provider entitlement, data coverage or key availability. Those remain bounded post-approval validations, after exact installation and deployment. An authenticated readiness response proves managed-key presence only.

## Exact action sequence and approval window

The [installation action packet](../review/massive-relay-v3/installation_action_packet_v3.json) contains the exact connector name, argument object, SQL, byte/hash pins and required approval fields. Its approval timestamp/reference are **unpopulated placeholders**, not a valid approval record.

The existing controller must reconcile ownership, scheduled successor, target runtime, unchanged artifact pins, relay absence and uncertain writes before execution. Once preparation is executable and independently reviewed, the owner can approve this exact v3 package in one message. The controller records the **actual new user approval time**, preserving the original 09:53 approval/10:08 expiry, and applies this candidate only within the unchanged 15-minute installation window. A later forwarding or database receipt time cannot replace the approval time. If the window expires, the hold remains.

Installation is single-use and consumes its matching approval in the same existing audit/metadata path. The controller must read back the exact resulting objects, grants, authenticated dispatcher, applied hash, audit and history before any uncertain retry. It then deploys only the already pinned existing Edge/worker changes and performs bounded readiness/page/readback verification. Independent ingestion continues under its existing permissions throughout preparation.

## Smallest owner action after preparation is ready

> Approve `managed-massive-relay-v3-review-20261030`, scope `a40f86ad49918644c5443586644b66ca9748ede1a91ffb8a09cdca0b522963d5`, installer `fe0f948824771dfa673548402e5d80a076d71f0211cf24091bb11e7ef0b6b013`: the exact connector-compatible transport validation, existing worker-token recipient, two restricted worker operations/private dispatch permissions, and pinned bounded six-endpoint Edge/worker integration. Apply once through the existing connector within 15 minutes of this new approval, retaining all source, cost, ownership, security and evidence restrictions.

This request does not ask the owner to run code, supply a database connection, create credentials or broaden the mission. It authorizes no package drift or silent extension of the approval window.
