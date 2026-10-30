-- Performance-only additive index; no function, grant, role, credential,
-- scheduler, timeout policy, source scope, cohort or data-row change.
-- Normal transactional build scans the task heap and temporarily blocks writes.
-- Global advisory gate precedes the run row and task-table lock. One8-second
-- DO budget includes lock acquisition, admission, build and postconditions.
-- A failed/uncertain result must be reconciled by exact catalog readback first.
-- Existing exact/valid target is a no-op; a same-name drifted object is rejected.
BEGIN;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $maintenance_index$
DECLARE
 v_target constant text:='backfill_tasks_breadth_pending_id_v2';
 v_namespace text:='astra_ingestion_v1';
 v_table oid;
 v_table_owner oid;
 v_oid oid;
 v_current_count integer;
 v_baseline_hash text;
 v_before_functions jsonb;
 v_after_functions jsonb;
 v_before_table jsonb;
 v_after_table jsonb;
 v_before_indexes jsonb;
 v_after_indexes jsonb;
 v_created boolean:=false;
 g record;
BEGIN
 IF current_setting('statement_timeout')<>'8s' OR current_setting('lock_timeout')<>'3s' THEN
  RAISE EXCEPTION 'Maintenance index requires the reviewed8-second statement and3-second lock installation bounds';
 END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(706314020261028);
 PERFORM 1 FROM astra_ingestion_v1.backfill_runs_v2
 WHERE id='fixed3000-20250901-20260731-v1-20261030' AND status='ACTIVE' AND fence=1
  AND cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
  AND metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
  AND (metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()
 FOR SHARE;
 IF NOT FOUND OR (SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2
  WHERE run_id='fixed3000-20250901-20260731-v1-20261030')<>3000 THEN
  RAISE EXCEPTION 'Maintenance index owner, lease, active run, fence or fixed cohort differs';
 END IF;
 FOR g IN SELECT * FROM (VALUES
  ('astra_ingestion_v1.backfill_breadth_project_pending_v2(integer)','65c981bd15a70f01d35eefc06a3807c7e6cfa1120a4b149ba3829951a63cc0d0'),
  ('astra_ingestion_v1.backfill_minute_account_pending_v2(integer)','49cc9131c989de8f2da0926a2d1312bee7262f2e7f63c7a800219257af1632f2'),
  ('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)','28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44'),
  ('astra_ingestion_v1.rpc_dispatch(text,jsonb)','a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520'),
  ('astra_ingestion_v1.backfill_maintain_v2(integer)','cd10046d9c9aa15e8bc66724d1258d95151364ffeee9070d761c4f7d930b5859'),
  ('astra_ingestion_v1.monitor_tick_v1()','875c017ecf73df15163d15d3f9129b4507235dc893ccb4233d0a435154389057')
 ) p(signature,expected_sha256) LOOP
  IF encode(sha256(convert_to(pg_get_functiondef(g.signature::regprocedure),'UTF8')),'hex')<>g.expected_sha256 THEN
   RAISE EXCEPTION 'Maintenance index authenticated or selector source differs; reconcile before applying';
  END IF;
 END LOOP;
 v_table:='astra_ingestion_v1.backfill_tasks_v2'::regclass;
 IF NOT EXISTS(SELECT 1 FROM pg_class WHERE oid=v_table AND relkind='r' AND relpersistence='p') THEN
  RAISE EXCEPTION 'Maintenance index requires the existing ordinary persistent task table';
 END IF;
 IF (SELECT count(*) FROM pg_attribute a JOIN (VALUES
   ('id','text'::regtype),('family','text'::regtype),('provider','text'::regtype),
   ('kind','text'::regtype),('scope','jsonb'::regtype)
  ) e(name,type_oid) ON a.attname=e.name AND a.atttypid=e.type_oid
  WHERE a.attrelid=v_table AND a.attnum>0 AND NOT a.attisdropped AND a.attnotnull)<>5 THEN
  RAISE EXCEPTION 'Maintenance index task key or exact predicate column types differ';
 END IF;
 LOCK TABLE astra_ingestion_v1.backfill_tasks_v2 IN SHARE MODE;
 SELECT relowner,jsonb_build_object('oid',oid,'owner',relowner,'acl',relacl,'rls',relrowsecurity,
   'force_rls',relforcerowsecurity,'kind',relkind,'persistence',relpersistence,'options',reloptions,
   'tablespace',reltablespace,'filenode',relfilenode,'access_method',relam)
 INTO STRICT v_table_owner,v_before_table FROM pg_class WHERE oid=v_table;
 SELECT jsonb_agg(to_jsonb(p) ORDER BY p.oid) INTO v_before_functions
 FROM pg_proc p WHERE p.pronamespace=v_namespace::regnamespace;
 SELECT count(*),encode(sha256(convert_to(string_agg(replace(pg_get_indexdef(c.oid),v_namespace,'astra'||'_ingestion_v1'),E'\n' ORDER BY c.relname),'UTF8')),'hex')
 INTO v_current_count,v_baseline_hash FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
 WHERE i.indrelid=v_table AND c.relname=ANY(ARRAY['backfill_contract_enum_task_v2','backfill_contract_old_child_cursor_v2','backfill_daily_month_units_v2','backfill_identity_derived_member_v2','backfill_identity_refresh_tasks_v2','backfill_reuse_children_v2','backfill_shared_action_tasks_v2','backfill_tasks_family_turn_v2','backfill_tasks_family_v2','backfill_tasks_minute_alias_status_v2','backfill_tasks_provider_v2','backfill_tasks_recovery_turn_v2','backfill_tasks_runnable_v2','backfill_tasks_runtime_summary_v2','backfill_tasks_v2_pkey']);
 IF v_current_count<>15 OR v_baseline_hash<>'2d87039e14365784d4c027e20c297e3b7c2354d096a466caab2c00fc5ead1f47'
  OR EXISTS(SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid WHERE i.indrelid=v_table
   AND c.relname<>ALL(ARRAY['backfill_contract_enum_task_v2','backfill_contract_old_child_cursor_v2','backfill_daily_month_units_v2','backfill_identity_derived_member_v2','backfill_identity_refresh_tasks_v2','backfill_reuse_children_v2','backfill_shared_action_tasks_v2','backfill_tasks_family_turn_v2','backfill_tasks_family_v2','backfill_tasks_minute_alias_status_v2','backfill_tasks_provider_v2','backfill_tasks_recovery_turn_v2','backfill_tasks_runnable_v2','backfill_tasks_runtime_summary_v2','backfill_tasks_v2_pkey','backfill_tasks_breadth_pending_id_v2','backfill_tasks_minute_pending_id_v2']))
  OR EXISTS(SELECT 1 FROM pg_index i WHERE i.indrelid=v_table AND (NOT i.indisvalid OR NOT i.indisready OR NOT i.indislive)) THEN
  RAISE EXCEPTION 'Maintenance index retained index set, definition or validity differs';
 END IF;
 -- Check both known candidate names before either no-op or a new build.
 FOR g IN SELECT * FROM (VALUES
  ('backfill_tasks_breadth_pending_id_v2',$definition$CREATE INDEX backfill_tasks_breadth_pending_id_v2 ON astra_ingestion_v1.backfill_tasks_v2 USING hash (id) WHERE ((family = 'D03'::text) AND (lower(provider) = 'derived'::text))$definition$),
  ('backfill_tasks_minute_pending_id_v2',$definition$CREATE INDEX backfill_tasks_minute_pending_id_v2 ON astra_ingestion_v1.backfill_tasks_v2 USING hash (id) WHERE ((family = ANY (ARRAY['P01'::text, 'P02'::text])) AND (kind = ANY (ARRAY['retained_reuse'::text, 'alpaca_stock_bars'::text])) AND (COALESCE((scope ->> 'timeframe'::text), '1Min'::text) = '1Min'::text))$definition$)
 ) d(index_name,expected_definition) LOOP
  v_oid:=to_regclass(format('%I.%I',v_namespace,g.index_name));
  IF v_oid IS NOT NULL AND NOT EXISTS(SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
    JOIN pg_am a ON a.oid=c.relam
   WHERE c.oid=v_oid AND i.indrelid=v_table AND c.relowner=v_table_owner AND c.relacl IS NULL
    AND c.relkind='i' AND c.relpersistence='p' AND a.amname='hash'
    AND i.indisvalid AND i.indisready AND i.indislive AND NOT i.indisunique AND NOT i.indisprimary
    AND NOT i.indisexclusion AND i.indnkeyatts=1 AND i.indnatts=1 AND i.indexprs IS NULL
    AND pg_get_indexdef(c.oid)=g.expected_definition) THEN
   RAISE EXCEPTION 'Maintenance candidate index name exists with unexpected definition, owner, access method or validity';
  END IF;
 END LOOP;
 IF to_regclass('astra_ingestion_v1.backfill_tasks_minute_pending_id_v2') IS NOT NULL AND to_regclass('astra_ingestion_v1.backfill_tasks_breadth_pending_id_v2') IS NULL THEN RAISE EXCEPTION 'Unexpected reversed maintenance index installation state'; END IF;
 IF to_regclass(format('%I.%I',v_namespace,v_target)) IS NOT NULL THEN
 FOR g IN SELECT * FROM (VALUES
  ('astra_ingestion_v1.backfill_breadth_project_pending_v2(integer)','65c981bd15a70f01d35eefc06a3807c7e6cfa1120a4b149ba3829951a63cc0d0'),
  ('astra_ingestion_v1.backfill_minute_account_pending_v2(integer)','49cc9131c989de8f2da0926a2d1312bee7262f2e7f63c7a800219257af1632f2'),
  ('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)','28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44'),
  ('astra_ingestion_v1.rpc_dispatch(text,jsonb)','a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520'),
  ('astra_ingestion_v1.backfill_maintain_v2(integer)','cd10046d9c9aa15e8bc66724d1258d95151364ffeee9070d761c4f7d930b5859'),
  ('astra_ingestion_v1.monitor_tick_v1()','875c017ecf73df15163d15d3f9129b4507235dc893ccb4233d0a435154389057')
 ) p(signature,expected_sha256) LOOP
  IF encode(sha256(convert_to(pg_get_functiondef(g.signature::regprocedure),'UTF8')),'hex')<>g.expected_sha256 THEN
   RAISE EXCEPTION 'Maintenance index authenticated or selector source differs; reconcile before applying';
  END IF;
 END LOOP;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2
  WHERE id='fixed3000-20250901-20260731-v1-20261030' AND status='ACTIVE' AND fence=1
   AND metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
   AND (metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()) THEN
  RAISE EXCEPTION 'Maintenance index owner lease or run fence expired during the bounded build';
 END IF;
  RAISE NOTICE 'Reviewed exact maintenance index is already valid; no build performed: %',v_target;
  RETURN;
 END IF;
 SELECT jsonb_agg(jsonb_build_object('catalog',to_jsonb(i),'name',c.relname,'owner',c.relowner,
   'acl',c.relacl,'options',c.reloptions,'definition',pg_get_indexdef(c.oid)) ORDER BY c.relname)
 INTO v_before_indexes FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid WHERE i.indrelid=v_table;
 EXECUTE $index$CREATE INDEX backfill_tasks_breadth_pending_id_v2 ON astra_ingestion_v1.backfill_tasks_v2 USING hash (id) WHERE ((family = 'D03'::text) AND (lower(provider) = 'derived'::text))$index$;
 v_created:=true;
 FOR g IN SELECT * FROM (VALUES
  ('astra_ingestion_v1.backfill_breadth_project_pending_v2(integer)','65c981bd15a70f01d35eefc06a3807c7e6cfa1120a4b149ba3829951a63cc0d0'),
  ('astra_ingestion_v1.backfill_minute_account_pending_v2(integer)','49cc9131c989de8f2da0926a2d1312bee7262f2e7f63c7a800219257af1632f2'),
  ('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)','28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44'),
  ('astra_ingestion_v1.rpc_dispatch(text,jsonb)','a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520'),
  ('astra_ingestion_v1.backfill_maintain_v2(integer)','cd10046d9c9aa15e8bc66724d1258d95151364ffeee9070d761c4f7d930b5859'),
  ('astra_ingestion_v1.monitor_tick_v1()','875c017ecf73df15163d15d3f9129b4507235dc893ccb4233d0a435154389057')
 ) p(signature,expected_sha256) LOOP
  IF encode(sha256(convert_to(pg_get_functiondef(g.signature::regprocedure),'UTF8')),'hex')<>g.expected_sha256 THEN
   RAISE EXCEPTION 'Maintenance index authenticated or selector source differs; reconcile before applying';
  END IF;
 END LOOP;

 v_oid:=to_regclass(format('%I.%I',v_namespace,v_target));
 IF NOT EXISTS(SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_am a ON a.oid=c.relam
  WHERE c.oid=v_oid AND i.indrelid=v_table AND c.relowner=v_table_owner AND c.relacl IS NULL
   AND c.relkind='i' AND c.relpersistence='p' AND a.amname='hash'
   AND i.indisvalid AND i.indisready AND i.indislive AND NOT i.indisunique AND NOT i.indisprimary
   AND NOT i.indisexclusion AND i.indnkeyatts=1 AND i.indnatts=1 AND i.indexprs IS NULL
   AND pg_get_indexdef(c.oid)=$expected$CREATE INDEX backfill_tasks_breadth_pending_id_v2 ON astra_ingestion_v1.backfill_tasks_v2 USING hash (id) WHERE ((family = 'D03'::text) AND (lower(provider) = 'derived'::text))$expected$) THEN
  RAISE EXCEPTION 'New maintenance index does not match the reviewed exact valid definition';
 END IF;
 SELECT jsonb_agg(jsonb_build_object('catalog',to_jsonb(i),'name',c.relname,'owner',c.relowner,
   'acl',c.relacl,'options',c.reloptions,'definition',pg_get_indexdef(c.oid)) ORDER BY c.relname)
 INTO v_after_indexes FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid WHERE i.indrelid=v_table AND c.oid<>v_oid;
 SELECT jsonb_agg(to_jsonb(p) ORDER BY p.oid) INTO v_after_functions
 FROM pg_proc p WHERE p.pronamespace=v_namespace::regnamespace;
 SELECT jsonb_build_object('oid',oid,'owner',relowner,'acl',relacl,'rls',relrowsecurity,
   'force_rls',relforcerowsecurity,'kind',relkind,'persistence',relpersistence,'options',reloptions,
   'tablespace',reltablespace,'filenode',relfilenode,'access_method',relam)
 INTO STRICT v_after_table FROM pg_class WHERE oid=v_table;
 IF v_before_indexes IS DISTINCT FROM v_after_indexes OR v_before_functions IS DISTINCT FROM v_after_functions
  OR v_before_table IS DISTINCT FROM v_after_table THEN
  RAISE EXCEPTION 'Maintenance index changed an existing index, function, owner, ACL, RLS or table property';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2
  WHERE id='fixed3000-20250901-20260731-v1-20261030' AND status='ACTIVE' AND fence=1
   AND metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
   AND (metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()) THEN
  RAISE EXCEPTION 'Maintenance index owner lease or run fence expired during the bounded build';
 END IF;
END $maintenance_index$;
COMMIT;
