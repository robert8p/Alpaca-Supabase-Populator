-- Read-only post-install profile of two exact original maintenance selectors.
-- Requires both reviewed hash indexes and the one-predicate maintain6c880 state.
-- Only the installed p_limit=2 is substituted; selector semantics are unchanged.
-- Direct read plans depend on current state/cache and do not prove cron latency.
-- No helper, provider, verifier, finalizer, gate or data mutation is invoked.
-- Named P0001 carries bounded plan evidence and intentionally aborts the wrapper.
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL transaction_read_only=on;
SET LOCAL transaction_isolation='repeatable read';
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $postinstall_profile$
DECLARE
 source_guard record;
 index_guard record;
 selector record;
 task_table oid;
 task_owner oid;
 index_oid oid;
 plan jsonb;
 results jsonb:='[]';
 started timestamptz:=clock_timestamp();
BEGIN
 IF current_setting('transaction_read_only')<>'on'
  OR current_setting('transaction_isolation')<>'repeatable read'
  OR current_setting('statement_timeout')<>'8s'
  OR current_setting('lock_timeout')<>'3s' THEN
  RAISE EXCEPTION 'Post-install selector profile requires explicit bounded read-only repeatable-read settings';
 END IF;
 FOR source_guard IN SELECT * FROM (VALUES
  ('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)','28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44'),
  ('astra_ingestion_v1.rpc_dispatch(text,jsonb)','a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520'),
  ('astra_ingestion_v1.backfill_maintain_v2(integer)','6c880114a645c8a9167d5260c4aeabf58a10617c4244cf0340be1d6cf4bf0ce7'),
  ('astra_ingestion_v1.backfill_breadth_project_pending_v2(integer)','65c981bd15a70f01d35eefc06a3807c7e6cfa1120a4b149ba3829951a63cc0d0'),
  ('astra_ingestion_v1.backfill_minute_account_pending_v2(integer)','49cc9131c989de8f2da0926a2d1312bee7262f2e7f63c7a800219257af1632f2')
 ) s(signature,expected_sha256) LOOP
  IF encode(sha256(convert_to(pg_get_functiondef(source_guard.signature::regprocedure),'UTF8')),'hex')<>source_guard.expected_sha256 THEN
   RAISE EXCEPTION 'Post-install selector source changed or final repair state is absent';
  END IF;
 END LOOP;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2
  WHERE id='fixed3000-20250901-20260731-v1-20261030' AND status='ACTIVE' AND fence=1
   AND cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
   AND metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
   AND (metadata->>'implementation_lease_until')::timestamptz>clock_timestamp())
  OR (SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2
   WHERE run_id='fixed3000-20250901-20260731-v1-20261030')<>3000 THEN
  RAISE EXCEPTION 'Post-install selector run, owner, lease, fence or fixed cohort changed';
 END IF;
 task_table:='astra_ingestion_v1.backfill_tasks_v2'::regclass;
 SELECT relowner INTO STRICT task_owner FROM pg_class
  WHERE oid=task_table AND relkind='r' AND relpersistence='p';
 FOR index_guard IN SELECT * FROM (VALUES
  ('backfill_tasks_breadth_pending_id_v2',$definition$CREATE INDEX backfill_tasks_breadth_pending_id_v2 ON astra_ingestion_v1.backfill_tasks_v2 USING hash (id) WHERE ((family = 'D03'::text) AND (lower(provider) = 'derived'::text))$definition$),
  ('backfill_tasks_minute_pending_id_v2',$definition$CREATE INDEX backfill_tasks_minute_pending_id_v2 ON astra_ingestion_v1.backfill_tasks_v2 USING hash (id) WHERE ((family = ANY (ARRAY['P01'::text, 'P02'::text])) AND (kind = ANY (ARRAY['retained_reuse'::text, 'alpaca_stock_bars'::text])) AND (COALESCE((scope ->> 'timeframe'::text), '1Min'::text) = '1Min'::text))$definition$)
 ) d(index_name,expected_definition) LOOP
  index_oid:=to_regclass(format('%I.%I','astra_ingestion_v1',index_guard.index_name));
  IF index_oid IS NULL OR NOT EXISTS(SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
    JOIN pg_am a ON a.oid=c.relam
   WHERE c.oid=index_oid AND i.indrelid=task_table AND c.relowner=task_owner AND c.relacl IS NULL
    AND c.relkind='i' AND c.relpersistence='p' AND a.amname='hash'
    AND i.indisvalid AND i.indisready AND i.indislive AND NOT i.indisunique AND NOT i.indisprimary
    AND NOT i.indisexclusion AND i.indnkeyatts=1 AND i.indnatts=1 AND i.indexprs IS NULL
    AND pg_get_indexdef(c.oid)=index_guard.expected_definition) THEN
   RAISE EXCEPTION 'Post-install selector exact reviewed hash index is absent or differs';
  END IF;
 END LOOP;
 FOR selector IN SELECT * FROM (VALUES
  ('BREADTH_PENDING',$query$SELECT pg.task_id,pg.page_no,pg.run_id FROM astra_ingestion_v1.backfill_pages_v2 pg JOIN astra_ingestion_v1.backfill_tasks_v2 t ON t.id=pg.task_id
  WHERE t.family='D03' AND lower(t.provider)='derived'
   AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_breadth_projected_pages_v2 q WHERE q.task_id=pg.task_id AND q.page_no=pg.page_no)
   AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_audit_v2 a WHERE a.task_id=pg.task_id AND a.action='D03_PROJECTION_FAILURE' AND a.evidence->>'page_no'=pg.page_no::text)
  ORDER BY pg.committed_at,pg.task_id,pg.page_no LIMIT GREATEST(1,LEAST(2,8))$query$),
  ('MINUTE_ACCOUNT_PENDING',$query$SELECT DISTINCT v.task_id FROM astra_ingestion_v1.backfill_readbacks_v2 v
  JOIN astra_ingestion_v1.backfill_tasks_v2 t ON t.id=v.task_id
  LEFT JOIN astra_ingestion_v1.backfill_minute_projection_v2 s ON s.task_id=v.task_id
  WHERE t.family IN('P01','P02') AND t.kind IN('retained_reuse','alpaca_stock_bars') AND COALESCE(t.scope->>'timeframe','1Min')='1Min'
   AND (s.task_id IS NULL OR s.last_verified_page<v.page_no) LIMIT GREATEST(1,LEAST(2,8))$query$)
 ) q(component,read_query) LOOP
  EXECUTE 'EXPLAIN (ANALYZE TRUE,BUFFERS TRUE,TIMING FALSE,SETTINGS TRUE,FORMAT JSON) '||selector.read_query INTO plan;
  results:=results||jsonb_build_array(jsonb_build_object('component',selector.component,'plan',plan));
  IF octet_length(results::text)>60000 THEN RAISE EXCEPTION 'Post-install selector profile exceeds bounded result size'; END IF;
 END LOOP;
 IF jsonb_array_length(results)<>2 THEN RAISE EXCEPTION 'Post-install selector profile is incomplete'; END IF;
 RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='ASTRA_MAINTENANCE_INDEX_POSTINSTALL_V72:'||jsonb_build_object(
  'schema','astra.maintenance-index-postinstall-selectors/1','started_at',started,'observed_at',clock_timestamp(),
  'transaction_read_only',current_setting('transaction_read_only'),'transaction_isolation',current_setting('transaction_isolation'),
  'statement_timeout',current_setting('statement_timeout'),'lock_timeout',current_setting('lock_timeout'),
  'source_pins_verified',5,'exact_hash_indexes_verified',2,'selector_count',2,'complete',true,
  'maintenance_functions_invoked',false,'advisory_lock_acquired',false,'raw_page_bodies_returned',false,
  'interpretation','Current direct SELECT plans; cache/state-dependent; not whole-cron or gate-hold timing.',
  'results',results)::text;
END $postinstall_profile$;
ROLLBACK;
