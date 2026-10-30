-- Same ten original selectors, compact source counts only, no helper invocation.
-- Separate snapshot from the selector profile; candidate identities may advance.
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL transaction_read_only=on;
SET LOCAL transaction_isolation='repeatable read';
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $profile$
DECLARE source_guard_record record; candidate_result jsonb; results jsonb:='[]'; started timestamptz:=clock_timestamp();
BEGIN
 IF current_setting('transaction_read_only')<>'on'
  OR current_setting('transaction_isolation')<>'repeatable read'
  OR current_setting('statement_timeout')<>'8s' OR current_setting('lock_timeout')<>'3s' THEN
  RAISE EXCEPTION 'Maintenance selector profile requires explicit bounded read-only repeatable-read settings';
 END IF;
 FOR source_guard_record IN SELECT * FROM (VALUES
  ('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)','28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44'),
  ('astra_ingestion_v1.rpc_dispatch(text,jsonb)','a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520'),
  ('astra_ingestion_v1.backfill_maintain_v2(integer)','cd10046d9c9aa15e8bc66724d1258d95151364ffeee9070d761c4f7d930b5859'),
  ('astra_ingestion_v1.monitor_tick_v1()','875c017ecf73df15163d15d3f9129b4507235dc893ccb4233d0a435154389057'),
  ('astra_ingestion_v1.backfill_breadth_project_pending_v2(integer)','65c981bd15a70f01d35eefc06a3807c7e6cfa1120a4b149ba3829951a63cc0d0'),
  ('astra_ingestion_v1.backfill_contract_maintain_v2()','52007f177dca38faf48fab8773936173519dcbfa54af896b5ef6f902ad64c748'),
  ('astra_ingestion_v1.backfill_identity_discover_pending_v2()','faf5e83a8f7baf717cfd9054948ed62a8fbda7aa432a1f671d895fe77db37618'),
  ('astra_ingestion_v1.backfill_identity_refresh_pending_v2(integer)','87ebac87ea08bea09b98f01ae123ed698e8252bcd6ff6abeb1cec3abf6ba5e25'),
  ('astra_ingestion_v1.backfill_minute_account_pending_v2(integer)','49cc9131c989de8f2da0926a2d1312bee7262f2e7f63c7a800219257af1632f2'),
  ('astra_ingestion_v1.backfill_nonminute_project_pending_v2(integer)','ceb1889732da767e8815741a792347ccb91c33c53acd38eeff36f9176d063cec'),
  ('astra_ingestion_v1.backfill_recheck_page_v2(text,integer)','0ccd4018d16e3ed3932176d2886fe78c2c1b442d70473d71e137d86e7b6dfb37'),
  ('astra_ingestion_v1.backfill_s02_maintain_v2()','40827de08ca59d1470a02aceff6ccc249e6b43bb8ef13ff39eddffa673e78939'),
  ('astra_ingestion_v1.backfill_shared_maintain_v2(integer)','5da488f3e44e2521b64f58230b2bc6db3c34800ae4ac259166f4dc223c8ad2be'),
  ('astra_ingestion_v1.backfill_try_finalize_v2(text)','f8f9ef6d8d9ada232b132170bde9922397a2b247dbc7e4b391cbca57b67b7063')
 ) s(signature,expected_sha256) LOOP
  IF encode(sha256(convert_to(pg_get_functiondef(source_guard_record.signature::regprocedure),'UTF8')),'hex')<>source_guard_record.expected_sha256 THEN
   RAISE EXCEPTION 'Maintenance selector source changed; reconcile before diagnosis';
  END IF;
 END LOOP;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2
  WHERE id='fixed3000-20250901-20260731-v1-20261030' AND status='ACTIVE' AND fence=1
   AND cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
   AND metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
   AND (metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()) THEN
  RAISE EXCEPTION 'Maintenance selector run, owner, lease, fence or fixed cohort changed';
 END IF;

 WITH
q0 AS MATERIALIZED(SELECT pg.task_id,pg.page_no,pg.run_id FROM astra_ingestion_v1.backfill_pages_v2 pg JOIN astra_ingestion_v1.backfill_tasks_v2 t ON t.id=pg.task_id
  WHERE t.family='D03' AND lower(t.provider)='derived'
   AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_breadth_projected_pages_v2 q WHERE q.task_id=pg.task_id AND q.page_no=pg.page_no)
   AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_audit_v2 a WHERE a.task_id=pg.task_id AND a.action='D03_PROJECTION_FAILURE' AND a.evidence->>'page_no'=pg.page_no::text)
  ORDER BY pg.committed_at,pg.task_id,pg.page_no LIMIT GREATEST(1,LEAST(2,8))),
