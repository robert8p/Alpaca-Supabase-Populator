CREATE OR REPLACE FUNCTION astra_ingestion_v1.backfill_maintain_v2(p_limit integer DEFAULT 2)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
 SET statement_timeout TO '8s'
 SET lock_timeout TO '2s'
AS $function$
DECLARE p record; r record; v_readbacks integer:=0; v_errors integer:=0; v_final jsonb:='[]'; v_result jsonb;
BEGIN
 -- backfill_bounded_maintenance_wait_v2: existing two-second lock timeout.
 BEGIN
  PERFORM pg_advisory_xact_lock(706314020261028);
 EXCEPTION WHEN lock_not_available THEN
  RETURN jsonb_build_object('state','BUSY','reason','BOUNDED_WORKER_LOCK_WAIT_EXHAUSTED');
 END;
 PERFORM astra_ingestion_v1.backfill_breadth_project_pending_v2(2);
 PERFORM astra_ingestion_v1.backfill_minute_account_pending_v2(2);
 PERFORM astra_ingestion_v1.backfill_identity_discover_pending_v2();
 PERFORM astra_ingestion_v1.backfill_identity_refresh_pending_v2(2);
 PERFORM astra_ingestion_v1.backfill_nonminute_project_pending_v2(2);
 PERFORM astra_ingestion_v1.backfill_s02_maintain_v2();
 PERFORM astra_ingestion_v1.backfill_shared_maintain_v2(4);
 PERFORM astra_ingestion_v1.backfill_contract_maintain_v2();
 FOR p IN SELECT pg.task_id,pg.page_no,pg.run_id FROM astra_ingestion_v1.backfill_pages_v2 pg
  JOIN astra_ingestion_v1.backfill_runs_v2 rr ON rr.id=pg.run_id
  WHERE rr.status IN ('ACTIVE','PARTIAL_OPERATIONAL_FAILURE','BLOCKED_EXTERNAL') AND pg.committed_at<transaction_timestamp() AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_readbacks_v2 v WHERE v.task_id=pg.task_id AND v.page_no=pg.page_no)
   AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_audit_v2 a WHERE a.task_id=pg.task_id AND a.action='READBACK_FAILURE' AND a.evidence->>'page_no'=pg.page_no::text)
  ORDER BY pg.committed_at,pg.task_id,pg.page_no LIMIT GREATEST(1,LEAST(p_limit,8))
 LOOP
  BEGIN
   PERFORM astra_ingestion_v1.backfill_recheck_page_v2(p.task_id,p.page_no);v_readbacks:=v_readbacks+1;
  EXCEPTION WHEN OTHERS THEN
   v_errors:=v_errors+1;
   IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_audit_v2 a WHERE a.task_id=p.task_id AND a.action='READBACK_FAILURE' AND a.evidence->>'page_no'=p.page_no::text) THEN
    INSERT INTO astra_ingestion_v1.backfill_audit_v2(run_id,task_id,action,evidence) VALUES(p.run_id,p.task_id,'READBACK_FAILURE',jsonb_build_object('page_no',p.page_no,'sqlstate',SQLSTATE,'reason',left(SQLERRM,500)));
   END IF;
  END;
 END LOOP;
 FOR r IN SELECT id FROM astra_ingestion_v1.backfill_runs_v2 WHERE status IN ('ACTIVE','PARTIAL_OPERATIONAL_FAILURE','BLOCKED_EXTERNAL') LOOP
  v_result:=astra_ingestion_v1.backfill_try_finalize_v2(r.id);v_final:=v_final||jsonb_build_array(jsonb_build_object('run_id',r.id,'result',v_result));
 END LOOP;
 RETURN jsonb_build_object('state','OBSERVED','verified_pages',v_readbacks,'readback_errors',v_errors,'runs',v_final);
END $function$
