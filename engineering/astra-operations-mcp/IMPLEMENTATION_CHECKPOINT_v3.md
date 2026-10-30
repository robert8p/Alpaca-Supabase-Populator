# ASTRA Operations MCP — executable engineering checkpoint v3 (2026-10-30 17:55 UTC)

**Owner:** https://chatgpt.com/c/6ae4ce37-54f0-83eb-9e51-6447e6a4d6ba — plugin capability ONLY. App operations remain exclusively with ingestion https://chatgpt.com/c/6ae206a6-9524-83ed-b103-7c23bcfe51e5 and scanner https://chatgpt.com/c/6adac650-cbe0-83eb-b09b-8cd8d61a16f7. No competing controller, queue, mission scheduler, data ingestion or scanner critical-path code was added.

## Executable source and verification

- Library artifact: `/ASTRA Operations/ASTRA_Operations_Engineering_Checkpoint_v3.zip` (uploaded and confirmed); local filename `ASTRA_Operations_Engineering_Checkpoint_v3.zip`.
- **Exact archive SHA-256:** `98477755d6920d0f34e3f9abe8428c5c59c657508f23f8f611db1bc298930003`.
- This branch includes `engineering/astra-operations-mcp/verify_v3.py`. Once the Library ZIP is materialized, execute `python engineering/astra-operations-mcp/verify_v3.py /path/to/ASTRA_Operations_Engineering_Checkpoint_v3.zip`; the verifier checks archive digest, safe paths, every source-file SHA, and all 46 tests before printing VERIFIED. Neither verifier nor tests contact live app/provider APIs.
- Source archive includes `operations.py` (reused), `transport.py` (updated), `oauth_security.py`, `admission.py`, original+new tests, `SOURCE_DIGESTS_v3.json`, `TEST_EVIDENCE_v3.json`, `checkpoint.json`, `README.md`, requirements, and **`SETUP_DECISION_FOR_DOT.md`**. The predecessor's 18 tests were retained; added 28 tests.
- **Local verification:** 46/46 unit/security/ASGI tests passed; Python compile passed. A real uvicorn 127.0.0.1 HTTP subprocess returned 200 for initialize, tools/list, implementation_context and connection_diagnostics; rejected no-token access with 401. No secrets or real provider requests were needed.
- **Important limitation:** tests used the available environment's FastAPI 0.128.2 and Uvicorn 0.48.0, not the pinned 0.116.1/0.35.0 requirements. Exact dependency/release image qualification, official SDK interoperability, hosted OAuth and fresh-chat use remain **unverified**.

## Actual source/controller contract reconciled

- Existing ingestion repo `robert8p/Alpaca-Supabase-Populator`, branch `feat/astra-ingestion-service`, `astra_ingestion/api.py` blob `23571883acd35dcab295f9486e993619003d69a8`.
- Verified GET `/api/backfill/status`, GET `/api/jobs`, GET `/api/jobs/{job_id}`; existing HTTP Basic authentication also gates POST `/api/jobs` and `/api/jobs/{job_id}/pause|resume|cancel`, with additional POST checks.
- **Newly established security blocker I1:** the Basic identity is control-capable, not read-only. v3 OAuth-mode adapter **refuses** to use `INGESTION_USER/PASSWORD` even if supplied. Dot must relay controller-owned request for independently verified GET-only identity; this plugin cannot modify the app controller.
- Render ingestion services remain `srv-dbh85vl9fdbs7387rucg` (web) and `srv-dbh9fko473hc739an8m0` (worker), workspace `tea-d562ma4hg0os73aejnfg`. No Render configuration write occurred.
- GitHub service/repository allowlist remains `robert8p/Alpaca-Supabase-Populator` and `robert8p/market-data-leading-indicator-lab`. No workflow dispatch, PR approval, Apps installation or repository permission edit occurred.

## v3 implementation, not future promise