q1 AS MATERIALIZED(SELECT DISTINCT v.task_id FROM astra_ingestion_v1.backfill_readbacks_v2 v
  JOIN astra_ingestion_v1.backfill_tasks_v2 t ON t.id=v.task_id
  LEFT JOIN astra_ingestion_v1.backfill_minute_projection_v2 s ON s.task_id=v.task_id
  WHERE t.family IN('P01','P02') AND t.kind IN('retained_reuse','alpaca_stock_bars') AND COALESCE(t.scope->>'timeframe','1Min')='1Min'
   AND (s.task_id IS NULL OR s.last_verified_page<v.page_no) LIMIT GREATEST(1,LEAST(2,8))),
q2 AS MATERIALIZED(SELECT d.run_id,d.member_id FROM astra_ingestion_v1.backfill_identity_discovered_members_v2 d
 JOIN astra_ingestion_v1.backfill_runs_v2 r ON r.id=d.run_id WHERE NOT d.complete AND r.status='ACTIVE'
 ORDER BY d.observed_at,d.run_id,d.member_id LIMIT 1),
q3 AS MATERIALIZED(SELECT x.* FROM astra_ingestion_v1.backfill_identity_refresh_v2 x JOIN astra_ingestion_v1.backfill_runs_v2 r ON r.id=x.run_id
  WHERE r.status='ACTIVE' AND x.ready_after<=clock_timestamp()
   AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_identity_source_members_v2 sm JOIN astra_ingestion_v1.backfill_tasks_v2 st ON st.id=sm.task_id
    WHERE sm.run_id=x.run_id AND sm.member_id=x.member_id AND st.status IN('PENDING','RUNNING','RETRY_WAIT'))
  ORDER BY x.ready_after,x.run_id,x.member_id LIMIT 1),
q4 AS MATERIALIZED(SELECT verified_at,task_id,page_no FROM astra_ingestion_v1.backfill_readbacks_v2
  WHERE (verified_at,task_id,page_no)>(SELECT c.verified_at,c.task_id,c.page_no FROM astra_ingestion_v1.backfill_nonminute_projection_cursor_v2 c WHERE singleton)
  ORDER BY verified_at,task_id,page_no LIMIT GREATEST(1,LEAST(2,8))),
q5 AS MATERIALIZED(SELECT verified_at,task_id,page_no FROM astra_ingestion_v1.backfill_readbacks_v2 WHERE (verified_at,task_id,page_no)>(SELECT c.verified_at,c.task_id,c.page_no FROM astra_ingestion_v1.backfill_s02_projection_cursor_v2 c WHERE singleton)
  ORDER BY verified_at,task_id,page_no LIMIT 8),
q6 AS MATERIALIZED(SELECT verified_at,task_id,page_no FROM astra_ingestion_v1.backfill_readbacks_v2
  WHERE (verified_at,task_id,page_no)>(SELECT c.verified_at,c.task_id,c.page_no FROM astra_ingestion_v1.backfill_shared_cursor_v2 c WHERE singleton) ORDER BY verified_at,task_id,page_no LIMIT GREATEST(1,LEAST(4,8))),
q7 AS MATERIALIZED(SELECT b.verified_at,b.task_id,b.page_no,t.kind FROM astra_ingestion_v1.backfill_readbacks_v2 b JOIN astra_ingestion_v1.backfill_tasks_v2 t ON t.id=b.task_id
  WHERE (b.verified_at,b.task_id,b.page_no)>(SELECT c.verified_at,c.task_id,c.page_no FROM astra_ingestion_v1.backfill_contract_readback_cursor_v2 c WHERE singleton) ORDER BY b.verified_at,b.task_id,b.page_no LIMIT 32),
q8 AS MATERIALIZED(SELECT e.task_id,e.page_no FROM astra_ingestion_v1.backfill_contract_enumeration_v2 e JOIN astra_ingestion_v1.backfill_readbacks_v2 b USING(task_id,page_no)
   WHERE e.run_id=(SELECT id FROM astra_ingestion_v1.backfill_runs_v2 WHERE status='ACTIVE' ORDER BY created_at LIMIT 1) AND e.processed_at IS NULL ORDER BY e.task_id,e.page_no LIMIT 1),
