# ASTRA Operations v10 — missing operations retained and controller-delegated

Implementation owner: https://chatgpt.com/c/6ae4ce37-54f0-83eb-9e51-6447e6a4d6ba
Dot is the sole publisher for Site appgprj_6ae4dcec2034819197d448ca2eea21a3; plugin plugin_asdk_app_sites_a5e127b6f02081918cde92d94b477c57. Existing application controllers retain sole execution ownership.

**Source/test archive:** Library `/ASTRA Operations/ASTRA_Operations_Missing_Capabilities_v10.zip` SHA-256 `ee25c8adfbe62abdb3eb2f99531a5fccfdcd4db182d06b8321316e355df70f6f`. Contains v9 baseline and new executable `v10/candidate/lib/controller-operations-v10.mjs` and test. **137/137 tests pass**: 117 candidate + 20 original native. No live provider write or credential used.

**Corrected backlog:** Render worker create/update/environment-group link and GitHub workflow dispatch remain in authorised capability implementation scope. Each is blocked from execution pending controller-owned admission, action-specific permission and grant, exact resource, cost/release gates, stop/fence and idempotent readback. New code delegates through controller-owned inspect/admit/execute/readback port; it does not create a competing controller or direct provider client.

**Read-only facts checked 2026-10-30:** Render existing ingestion worker `srv-dbh9fko473hc739an8m0` exists, auto-deploy off, branch feat/astra-ingestion-service; don't duplicate it. Render workspace `tea-d562ma4hg0os73aejnfg` is accessible, but exposed tools have no scoped-key beta eligibility read: eligibility UNKNOWN, not denied. GitHub repo `robert8p/Alpaca-Supabase-Populator` is public and connected account has admin access; this does NOT establish App Actions:Write. Critically `.github/workflows/astra-ingestion-qualification.yml` has NO `workflow_dispatch` trigger, so dispatch cannot work without controller-authorised workflow change and qualification. No repo or workflow changes made.

**Next executable steps:** (1) reconcile existing controller port/fence/idempotency/readback schema and test with contract fixtures; (2) ask ingestion controller, not this plugin, to qualify adding workflow_dispatch to the named workflow only if useful; (3) inspect account-level Render scoped-key eligibility via a supported read-only tool if exposed; do not guess; (4) establish exact provider permissions/secure destination/expiry/revocation/zero-cost and request action-time consent through dot before any grant; (5) dot alone publishes approved changes to existing Site. No provider credentials, no production writes, no new Site/plugin, no trading.

Hourly continuation task: `6ae4d6e1e2a48191aa7edaf9464f77e5`. Routine reporting via dot only.
