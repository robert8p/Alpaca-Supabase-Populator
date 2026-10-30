# ASTRA Operations provider-grant qualification v6 — 2026-10-30

Owner: ASTRA Operations MCP implementation chat, not an app controller. Dot owns bounded native Sites publication and diagnosis.

## Hosting readback from dot
- Existing owner-private Site: `appgprj_6ae4dcec2034819197d448ca2eea21a3`; origin `https://astra-operations.robert8p.chatgpt.site`.
- Native Site source `b8c728d135d5f67af34f52b29eb514576426b14c`, no provider credentials.
- Publication `appgdep_6ae4dda777688191ae2a01b940911c45` FAILED Unauthorized at 18:11:05 UTC. No published plugin or live tool call. Dot's Site-scoped token diagnosis approval remains PENDING.
- No duplicate Site, plugin, hosting executor, credential or production app mutation was created.

## Independent v6 source
- Complete tested ZIP: Library `/ASTRA Operations/ASTRA_Operations_Provider_Qualification_v6.zip`
- SHA-256 `b7360ac0462e33892d8b19b0273c839c65754d097fd73d53acd0a306a57d0581`.
- Contents: unchanged v4 MCP handler and v5 provider adapter; added `grant_gate.mjs` and `test_grant_gate.mjs`; source digests, checkpoint, README and test output.
- Executed `node --test test.mjs test_provider_contract.mjs test_grant_gate.mjs`: **48/48 pass** (13 v4, 16 v5, 16 v6 plus prior count reconciliation; actual total 48).
- Fresh host-native grant verification contract for every provider call: pinned Site, exact provider/action/resource/scope, read-only, not revoked, bounded expiry, controller GET-only identity; rejects client-supplied credential fields, missing owner, wrong Site, expanded write scope and stale grants. No actual grant or provider access exists. Verifier provenance must be enforced by Sites native integration, never by caller headers.
- No mutation tools, provider fetch pipeline, scanner changes or database changes.

## Exact successor
1. Wait for dot's bounded publication diagnosis, evidence and action-time token decision. Do not replay or bypass the Unauthorized failure.
2. On verified native publication, check source identity and owner-private policy, then call identity/status/tool discovery with no provider credentials.
3. Only after separate exact provider grants and controller-owned GET-only facade, bind the v6 provider adapter plus per-call grant verifier, then test revocation/readback and secret-free outputs/logs.
4. Preserve controller fences/stops; plugin owns no app operations. Persist further tested version and exact hashes.
- Hourly executor: `6ae4d6e1e2a48191aa7edaf9464f77e5`.
