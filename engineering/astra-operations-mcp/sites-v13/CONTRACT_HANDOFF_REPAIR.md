# ASTRA Operations v13 — repaired v11 contract handoff (2026-10-30)

## Authoritative immutable contract
- GitHub repo: `robert8p/Alpaca-Supabase-Populator`
- Existing branch: `feat/astra-operations-sites-handoff-20261030`
- Exact path: `engineering/astra-operations-mcp/sites-v11/docs/OWNER_PORT_ADOPTION_CONTRACT.md`
- Immutable commit: `db0efa4140ae6d59b4c8f36d0d0ebd39b5ff3cd0`
- Blob SHA-1: `622d820e97b62a99a1278223bdc677972be8bf3f`
- Content SHA-256: `58b61d0026d4dc9f7a53185d0d06bd5db216dc9b50e8d575cc96377e2e65c0cb`
- UTF-8 length: 4920 bytes.
- Immutable URL: https://github.com/robert8p/Alpaca-Supabase-Populator/blob/db0efa4140ae6d59b4c8f36d0d0ebd39b5ff3cd0/engineering/astra-operations-mcp/sites-v11/docs/OWNER_PORT_ADOPTION_CONTRACT.md
- Verified by extracting member `v11/docs/OWNER_PORT_ADOPTION_CONTRACT.md` from Library v11 ZIP, SHA-256 and `git hash-object`, and fetching immutable GitHub file whose blob SHA matches.

## Existing owner acknowledgement and issue repair
Ingestion owner **acknowledged** issue #94 in backfill audit 96 and **deferred** it behind active reliability repair. The previous 404 was a stale-branch/path mismatch at `feat/astra-operations-mcp-20261030` `fb20e97`, not evidence the contract was absent from the v11 archive. The contract is now committed at the immutable URL above.

Existing issue #94 updated **by comment, not a new issue**: https://github.com/robert8p/Alpaca-Supabase-Populator/issues/94#issuecomment-6534994041. Comment readback verified, with exact SHA. Owner is already acknowledged; do not seek redundant acknowledgement or interrupt active work.

## Scope and next executable action
- Ingestion controller owns the deferred adoption decision, source mapping, stop/fence/lease and atomic provider write guard; no plugin-side second controller.
- Plugin implementation owner continues independent provider permission and response contract qualification, and monitors the existing issue read-only for an owner mapping after reliability repair permits it. No live provider integration claim.
- Dot owns Sites publication and specific action-time permission confirmations; no provider grant is ready.
- Render scoped-key beta entitlement inspection unavailable through exposed account tools: `UNKNOWN/NO ELIGIBILITY ACTION`, not denial. Native Sites eligibility discovery action also unavailable. No keys created, no secrets read.
- GitHub workflow dispatch remains blocked by default-branch `workflow_dispatch` and actual Actions:Write grant, to be qualified by ingestion owner.
- Existing private Site and plugin unchanged. No new credentials, paid service, production write, PR approval, scanner operation, or trading.

## Continuation
Existing hourly task `6ae4d6e1e2a48191aa7edaf9464f77e5` retains implementation ownership and schedule. Next: read issue #94 and owner audit source without modifying ingestion, qualify any returned port mapping, otherwise continue exact provider-scope research and no credential work.
