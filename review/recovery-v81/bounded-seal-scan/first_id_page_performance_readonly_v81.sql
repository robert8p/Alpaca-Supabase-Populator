-- Prepared only: ONE new root-selected read; no invocation has been authorized by this file.
-- v79 whole-population measurement timed out; this distinct read measures only the concrete v81 finite first-ID-page access path.
-- Reads one global upper ID and executes ONE pure first-page selector limited to500 IDs. No business helper, explicit application/advisory lock, mutation or test suite.
-- Expected terminal envelope: deliberate P0001 ASTRA_BOUNDED_SEAL_PAGE_PERF_V81: + <=30000B safe JSON.
-- Missing/truncated/nonterminal/different output remains unresolved; no automatic retry/reselection.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL transaction_read_only=on;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $selector_read$
DECLARE
 page_upper text; trigger_pin jsonb; trigger_observed record; trigger_results jsonb:='[]';
 trigger_pins jsonb:=$v81_triggers$[{"definition":"CREATE TRIGGER backfill_plan_units_immutable_v2 BEFORE DELETE OR UPDATE OR TRUNCATE ON astra_ingestion_v1.backfill_plan_units_v2 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.backfill_evidence_guard_v2()","found":true,"full_trigger_metadata_sha256":"10a7f1b4ecfdc225e97069f8ce7f0a084f4cad96532cb64bc370e7e7176fc5f5","function_oid":"16040226","relation_oid":"16041315","table_name":"astra_ingestion_v1.backfill_plan_units_v2","tgenabled":"O","tgisinternal":false,"tgtype":58,"trigger_name":"backfill_plan_units_immutable_v2","trigger_oid":"16041361"},{"definition":"CREATE TRIGGER backfill_run_immutable_v2 BEFORE UPDATE ON astra_ingestion_v1.backfill_runs_v2 FOR EACH ROW EXECUTE FUNCTION astra_ingestion_v1.backfill_run_guard_v2()","found":true,"full_trigger_metadata_sha256":"324ed022b79f8710c442e2876bd8e4c209f1084a7fb730251e649adce9e3548c","function_oid":"16040222","relation_oid":"16040070","table_name":"astra_ingestion_v1.backfill_runs_v2","tgenabled":"O","tgisinternal":false,"tgtype":19,"trigger_name":"backfill_run_immutable_v2","trigger_oid":"16040223"},{"definition":"CREATE TRIGGER backfill_static_plan_snapshot_v2 AFTER INSERT ON astra_ingestion_v1.backfill_tasks_v2 FOR EACH ROW EXECUTE FUNCTION astra_ingestion_v1.backfill_snapshot_insert_v2()","found":true,"full_trigger_metadata_sha256":"74709c28f3db1ec351d07deaf492e29636c63b39245f5bd77e2aa19964deddf9","function_oid":"16041467","relation_oid":"16040120","table_name":"astra_ingestion_v1.backfill_tasks_v2","tgenabled":"O","tgisinternal":false,"tgtype":5,"trigger_name":"backfill_static_plan_snapshot_v2","trigger_oid":"16041468"},{"definition":"CREATE TRIGGER backfill_task_scope_v2 BEFORE INSERT OR UPDATE ON astra_ingestion_v1.backfill_tasks_v2 FOR EACH ROW EXECUTE FUNCTION astra_ingestion_v1.backfill_task_guard_v2()","found":true,"full_trigger_metadata_sha256":"d1705f679536181300a1f6dea3efe94d02068127b5b6d5da908fe78ae27ae4c1","function_oid":"16040224","relation_oid":"16040120","table_name":"astra_ingestion_v1.backfill_tasks_v2","tgenabled":"O","tgisinternal":false,"tgtype":23,"trigger_name":"backfill_task_scope_v2","trigger_oid":"16040225"},{"definition":"CREATE TRIGGER backfill_plan_manifest_immutable_v2 BEFORE DELETE OR UPDATE OR TRUNCATE ON astra_ingestion_v1.backfill_plan_manifests_v2 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.backfill_evidence_guard_v2()","found":true,"full_trigger_metadata_sha256":"82707ad7bbf31a1fe5f6296ef81c2fe3867d277be90b06077ba08252748b1aa6","function_oid":"16040226","relation_oid":"16041342","table_name":"astra_ingestion_v1.backfill_plan_manifests_v2","tgenabled":"O","tgisinternal":false,"tgtype":58,"trigger_name":"backfill_plan_manifest_immutable_v2","trigger_oid":"16041362"}]$v81_triggers$::jsonb;
 primary_key_pins jsonb:='[{"relation_oid":"16040120","relation_name":"backfill_tasks_v2","index_oid":"16040151","index_name":"backfill_tasks_v2_pkey","index_definition_sha256":"b5c5e71c2fdc51167b2308a16b62c1838bf90710040a6b274e3a22ed09a37a28","attribute":"id","type_oid":"25","typmod":-1,"collation_oid":"100"},{"relation_oid":"16041315","relation_name":"backfill_plan_units_v2","index_oid":"16041321","index_name":"backfill_plan_units_v2_pkey","index_definition_sha256":"a2fe7dc9f8249fbb3ffdc2ec706982522272751ce28829909b5d47f91170fdbd","attribute":"task_id","type_oid":"25","typmod":-1,"collation_oid":"100"}]'::jsonb;
 pk_pin jsonb; pk_observed record; pk_results jsonb:='[]';
 expected jsonb:='[{"metadata_sha256":"e7c2c36c0fa1db906255f0194e62ae1d1ebbdf3b11c0fb718723b6ec524a79b6","oid":"16040232","signature":"astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)","source_sha256":"dbe8eb5a563eaf9e8e00678045f8a28da65c8c4b83b4a3295c4eb32c05f50fbf"},{"metadata_sha256":"ca71e86cf6901b655a7d81b1ca15d39ee8d8db1fa0cef329e2ee92bc0b04f875","oid":"16041635","signature":"astra_ingestion_v1.backfill_plan_next_v2(jsonb)","source_sha256":"54c73bd41769eb6c698a7941d0785e503c9f48f88a3ccb7afcc6448d46c5048d"},{"metadata_sha256":"2298d7d2dc6af8f2360df643ed9c05067e625103fe3e09ba59b3fdc1a7ed1f69","oid":"16041469","signature":"astra_ingestion_v1.backfill_plan_snapshot_v2(text,integer)","source_sha256":"8b8f595bfca0e6ddf74aa12271314620b8364df26079cd86f843a4a81f92b18f"},{"metadata_sha256":"26059708eb74c9b3f291e98da0a74b3b2c381073ec04feb947c07e5fa91a2f8c","oid":"16041471","signature":"astra_ingestion_v1.backfill_seal_plan_v2(text,bigint,text,jsonb)","source_sha256":"a93e5fbede881afc9e813e8eaaec1c300d636e008fe8c3423d478d55243d2ba1"},{"metadata_sha256":"05efbf80a36ecaf99c1ecf1c3bde8372489963c867bd98708f5fc12223b05f43","oid":"16050105","signature":"astra_ingestion_v1.backfill_shared_refresh_v2(text,jsonb)","source_sha256":"7f538bf47cb5e74050c20266e01cbe9d6521c1a65663aaf2e0fe38d62041f1a4"},{"metadata_sha256":"3b039c556a14a96cec82bbe9cf701f6fd45474393b255460fb14d62648087418","oid":"16041466","signature":"astra_ingestion_v1.backfill_snapshot_task_v2(text)","source_sha256":"66cf1ddad758759353ac0e7ca10aa119cbc88b21bee26d1b5f8356df090518b2"},{"metadata_sha256":"1f123366c142c43aadb28a9a4ea3df9e8c376a74a90c69c81b1363c10afeca7e","oid":"15986028","signature":"astra_ingestion_v1.rpc_dispatch(text,jsonb)","source_sha256":"a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520"},{"metadata_sha256":"412040bbed9e8a96e9c7231c1f1474326c0eacf7a8157043703983c68b2d1f51","oid":"15986030","signature":"public.astra_ingestion_rpc_v1(text,jsonb)","source_sha256":"566d2248b8addac92a5dc2659233fb50f12ae1c55869fc278555da6cbd1ffffb"},{"metadata_sha256":"4497ec91787767ee138d167beb19970a5289f9baec3d01c9eeda6962a8d0460d","oid":"16041463","signature":"astra_ingestion_v1.backfill_maintain_v2(integer)","source_sha256":"6c880114a645c8a9167d5260c4aeabf58a10617c4244cf0340be1d6cf4bf0ce7"},{"metadata_sha256":"f7b0c166958ff0da7fdd453d57fa0c45134cdac1d52c389a72c87ed53bb8bb63","oid":"16041470","signature":"astra_ingestion_v1.backfill_plan_coverage_check_v2(text,datemultirange,datemultirange)","source_sha256":"b2503ecd484e3fb7023a00d474cfc44410e8cf9489c037f8a69a37dfc8c0cc5e"},{"metadata_sha256":"0b1c18018c2277b8de57e12248815d1ead7f7ef7634091fe560dc5693a4557fd","oid":"15986014","signature":"astra_ingestion_v1.rpc_canonical(jsonb)","source_sha256":"a7ddedfe281d1494141830d8e89773314856ca94f4d5a4b64b76bb25b3c5e5eb"},{"metadata_sha256":"e0f12f2f1e16dc4ca3802733c39652defb8437abc8ed652a62229fde6bc2c958","oid":"16041364","signature":"astra_ingestion_v1.backfill_date_v2(text)","source_sha256":"7adc3f4ac60be32dd4348becbb325aeaf625cfd8c624b4d266fdbb7a038302f9"},{"metadata_sha256":"0b4e6822e020b5db4a45fc0c84409b2b8b3a70af1a4c76eeef58dd6bcc7f24dc","oid":"16041465","signature":"astra_ingestion_v1.backfill_task_definition_sha256_v2(astra_ingestion_v1.backfill_tasks_v2)","source_sha256":"ba6d5bfd137045abfedb61524d47e734c0489f01957b153fa913f7686db45633"},{"metadata_sha256":"9b757fe27c7ac0713887926ac5c50da7c348f65e325d8c69e355d65af1d01278","oid":"16040226","signature":"astra_ingestion_v1.backfill_evidence_guard_v2()","source_sha256":"b96725307395500c65f69238c138e40338a19a922c3ff235198b1ad376289dd8"},{"metadata_sha256":"98615ec21c2bc752328d8ad460d2c33a61117068854d0b6b53756b61ecca287f","oid":"16040222","signature":"astra_ingestion_v1.backfill_run_guard_v2()","source_sha256":"6bf61021944840245e8cf66db118aff413c9f7a8809ecafe025ec4d7f2f5512c"},{"metadata_sha256":"628354e3254f593acddd0e874f576073b388126a3a916b1c125932b2321fbee3","oid":"16041467","signature":"astra_ingestion_v1.backfill_snapshot_insert_v2()","source_sha256":"dd4b49c8d3b5ec85d2c144a99464482f3b584628b516c0afcb8218e06094434e"},{"metadata_sha256":"14ea179e67155da200192fb05cd1117bc3b0aea892b94ade7956343f7cf2f4a6","oid":"16040224","signature":"astra_ingestion_v1.backfill_task_guard_v2()","source_sha256":"94646a710138c821c9779849edca400d6445b84bec270cc2761a019ecac4b13e"}]'::jsonb;
 pin jsonb; observed record; r astra_ingestion_v1.backfill_runs_v2%ROWTYPE;
 m astra_ingestion_v1.backfill_plan_manifests_v2%ROWTYPE;
 source_results jsonb:='[]'; result jsonb; members integer; member_hash text; active_count integer;
 relations oid[]; relation_count integer; index_count integer; role_context jsonb; setting_context jsonb;
 relation_context jsonb; index_context jsonb; statistic_context jsonb; v_plan jsonb;
 v_queue jsonb; v_item jsonb; v_node jsonb; v_child jsonb; v_nodes jsonb:='[]'; v_n integer:=0;
