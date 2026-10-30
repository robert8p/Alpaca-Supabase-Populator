-- Three unchanged pure SELECTs from current contract admission.
-- The retained immutable page is fixed; current registry state may have advanced.
-- This measures direct-role reads, excluding inserts/triggers, locks and cron cached plans.
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL transaction_read_only=on;
SET LOCAL transaction_isolation='repeatable read';
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $profile$
DECLARE source_guard_record record; candidate_result jsonb; v_task astra_ingestion_v1.backfill_tasks_v2; v_rows jsonb; v_plan jsonb; v_nodes jsonb; v_phase record; v_pending boolean; v_source_hash text; v_started timestamptz; v_parse_ms numeric; results jsonb:='[]'; started timestamptz:=clock_timestamp();
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
  ('astra_ingestion_v1.backfill_try_finalize_v2(text)','f8f9ef6d8d9ada232b132170bde9922397a2b247dbc7e4b391cbca57b67b7063'),
  ('astra_ingestion_v1.backfill_contract_admit_page_v2(text,integer)','f72da3cb88f30d3ac66e2e20a51bd2dfd55195bc76ae2997decdc6b10020d7c1'),
  ('astra_ingestion_v1.backfill_page_rows_v2(text,integer)','e0d0a4bceb9f107c00f770546ef0a200ccb9dd7ca48df01c9c821569ac3b897c'),
  ('astra_ingestion_v1.backfill_contract_key_v2(text,timestamptz,timestamptz,text,text)','d5349e3ec4e084dcd53a0ace556e81afe1f8f76b94c6f358cf8e493238a89f90'),
  ('astra_ingestion_v1.backfill_contract_register_child_v2(text)','c5756d3872e552716bffb575025942500946e0e0a8a19c29ef29326b8bc78795'),
  ('astra_ingestion_v1.backfill_contract_enqueue_v2(text,integer)','e79997417569efc1295fbf8dbbb3b90e8b0c82ded972e213fc1b1e69dffc3c0c'),
  ('astra_ingestion_v1.backfill_contract_child_trigger_v2()','96fd9d7485ac6312a8b6facfafd4c8438d145ad69af2db0cdbfd2e49f3291e6b'),
  ('astra_ingestion_v1.backfill_date_v2(text)','7adc3f4ac60be32dd4348becbb325aeaf625cfd8c624b4d266fdbb7a038302f9'),
  ('astra_ingestion_v1.backfill_stamp_v2(text)','63988e76443273e860cfc5cc7929dd2282c5525d9e824c443e79c03b15e6a1e9')
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

 SELECT * INTO STRICT v_task FROM astra_ingestion_v1.backfill_tasks_v2
 WHERE id='backfill-plan-0a93df963fd7ef5a5c67e7534302d55c4fc5db535c9ff5bb8f7238d78af181e8'
  AND run_id='fixed3000-20250901-20260731-v1-20261030' AND run_fence=1
  AND family='CTX02' AND provider='Alpaca' AND kind='alpaca_option_contracts';
 SELECT p.body_sha256 INTO STRICT v_source_hash FROM astra_ingestion_v1.backfill_pages_v2 p
 JOIN astra_ingestion_v1.backfill_readbacks_v2 b USING(task_id,page_no)
 WHERE p.task_id=v_task.id AND p.page_no=0 AND p.record_count=1000 AND octet_length(p.raw_body)=705542
  AND p.committed_at='2026-10-30T07:14:07.869655+00:00'::timestamptz
  AND b.actual_records=p.record_count AND p.body_sha256=b.body_sha256 AND b.body_sha256=b.readback_sha256;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_contract_state_v2 WHERE run_id=v_task.run_id AND seed_complete) THEN
  RAISE EXCEPTION 'Retained contract seed completion changed; reconcile reached path';
 END IF;
 SELECT processed_at IS NULL INTO STRICT v_pending FROM astra_ingestion_v1.backfill_contract_enumeration_v2
 WHERE task_id=v_task.id AND page_no=0;
 v_started:=clock_timestamp();
 EXECUTE $parse$SELECT COALESCE(jsonb_agg(jsonb_build_object('ordinal',x.record_ordinal,'symbol',x.source_row->>'symbol','underlying',x.source_row->>'underlying_symbol',
  'eligible',COALESCE(x.source_row->>'symbol' ~ '^[A-Za-z0-9][A-Za-z0-9._/-]{0,63}$' AND ($3->'symbols') ? (x.source_row->>'underlying_symbol'),false))),'[]')
 FROM astra_ingestion_v1.backfill_page_rows_v2($1,$2) x$parse$ INTO v_rows USING v_task.id,0,v_task.scope;
 v_parse_ms:=extract(epoch FROM clock_timestamp()-v_started)*1000;
 IF jsonb_array_length(v_rows)<>1000 THEN RAISE EXCEPTION 'Retained contract parse count changed';END IF;
 FOR v_phase IN SELECT * FROM (VALUES
  ('UNREGISTERED_SYMBOL_BATCHES',$read$SELECT jsonb_agg(symbol ORDER BY symbol),g FROM(SELECT symbol,((row_number() OVER(ORDER BY symbol)-1)/100)::int g FROM(
   SELECT DISTINCT x->>'symbol' symbol FROM jsonb_array_elements($1) x WHERE x->'eligible'='true'::jsonb
    AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_contract_work_v2 w WHERE w.run_id=$2 AND w.work_key=astra_ingestion_v1.backfill_contract_key_v2(x->>'symbol',$5,$6,'opra','1Day'))
  ) unique_symbols) numbered GROUP BY g$read$),
  ('EXISTING_PARENT_LINKS',$read$SELECT $2,$3,$4,(x->>'ordinal')::bigint,x->>'symbol',x->>'underlying',w.work_key,w.canonical_task_id
 FROM jsonb_array_elements($1) x JOIN astra_ingestion_v1.backfill_contract_work_v2 w
  ON w.run_id=$2 AND w.work_key=astra_ingestion_v1.backfill_contract_key_v2(x->>'symbol',$5,$6,'opra','1Day') WHERE x->'eligible'='true'::jsonb$read$)
 ) phases(component,read_sql) LOOP
  EXECUTE 'EXPLAIN (ANALYZE TRUE,BUFFERS TRUE,TIMING FALSE,SETTINGS FALSE,FORMAT JSON) '||v_phase.read_sql
   INTO v_plan USING v_rows,v_task.run_id,v_task.id,0,'2025-09-01T00:00:00-04:00'::timestamptz,'2026-07-31T23:59:59-04:00'::timestamptz;
  -- Plans are sanitized to counts, node labels and catalog identifiers only.
  -- No expression, function argument, predicate or source value is returned.
  WITH RECURSIVE nodes(path,node) AS(
   SELECT ARRAY[0::bigint],v_plan->0->'Plan'
   UNION ALL SELECT n.path||c.ordinality,c.value FROM nodes n
    CROSS JOIN LATERAL jsonb_array_elements(COALESCE(n.node->'Plans','[]')) WITH ORDINALITY c(value,ordinality)
  )
  SELECT jsonb_agg(jsonb_build_object('path',path,'node_type',node->'Node Type',
   'parent_relationship',node->'Parent Relationship','join_type',node->'Join Type',
   'relation',node->'Relation Name','index',node->'Index Name','actual_rows',node->'Actual Rows',
   'actual_loops',node->'Actual Loops','rows_removed_filter',node->'Rows Removed by Filter',
   'rows_removed_join_filter',node->'Rows Removed by Join Filter',
   'shared_hits',node->'Shared Hit Blocks','shared_reads',node->'Shared Read Blocks',
   'temp_reads',node->'Temp Read Blocks','temp_writes',node->'Temp Written Blocks') ORDER BY path) INTO v_nodes FROM nodes;
  results:=results||jsonb_build_array(jsonb_build_object('component',v_phase.component,
   'planning_ms',v_plan->0->'Planning Time','execution_ms',v_plan->0->'Execution Time','nodes',v_nodes));
 END LOOP;
 candidate_result:=jsonb_build_object('schema','astra.contract-admission-pure-reads/1','complete',true,
  'observed_at',clock_timestamp(),'task_id',v_task.id,'page_no',0,'source_sha256',v_source_hash,
  'admission_currently_pending',v_pending,'seed_complete',true,'parsed_records',jsonb_array_length(v_rows),
  'parsed_rows_sha256',encode(sha256(convert_to(v_rows::text,'UTF8')),'hex'),'parse_elapsed_ms',v_parse_ms,
  'eligible_rows',(SELECT count(*) FROM jsonb_array_elements(v_rows) r WHERE r->'eligible'='true'::jsonb),
  'results',results,'transaction_read_only',current_setting('transaction_read_only'),
  'transaction_isolation',current_setting('transaction_isolation'),'raw_source_or_parsed_rows_returned',false,
  'admission_or_registration_invoked',false,'advisory_lock_acquired',false);
 IF octet_length(candidate_result::text)>60000 THEN RAISE EXCEPTION 'Contract read diagnostic exceeds bounded result size';END IF;
 RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='ASTRA_CONTRACT_READS_V71:'||candidate_result::text;
END $profile$;
ROLLBACK;
