-- One component only. No mutating helper, provider request, advisory gate or write.
-- The page is an immutable temporal candidate, not a proved individual cause.
-- Summary and refresh inputs use current projected after-state, not historical old_summary.
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL transaction_read_only='on';
SET LOCAL transaction_isolation='repeatable read';
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $shared_read_profile$
DECLARE
 v_pins constant jsonb := $source_pins$[{"signature":"astra_ingestion_v1.backfill_maintain_v2(integer)","sha256":"6c880114a645c8a9167d5260c4aeabf58a10617c4244cf0340be1d6cf4bf0ce7","metadata":{"acl":["astra_ingestion_rpc_owner_v1=X/astra_ingestion_rpc_owner_v1","astra_ingestion_monitor_owner_v1=X/astra_ingestion_rpc_owner_v1"],"owner":"15985999","config":["search_path=\"\"","statement_timeout=8s","lock_timeout=2s"],"security_definer":true},"metadata_kind":"compact"},{"signature":"astra_ingestion_v1.rpc_dispatch(text,jsonb)","sha256":"a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520","metadata":{"acl":["astra_ingestion_rpc_owner_v1=X/astra_ingestion_rpc_owner_v1","anon=X/astra_ingestion_rpc_owner_v1"],"owner":"15985999","config":["search_path=\"\"","statement_timeout=10s","lock_timeout=3s"],"security_definer":true},"metadata_kind":"compact"},{"signature":"astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)","sha256":"28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44","metadata":{"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"owner":"16388","config":["search_path=\"\""],"security_definer":false},"metadata_kind":"compact"},{"signature":"astra_ingestion_v1.monitor_tick_v1()","sha256":"875c017ecf73df15163d15d3f9129b4507235dc893ccb4233d0a435154389057","metadata":{"acl":["astra_ingestion_monitor_owner_v1=X/astra_ingestion_monitor_owner_v1","postgres=X/astra_ingestion_monitor_owner_v1"],"owner":"15990376","config":["search_path=\"\"","statement_timeout=8s","lock_timeout=2s"],"security_definer":true},"metadata_kind":"compact"},{"signature":"astra_ingestion_v1.backfill_shared_maintain_v2(integer)","sha256":"5da488f3e44e2521b64f58230b2bc6db3c34800ae4ac259166f4dc223c8ad2be","metadata_kind":"full","metadata":{"oid":"16050110","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"probin":null,"procost":100,"prokind":"f","prolang":"13619","proname":"backfill_shared_maintain_v2","prorows":0,"pronargs":1,"proowner":"16388","proconfig":["search_path=\"\"","statement_timeout=15s"],"proretset":false,"prosecdef":true,"prorettype":"23","prosqlbody":null,"prosupport":"-","proargmodes":null,"proargnames":["p_limit"],"proargtypes":["23"],"proisstrict":false,"proparallel":"u","protrftypes":null,"provariadic":"0","provolatile":"v","proleakproof":false,"pronamespace":"15984556","proallargtypes":null,"proargdefaults":"({CONST :consttype 23 :consttypmod -1 :constcollid 0 :constlen 4 :constbyval true :constisnull false :location -1 :constvalue 4 [ 4 0 0 0 0 0 0 0 ]})","pronargdefaults":1}},{"signature":"astra_ingestion_v1.backfill_shared_project_v2(text,integer)","sha256":"78ceb1e794e9725ae8d0365ec92081c769853fa1c8345ab96c4adaf6e786fb9d","metadata_kind":"full","metadata":{"oid":"16050107","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"probin":null,"procost":100,"prokind":"f","prolang":"13619","proname":"backfill_shared_project_v2","prorows":0,"pronargs":2,"proowner":"16388","proconfig":["search_path=\"\"","statement_timeout=12s"],"proretset":false,"prosecdef":true,"prorettype":"3802","prosqlbody":null,"prosupport":"-","proargmodes":null,"proargnames":["p_task","p_page"],"proargtypes":["25","23"],"proisstrict":false,"proparallel":"u","protrftypes":null,"provariadic":"0","provolatile":"v","proleakproof":false,"pronamespace":"15984556","proallargtypes":null,"proargdefaults":null,"pronargdefaults":0}},{"signature":"astra_ingestion_v1.backfill_page_rows_v2(text,integer)","sha256":"e0d0a4bceb9f107c00f770546ef0a200ccb9dd7ca48df01c9c821569ac3b897c","metadata_kind":"full","metadata":{"oid":"16041365","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"probin":null,"procost":100,"prokind":"f","prolang":"13619","proname":"backfill_page_rows_v2","prorows":1000,"pronargs":2,"proowner":"16388","proconfig":["search_path=\"\""],"proretset":true,"prosecdef":false,"prorettype":"2249","prosqlbody":null,"prosupport":"-","proargmodes":["i","i","t","t","t","t","t","t","t"],"proargnames":["p_task_id","p_page_no","record_ordinal","symbol","market_date","session","target_window","record_group","source_row"],"proargtypes":["25","23"],"proisstrict":false,"proparallel":"u","protrftypes":null,"provariadic":"0","provolatile":"s","proleakproof":false,"pronamespace":"15984556","proallargtypes":["25","23","20","25","1082","25","16","25","3802"],"proargdefaults":null,"pronargdefaults":0}},{"signature":"astra_ingestion_v1.backfill_shared_apply_delta_v2(text,jsonb,jsonb)","sha256":"a221c414728aa7c83fbbe21d529689f814ea803f67c374adf3a9758f4a2b2142","metadata_kind":"full","metadata":{"oid":"16050112","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"probin":null,"procost":100,"prokind":"f","prolang":"13619","proname":"backfill_shared_apply_delta_v2","prorows":0,"pronargs":3,"proowner":"16388","proconfig":["search_path=\"\""],"proretset":false,"prosecdef":false,"prorettype":"2278","prosqlbody":null,"prosupport":"-","proargmodes":null,"proargnames":["p_run","p_old","p_new"],"proargtypes":["25","3802","3802"],"proisstrict":false,"proparallel":"u","protrftypes":null,"provariadic":"0","provolatile":"v","proleakproof":false,"pronamespace":"15984556","proallargtypes":null,"proargdefaults":null,"pronargdefaults":0}},{"signature":"astra_ingestion_v1.backfill_shared_meta_v2(text,text,text,text,jsonb)","sha256":"b7b0b8f8d3787b9370643dbe810938f6fbca75d3cfe50a0e007d3ae6970d3932","metadata_kind":"full","metadata":{"oid":"16050103","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"probin":null,"procost":100,"prokind":"f","prolang":"13619","proname":"backfill_shared_meta_v2","prorows":0,"pronargs":5,"proowner":"16388","proconfig":["search_path=\"\""],"proretset":false,"prosecdef":false,"prorettype":"3802","prosqlbody":null,"prosupport":"-","proargmodes":null,"proargnames":["p_provider","p_kind","p_group","p_symbol","p_row"],"proargtypes":["25","25","25","25","3802"],"proisstrict":false,"proparallel":"u","protrftypes":null,"provariadic":"0","provolatile":"i","proleakproof":false,"pronamespace":"15984556","proallargtypes":null,"proargdefaults":null,"pronargdefaults":0}},{"signature":"astra_ingestion_v1.backfill_shared_refresh_v2(text,jsonb)","sha256":"b18a30c47e13a9738f111ff739e8cda53120e882eaa7e7e0427144372ab8dbc4","metadata_kind":"full","metadata":{"oid":"16050105","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"probin":null,"procost":100,"prokind":"f","prolang":"13619","proname":"backfill_shared_refresh_v2","prorows":0,"pronargs":2,"proowner":"16388","proconfig":["search_path=\"\""],"proretset":false,"prosecdef":false,"prorettype":"2278","prosqlbody":null,"prosupport":"-","proargmodes":null,"proargnames":["p_run","p_keys"],"proargtypes":["25","3802"],"proisstrict":false,"proparallel":"u","protrftypes":null,"provariadic":"0","provolatile":"v","proleakproof":false,"pronamespace":"15984556","proallargtypes":null,"proargdefaults":null,"pronargdefaults":0}},{"signature":"astra_ingestion_v1.backfill_shared_summary_v2(text,jsonb)","sha256":"e6459ef0b9dbe71bcd0ede375e904154b3d4278c6af27f033fc0c942ee9e0a78","metadata_kind":"full","metadata":{"oid":"16050111","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"probin":null,"procost":100,"prokind":"f","prolang":"14","proname":"backfill_shared_summary_v2","prorows":0,"pronargs":2,"proowner":"16388","proconfig":["search_path=\"\""],"proretset":false,"prosecdef":false,"prorettype":"3802","prosqlbody":null,"prosupport":"-","proargmodes":null,"proargnames":["p_run","p_keys"],"proargtypes":["25","3802"],"proisstrict":false,"proparallel":"u","protrftypes":null,"provariadic":"0","provolatile":"s","proleakproof":false,"pronamespace":"15984556","proallargtypes":null,"proargdefaults":null,"pronargdefaults":0}},{"signature":"astra_ingestion_v1.backfill_date_v2(text)","sha256":"7adc3f4ac60be32dd4348becbb325aeaf625cfd8c624b4d266fdbb7a038302f9","metadata_kind":"full","metadata":{"oid":"16041364","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"probin":null,"procost":100,"prokind":"f","prolang":"13619","proname":"backfill_date_v2","prorows":0,"pronargs":1,"proowner":"16388","proconfig":["search_path=\"\""],"proretset":false,"prosecdef":false,"prorettype":"1082","prosqlbody":null,"prosupport":"-","proargmodes":null,"proargnames":["v"],"proargtypes":["25"],"proisstrict":false,"proparallel":"u","protrftypes":null,"provariadic":"0","provolatile":"i","proleakproof":false,"pronamespace":"15984556","proallargtypes":null,"proargdefaults":null,"pronargdefaults":0}},{"signature":"astra_ingestion_v1.backfill_nonminute_field_reason_v2(jsonb,text,text)","sha256":"806b0acab6e7cab1f085cb0310f781ffe29806f83df04ab65351a7cc59bde107","metadata_kind":"full","metadata":{"oid":"16047819","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"probin":null,"procost":100,"prokind":"f","prolang":"13619","proname":"backfill_nonminute_field_reason_v2","prorows":0,"pronargs":3,"proowner":"16388","proconfig":["search_path=\"\""],"proretset":false,"prosecdef":false,"prorettype":"25","prosqlbody":null,"prosupport":"-","proargmodes":null,"proargnames":["v","p_type","p_reason"],"proargtypes":["3802","25","25"],"proisstrict":false,"proparallel":"u","protrftypes":null,"provariadic":"0","provolatile":"i","proleakproof":false,"pronamespace":"15984556","proallargtypes":null,"proargdefaults":null,"pronargdefaults":0}},{"signature":"astra_ingestion_v1.backfill_nonminute_field_spec_v2(text,text)","sha256":"bcea12a2a66ae2915e7f0332ee461e576b94e94dfe637ed4617eb77e1398e740","metadata_kind":"full","metadata":{"oid":"16047817","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"probin":null,"procost":100,"prokind":"f","prolang":"14","proname":"backfill_nonminute_field_spec_v2","prorows":0,"pronargs":2,"proowner":"16388","proconfig":["search_path=\"\""],"proretset":false,"prosecdef":false,"prorettype":"3802","prosqlbody":null,"prosupport":"-","proargmodes":null,"proargnames":["p_family","p_kind"],"proargtypes":["25","25"],"proisstrict":false,"proparallel":"u","protrftypes":null,"provariadic":"0","provolatile":"i","proleakproof":false,"pronamespace":"15984556","proallargtypes":null,"proargdefaults":null,"pronargdefaults":0}},{"signature":"astra_ingestion_v1.backfill_stamp_v2(text)","sha256":"63988e76443273e860cfc5cc7929dd2282c5525d9e824c443e79c03b15e6a1e9","metadata_kind":"full","metadata":{"oid":"16041363","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"probin":null,"procost":100,"prokind":"f","prolang":"13619","proname":"backfill_stamp_v2","prorows":0,"pronargs":1,"proowner":"16388","proconfig":["search_path=\"\""],"proretset":false,"prosecdef":false,"prorettype":"1184","prosqlbody":null,"prosupport":"-","proargmodes":null,"proargnames":["v"],"proargtypes":["25"],"proisstrict":false,"proparallel":"u","protrftypes":null,"provariadic":"0","provolatile":"i","proleakproof":false,"pronamespace":"15984556","proallargtypes":null,"proargdefaults":null,"pronargdefaults":0}}]$source_pins$::jsonb;
 v_component constant text := 'REFRESH_RECORD_SELECT_INPUT';
 v_sql constant text := $read_select$WITH keys AS MATERIALIZED(SELECT value record_key FROM jsonb_array_elements_text($6)),
 versions AS MATERIALIZED(SELECT v.* FROM keys k CROSS JOIN LATERAL(
  SELECT v.* FROM astra_ingestion_v1.backfill_shared_versions_v2 v
  WHERE v.run_id=$5 AND v.record_key=k.record_key OFFSET 0) v),
 stats AS MATERIALIZED(SELECT record_key,count(*) versions,bool_and(version_timestamp IS NOT NULL) ordered,max(version_timestamp) latest FROM versions GROUP BY record_key),
 candidates AS MATERIALIZED(SELECT v.*,s.versions,s.ordered FROM versions v JOIN stats s USING(record_key) WHERE NOT s.ordered OR v.version_timestamp=s.latest),
 candidate_counts AS MATERIALIZED(SELECT record_key,count(*) n FROM candidates GROUP BY record_key),
 chosen AS MATERIALIZED(SELECT DISTINCT ON(record_key) * FROM candidates ORDER BY record_key,row_sha256,task_id,page_no,record_ordinal),
 votes AS MATERIALIZED(SELECT c.record_key,f.key field,count(*) n,count(DISTINCT f.value->>'value_sha256') values,
  bool_or((f.value->>'nonnull')::boolean) nonnull,min(f.value->>'datatype') datatype
  FROM candidates c CROSS JOIN LATERAL jsonb_each(c.field_states) f GROUP BY c.record_key,f.key),
 chosen_fields AS MATERIALIZED(SELECT c.record_key,f.key field,f.value field_state FROM chosen c CROSS JOIN LATERAL jsonb_each(c.field_states) f),
 fields AS MATERIALIZED(SELECT c.record_key,jsonb_object_agg(v.field,COALESCE(cf.field_state,jsonb_build_object('datatype',v.datatype,'nonnull',v.nonnull))||
  CASE WHEN v.n<n.n OR v.values>1 THEN jsonb_build_object('nonnull',v.nonnull,'reason','CONFLICTING_PROVIDER_RECORD_VERSIONS') ELSE '{}'::jsonb END) states,
  COALESCE(jsonb_agg(v.field ORDER BY v.field) FILTER(WHERE v.n<n.n OR v.values>1),'[]') conflicts
  FROM chosen c JOIN votes v USING(record_key) JOIN candidate_counts n USING(record_key)
  LEFT JOIN chosen_fields cf ON cf.record_key=c.record_key AND cf.field=v.field GROUP BY c.record_key),
 clean AS MATERIALIZED(SELECT c.*,n.n candidates,f.states,f.conflicts,
  (SELECT COALESCE(jsonb_object_agg(d.key,CASE WHEN f.conflicts ? CASE d.key WHEN 'publication_date_new_york' THEN c.primary_date_field WHEN 'market_session_new_york' THEN 't' ELSE d.key END THEN 'null'::jsonb ELSE d.value END),'{}') FROM jsonb_each(c.date_axes) d) clean_axes
  FROM chosen c JOIN fields f USING(record_key) JOIN candidate_counts n USING(record_key)),
 dated AS MATERIALIZED(SELECT c.*,a.first_date,a.last_date,COALESCE(a.in_target,false) in_target
  FROM clean c LEFT JOIN LATERAL(SELECT min((value#>>'{}')::date) first_date,max((value#>>'{}')::date) last_date,
   bool_or((value#>>'{}')::date BETWEEN '2025-09-01'::date AND '2026-07-31'::date) in_target FROM jsonb_each(c.clean_axes) WHERE value<>'null'::jsonb) a ON true),
 occurrences AS MATERIALIZED(SELECT k.record_key,count(*) n FROM keys k CROSS JOIN LATERAL(
  SELECT 1 FROM astra_ingestion_v1.backfill_shared_occurrences_v2 o
  WHERE o.run_id=$5 AND o.record_key=k.record_key OFFSET 0) o GROUP BY k.record_key)

 SELECT $5,c.record_key,c.row_sha256,c.provider,c.record_type,c.kind,c.record_group,c.provider_record_id,c.identity_basis,
  CASE WHEN c.record_type='ACTION' AND c.conflicts ?| ARRAY['ticker','symbol','initiating_symbol'] THEN NULL ELSE c.symbol END,
  CASE WHEN c.conflicts ? c.primary_date_field THEN NULL ELSE c.market_date END,c.clean_axes,c.primary_date_field,
  CASE WHEN c.in_target THEN 'TARGET' WHEN c.last_date<'2025-09-01'::date THEN 'SUPPORT' WHEN c.first_date>'2026-07-31'::date THEN 'AFTER_TARGET'
   WHEN c.first_date IS NOT NULL THEN 'BOUNDARY_SUPPORT' ELSE 'UNKNOWN_DATE' END,
  COALESCE(c.first_date<'2025-09-01'::date AND c.last_date>='2025-09-01'::date OR c.first_date<='2026-07-31'::date AND c.last_date>'2026-07-31'::date,false),
  COALESCE(NOT c.in_target AND c.first_date<'2025-09-01'::date AND c.last_date>'2026-07-31'::date,false),
  c.versions,c.candidates,c.ordered,o.n,c.conflicts,c.states,c.delivery_families,c.task_id,c.page_no,c.record_ordinal
 FROM dated c JOIN occurrences o USING(record_key)$read_select$;
 v_task astra_ingestion_v1.backfill_tasks_v2;
 v_run jsonb; v_member_count bigint; v_definition text; v_metadata jsonb; v_pin jsonb;
 v_keys jsonb; v_occurrences bigint; v_key_count integer; v_keys_ms numeric;
 v_plan jsonb; v_nodes jsonb; v_node_count integer; v_result jsonb; v_started timestamptz;
 v_role_matches_project_owner boolean; v_body_digest text; v_raw_bytes integer;
BEGIN
 IF current_setting('transaction_read_only')<>'on'
  OR current_setting('transaction_isolation')<>'repeatable read'
  OR current_setting('statement_timeout')<>'8s' OR current_setting('lock_timeout')<>'3s' THEN
  RAISE EXCEPTION 'Shared read profile requires enforced read-only repeatable-read 8s/3s bounds';
 END IF;
 IF v_component NOT IN ('PARSE_FULL_PAGE','PROJECT_FULL_METADATA','CURRENT_SUMMARY',
  'REFRESH_RECORD_SELECT_INPUT','REFRESH_LINK_SELECT_INPUT') THEN
  RAISE EXCEPTION 'Shared read profile component is not admitted';
 END IF;
 FOR v_pin IN SELECT value FROM jsonb_array_elements(v_pins) LOOP
  SELECT pg_get_functiondef(f.oid),CASE WHEN v_pin->>'metadata_kind'='full'
   THEN to_jsonb(f)-'prosrc' ELSE jsonb_build_object('acl',f.proacl,'owner',f.proowner::text,
    'config',f.proconfig,'security_definer',f.prosecdef) END
   INTO STRICT v_definition,v_metadata FROM pg_proc f WHERE f.oid=(v_pin->>'signature')::regprocedure;
  IF encode(sha256(convert_to(v_definition,'UTF8')),'hex') IS DISTINCT FROM v_pin->>'sha256'
   OR v_metadata IS DISTINCT FROM v_pin->'metadata' THEN
   RAISE EXCEPTION 'Shared read profile source or metadata changed';
  END IF;
 END LOOP;
 SELECT current_user=pg_get_userbyid(proowner) INTO STRICT v_role_matches_project_owner
 FROM pg_proc WHERE oid='astra_ingestion_v1.backfill_shared_project_v2(text,integer)'::regprocedure;
 SELECT jsonb_build_object('id',id,'status',status,'fence',fence,'cohort_sha256',cohort_sha256,
  'owner',metadata->>'implementation_owner','lease_until',metadata->>'implementation_lease_until')
 INTO STRICT v_run FROM astra_ingestion_v1.backfill_runs_v2
 WHERE id='fixed3000-20250901-20260731-v1-20261030';
 SELECT count(*) INTO v_member_count FROM astra_ingestion_v1.backfill_members_v2
 WHERE run_id=v_run->>'id';
 IF v_run->>'owner' IS DISTINCT FROM 'root-replacement-20261030T042603Z'
  OR COALESCE((v_run->>'lease_until')::timestamptz>clock_timestamp(),false) IS NOT TRUE
  OR (v_run->>'fence')::bigint IS DISTINCT FROM 1
  OR v_run->>'cohort_sha256' IS DISTINCT FROM '2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
  OR v_member_count<>3000 THEN
  RAISE EXCEPTION 'Shared read profile owner, lease, fence, cohort or members changed';
 END IF;
 SELECT * INTO STRICT v_task FROM astra_ingestion_v1.backfill_tasks_v2
 WHERE id='backfill-plan-e0b79e51a28872e6abbee0d1f23c340ab77857acfa36dc3fbd85dba162329bec' AND run_id=v_run->>'id' AND run_fence=1
  AND family='CTX02' AND kind='alpaca_option_contracts' AND provider='Alpaca';
 SELECT encode(sha256(convert_to(p.raw_body,'UTF8')),'hex'),octet_length(p.raw_body)
 INTO STRICT v_body_digest,v_raw_bytes
 FROM astra_ingestion_v1.backfill_pages_v2 p
 JOIN astra_ingestion_v1.backfill_readbacks_v2 b USING(task_id,page_no)
 JOIN astra_ingestion_v1.backfill_shared_pages_v2 s USING(task_id,page_no)
 WHERE p.task_id=v_task.id AND p.page_no=0 AND p.run_id=v_run->>'id'
  AND b.run_id=p.run_id AND s.run_id=p.run_id
  AND p.record_count=1000 AND p.source_bytes=711481 AND s.source_records=1000
  AND p.body_sha256='9adb2b2051d81b7906efd0776a2ff759912a5eda0c216a605098515b0ec1a720' AND p.records_sha256='f0078f38422a29f854bedbe0555ad626458dec83282b2738b17bf89dc14e622f'
  AND p.committed_at='2026-10-30T07:11:48.557746+00:00'::timestamptz
  AND b.actual_records=1000 AND b.expected_records=b.actual_records
  AND b.body_sha256=p.body_sha256 AND b.readback_sha256=b.body_sha256
  AND b.verified_at='2026-10-30T07:11:49.345024+00:00'::timestamptz
  AND s.projected_at='2026-10-30T15:42:07.642071+00:00'::timestamptz;
 IF v_body_digest IS DISTINCT FROM '9adb2b2051d81b7906efd0776a2ff759912a5eda0c216a605098515b0ec1a720' OR v_raw_bytes IS DISTINCT FROM 711481 THEN
  RAISE EXCEPTION 'Shared read profile retained body integrity changed';
 END IF;
 IF v_component IN ('CURRENT_SUMMARY','REFRESH_RECORD_SELECT_INPUT','REFRESH_LINK_SELECT_INPUT') THEN
  v_started:=clock_timestamp();
  SELECT count(*),COALESCE(jsonb_agg(DISTINCT record_key),'[]') INTO v_occurrences,v_keys
  FROM astra_ingestion_v1.backfill_shared_occurrences_v2
  WHERE task_id=v_task.id AND page_no=0 AND run_id=v_run->>'id';
  v_keys_ms:=extract(epoch FROM clock_timestamp()-v_started)*1000;
  v_key_count:=jsonb_array_length(v_keys);
  IF v_occurrences<>1000 OR v_key_count<1 OR v_key_count>1000 THEN
   RAISE EXCEPTION 'Shared read profile retained occurrence/key bounds changed';
  END IF;
 END IF;
 EXECUTE 'EXPLAIN (ANALYZE TRUE,BUFFERS TRUE,TIMING FALSE,SETTINGS FALSE,FORMAT JSON) '||v_sql
 INTO v_plan USING v_task.id,0,v_task.provider,v_task.kind,v_task.run_id,v_keys;
 WITH RECURSIVE nodes(path,node) AS(
  SELECT ARRAY[0::bigint],v_plan->0->'Plan'
  UNION ALL SELECT n.path||c.ordinality,c.value FROM nodes n
   CROSS JOIN LATERAL jsonb_array_elements(COALESCE(n.node->'Plans','[]')) WITH ORDINALITY c(value,ordinality)
 )
 SELECT count(*),jsonb_agg(jsonb_build_object('path',path,'node_type',node->'Node Type',
  'parent_relationship',node->'Parent Relationship','join_type',node->'Join Type',
  'relation',CASE WHEN node->>'Relation Name'=ANY(ARRAY[
   'backfill_shared_versions_v2','backfill_shared_records_v2','backfill_shared_occurrences_v2',
   'backfill_shared_version_links_v2','backfill_shared_links_v2','backfill_members_v2'])
   THEN node->'Relation Name' ELSE NULL END,
  'actual_rows',node->'Actual Rows','actual_loops',node->'Actual Loops',
  'rows_removed_filter',node->'Rows Removed by Filter','rows_removed_join_filter',node->'Rows Removed by Join Filter',
  'shared_hits',node->'Shared Hit Blocks','shared_reads',node->'Shared Read Blocks',
  'temp_reads',node->'Temp Read Blocks','temp_writes',node->'Temp Written Blocks') ORDER BY path)
 INTO v_node_count,v_nodes FROM nodes;
 IF v_node_count>300 THEN RAISE EXCEPTION 'Shared read profile plan exceeded bounded node count';END IF;
 IF COALESCE((v_run->>'lease_until')::timestamptz>clock_timestamp(),false) IS NOT TRUE THEN
  RAISE EXCEPTION 'Shared read profile lease expired during read';
 END IF;
 v_result:=jsonb_build_object('schema','astra.shared-pure-read-profile/1','complete',true,
  'observed_at',clock_timestamp(),'component',v_component,'variant','CANDIDATE_SELECT_ONLY_FUNCTION_NOT_INSTALLED',
  'candidate_definition_sha256','7f538bf47cb5e74050c20266e01cbe9d6521c1a65663aaf2e0fe38d62041f1a4',
  'installed_function_sha256','b18a30c47e13a9738f111ff739e8cda53120e882eaa7e7e0427144372ab8dbc4','run',v_run,'member_count',v_member_count,
  'task_id',v_task.id,'page_no',0,'body_sha256',v_body_digest,'raw_bytes',v_raw_bytes,
  'retained_page_records',1000,'source_and_readback_integrity_verified',true,
  'temporal_origin_audit_id',41,'page_backend_identity_proven',false,
  'key_source',CASE WHEN v_keys IS NOT NULL THEN 'CURRENT_IMMUTABLE_PAGE_OCCURRENCES' ELSE 'NOT_USED' END,
  'current_occurrences',v_occurrences,'current_distinct_keys',v_key_count,'key_derivation_ms',v_keys_ms,
  'keys_sha256',CASE WHEN v_keys IS NOT NULL THEN encode(sha256(convert_to(v_keys::text,'UTF8')),'hex') ELSE NULL END,
  'planning_ms',v_plan->0->'Planning Time','execution_ms',v_plan->0->'Execution Time','nodes',v_nodes,
  'source_pin_count',jsonb_array_length(v_pins),'source_and_metadata_pins_verified',true,
  'execution_role_matches_shared_project_owner',v_role_matches_project_owner,
  'transaction_read_only',current_setting('transaction_read_only'),
  'transaction_isolation',current_setting('transaction_isolation'),
  'statement_timeout',current_setting('statement_timeout'),'lock_timeout',current_setting('lock_timeout'),
  'raw_source_metadata_values_keys_or_plan_expressions_returned',false,
  'mutating_helpers_or_provider_calls',false,'advisory_lock_acquired',false,
  'interpretation',jsonb_build_array(
   'A full SELECT projection is evaluated; no COUNT wrapper can prune its output expressions.',
   'This already-projected immutable page is a temporal candidate, not a proved individual cause of audit41 shared time.',
   'Summary and refresh inputs read current persisted after-state; they do not reconstruct historical old_summary or initial insert work.',
   'These independently bounded calls have separate snapshots and cache conditions; no uncontrolled latency ratio is justified.',
   'A dynamic direct-role SELECT plan does not establish the original cached function plan, write/trigger cost, lock wait or whole-phase recovery.'));
 IF octet_length(v_result::text)>60000 THEN RAISE EXCEPTION 'Shared read profile output exceeded bound';END IF;
 RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='SHARED_READ_PROFILE_V74 '||v_result::text;
END $shared_read_profile$;
ROLLBACK;
