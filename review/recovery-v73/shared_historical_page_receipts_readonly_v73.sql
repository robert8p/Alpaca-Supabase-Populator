-- Historical shared-page receipt lookup only; no helper, provider, gate or mutation.
-- At most eight safe rows per fixed sample window; a ninth row detects overflow.
-- Timestamp containment is temporal association, not backend identity or causal timing.
BEGIN;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
DO $shared_historical_receipts$
DECLARE
 v_definition text; v_metadata jsonb; v_run jsonb; v_member_count bigint;
 v_columns jsonb; v_default text; v_windows jsonb:='[]'; v_result jsonb;
 v_rows jsonb; v_bounded_count integer; v_bad_metadata integer; g record; p jsonb;
 v_pins constant jsonb := $source_pins$[{"signature":"astra_ingestion_v1.backfill_maintain_v2(integer)","sha256":"6c880114a645c8a9167d5260c4aeabf58a10617c4244cf0340be1d6cf4bf0ce7","metadata":{"acl":["astra_ingestion_rpc_owner_v1=X/astra_ingestion_rpc_owner_v1","astra_ingestion_monitor_owner_v1=X/astra_ingestion_rpc_owner_v1"],"owner":"15985999","config":["search_path=\"\"","statement_timeout=8s","lock_timeout=2s"],"security_definer":true}},{"signature":"astra_ingestion_v1.rpc_dispatch(text,jsonb)","sha256":"a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520","metadata":{"acl":["astra_ingestion_rpc_owner_v1=X/astra_ingestion_rpc_owner_v1","anon=X/astra_ingestion_rpc_owner_v1"],"owner":"15985999","config":["search_path=\"\"","statement_timeout=10s","lock_timeout=3s"],"security_definer":true}},{"signature":"astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)","sha256":"28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44","metadata":{"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"owner":"16388","config":["search_path=\"\""],"security_definer":false}},{"signature":"astra_ingestion_v1.monitor_tick_v1()","sha256":"875c017ecf73df15163d15d3f9129b4507235dc893ccb4233d0a435154389057","metadata":{"acl":["astra_ingestion_monitor_owner_v1=X/astra_ingestion_monitor_owner_v1","postgres=X/astra_ingestion_monitor_owner_v1"],"owner":"15990376","config":["search_path=\"\"","statement_timeout=8s","lock_timeout=2s"],"security_definer":true}},{"signature":"astra_ingestion_v1.backfill_shared_maintain_v2(integer)","sha256":"5da488f3e44e2521b64f58230b2bc6db3c34800ae4ac259166f4dc223c8ad2be","metadata":{"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"owner":"16388","config":["search_path=\"\"","statement_timeout=15s"],"security_definer":true}},{"signature":"astra_ingestion_v1.backfill_shared_project_v2(text,integer)","sha256":"78ceb1e794e9725ae8d0365ec92081c769853fa1c8345ab96c4adaf6e786fb9d","metadata":{"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"owner":"16388","config":["search_path=\"\"","statement_timeout=12s"],"security_definer":true}}]$source_pins$::jsonb;