q9 AS MATERIALIZED(SELECT pg.task_id,pg.page_no,pg.run_id FROM astra_ingestion_v1.backfill_pages_v2 pg
  JOIN astra_ingestion_v1.backfill_runs_v2 rr ON rr.id=pg.run_id
  WHERE rr.status IN ('ACTIVE','PARTIAL_OPERATIONAL_FAILURE','BLOCKED_EXTERNAL') AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_readbacks_v2 v WHERE v.task_id=pg.task_id AND v.page_no=pg.page_no)
   AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_audit_v2 a WHERE a.task_id=pg.task_id AND a.action='READBACK_FAILURE' AND a.evidence->>'page_no'=pg.page_no::text)
  ORDER BY pg.committed_at,pg.task_id,pg.page_no LIMIT GREATEST(1,LEAST(2,8))),
 candidates AS MATERIALIZED(SELECT 'BREADTH_PENDING'::text component,task_id,page_no page_no FROM q0 UNION ALL SELECT 'MINUTE_ACCOUNT_PENDING'::text component,task_id,NULL::integer page_no FROM q1 UNION ALL SELECT 'NONMINUTE_CURSOR'::text component,task_id,page_no page_no FROM q4 UNION ALL SELECT 'S02_CURSOR'::text component,task_id,page_no page_no FROM q5 UNION ALL SELECT 'SHARED_CURSOR'::text component,task_id,page_no page_no FROM q6 UNION ALL SELECT 'CONTRACT_CURSOR'::text component,task_id,page_no page_no FROM q7 UNION ALL SELECT 'CONTRACT_ENUM_PENDING'::text component,task_id,page_no page_no FROM q8 UNION ALL SELECT 'MISSING_READBACK'::text component,task_id,page_no page_no FROM q9),
 page_metadata AS (
  SELECT c.component,c.task_id,c.page_no,t.run_id,t.family,t.provider,t.kind,t.status,
   COALESCE(t.scope->>'timeframe','') timeframe,
   a.archived_pages,a.verified_pages,a.source_records,a.raw_bytes,a.max_page_no,a.max_verified_page,
   a.earliest_committed_at,a.latest_committed_at,
   mp.last_verified_page minute_projection_last_page,
   CASE WHEN c.page_no IS NOT NULL THEN EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_shared_pages_v2 s
    WHERE s.task_id=c.task_id AND s.page_no=c.page_no) ELSE NULL END shared_page_already_projected
  FROM candidates c JOIN astra_ingestion_v1.backfill_tasks_v2 t ON t.id=c.task_id
  LEFT JOIN astra_ingestion_v1.backfill_minute_projection_v2 mp ON mp.task_id=c.task_id
  CROSS JOIN LATERAL (
   SELECT count(*) archived_pages,count(b.task_id) verified_pages,COALESCE(sum(pg.record_count),0) source_records,
    COALESCE(sum(octet_length(pg.raw_body)),0) raw_bytes,max(pg.page_no) max_page_no,max(b.page_no) max_verified_page,
    min(pg.committed_at) earliest_committed_at,max(pg.committed_at) latest_committed_at
   FROM astra_ingestion_v1.backfill_pages_v2 pg
   LEFT JOIN astra_ingestion_v1.backfill_readbacks_v2 b ON b.task_id=pg.task_id AND b.page_no=pg.page_no
   WHERE pg.task_id=c.task_id AND (c.page_no IS NULL OR pg.page_no=c.page_no)
    AND (c.component<>'MINUTE_ACCOUNT_PENDING' OR b.task_id IS NOT NULL)
  ) a
 )
 SELECT jsonb_build_object('schema','astra.maintenance-candidate-metadata/1','observed_at',clock_timestamp(),
  'complete',true,'selector_count',10,'maintenance_functions_invoked',false,'advisory_lock_acquired',false,
  'raw_page_bodies_returned',false,'transaction_read_only',current_setting('transaction_read_only'),
  'transaction_isolation',current_setting('transaction_isolation'),
  'page_candidates',COALESCE((SELECT jsonb_agg(to_jsonb(m) ORDER BY component,task_id,page_no) FROM page_metadata m),'[]'::jsonb),
  'identity_discovery_candidates',COALESCE((SELECT jsonb_agg(jsonb_build_object('run_id',run_id,'member_id',member_id)) FROM q2),'[]'::jsonb),
  'identity_refresh_candidates',COALESCE((SELECT jsonb_agg(jsonb_build_object('run_id',run_id,'member_id',member_id,
    'ready_after',ready_after,'after_task_id',after_task_id,'earliest_date',earliest_date,'latest_date',latest_date)) FROM q3),'[]'::jsonb),
  'current_run_finalizer_gates',(SELECT jsonb_build_object('status',r.status,'planning_complete',r.metadata->'planning_complete',
    'identity_discovery_pending',EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_identity_discovered_members_v2 d WHERE d.run_id=r.id AND NOT d.complete),
    'identity_refresh_pending',EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_identity_refresh_v2 f WHERE f.run_id=r.id),
    'plan_manifest_exists',EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_plan_manifests_v2 f WHERE f.run_id=r.id),
    'runnable_work_exists',EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 t WHERE t.run_id=r.id AND t.status IN('PENDING','RUNNING','RETRY_WAIT')))
   FROM astra_ingestion_v1.backfill_runs_v2 r WHERE r.id='fixed3000-20250901-20260731-v1-20261030')
 ) INTO candidate_result;
 IF octet_length(candidate_result::text)>60000 THEN RAISE EXCEPTION 'Maintenance candidate metadata exceeds bounded result size';END IF;
 RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='ASTRA_MAINTENANCE_CANDIDATES_V71:'||candidate_result::text;
END $profile$;
ROLLBACK;
