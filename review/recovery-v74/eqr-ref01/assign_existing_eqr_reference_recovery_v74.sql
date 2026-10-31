-- Same-controller EQR recovery assignment; reuse one existing admitted task.
-- This is not a relay installation, permission change, source fetch or counter reset.
BEGIN;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $eqr_recovery$
DECLARE
 r astra_ingestion_v1.backfill_runs_v2%ROWTYPE;
 r_after astra_ingestion_v1.backfill_runs_v2%ROWTYPE;
 original astra_ingestion_v1.backfill_tasks_v2%ROWTYPE;
 target astra_ingestion_v1.backfill_tasks_v2%ROWTYPE;
 target_after astra_ingestion_v1.backfill_tasks_v2%ROWTYPE;
 exc astra_ingestion_v1.backfill_exceptions_v2%ROWTYPE;
 queue_key constant text := 'REF01:CIK:0000906107:exception:2282';
 request_id constant text := 'v74-eqr-ref01-exception2282-existing-massive-target-end';
 assignment jsonb;
 definition_before text;
BEGIN
 IF NOT pg_try_advisory_xact_lock(706314020261028) THEN
  RAISE EXCEPTION 'Existing control gate busy; no recovery assignment written';
 END IF;
 SELECT * INTO STRICT r FROM astra_ingestion_v1.backfill_runs_v2
 WHERE id='fixed3000-20250901-20260731-v1-20261030' FOR UPDATE;
 IF r.status<>'ACTIVE' OR r.fence<>1
  OR r.cohort_sha256<>'2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
  OR r.metadata->>'implementation_owner' IS DISTINCT FROM 'root-replacement-20261030T042603Z'
  OR COALESCE((r.metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()+interval '10 seconds',false) IS NOT TRUE
  OR r.metadata#>>'{implementation_checkpoint,commit}' IS DISTINCT FROM 'a3bc0520e624054b278e46682b04cebb33e9b677'
  OR r.metadata#>>'{massive_relay_security_confirmation,state}' IS DISTINCT FROM 'APPROVED_AT_ACTION_TIME'
  OR r.metadata#>>'{massive_relay_security_confirmation,review_id}' IS DISTINCT FROM 'managed-massive-relay-v3-review-20261030'
  OR r.metadata#>>'{massive_relay_security_confirmation,scope_sha256}' IS DISTINCT FROM 'a40f86ad49918644c5443586644b66ca9748ede1a91ffb8a09cdca0b522963d5'
  OR r.metadata#>>'{massive_relay_security_confirmation,confirmation_source}' IS DISTINCT FROM 'EXPLICIT_USER_ACTION_TIME_CONFIRMATION'
 THEN RAISE EXCEPTION 'Current owner, scope, checkpoint or installed relay authority changed'; END IF;
 IF encode(sha256(convert_to(pg_get_functiondef('astra_ingestion_v1.rpc_dispatch(text,jsonb)'::regprocedure),'UTF8')),'hex')<>'a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520'
  OR encode(sha256(convert_to(pg_get_functiondef('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure),'UTF8')),'hex')<>'28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44'
  OR encode(sha256(convert_to(pg_get_functiondef('astra_ingestion_v1.backfill_relay_v2(text,jsonb)'::regprocedure),'UTF8')),'hex')<>'2d3cd0e58e17d814e6af3e98fd771862137b6db7d3211b508d7df8a2fda74cba'
  OR encode(sha256(convert_to(pg_get_functiondef('astra_ingestion_v1.backfill_task_guard_v2()'::regprocedure),'UTF8')),'hex')<>'94646a710138c821c9779849edca400d6445b84bec270cc2761a019ecac4b13e'
  OR encode(sha256(convert_to(pg_get_functiondef('astra_ingestion_v1.backfill_task_definition_sha256_v2(astra_ingestion_v1.backfill_tasks_v2)'::regprocedure),'UTF8')),'hex')<>'ba6d5bfd137045abfedb61524d47e734c0489f01957b153fa913f7686db45633'
 THEN RAISE EXCEPTION 'Exact existing execution or task-integrity source changed'; END IF;
 IF r.metadata ? 'implementation_remediation_queue'
  AND jsonb_typeof(r.metadata->'implementation_remediation_queue') IS DISTINCT FROM 'object'
 THEN RAISE EXCEPTION 'Existing remediation queue has another shape; reconcile'; END IF;
 IF COALESCE(r.metadata->'implementation_remediation_queue','{}') ? queue_key
  OR EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_audit_v2 a WHERE a.run_id=r.id
    AND (a.evidence->>'request_id'=request_id OR a.evidence->>'original_exception_id'='2282' OR a.evidence->>'exception_id'='2282'))
 THEN RAISE EXCEPTION 'Equivalent recovery may already be assigned; reconcile instead of duplicating'; END IF;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_members_v2 m
  WHERE m.run_id=r.id AND m.member_id='CIK:0000906107' AND m.selection_order=446 AND m.anchor_ticker='EQR'
  AND encode(sha256(convert_to(m.anchor::text,'UTF8')),'hex')='85d0f5adcb21c83a653728005dbefc632887f9e006f8feeda6fdc5fbe4eeaa00')
 THEN RAISE EXCEPTION 'Fixed EQR member or anchor evidence changed'; END IF;
 SELECT * INTO STRICT original FROM astra_ingestion_v1.backfill_tasks_v2
 WHERE id='backfill-plan-d54009e35cd9cd283f26e6c455425be613d24af035420b982f964c3ba97bfa54' FOR UPDATE;
 IF original.run_id<>r.id OR original.run_fence<>1 OR original.family<>'REF01' OR original.provider<>'Alpaca'
  OR original.kind<>'alpaca_reference' OR original.status<>'OPERATIONAL_ERROR'
  OR original.owner IS NOT NULL OR original.lease_until IS NOT NULL
  OR original.generation<>1 OR original.attempts<>1 OR original.page_attempts<>1
  OR original.requests_reserved<>1 OR original.records_committed<>0 OR original.page_no<>0
  OR original.error_code IS DISTINCT FROM 'SOURCE_HTTP_ERROR'
  OR encode(sha256(convert_to(original.scope::text,'UTF8')),'hex')<>'0e63617a4df227ad133d373b8ede374e4c28b2a132089aa188d4b402877a1068'
  OR EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_pages_v2 p WHERE p.task_id=original.id)
  OR EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_readbacks_v2 b WHERE b.task_id=original.id)
 THEN RAISE EXCEPTION 'Original EQR failure state changed; reconcile'; END IF;
 SELECT * INTO STRICT exc FROM astra_ingestion_v1.backfill_exceptions_v2 WHERE id=2282;
 IF exc.run_id<>r.id OR exc.task_id<>original.id OR exc.generation<>1 OR exc.page_no<>0
  OR exc.state<>'OPERATIONAL_ERROR' OR exc.code<>'SOURCE_HTTP_ERROR'
  OR exc.recorded_at<>'2026-10-30T13:21:50.913209Z'::timestamptz OR exc.next_retry_at IS NOT NULL
  OR encode(sha256(convert_to(exc.evidence::text,'UTF8')),'hex')<>'4f4a3f759c43e712ebb2c19c83cea027fe2cf6ba083b8fb1fe7d9fa61710b3e0'
  OR encode(sha256(convert_to(exc.message,'UTF8')),'hex')<>'606f1903c96dd615ced7093031e770c4ff6cc0ca71ad7370e863d9a0957dd379'
 THEN RAISE EXCEPTION 'Original EQR exception receipt changed; reconcile'; END IF;
 SELECT * INTO STRICT target FROM astra_ingestion_v1.backfill_tasks_v2
 WHERE id='backfill-plan-b02f70882418e225433c701a33576aa43da36817f158e1227366497287c7ba3e' FOR UPDATE;
 IF target.run_id<>r.id OR target.run_fence<>1 OR target.family<>'REF01' OR target.provider<>'Massive' OR target.kind<>'massive_reference'
  OR target.status<>'PENDING' OR target.priority<>40 OR target.owner IS NOT NULL OR target.lease_until IS NOT NULL
  OR target.generation<>0 OR target.attempts<>0 OR target.page_attempts<>0 OR target.requests_reserved<>0 OR target.records_committed<>0
  OR target.page_no<>0 OR target.cursor IS NOT NULL OR target.attempt_deadline IS NOT NULL OR cardinality(target.dependencies)<>0
  OR target.next_retry_at>clock_timestamp()
  OR encode(sha256(convert_to(target.scope::text,'UTF8')),'hex')<>'b00128012f223a24d0d6fe72529351960287183a5eda7d505529e6a89e65ea5f'
  OR EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_pages_v2 p WHERE p.task_id=target.id)
  OR EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_exceptions_v2 e WHERE e.task_id=target.id)
 THEN RAISE EXCEPTION 'Existing alternative task changed or is already attempted; reconcile'; END IF;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_provider_dependencies_v2 d WHERE d.run_id=r.id AND d.provider='Massive' AND d.state='AVAILABLE')
  OR NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_workers_v2 w WHERE w.observed_at>clock_timestamp()-interval '15 minutes'
   AND w.source_revision='3ee4db2a79c081ffb65ef0d7ec2a04228d69fb1d' AND w.supported_kinds ? 'massive_reference')
 THEN RAISE EXCEPTION 'Current existing Massive worker capability unavailable'; END IF;
 definition_before:=astra_ingestion_v1.backfill_task_definition_sha256_v2(target);
 assignment:=jsonb_build_object(
  'request_id',request_id,'state','EXECUTABLE_EXISTING_TASK_ASSIGNED','assigned_at',clock_timestamp(),
  'owner',r.metadata->>'implementation_owner','run_fence',r.fence,'same_controller',true,
  'authority_ref','CURRENT_USER_INSTRUCTION_ADD_EQR_EXCEPTION2282_WITHOUT_DISPLACING_CONTENTION',
  'original_exception_id',2282,'original_task_id',original.id,'original_exception_recorded_at',exc.recorded_at,
  'original_exception_evidence_sha256','4f4a3f759c43e712ebb2c19c83cea027fe2cf6ba083b8fb1fe7d9fa61710b3e0',
  'original_task_sha256',encode(sha256(convert_to(to_jsonb(original)::text,'UTF8')),'hex'),
  'member_id','CIK:0000906107','anchor_ticker','EQR','family','REF01',
  'recovery_task_id',target.id,'existing_task_reused',true,'recovery_provider','Massive',
  'endpoint_path','/v3/reference/tickers/EQR','asof','2026-07-31',
  'recovery_scope_sha256','b00128012f223a24d0d6fe72529351960287183a5eda7d505529e6a89e65ea5f',
  'task_definition_sha256',definition_before,'previous_priority',40,'execution_priority',9,
  'existing_execution_bounds',jsonb_build_object('attempt_deadline_seconds',300,'claim_lease_seconds_minimum',30,'claim_lease_seconds_maximum',300,'maximum_page_attempts',8,
    'provider_rate_limit_unchanged',true,'no_new_task_or_worker',true,'no_rpc_or_provider_replay_by_this_assignment',true),
  'next_executable_step','Existing worker claims this unchanged dated reference task, reserves within existing pacing, uses approved relay, commits native response, and performs independent hash/count readback.',
  'verification_step','Read the task/page/readback/relay receipt; compare supplied CIK and security identifiers to the fixed member evidence; retain any conflict or missing field as uncertainty. A dated reference success does not establish current Alpaca asset UUID or full-period identity.',
  'failure_step','Retain any new failure and existing attempt accounting. Reconcile its exact class and already-planned dated/retained routes before another material recovery; do not label404as provider absence or use an unapproved endpoint.',
  'identity_policy','UNRESOLVED_PROVIDER_ANCHOR_PRESERVED_UNTIL_EXISTING_EVIDENCE_CRITERIA_PASS',
  'original_failure_preserved',true,'new_source_subscription_or_security_grant',false,
  'contention_repair_preserved',true,'successor_task_id','6ae2a4c96bbc819182133e17e9b7f779');
 UPDATE astra_ingestion_v1.backfill_tasks_v2 SET priority=9 WHERE id=target.id RETURNING * INTO STRICT target_after;
 IF (to_jsonb(target_after)-'priority') IS DISTINCT FROM (to_jsonb(target)-'priority')
  OR astra_ingestion_v1.backfill_task_definition_sha256_v2(target_after) IS DISTINCT FROM definition_before
 THEN RAISE EXCEPTION 'Unexpected alternative task change; rollback assignment'; END IF;
 UPDATE astra_ingestion_v1.backfill_runs_v2 SET metadata=jsonb_set(metadata,'{implementation_remediation_queue}',
  COALESCE(metadata->'implementation_remediation_queue','{}')||jsonb_build_object(queue_key,assignment),true)
 WHERE id=r.id RETURNING * INTO STRICT r_after;
 IF (to_jsonb(r_after)-'metadata') IS DISTINCT FROM (to_jsonb(r)-'metadata')
  OR (r_after.metadata-'implementation_remediation_queue') IS DISTINCT FROM (r.metadata-'implementation_remediation_queue')
  OR (SELECT to_jsonb(t) FROM astra_ingestion_v1.backfill_tasks_v2 t WHERE t.id=original.id) IS DISTINCT FROM to_jsonb(original)
  OR (SELECT to_jsonb(e) FROM astra_ingestion_v1.backfill_exceptions_v2 e WHERE e.id=2282) IS DISTINCT FROM to_jsonb(exc)
  OR (r.metadata->>'implementation_lease_until')::timestamptz<=clock_timestamp()
 THEN RAISE EXCEPTION 'Original evidence, counters, other work or ownership changed; rollback assignment'; END IF;
 INSERT INTO astra_ingestion_v1.backfill_audit_v2(run_id,task_id,generation,action,source_revision,evidence)
 VALUES(r.id,original.id,original.generation,'REMEDIATION_RECOVERY_ASSIGNED','a3bc0520e624054b278e46682b04cebb33e9b677',assignment);
END $eqr_recovery$;
SELECT id,action,task_id,recorded_at,evidence
FROM astra_ingestion_v1.backfill_audit_v2
WHERE run_id='fixed3000-20250901-20260731-v1-20261030'
 AND evidence->>'request_id'='v74-eqr-ref01-exception2282-existing-massive-target-end';
COMMIT;