BEGIN
 IF current_setting('statement_timeout')<>'8s' OR current_setting('lock_timeout')<>'3s'
  OR current_setting('transaction_read_only')<>'on'
  OR current_setting('transaction_isolation')<>'repeatable read' THEN
  RAISE EXCEPTION 'Historical shared lookup requires read-only repeatable-read 8s/3s bounds';
 END IF;
 FOR p IN SELECT value FROM jsonb_array_elements(v_pins) LOOP
  SELECT pg_get_functiondef(f.oid),jsonb_build_object('acl',f.proacl,'owner',f.proowner::text,
   'config',f.proconfig,'security_definer',f.prosecdef) INTO STRICT v_definition,v_metadata
  FROM pg_proc f WHERE f.oid=(p->>'signature')::regprocedure;
  IF encode(sha256(convert_to(v_definition,'UTF8')),'hex') IS DISTINCT FROM p->>'sha256'
   OR v_metadata IS DISTINCT FROM p->'metadata' THEN
   RAISE EXCEPTION 'Historical shared lookup source or metadata differs';
  END IF;
 END LOOP;
 SELECT jsonb_build_object('id',id,'status',status,'fence',fence,'cohort_sha256',cohort_sha256,
  'owner',metadata->>'implementation_owner','lease_until',metadata->>'implementation_lease_until')
 INTO STRICT v_run FROM astra_ingestion_v1.backfill_runs_v2
 WHERE id='fixed3000-20250901-20260731-v1-20261030';
 SELECT count(*) INTO v_member_count FROM astra_ingestion_v1.backfill_members_v2
 WHERE run_id='fixed3000-20250901-20260731-v1-20261030';
 IF v_run->>'owner' IS DISTINCT FROM 'root-replacement-20261030T042603Z'
  OR COALESCE((v_run->>'lease_until')::timestamptz>clock_timestamp(),false) IS NOT TRUE
  OR (v_run->>'fence')::bigint IS DISTINCT FROM 1
  OR v_run->>'cohort_sha256' IS DISTINCT FROM '2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
  OR v_member_count<>3000 THEN
  RAISE EXCEPTION 'Historical shared lookup owner, lease, fence, cohort or members differs';
 END IF;
 SELECT jsonb_object_agg(a.attname,jsonb_build_object('type',format_type(a.atttypid,a.atttypmod),'not_null',a.attnotnull))
 INTO v_columns FROM pg_attribute a WHERE a.attrelid='astra_ingestion_v1.backfill_shared_pages_v2'::regclass
  AND a.attnum>0 AND NOT a.attisdropped;
 IF v_columns IS DISTINCT FROM '{"task_id":{"type":"text","not_null":true},"page_no":{"type":"integer","not_null":true},"run_id":{"type":"text","not_null":true},"delivery_families":{"type":"text[]","not_null":true},"source_records":{"type":"integer","not_null":true},"projected_at":{"type":"timestamp with time zone","not_null":true}}'::jsonb THEN
  RAISE EXCEPTION 'Historical shared receipt schema differs';
 END IF;
 SELECT pg_get_expr(d.adbin,d.adrelid) INTO STRICT v_default FROM pg_attrdef d JOIN pg_attribute a
  ON a.attrelid=d.adrelid AND a.attnum=d.adnum
  WHERE a.attrelid='astra_ingestion_v1.backfill_shared_pages_v2'::regclass AND a.attname='projected_at';
 IF v_default NOT IN ('clock_timestamp()','pg_catalog.clock_timestamp()') THEN
  RAISE EXCEPTION 'Historical shared projection clock default differs';
 END IF;
 FOR g IN SELECT * FROM (VALUES
  (41::bigint,4599::integer,4068765::bigint,'2026-10-30 15:42:00.025984+00'::timestamptz,'2026-10-30 15:42:09.822799+00'::timestamptz,'2026-10-30 15:42:09.813373+00'::timestamptz,9778.570::numeric,5320.806::numeric),
  (42::bigint,4645::integer,4068767::bigint,'2026-10-30 15:44:00.029452+00'::timestamptz,'2026-10-30 15:44:02.770458+00'::timestamptz,'2026-10-30 15:44:02.762337+00'::timestamptz,2725.346::numeric,6.202::numeric)
 ) fixed(audit_id,backend_pid,cron_runid,cron_start,cron_end,audit_recorded_at,total_ms,shared_ms) LOOP
  IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_audit_v2 a
   WHERE a.id=g.audit_id AND a.run_id='fixed3000-20250901-20260731-v1-20261030'
    AND a.action='MAINTENANCE_PHASE_OBSERVATION_V73'
    AND a.source_revision='maintenance-global-phase-observation-v73-20261030T1545Z'
    AND a.evidence->>'probe_id'='maintenance-global-phase-observation-v73-20261030T1545Z'
    AND a.evidence->>'timing_scope'='GLOBAL_MAINTENANCE_BEFORE_TELEMETRY'
    AND a.evidence->'backend_pid'=to_jsonb(g.backend_pid)
    AND a.evidence->'total_ms'=to_jsonb(g.total_ms)
    AND a.evidence#>'{phases_ms,shared_ms}'=to_jsonb(g.shared_ms)
    AND a.recorded_at=g.audit_recorded_at)
   OR NOT EXISTS(SELECT 1 FROM cron.job_run_details c WHERE c.jobid=602 AND c.runid=g.cron_runid
    AND c.job_pid=g.backend_pid AND c.start_time=g.cron_start AND c.end_time=g.cron_end AND c.status='succeeded') THEN
   RAISE EXCEPTION 'Historical shared lookup fixed sample or unique cron evidence differs';
  END IF;
  WITH candidates AS MATERIALIZED(
   SELECT s.task_id,s.page_no,s.run_id,s.source_records,s.projected_at
   FROM astra_ingestion_v1.backfill_shared_pages_v2 s
   WHERE s.run_id='fixed3000-20250901-20260731-v1-20261030'
    AND s.projected_at>=g.cron_start AND s.projected_at<=g.audit_recorded_at
   ORDER BY s.projected_at,s.task_id,s.page_no LIMIT 9
  ), ranked AS MATERIALIZED(
   SELECT s.*,row_number() OVER(ORDER BY s.projected_at,s.task_id,s.page_no) ordinal FROM candidates s
  ), safe AS MATERIALIZED(
   SELECT s.ordinal,s.task_id,s.page_no,s.projected_at,s.source_records,t.family,t.provider,t.kind,
    pg.record_count,pg.source_bytes,pg.body_sha256,pg.records_sha256,pg.committed_at,
    b.actual_records,b.readback_sha256,b.verified_at,
    COALESCE(t.run_id=s.run_id AND pg.run_id=s.run_id AND b.run_id=s.run_id
     AND s.source_records=pg.record_count AND pg.record_count=b.actual_records
     AND b.expected_records=b.actual_records AND pg.body_sha256=b.body_sha256
     AND b.body_sha256=b.readback_sha256,false) stored_metadata_consistent
   FROM ranked s LEFT JOIN astra_ingestion_v1.backfill_tasks_v2 t ON t.id=s.task_id
   LEFT JOIN astra_ingestion_v1.backfill_pages_v2 pg ON pg.task_id=s.task_id AND pg.page_no=s.page_no
   LEFT JOIN astra_ingestion_v1.backfill_readbacks_v2 b ON b.task_id=s.task_id AND b.page_no=s.page_no
   WHERE s.ordinal<=8
  )
  SELECT (SELECT count(*) FROM candidates),COALESCE(jsonb_agg(to_jsonb(safe)-'ordinal' ORDER BY ordinal),'[]'),
   count(*) FILTER(WHERE NOT stored_metadata_consistent) INTO v_bounded_count,v_rows,v_bad_metadata FROM safe;
  v_windows:=v_windows||jsonb_build_array(jsonb_build_object(
   'audit_id',g.audit_id,'backend_pid',g.backend_pid,'cron_jobid',602,'cron_runid',g.cron_runid,
   'cron_start',g.cron_start,'cron_end',g.cron_end,'receipt_window_end',g.audit_recorded_at,
   'measured_maintain_ms',g.total_ms,'measured_shared_ms',g.shared_ms,
   'returned_rows',jsonb_array_length(v_rows),'bounded_match_count',v_bounded_count,
   'match_scan_limit',9,'output_limit',8,'overflow',v_bounded_count>8,
   'more_than_configured_four_page_batch',v_bounded_count>4,
   'stored_metadata_inconsistencies',v_bad_metadata,'temporal_association_only',true,
   'page_backend_identity_proven',false,'receipts',v_rows));
 END LOOP;
 IF COALESCE((v_run->>'lease_until')::timestamptz>clock_timestamp(),false) IS NOT TRUE THEN
  RAISE EXCEPTION 'Historical shared lookup lease expired during read';
 END IF;
 v_result:=jsonb_build_object('schema','astra.shared-historical-page-receipts/1','observed_at',clock_timestamp(),
  'complete',true,'run',v_run,'member_count',v_member_count,'source_state','RESTORED_BASELINE_6C880',
  'source_pin_count',jsonb_array_length(v_pins),'source_and_metadata_pins_verified',true,
  'shared_receipt_schema_and_clock_default_verified',true,
  'transaction_read_only',current_setting('transaction_read_only'),'transaction_isolation',current_setting('transaction_isolation'),
  'statement_timeout',current_setting('statement_timeout'),'lock_timeout',current_setting('lock_timeout'),
  'raw_payload_or_request_data_returned',false,'helpers_invoked',false,'windows',v_windows,
  'interpretation',jsonb_build_array(
   'Fixed sample audit rows and completed cron PID/interval evidence are rechecked, but shared page receipts have no backend identity.',
   'Projection clock containment is a temporal candidate association only; it does not allocate shared-phase time to an individual page or query.',
   'More than four matches cannot all be attributed to one configured four-page maintain batch; more than eight matches is explicitly truncated.',
   'Zero receipts does not establish zero shared work: separate-family and already-projected paths produce no new receipt.',
   'These are stored count/hash consistency checks, not a new raw-body rehash, acquisition count or current cursor reconstruction.'));
 IF octet_length(v_result::text)>24000 THEN RAISE EXCEPTION 'Historical shared lookup result exceeded bounded output'; END IF;
 RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='SHARED_HISTORICAL_PAGE_RECEIPTS_V73 '||v_result::text;
END $shared_historical_receipts$;
ROLLBACK;
