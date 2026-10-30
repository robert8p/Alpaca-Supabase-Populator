BEGIN; SET LOCAL statement_timeout='8s'; SET LOCAL lock_timeout='3s';
DO $progress$
DECLARE r astra_ingestion_v1.backfill_runs_v2%ROWTYPE; r_after astra_ingestion_v1.backfill_runs_v2%ROWTYPE; before_original jsonb; before_exc jsonb; before_target jsonb; payload jsonb := '{"request_id":"v74-eqr-ref01-alternative-acquisition-verified","state":"ALTERNATIVE_REFERENCE_ACQUIRED_VERIFIED","observed_at":"2026-10-30T16:33:51.43443+00:00","acquired_at":"2026-10-30T16:23:26.326148+00:00","readback_verified_at":"2026-10-30T16:23:26.419964+00:00","provider":"Massive","asof":"2026-07-31","recovery_task_id":"backfill-plan-b02f70882418e225433c701a33576aa43da36817f158e1227366497287c7ba3e","body_sha256":"f11931dd96941da93c70c2022e484a8ed84bbe48ed20c3aa84ffdd135e86b359","records_sha256":"ede5c9bc8db7250eae8640214ca6532dd43bd68703e78df71037682e2660b446","record_count":1,"source_bytes":1288,"dispatch_id":"a3e287d5-fb19-4850-8a8f-89947d69f3c0","identity_comparison":{"cik_matches_fixed_member":true,"ticker_matches":true,"composite_figi_matches":true,"share_class_figi_matches":true,"exchange_matches":true,"security_type_matches":true,"anchor_sha256":"85d0f5adcb21c83a653728005dbefc632887f9e006f8feeda6fdc5fbe4eeaa00","anchor_observation_date":"2026-08-03"},"original_failure_preserved":true,"provider_absence_disposition":false,"complete_identity_resolution_claimed":false,"next_executable_step":"Reconcile this already-verified dated page with the existing REF01 identity evidence and queued dated reference tasks. Reuse those tasks and receipts; preserve any missing current Alpaca UUID or historical interval evidence and affected derivation NULL/reasons. Do not repeat this acquired page.","evidence_path":"evidence/replacement-eqr-ref01-acquisition-readback-v74.json","same_controller":true,"new_source_subscription_credentials_or_grants":false}'::jsonb; k constant text := 'REF01:CIK:0000906107:exception:2282';
BEGIN
 IF NOT pg_try_advisory_xact_lock(706314020261028) THEN RAISE EXCEPTION 'Existing control gate busy; no progress mutation'; END IF;
 SELECT * INTO STRICT r FROM astra_ingestion_v1.backfill_runs_v2 WHERE id='fixed3000-20250901-20260731-v1-20261030' FOR UPDATE;
 IF r.status<>'ACTIVE' OR r.fence<>1 OR r.cohort_sha256<>'2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
 OR r.metadata->>'implementation_owner' IS DISTINCT FROM 'root-replacement-20261030T042603Z'
 OR coalesce((r.metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()+interval '10 seconds',false) IS NOT TRUE
 OR r.metadata#>>ARRAY['implementation_remediation_queue',k,'request_id'] IS DISTINCT FROM 'v74-eqr-ref01-exception2282-existing-massive-target-end'
 OR r.metadata#>>ARRAY['implementation_remediation_queue',k,'state'] IS DISTINCT FROM 'EXECUTABLE_EXISTING_TASK_ASSIGNED'
 OR r.metadata#>>'{implementation_reporting_policy,mode}' IS DISTINCT FROM 'DOT_CONSOLIDATED_CHECKPOINTS_ONLY'
 THEN RAISE EXCEPTION 'Owner, scope, reporting or assignment changed; reconcile'; END IF;
 IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_audit_v2 WHERE run_id=r.id AND evidence->>'request_id'=payload->>'request_id') THEN RAISE EXCEPTION 'Progress may already be recorded; reconcile'; END IF;
 SELECT to_jsonb(t) INTO STRICT before_original FROM astra_ingestion_v1.backfill_tasks_v2 t WHERE id='backfill-plan-d54009e35cd9cd283f26e6c455425be613d24af035420b982f964c3ba97bfa54' FOR SHARE;
 SELECT to_jsonb(t) INTO STRICT before_target FROM astra_ingestion_v1.backfill_tasks_v2 t WHERE id='backfill-plan-b02f70882418e225433c701a33576aa43da36817f158e1227366497287c7ba3e' FOR SHARE;
 SELECT to_jsonb(x) INTO STRICT before_exc FROM astra_ingestion_v1.backfill_exceptions_v2 x WHERE id=2282;
 IF encode(sha256(convert_to(before_original::text,'UTF8')),'hex')<>'9409c71fe6f84108de7b995312588710fca0d03edf27667069b2b3105cce75e5'
 OR before_target->>'status'<>'INGESTED' OR before_target->>'attempts'<>'1' OR before_target->>'records_committed'<>'1'
 OR encode(sha256(convert_to((before_exc->'evidence')::text,'UTF8')),'hex')<>'4f4a3f759c43e712ebb2c19c83cea027fe2cf6ba083b8fb1fe7d9fa61710b3e0'
 THEN RAISE EXCEPTION 'Original or acquired task changed'; END IF;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_pages_v2 p
 JOIN astra_ingestion_v1.backfill_readbacks_v2 b ON b.task_id=p.task_id AND b.page_no=p.page_no
 JOIN astra_ingestion_v1.backfill_relay_dispatches_v2 d ON d.task_id=p.task_id AND d.page_no=p.page_no AND d.generation=p.generation
 JOIN astra_ingestion_v1.backfill_members_v2 m ON m.run_id=p.run_id AND m.member_id='CIK:0000906107'
 WHERE p.task_id=payload->>'recovery_task_id' AND p.page_no=0 AND p.generation=1 AND p.run_fence=1 AND p.http_status=200
 AND p.body_sha256=payload->>'body_sha256' AND p.body_sha256=encode(sha256(convert_to(p.raw_body,'UTF8')),'hex')
 AND b.body_sha256=p.body_sha256 AND b.readback_sha256=p.body_sha256 AND p.record_count=1 AND b.actual_records=1 AND b.expected_records=1
 AND d.request=p.request AND d.dispatch_id::text=payload->>'dispatch_id' AND d.authorized_at<=p.fetched_at AND p.fetched_at<=d.not_after
 AND p.request->>'path'='/v3/reference/tickers/EQR' AND p.request->'params'->>'date'='2026-07-31'
 AND encode(sha256(convert_to(m.anchor::text,'UTF8')),'hex')='85d0f5adcb21c83a653728005dbefc632887f9e006f8feeda6fdc5fbe4eeaa00'
 AND 'CIK:'||(p.raw_body::jsonb->'results'->>'cik')=m.member_id AND p.raw_body::jsonb->'results'->>'ticker'=m.anchor_ticker
 AND p.raw_body::jsonb->'results'->>'composite_figi'=m.anchor->>'anchor_composite_figi'
 AND p.raw_body::jsonb->'results'->>'share_class_figi'=m.anchor->>'anchor_share_class_figi'
 AND p.raw_body::jsonb->'results'->>'primary_exchange'=m.anchor->>'anchor_exchange'
 AND p.raw_body::jsonb->'results'->>'type'=m.anchor->>'anchor_security_type')
 THEN RAISE EXCEPTION 'Acquisition, relay, readback or fixed identity proof no longer matches'; END IF;
 payload:=payload||jsonb_build_object('recorded_at',clock_timestamp());
 UPDATE astra_ingestion_v1.backfill_runs_v2 SET metadata=jsonb_set(metadata,ARRAY['implementation_remediation_queue',k],
 (metadata#>ARRAY['implementation_remediation_queue',k])||jsonb_build_object('state',payload->>'state','progress',payload,'next_executable_step',payload->>'next_executable_step'),false)
 WHERE id=r.id RETURNING * INTO STRICT r_after;
 IF to_jsonb(r_after)-'metadata' IS DISTINCT FROM to_jsonb(r)-'metadata'
 OR (r_after.metadata#-ARRAY['implementation_remediation_queue',k]) IS DISTINCT FROM (r.metadata#-ARRAY['implementation_remediation_queue',k])
 OR (SELECT to_jsonb(t) FROM astra_ingestion_v1.backfill_tasks_v2 t WHERE id=before_original->>'id') IS DISTINCT FROM before_original
 OR (SELECT to_jsonb(t) FROM astra_ingestion_v1.backfill_tasks_v2 t WHERE id=before_target->>'id') IS DISTINCT FROM before_target
 OR (SELECT to_jsonb(x) FROM astra_ingestion_v1.backfill_exceptions_v2 x WHERE id=2282) IS DISTINCT FROM before_exc
 OR (r.metadata->>'implementation_lease_until')::timestamptz<=clock_timestamp()
 THEN RAISE EXCEPTION 'Unexpected mutation or expired ownership; rollback progress'; END IF;
 INSERT INTO astra_ingestion_v1.backfill_audit_v2(run_id,task_id,generation,action,source_revision,evidence)
 VALUES(r.id,before_original->>'id',1,'REMEDIATION_ALTERNATIVE_ACQUISITION_VERIFIED','a3bc0520e624054b278e46682b04cebb33e9b677',payload);
END $progress$;
SELECT id,action,recorded_at,evidence FROM astra_ingestion_v1.backfill_audit_v2 WHERE run_id='fixed3000-20250901-20260731-v1-20261030' AND evidence->>'request_id'='v74-eqr-ref01-alternative-acquisition-verified'; COMMIT;