Six callable **local** MCP tools: `render_inspect`, `github_workflow_inspect`, `ingestion_status`, `ingestion_job`, `connection_diagnostics`, `implementation_context`. Only GET adapter verbs; exact allowlisted resources, HTTPS fixed destinations, no redirects, 8s bounded reads, 64-KiB streaming cap, no arbitrary provider output; positive status/job projections and masking in permitted scalar fields. The controller returns bounded actual `runs` status in `/api/backfill/status`, rather than the v2 adapter incorrectly dropping it.

MCP 2025-03-26 stateless Streamable HTTP subset (POST application/json, GET 405); validates Origin, Host, Accept and protocol version; rejects duplicate JSON fields and malformed messages and oversized requests. Qualification token is loopback-only. OAuth mode is disabled by default; v3 can verify RS256 owner-bound, client-bound access tokens with pinned issuer, audience, scope, times and public JWKS and provides unauthenticated RFC 9728 metadata at `/.well-known/oauth-protected-resource/mcp` plus a 401 discovery challenge. **The OAuth provider/client/grant and signing key rotation are not connected or verified.** This candidate is not a production OAuth integration or authenticated public MCP service.

`admission.py` tests exact mission/owner/stop generation/fence/request hash/expiry and independent controller readback, while explicitly returning PRECHECK_ONLY_NOT_MUTATION_AUTHORITY. Uncertain-effect recovery needs two matching committed readbacks; unknown/stale/conflicting outcomes HOLD with retry=false. **No mutating tools are published.** No operation is retried or submitted.

## Exact outstanding setup decision (not approved or executed)

Read artifact `SETUP_DECISION_FOR_DOT.md` and relay the **exact smallest** per-action confirmation:
1. H1: one new isolated zero-incremental-cost Render MCP service with autodeploy off, only after verifying actual free capacity and price; no credentials or public tool access.
2. A1: separately approve owner-only OAuth for `astra.operations.read` **after** exact issuer, client ID, owner subject, JWKS, audience and canonical host are resolved. No chat credential disclosure.
3. R1: Render read-only identity, scope read back before attachment; workspace-wide key requires explicit broader-scope confirmation.
4. G1: GitHub App on exactly the two named repositories, metadata READ and Actions READ only; short-lived installation tokens; install/grant separately confirmed.
5. I1: ingestion controller itself owns GET-only read-identity implementation/proof. Existing Basic password MUST NOT be transferred.

Neither earlier general approvals nor this continuation are these specific confirmations. All mutations remain disabled, including worker creation, workflow dispatch, ingestion controls, database writes, trading and paid services. No new subscriptions or upgrades.

## Durable exact successor

Automation `6ae4d6e1e2a48191aa7edaf9464f77e5` remains enabled and owned by this implementation chat. **NEXT EXECUTABLE ACTION:** read this file, materialize the Library ZIP, execute the GitHub `verify_v3.py`, inspect latest current source/controller head, and independently qualify MCP HTTP/OAuth errors and pinned runtime in a disposable localhost environment without live credentials. If Sites MCP becomes available, use its supported hosting process; otherwise DO NOT substitute skills-only wrappers or attach secrets to existing services. Route H1/A1/R1/G1/I1 exact questions only to dot. After action-time confirmation, deploy only isolated service, independently test public OAuth discovery, owner grant, scoped provider reads, no-log secrets and fresh-chat tool calls. Never promote without those observations. Record any new code, exact test evidence and next successor in a v4 checkpoint, not a prose next action alone.

**Progress channel:** persistent GitHub/Library readback for dot. No direct routine notification to Rob. Status `LOCAL_QUALIFIED_HOSTING_AUTH_GATED`, not `LIVE`, `COMPLETE` or `AUTONOMOUS_HOSTED`.

Official protocol references used for design: https://github.com/modelcontextprotocol/modelcontextprotocol/blob/main/docs/specification/2025-11-25/basic/transports.mdx and https://py.sdk.modelcontextprotocol.io/run/authorization/.
