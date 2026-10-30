SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $reconcile$
DECLARE
 r astra_ingestion_v1.backfill_runs_v2;
 t astra_ingestion_v1.backfill_tasks_v2;
 p astra_ingestion_v1.backfill_pages_v2;
 b astra_ingestion_v1.backfill_readbacks_v2;
 failure_id bigint;
 created_readback boolean:=false;
BEGIN
 IF current_setting('statement_timeout')<>'8s' OR current_setting('lock_timeout')<>'3s' OR current_setting('transaction_read_only')<>'off' THEN RAISE EXCEPTION 'Readback reconciliation requires bounded writable transaction settings'; END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(706314020261028);
 IF encode(sha256(convert_to(pg_get_functiondef('astra_ingestion_v1.backfill_recheck_page_v2(text,integer)'::regprocedure),'UTF8')),'hex')<>'0ccd4018d16e3ed3932176d2886fe78c2c1b442d70473d71e137d86e7b6dfb37'
 OR encode(sha256(convert_to(pg_get_functiondef('astra_ingestion_v1.backfill_page_rows_v2(text,integer)'::regprocedure),'UTF8')),'hex')<>'e0d0a4bceb9f107c00f770546ef0a200ccb9dd7ca48df01c9c821569ac3b897c'
 OR encode(sha256(convert_to(pg_get_functiondef('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure),'UTF8')),'hex')<>'28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44'
 OR encode(sha256(convert_to(pg_get_functiondef('astra_ingestion_v1.rpc_dispatch(text,jsonb)'::regprocedure),'UTF8')),'hex')<>'a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520' THEN
  RAISE EXCEPTION 'Readback reconciliation source changed';
 END IF;
 SELECT * INTO STRICT r FROM astra_ingestion_v1.backfill_runs_v2 WHERE id='fixed3000-20250901-20260731-v1-20261030' FOR UPDATE;
 IF r.status<>'ACTIVE' OR r.fence<>1 OR r.cohort_sha256<>'2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
 OR r.metadata->>'implementation_owner' IS DISTINCT FROM 'root-replacement-20261030T042603Z'
 OR NOT COALESCE((r.metadata->>'implementation_lease_until')::timestamptz>clock_timestamp(),false) THEN
  RAISE EXCEPTION 'Readback reconciliation owner, lease, run or cohort changed';
 END IF;
 SELECT * INTO STRICT t FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id='backfill-plan-28241a0a18d98d6b64c6a8e4a14027c1fe08a945048b089a02522b9cb52f42e2' FOR UPDATE;
 IF t.run_id<>r.id OR t.run_fence<>r.fence OR t.generation<>1 OR t.kind<>'massive_news' OR t.family<>'N01' THEN
  RAISE EXCEPTION 'Exact readback task binding changed';
 END IF;
 SELECT * INTO STRICT p FROM astra_ingestion_v1.backfill_pages_v2 WHERE task_id=t.id AND page_no=0;
 IF p.run_id<>r.id OR p.generation<>1 OR p.run_fence<>1 OR p.provider<>'Massive' OR p.body_sha256<>'255ec70d01487893dfeeaaccf5dc9638adc325ad71c0fc13986fa7187b600a9b'
 OR p.record_count<>100 OR octet_length(p.raw_body)<>246966 OR p.committed_at<>'2026-10-30T14:00:00.061968Z'::timestamptz
 OR p.committed_at>=transaction_timestamp() THEN
  RAISE EXCEPTION 'Exact committed page or subsequent-transaction condition changed';
 END IF;
 SELECT id INTO STRICT failure_id FROM astra_ingestion_v1.backfill_audit_v2
 WHERE run_id=r.id AND task_id=t.id AND action='READBACK_FAILURE' AND evidence->>'page_no'='0'
 AND evidence->>'sqlstate'='AI005' AND evidence->>'reason'='Independent readback requires a subsequent transaction';
 SELECT * INTO b FROM astra_ingestion_v1.backfill_readbacks_v2 WHERE task_id=t.id AND page_no=0;
 IF NOT FOUND THEN
  PERFORM astra_ingestion_v1.backfill_recheck_page_v2(t.id,0);
  created_readback:=true;
  SELECT * INTO STRICT b FROM astra_ingestion_v1.backfill_readbacks_v2 WHERE task_id=t.id AND page_no=0;
 END IF;
 IF b.run_id<>r.id OR b.body_sha256<>p.body_sha256 OR b.readback_sha256<>p.body_sha256 OR b.expected_records<>100 OR b.actual_records<>100 THEN
  RAISE EXCEPTION 'Independent readback integrity result differs';
 END IF;
 INSERT INTO astra_ingestion_v1.backfill_audit_v2(run_id,task_id,generation,action,source_revision,evidence)
 SELECT r.id,t.id,t.generation,'READBACK_FAILURE_RECONCILED','536bb850cf5c5653b4865e63db3f20f50a6769a1',
 jsonb_build_object('page_no',0,'original_failure_id',failure_id,'reason','SUBSEQUENT_TRANSACTION_CONDITION_NOW_SATISFIED','body_sha256',p.body_sha256,'expected_records',100,'actual_records',100,'created_readback',created_readback,'original_failure_retained',true,'verifier_unchanged',true,'scope_or_counters_reset',false,'same_controller',true,'request_id','v72-exact-readback-transaction-reconciliation')
 WHERE NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_audit_v2 a WHERE a.task_id=t.id AND a.action='READBACK_FAILURE_RECONCILED' AND a.evidence->>'original_failure_id'=failure_id::text);
END $reconcile$;
SELECT clock_timestamp() AS observed_at,b.task_id,b.page_no,b.body_sha256,b.readback_sha256,b.expected_records,b.actual_records,b.verified_at,
 (SELECT jsonb_agg(jsonb_build_object('id',a.id,'action',a.action,'recorded_at',a.recorded_at,'evidence',a.evidence) ORDER BY a.id) FROM astra_ingestion_v1.backfill_audit_v2 a WHERE a.task_id=b.task_id AND a.action='READBACK_FAILURE_RECONCILED') AS reconciliation
FROM astra_ingestion_v1.backfill_readbacks_v2 b
WHERE b.task_id='backfill-plan-28241a0a18d98d6b64c6a8e4a14027c1fe08a945048b089a02522b9cb52f42e2' AND b.page_no=0;