BEGIN
 IF current_setting('transaction_read_only')<>'on' OR current_setting('transaction_isolation')<>'repeatable read'
  OR current_setting('statement_timeout')<>'8s' OR current_setting('lock_timeout')<>'3s' THEN
  RAISE EXCEPTION 'v81 read transaction bounds unavailable'; END IF;
 SELECT * INTO STRICT r FROM astra_ingestion_v1.backfill_runs_v2 WHERE id='fixed3000-20250901-20260731-v1-20261030';
 IF r.status IS DISTINCT FROM 'ACTIVE' OR r.fence IS DISTINCT FROM 1
  OR r.metadata->>'implementation_owner' IS DISTINCT FROM 'root-replacement-20261030T042603Z'
  OR r.cohort_sha256 IS DISTINCT FROM '2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
  OR r.cohort_manifest_sha256 IS DISTINCT FROM '4134b415e2c26fcde9fced749c0d54ef51376e23f0d2f8c6ce9ef562f9fab99f'
  OR r.target_start IS DISTINCT FROM '2025-09-01'::date OR r.target_end IS DISTINCT FROM '2026-07-31'::date
  OR r.metadata#>>'{implementation_reporting_policy,mode}' IS DISTINCT FROM 'DOT_CONSOLIDATED_CHECKPOINTS_ONLY'
  OR NOT COALESCE(isfinite((r.metadata->>'implementation_lease_until')::timestamptz)
   AND (r.metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()+interval '10 seconds',false) THEN
  RAISE EXCEPTION 'v81 read existing owner, finite lease, fence or fixed scope changed'; END IF;
 SELECT count(*),encode(sha256(convert_to(string_agg(member_id,E'\n' ORDER BY selection_order,member_id),'UTF8')),'hex')
  INTO members,member_hash FROM (SELECT member_id,selection_order FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id=r.id ORDER BY selection_order,member_id LIMIT 3001) x;
 SELECT count(*) INTO active_count FROM (SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2 WHERE status='ACTIVE' LIMIT 2) x;
 IF members<>3000 OR member_hash IS DISTINCT FROM 'a83310df6a6465ce8d37ffd5352095f6e38d91a3204afd8807fff39092cfd85e' OR active_count<>1 THEN
  RAISE EXCEPTION 'v81 read exact membership or sole active-run bound changed'; END IF;
 IF jsonb_array_length(expected)<>17 THEN RAISE EXCEPTION 'v81 exact seventeen-pin set unavailable'; END IF;
 FOR pin IN SELECT value FROM jsonb_array_elements(expected) LOOP
  SELECT p.oid::text oid,encode(sha256(convert_to(pg_get_functiondef(p.oid),'UTF8')),'hex') source_sha256,
   encode(sha256(convert_to((to_jsonb(p)-'prosrc')::text,'UTF8')),'hex') metadata_sha256 INTO observed
   FROM pg_catalog.pg_proc p WHERE p.oid=to_regprocedure(pin->>'signature');
  IF NOT FOUND OR observed.oid IS DISTINCT FROM pin->>'oid' OR observed.source_sha256 IS DISTINCT FROM pin->>'source_sha256'
   OR observed.metadata_sha256 IS DISTINCT FROM pin->>'metadata_sha256' THEN
   RAISE EXCEPTION 'v81 post-v78 exact source, OID or full metadata changed'; END IF;
  source_results:=source_results||jsonb_build_array(jsonb_build_object('signature',pin->>'signature','oid',observed.oid,
   'source_sha256',observed.source_sha256,'metadata_sha256',observed.metadata_sha256));
 END LOOP;
 result:=jsonb_build_object('run_id',r.id,'owner',r.metadata->>'implementation_owner','fence',r.fence,
  'guard_passed',true,'sources',source_results,'planning_complete',r.metadata->'planning_complete','explicit_locks',0,
  'business_helper_calls',0,'selector_execution_count',0,'plan_count',0,'source_first_page_sha256','0260e072bc7f18373f03af406701ce9d495e92cf7c9ee293909c94a947e5c0c4',
  'bound_first_page_sha256','dafff4be9a4c54c9895038a01c459fda809f221fed11835ccf99dfda3e2cfe7d');
 IF r.metadata->'planning_complete'='true'::jsonb THEN
  SELECT * INTO m FROM astra_ingestion_v1.backfill_plan_manifests_v2 WHERE run_id=r.id;
  IF NOT FOUND OR r.metadata->>'expected_static_task_count' IS DISTINCT FROM m.expected_task_count::text
   OR r.metadata->>'expected_plan_sha256' IS DISTINCT FROM m.expected_plan_sha256
   OR NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_audit_v2 a WHERE a.run_id=r.id AND a.action='FULL_PLAN_SEALED'
    AND a.evidence->>'expected_task_count'=m.expected_task_count::text AND a.evidence->>'expected_plan_sha256'=m.expected_plan_sha256
    AND a.evidence->>'cohort_sha256'=r.cohort_sha256) THEN
   RAISE EXCEPTION 'v81 completed-plan flag has no consistent stored manifest and audit'; END IF;
  result:=result||jsonb_build_object('state','CONSISTENT_SEALED_RECEIPT_SKIP_NO_PLAN','stored_count',m.expected_task_count,
   'stored_plan_sha256',m.expected_plan_sha256,'sealed_at',m.sealed_at,'limits','Stored receipt consistency only; no independent count/hash recalculation.');
 ELSE
  IF r.metadata->'planning_complete' IS DISTINCT FROM 'false'::jsonb
   OR r.metadata->>'planner_phase' IS DISTINCT FROM 'SEAL'
   OR r.metadata->>'planner_next_selection_order' IS DISTINCT FROM '3001'
   OR r.metadata->>'planner_next_breadth_index' IS DISTINCT FROM '230'
   OR r.metadata->>'planner_expected_static_count' IS DISTINCT FROM '979516'
   OR EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_plan_manifests_v2 WHERE run_id=r.id) THEN
   RAISE EXCEPTION 'v81 reconciled unsealed planner state changed; no plan obtained'; END IF;
  IF jsonb_array_length(primary_key_pins) IS DISTINCT FROM 2 THEN
   RAISE EXCEPTION 'v81 requires exactly two pinned global primary keys; no query executed'; END IF;
  FOR pk_pin IN SELECT value FROM jsonb_array_elements(primary_key_pins) LOOP
   SELECT c.oid::text relation_oid,c.relname,c.relkind,c.relispartition,c.relhassubclass,
    i.indexrelid::text index_oid,i.indisprimary,i.indisunique,i.indimmediate,i.indisvalid,i.indisready,i.indislive,
    i.indnkeyatts,i.indnatts,i.indpred IS NULL predicate_absent,i.indexprs IS NULL expressions_absent,
    a.attname,a.attnotnull,a.atttypid::text type_oid,a.atttypmod typmod,a.attcollation::text collation_oid,
    k.condeferrable,k.condeferred,k.convalidated,k.conkey=ARRAY[a.attnum]::smallint[] exact_constraint_key,
    encode(sha256(convert_to(pg_get_indexdef(i.indexrelid),'UTF8')),'hex') index_definition_sha256,
    EXISTS(SELECT 1 FROM pg_catalog.pg_inherits h WHERE h.inhrelid=c.oid OR h.inhparent=c.oid) inheritance_present
    INTO pk_observed FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    JOIN pg_catalog.pg_index i ON i.indrelid=c.oid JOIN pg_catalog.pg_attribute a ON a.attrelid=c.oid AND a.attnum=i.indkey[0]
    JOIN pg_catalog.pg_constraint k ON k.conrelid=c.oid AND k.conindid=i.indexrelid AND k.contype='p'
    WHERE c.oid=(pk_pin->>'relation_oid')::oid AND i.indexrelid=(pk_pin->>'index_oid')::oid AND n.nspname='astra_ingestion_v1';
   IF NOT FOUND OR pk_observed.relation_oid IS DISTINCT FROM pk_pin->>'relation_oid' OR pk_observed.relname IS DISTINCT FROM pk_pin->>'relation_name'
    OR pk_observed.index_oid IS DISTINCT FROM pk_pin->>'index_oid' OR pk_observed.relkind IS DISTINCT FROM 'r'::"char"
    OR pk_observed.relispartition OR pk_observed.relhassubclass OR pk_observed.inheritance_present
    OR NOT COALESCE(pk_observed.indisprimary AND pk_observed.indisunique AND pk_observed.indimmediate AND pk_observed.indisvalid
     AND pk_observed.indisready AND pk_observed.indislive AND pk_observed.predicate_absent AND pk_observed.expressions_absent
     AND pk_observed.attnotnull AND pk_observed.exact_constraint_key AND pk_observed.convalidated,false)
    OR pk_observed.indnkeyatts IS DISTINCT FROM 1 OR pk_observed.indnatts IS DISTINCT FROM 1
    OR pk_observed.condeferrable IS DISTINCT FROM false OR pk_observed.condeferred IS DISTINCT FROM false
    OR pk_observed.attname IS DISTINCT FROM pk_pin->>'attribute' OR pk_observed.type_oid IS DISTINCT FROM pk_pin->>'type_oid'
    OR pk_observed.typmod IS DISTINCT FROM (pk_pin->>'typmod')::integer OR pk_observed.collation_oid IS DISTINCT FROM pk_pin->>'collation_oid'
    OR pk_observed.index_definition_sha256 IS DISTINCT FROM pk_pin->>'index_definition_sha256' THEN
    RAISE EXCEPTION 'v81 candidate immediate global primary-key/catalog premise changed; no query executed'; END IF;
   pk_results:=pk_results||jsonb_build_array(to_jsonb(pk_observed));
  END LOOP;
  IF current_setting('session_replication_role') IS DISTINCT FROM 'origin' OR jsonb_array_length(trigger_pins) IS DISTINCT FROM 5 OR r.metadata?'planner_seal_snapshot_scan_v81' THEN RAISE EXCEPTION 'v81 origin, trigger-set or unstarted runtime scan premise changed'; END IF;
  FOR trigger_pin IN SELECT value FROM jsonb_array_elements(trigger_pins) LOOP
   SELECT tr.oid::text trigger_oid,tr.tgrelid::text relation_oid,tr.tgfoid::text function_oid,tr.tgenabled,tr.tgtype,tr.tgisinternal,pg_get_triggerdef(tr.oid,true) definition,encode(sha256(convert_to(to_jsonb(tr)::text,'UTF8')),'hex') full_trigger_metadata_sha256 INTO trigger_observed FROM pg_catalog.pg_trigger tr WHERE tr.oid=(trigger_pin->>'trigger_oid')::oid AND tr.tgrelid=to_regclass(trigger_pin->>'table_name');
   IF NOT FOUND OR trigger_observed.trigger_oid IS DISTINCT FROM trigger_pin->>'trigger_oid' OR trigger_observed.relation_oid IS DISTINCT FROM trigger_pin->>'relation_oid' OR trigger_observed.function_oid IS DISTINCT FROM trigger_pin->>'function_oid' OR trigger_observed.tgenabled IS DISTINCT FROM 'O'::"char" OR trigger_observed.tgtype IS DISTINCT FROM (trigger_pin->>'tgtype')::smallint OR trigger_observed.tgisinternal IS DISTINCT FROM false OR trigger_observed.definition IS DISTINCT FROM trigger_pin->>'definition' OR trigger_observed.full_trigger_metadata_sha256 IS DISTINCT FROM trigger_pin->>'full_trigger_metadata_sha256' THEN RAISE EXCEPTION 'v81 exact enabled trigger premise changed';END IF;
   trigger_results:=trigger_results||jsonb_build_array(to_jsonb(trigger_observed));
  END LOOP;
  SELECT jsonb_build_object('session_user',session_user,'current_user',current_user,'current_role',current_role,
   'current_database',current_database(),'server_version_num',current_setting('server_version_num'),
   'current_role_superuser',me.rolsuper,'current_role_bypass_rls',me.rolbypassrls,
   'planner_security_definer',p.prosecdef,'planner_owner_oid',p.proowner,'planner_owner_name',owner.rolname,
   'planner_owner_superuser',owner.rolsuper,'planner_owner_bypass_rls',owner.rolbypassrls,
   'planner_proconfig',p.proconfig,'snapshot_security_definer',snapshot.prosecdef,'snapshot_proconfig',snapshot.proconfig)
   INTO role_context FROM pg_catalog.pg_roles me CROSS JOIN pg_catalog.pg_proc p
   JOIN pg_catalog.pg_roles owner ON owner.oid=p.proowner CROSS JOIN pg_catalog.pg_proc snapshot
   WHERE me.rolname=current_user AND p.oid=to_regprocedure('astra_ingestion_v1.backfill_plan_next_v2(jsonb)')
    AND snapshot.oid=to_regprocedure('astra_ingestion_v1.backfill_plan_snapshot_v2(text,integer)');
  SELECT jsonb_object_agg(name,jsonb_build_object('setting',setting,'unit',unit,'source',source)) INTO setting_context
   FROM pg_catalog.pg_settings WHERE name IN('search_path','row_security','work_mem','effective_cache_size','shared_buffers',
    'random_page_cost','seq_page_cost','cpu_tuple_cost','cpu_index_tuple_cost','cpu_operator_cost','default_statistics_target',
    'enable_nestloop','enable_hashjoin','enable_mergejoin','enable_indexscan','enable_indexonlyscan','enable_seqscan','enable_bitmapscan',
    'enable_memoize','enable_material','enable_sort','enable_incremental_sort','jit','plan_cache_mode','max_parallel_workers_per_gather',
    'effective_io_concurrency','lc_collate','lc_ctype','statement_timeout','lock_timeout','transaction_read_only','transaction_isolation','TimeZone');
  IF role_context->>'current_user' IS DISTINCT FROM 'postgres' OR role_context->>'planner_owner_name' IS DISTINCT FROM 'postgres'
   OR role_context->'current_role_bypass_rls' IS DISTINCT FROM 'true'::jsonb OR role_context->'planner_owner_bypass_rls' IS DISTINCT FROM 'true'::jsonb
   OR setting_context#>>'{work_mem,setting}' IS DISTINCT FROM '5120' OR setting_context#>>'{jit,setting}' IS DISTINCT FROM 'off' THEN
   RAISE EXCEPTION 'v81 candidate role/RLS or observed memory/JIT context changed; no query executed'; END IF;
  SELECT task.id INTO page_upper FROM astra_ingestion_v1.backfill_tasks_v2 task ORDER BY task.id DESC LIMIT 1;
  IF page_upper IS NULL THEN RAISE EXCEPTION 'v81 first-page observation has no global upper ID; no page measured';END IF;
  EXECUTE $explain$EXPLAIN (ANALYZE true, BUFFERS true, TIMING false, FORMAT JSON, COSTS true, VERBOSE false, SETTINGS false, SUMMARY true)
