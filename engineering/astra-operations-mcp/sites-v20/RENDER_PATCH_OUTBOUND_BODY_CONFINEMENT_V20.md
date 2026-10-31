# ASTRA Operations v20 — Render PATCH complete outbound body confinement

**Source-only / dormant, no provider call or credential.** Existing ingestion controller remains the exclusive application executor and owner of any durable admission, lease/fence, physical-resource locking and provider-result capture. Dot alone owns the existing native private Site and canonical plugin publication. These synthetic tests do not establish live controller/provenance integration.

## Newly confirmed actual provider schema and risk

Render's official [Update service](https://api-docs.render.com/reference/update-service) API is `PATCH /v1/services/{serviceId}`. It accepts many independent request body fields, including `autoDeployTrigger`, `repo`, `branch`, `buildSourceId`, `serviceDetails`, `image`, `rootDir` and more. It can modify branch and startup settings in the SAME request as turning off autodeploy. Its successful HTTP 200 response can show `id` and `autoDeployTrigger:'off'` even if the request body also changed other configuration. The PATCH itself does not deploy; deployment is a separate operation.

In v19, `patch_ack` bound the expected `requested_field:'autoDeployTrigger'`, `requested_value:'off'` and original HTTP 200 response, but **never bound the complete, actual outbound JSON body**. Therefore an original provider response with the expected setting could appear causally verified even when additional, unapproved configuration mutations were present in the request. The v20 regression demonstrates that an otherwise sufficient v19 receipt with no outbound-body proof returns `complete` in v19 but is blocked in v20. This is a source-level missing-proof vulnerability, NOT evidence of any actual provider mutation.

## v20 exact outbound-body commitment

The only approved v10 user-level `render_update_worker` intent is `params:{auto_deploy:false}`, mapped by the controller to the exact UTF-8 HTTP body:

```json
{"autoDeployTrigger":"off"}
```

With only that field and no trailing whitespace, bytes = **27**, SHA-256 = `8525a932af773f1d2b9a91210582e00f3280c1a281fc34155d82d6b825946d2d`. The new v20 `renderPatchAckValid` requires the original owner-captured PATCH ACK to include the complete outbound-body proof as a bounded, secret-free projection:

- `request_body_capture:'controller_observed_outbound_http_bytes'`
- `request_content_type:'application/json'`
- `request_body_length:27`
- `request_body_sha256:'8525a932af773f1d2b9a91210582e00f3280c1a281fc34155d82d6b825946d2d'`

All four fields must be captured **from the actual HTTP body supplied to the provider transport inside the controller's guarded dispatch**, not derived by the client from the intended body, a later GET, a caller field or another operation. This actual provenance cannot be verified until the existing controller implements a real port. The digest/length is a *necessary client check*, not a cryptographic attestation of who sent the request. The owner's immutability, lock, transport capture and stop/fence validation must be separately proven. The bounded receipt must never carry raw body text, provider secrets or full responses.

Original reservation/exact historical lookup and later readback must preserve these exact fields. A different body, extra branch/build-source/startup field, deprecated `autoDeploy`, modified content type, missing proof, changed readback or raw-response passthrough yields `original_render_patch_ack_unverified_no_retry`, and no replay is allowed. This is a versioned forward-only contract: **do not transform historical v19 receipts into v20 proof**, and do not silently change v10 `v10-json-v1` request digest semantics.

## Other official security and setup facts (read-only)

- Render's [Link service](https://api-docs.render.com/reference/link-service-to-env-group) response schema contains `envVars.value` and `secretFiles.content`; its link operation gives the service access to those secrets and triggers deployment. Existing v16 pre-admission block for new links remains. Render [List environment variables](https://api-docs.render.com/reference/get-env-vars-for-service) explicitly excludes linked environment-group variables; it cannot safely prove collision-free group inheritance. [List environment groups](https://api-docs.render.com/reference/list-env-groups) omits those values, while group retrieval APIs can be secret-bearing. The controller needs a security-approved **redacted metadata** attestation rather than an indiscriminate raw secret fetch.
- Render's [scoped-key beta](https://render.com/blog/scoped-api-keys-private-beta) is private beta (2026-10-27) and actual account entitlement remains UNKNOWN. A provider 403 `insufficient_token_scope` may name minimum scopes but no production test was authorised. No broad classic key substitution, credential creation or external write.
- GitHub workflow dispatch still requires default-branch `workflow_dispatch`, effective repo-limited Actions:Write grant, original exact run ID and first-attempt successful terminal causal proof; installation identity/destination/revocation remain unverified. No workflow change was made.

## Acceptance and tests

V19 source-only prior = **240/240**. New v20 source-only regression = **20** cases, including reproduced v19 false-positive, exact approved body, historical no-redispatch, extra branch/build source, deprecated alias, changed setting, whitespace/unknown serialization, wrong hash/source/length/content type, late proof, raw-body exclusion, env-group gate and unbound owner port. Combined candidate expected **260/260**. Owner-side live tests remain required for durable logical-change and physical-resource locks, 20 concurrent same/alternate-key/revision requests, stopped/fenced/expired operations, PREPARED/DISPATCHING crash windows and UNKNOWN no-replay.

The four missing writes remain backlog. No new controller, worker, durable journal, executor, Site, plugin, OAuth server, credential, provider call, paid service, trading operation or app mutation was created.