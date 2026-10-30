# ASTRA Operations v8 — native connector capability gap and source correction

Implementation owner: https://chatgpt.com/c/6ae4ce37-54f0-83eb-9e51-6447e6a4d6ba. Dot remains sole native Sites publisher; ingestion/scanner controllers retain app operations.

## Exact evidence
Existing private Site `appgprj_6ae4dcec2034819197d448ca2eea21a3`; canonical plugin `plugin_asdk_app_sites_a5e127b6f02081918cde92d94b477c57`; successful deployment `appgdep_6ae4e214b77481918e5102573e560ef9`; source commit `3d260fbe95d3600c1519e28d49af7be36c9f4712`. Existing plugin calls implementation_context/connection_diagnostics worked in this chat; render_inspect returned provider_adapter_not_provisioned. No provider access.

Dot verified Sites app-integrations requires `sites_list_plugin_eligibility` before selecting/deploying connectors; currently exposed Sites tool inventory lacks this and connector context/schema inspection. **Missing tool exposure is not an account/admin denial.** `getContext` is cached hints, not authorization or eligibility. Sites native `read_only` is **connector-wide reads**, not custom action-level host enforcement. The v7 consent wording claiming host action scoping is withdrawn.

## v8 tested source
Full source ZIP in Library `/ASTRA Operations/ASTRA_Operations_Native_Integration_Correction_v8.zip`; SHA-256 `450ecfc5dbe0d7e691c4ea1362cef16c1e340b4d858e90c888811a4a7f24ae43`.
Contains unchanged published native source, corrected native candidate (trusted eligibility and explicit connector-wide scope acknowledgement, backend-enforced action/target restrictions), direct-provider admission validator, tests, and checkpoint. 65/65 tests passed: 20 native published-source tests + 26 corrected candidate + 19 direct-provider proposal checks. All offline; no credential or provider invocation. The validator checks proposal structure, not actual permission evidence.

## Direct-provider fallback boundaries
Render workspace `tea-d562ma4hg0os73aejnfg`, services `srv-dbh85vl9fdbs7387rucg` and `srv-dbh9fko473hc739an8m0`. If a Render key cannot be provider-scoped, **broad provider rights remain even with backend resource allowlist**; disclose that explicitly before action-time consent. GitHub `robert8p/Alpaca-Supabase-Populator` repository, workflow `astra-ingestion-qualification.yml`; fetch_file proves source presence only, not workflow dispatch. GitHub App install/permissions require separate specific confirmation. Ingestion Basic identity can POST controls and must never be transferred to Sites; GET-only controller-owned facade required.

## Concrete successor
Continue provider permission documentation and response-schema tests without credentials. Dot checks supported exposure of native eligibility capability, otherwise returns precise unsupported state. Only prepare action-time grant payload when exact account, provider-enforced effective permissions, target, secure destination, expiry/revocation and zero incremental cost have been verified. No new Site/plugin/host, OAuth server, secret, production mutation, PR approval, trading or paid commitment. Dot publishes only an approved reviewed overlay to the existing Site. Existing hourly successor `6ae4d6e1e2a48191aa7edaf9464f77e5`.