SELECT COALESCE(array_agg(page.id ORDER BY page.id),'{}'::text[]) FROM
      (SELECT task.id FROM astra_ingestion_v1.backfill_tasks_v2 task WHERE task.id<=$1 ORDER BY task.id LIMIT 500) page$explain$ INTO v_plan USING page_upper;
  IF jsonb_typeof(v_plan) IS DISTINCT FROM 'array' OR jsonb_array_length(v_plan)<>1
   OR jsonb_typeof(v_plan->0->'Plan') IS DISTINCT FROM 'object' OR octet_length(v_plan::text)>32768 THEN
   RAISE EXCEPTION 'v81 estimated plan shape or32768byte bound exceeded'; END IF;
  v_queue:=jsonb_build_array(jsonb_build_object('node',v_plan->0->'Plan','parent',NULL,'depth',0));
  WHILE jsonb_array_length(v_queue)>0 LOOP
   IF v_n>=64 THEN RAISE EXCEPTION 'v81 estimated plan exceeds64 nodes'; END IF;
   v_item:=v_queue->0;v_queue:=v_queue-0;v_node:=v_item->'node';v_n:=v_n+1;
   v_nodes:=v_nodes||jsonb_build_array(jsonb_strip_nulls(jsonb_build_object('ordinal',v_n,'parent',v_item->'parent','depth',v_item->'depth',
    'node_type',v_node->'Node Type','parent_relationship',v_node->'Parent Relationship','join_type',v_node->'Join Type',
    'relation',v_node->'Relation Name','alias',v_node->'Alias','index',v_node->'Index Name','scan_direction',v_node->'Scan Direction',
    'parallel_aware',v_node->'Parallel Aware','inner_unique',v_node->'Inner Unique','strategy',v_node->'Strategy',
    'startup_cost',v_node->'Startup Cost','total_cost',v_node->'Total Cost','estimated_rows',v_node->'Plan Rows','estimated_width',v_node->'Plan Width',
    'workers_planned',v_node->'Workers Planned','actual_rows',v_node->'Actual Rows','actual_loops',v_node->'Actual Loops',
    'heap_fetches',v_node->'Heap Fetches','rows_removed_filter',v_node->'Rows Removed by Filter',
    'shared_hit_blocks',v_node->'Shared Hit Blocks','shared_read_blocks',v_node->'Shared Read Blocks',
    'temp_read_blocks',v_node->'Temp Read Blocks','temp_written_blocks',v_node->'Temp Written Blocks',
    'matched_id_equality',CASE WHEN v_node->>'Alias'='matched' THEN v_node->>'Index Cond'='(id = missing_id.id)' END,'filter_sha256',CASE WHEN v_node?'Filter' THEN encode(sha256(convert_to(v_node->>'Filter','UTF8')),'hex') END,
    'index_condition_sha256',CASE WHEN v_node?'Index Cond' THEN encode(sha256(convert_to(v_node->>'Index Cond','UTF8')),'hex') END,
    'join_filter_sha256',CASE WHEN v_node?'Join Filter' THEN encode(sha256(convert_to(v_node->>'Join Filter','UTF8')),'hex') END)));
   FOR v_child IN SELECT value FROM jsonb_array_elements(COALESCE(v_node->'Plans','[]')) LOOP
    v_queue:=v_queue||jsonb_build_array(jsonb_build_object('node',v_child,'parent',v_n,'depth',(v_item->>'depth')::integer+1));
   END LOOP;
  END LOOP;
  result:=result||jsonb_build_object('state','BOUNDED_FIRST_ID_PAGE_MEASURED_READ_ONLY','plan_count',1,'selector_execution_count',1,
   'candidate_source_sha256','b4d89146c677d38889ddd15a7986bd03723eb2f1b986582da30e46d24b5e172d','candidate_selector_sha256','dafff4be9a4c54c9895038a01c459fda809f221fed11835ccf99dfda3e2cfe7d','upper_lookup_count',1,'trigger_proof',trigger_results,
   'primary_key_proof',pk_results,'role_context',role_context,'session_settings',setting_context,
   'planning_ms',v_plan->0->'Planning Time','execution_ms',v_plan->0->'Execution Time','result_rows',v_plan->0->'Plan'->'Actual Rows',
   'nodes',v_nodes,'limits',jsonb_build_array('One upper-ID lookup and one execution of the exact finite first-ID-page selector; no function installed or business helper invoked.',
    'Actual measurements belong to this connector-role snapshot and upper-ID-bound first-page query, not an RPC/cached-plan replay or a measured comparison with the cancelled whole-scan statement.',
    'No source rows, task IDs, raw predicates, MCVs/histograms or credential values are returned.',
    'Only explicit application/advisory locks are absent; ordinary relation locks may be acquired.',
    'Later scan pages, the500 per-ID existence/scope loops, snapshot writes, accounting and final sealing are not measured by this proposal.',
    'No performance success, activation, alternative query, second attempt or retry is authorized by this result.'));

 END IF;
 IF NOT COALESCE(isfinite((r.metadata->>'implementation_lease_until')::timestamptz)
  AND (r.metadata->>'implementation_lease_until')::timestamptz>clock_timestamp(),false) THEN
  RAISE EXCEPTION 'v81 read finite lease expired'; END IF;
 result:=result||jsonb_build_object('observed_at',clock_timestamp(),'lease_until',r.metadata->>'implementation_lease_until');
 IF octet_length(result::text)>30000 THEN RAISE EXCEPTION 'v81 safe output exceeds30000bytes'; END IF;
 RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='ASTRA_BOUNDED_SEAL_PAGE_PERF_V81:'||result::text;
END $selector_read$;
ROLLBACK;
