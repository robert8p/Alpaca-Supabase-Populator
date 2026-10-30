-- PREPARATION ONLY: exact-head publication/CI and root selection precede activation.
-- forward only the shared-refresh function body; no provider/helper call, grant, table or index change.
-- Existing global gate -> run FOR SHARE; strict before/after source, full metadata and catalog checks.
BEGIN;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $shared_field_cache_forward$
DECLARE
 v_pins constant jsonb := $shared_pins$[{"signature":"astra_ingestion_v1.backfill_maintain_v2(integer)","sha256":"6c880114a645c8a9167d5260c4aeabf58a10617c4244cf0340be1d6cf4bf0ce7","metadata":{"acl":["astra_ingestion_rpc_owner_v1=X/astra_ingestion_rpc_owner_v1","astra_ingestion_monitor_owner_v1=X/astra_ingestion_rpc_owner_v1"],"owner":"15985999","config":["search_path=\"\"","statement_timeout=8s","lock_timeout=2s"],"security_definer":true},"metadata_kind":"compact"},{"signature":"astra_ingestion_v1.rpc_dispatch(text,jsonb)","sha256":"a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520","metadata":{"acl":["astra_ingestion_rpc_owner_v1=X/astra_ingestion_rpc_owner_v1","anon=X/astra_ingestion_rpc_owner_v1"],"owner":"15985999","config":["search_path=\"\"","statement_timeout=10s","lock_timeout=3s"],"security_definer":true},"metadata_kind":"compact"},{"signature":"astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)","sha256":"28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44","metadata":{"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"owner":"16388","config":["search_path=\"\""],"security_definer":false},"metadata_kind":"compact"},{"signature":"astra_ingestion_v1.monitor_tick_v1()","sha256":"875c017ecf73df15163d15d3f9129b4507235dc893ccb4233d0a435154389057","metadata":{"acl":["astra_ingestion_monitor_owner_v1=X/astra_ingestion_monitor_owner_v1","postgres=X/astra_ingestion_monitor_owner_v1"],"owner":"15990376","config":["search_path=\"\"","statement_timeout=8s","lock_timeout=2s"],"security_definer":true},"metadata_kind":"compact"},{"signature":"astra_ingestion_v1.backfill_shared_maintain_v2(integer)","sha256":"5da488f3e44e2521b64f58230b2bc6db3c34800ae4ac259166f4dc223c8ad2be","metadata_kind":"full","metadata":{"oid":"16050110","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"probin":null,"procost":100,"prokind":"f","prolang":"13619","proname":"backfill_shared_maintain_v2","prorows":0,"pronargs":1,"proowner":"16388","proconfig":["search_path=\"\"","statement_timeout=15s"],"proretset":false,"prosecdef":true,"prorettype":"23","prosqlbody":null,"prosupport":"-","proargmodes":null,"proargnames":["p_limit"],"proargtypes":["23"],"proisstrict":false,"proparallel":"u","protrftypes":null,"provariadic":"0","provolatile":"v","proleakproof":false,"pronamespace":"15984556","proallargtypes":null,"proargdefaults":"({CONST :consttype 23 :consttypmod -1 :constcollid 0 :constlen 4 :constbyval true :constisnull false :location -1 :constvalue 4 [ 4 0 0 0 0 0 0 0 ]})","pronargdefaults":1}},{"signature":"astra_ingestion_v1.backfill_shared_project_v2(text,integer)","sha256":"78ceb1e794e9725ae8d0365ec92081c769853fa1c8345ab96c4adaf6e786fb9d","metadata_kind":"full","metadata":{"oid":"16050107","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"probin":null,"procost":100,"prokind":"f","prolang":"13619","proname":"backfill_shared_project_v2","prorows":0,"pronargs":2,"proowner":"16388","proconfig":["search_path=\"\"","statement_timeout=12s"],"proretset":false,"prosecdef":true,"prorettype":"3802","prosqlbody":null,"prosupport":"-","proargmodes":null,"proargnames":["p_task","p_page"],"proargtypes":["25","23"],"proisstrict":false,"proparallel":"u","protrftypes":null,"provariadic":"0","provolatile":"v","proleakproof":false,"pronamespace":"15984556","proallargtypes":null,"proargdefaults":null,"pronargdefaults":0}},{"signature":"astra_ingestion_v1.backfill_page_rows_v2(text,integer)","sha256":"e0d0a4bceb9f107c00f770546ef0a200ccb9dd7ca48df01c9c821569ac3b897c","metadata_kind":"full","metadata":{"oid":"16041365","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"probin":null,"procost":100,"prokind":"f","prolang":"13619","proname":"backfill_page_rows_v2","prorows":1000,"pronargs":2,"proowner":"16388","proconfig":["search_path=\"\""],"proretset":true,"prosecdef":false,"prorettype":"2249","prosqlbody":null,"prosupport":"-","proargmodes":["i","i","t","t","t","t","t","t","t"],"proargnames":["p_task_id","p_page_no","record_ordinal","symbol","market_date","session","target_window","record_group","source_row"],"proargtypes":["25","23"],"proisstrict":false,"proparallel":"u","protrftypes":null,"provariadic":"0","provolatile":"s","proleakproof":false,"pronamespace":"15984556","proallargtypes":["25","23","20","25","1082","25","16","25","3802"],"proargdefaults":null,"pronargdefaults":0}},{"signature":"astra_ingestion_v1.backfill_shared_apply_delta_v2(text,jsonb,jsonb)","sha256":"a221c414728aa7c83fbbe21d529689f814ea803f67c374adf3a9758f4a2b2142","metadata_kind":"full","metadata":{"oid":"16050112","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"probin":null,"procost":100,"prokind":"f","prolang":"13619","proname":"backfill_shared_apply_delta_v2","prorows":0,"pronargs":3,"proowner":"16388","proconfig":["search_path=\"\""],"proretset":false,"prosecdef":false,"prorettype":"2278","prosqlbody":null,"prosupport":"-","proargmodes":null,"proargnames":["p_run","p_old","p_new"],"proargtypes":["25","3802","3802"],"proisstrict":false,"proparallel":"u","protrftypes":null,"provariadic":"0","provolatile":"v","proleakproof":false,"pronamespace":"15984556","proallargtypes":null,"proargdefaults":null,"pronargdefaults":0}},{"signature":"astra_ingestion_v1.backfill_shared_meta_v2(text,text,text,text,jsonb)","sha256":"b7b0b8f8d3787b9370643dbe810938f6fbca75d3cfe50a0e007d3ae6970d3932","metadata_kind":"full","metadata":{"oid":"16050103","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"probin":null,"procost":100,"prokind":"f","prolang":"13619","proname":"backfill_shared_meta_v2","prorows":0,"pronargs":5,"proowner":"16388","proconfig":["search_path=\"\""],"proretset":false,"prosecdef":false,"prorettype":"3802","prosqlbody":null,"prosupport":"-","proargmodes":null,"proargnames":["p_provider","p_kind","p_group","p_symbol","p_row"],"proargtypes":["25","25","25","25","3802"],"proisstrict":false,"proparallel":"u","protrftypes":null,"provariadic":"0","provolatile":"i","proleakproof":false,"pronamespace":"15984556","proallargtypes":null,"proargdefaults":null,"pronargdefaults":0}},{"signature":"astra_ingestion_v1.backfill_shared_summary_v2(text,jsonb)","sha256":"e6459ef0b9dbe71bcd0ede375e904154b3d4278c6af27f033fc0c942ee9e0a78","metadata_kind":"full","metadata":{"oid":"16050111","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"probin":null,"procost":100,"prokind":"f","prolang":"14","proname":"backfill_shared_summary_v2","prorows":0,"pronargs":2,"proowner":"16388","proconfig":["search_path=\"\""],"proretset":false,"prosecdef":false,"prorettype":"3802","prosqlbody":null,"prosupport":"-","proargmodes":null,"proargnames":["p_run","p_keys"],"proargtypes":["25","3802"],"proisstrict":false,"proparallel":"u","protrftypes":null,"provariadic":"0","provolatile":"s","proleakproof":false,"pronamespace":"15984556","proallargtypes":null,"proargdefaults":null,"pronargdefaults":0}},{"signature":"astra_ingestion_v1.backfill_date_v2(text)","sha256":"7adc3f4ac60be32dd4348becbb325aeaf625cfd8c624b4d266fdbb7a038302f9","metadata_kind":"full","metadata":{"oid":"16041364","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"probin":null,"procost":100,"prokind":"f","prolang":"13619","proname":"backfill_date_v2","prorows":0,"pronargs":1,"proowner":"16388","proconfig":["search_path=\"\""],"proretset":false,"prosecdef":false,"prorettype":"1082","prosqlbody":null,"prosupport":"-","proargmodes":null,"proargnames":["v"],"proargtypes":["25"],"proisstrict":false,"proparallel":"u","protrftypes":null,"provariadic":"0","provolatile":"i","proleakproof":false,"pronamespace":"15984556","proallargtypes":null,"proargdefaults":null,"pronargdefaults":0}},{"signature":"astra_ingestion_v1.backfill_nonminute_field_reason_v2(jsonb,text,text)","sha256":"806b0acab6e7cab1f085cb0310f781ffe29806f83df04ab65351a7cc59bde107","metadata_kind":"full","metadata":{"oid":"16047819","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"probin":null,"procost":100,"prokind":"f","prolang":"13619","proname":"backfill_nonminute_field_reason_v2","prorows":0,"pronargs":3,"proowner":"16388","proconfig":["search_path=\"\""],"proretset":false,"prosecdef":false,"prorettype":"25","prosqlbody":null,"prosupport":"-","proargmodes":null,"proargnames":["v","p_type","p_reason"],"proargtypes":["3802","25","25"],"proisstrict":false,"proparallel":"u","protrftypes":null,"provariadic":"0","provolatile":"i","proleakproof":false,"pronamespace":"15984556","proallargtypes":null,"proargdefaults":null,"pronargdefaults":0}},{"signature":"astra_ingestion_v1.backfill_nonminute_field_spec_v2(text,text)","sha256":"bcea12a2a66ae2915e7f0332ee461e576b94e94dfe637ed4617eb77e1398e740","metadata_kind":"full","metadata":{"oid":"16047817","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"probin":null,"procost":100,"prokind":"f","prolang":"14","proname":"backfill_nonminute_field_spec_v2","prorows":0,"pronargs":2,"proowner":"16388","proconfig":["search_path=\"\""],"proretset":false,"prosecdef":false,"prorettype":"3802","prosqlbody":null,"prosupport":"-","proargmodes":null,"proargnames":["p_family","p_kind"],"proargtypes":["25","25"],"proisstrict":false,"proparallel":"u","protrftypes":null,"provariadic":"0","provolatile":"i","proleakproof":false,"pronamespace":"15984556","proallargtypes":null,"proargdefaults":null,"pronargdefaults":0}},{"signature":"astra_ingestion_v1.backfill_stamp_v2(text)","sha256":"63988e76443273e860cfc5cc7929dd2282c5525d9e824c443e79c03b15e6a1e9","metadata_kind":"full","metadata":{"oid":"16041363","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"probin":null,"procost":100,"prokind":"f","prolang":"13619","proname":"backfill_stamp_v2","prorows":0,"pronargs":1,"proowner":"16388","proconfig":["search_path=\"\""],"proretset":false,"prosecdef":false,"prorettype":"1184","prosqlbody":null,"prosupport":"-","proargmodes":null,"proargnames":["v"],"proargtypes":["25"],"proisstrict":false,"proparallel":"u","protrftypes":null,"provariadic":"0","provolatile":"i","proleakproof":false,"pronamespace":"15984556","proallargtypes":null,"proargdefaults":null,"pronargdefaults":0}}]$shared_pins$::jsonb;
 v_expected_metadata constant jsonb := $shared_metadata${"oid":"16050105","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"probin":null,"procost":100,"prokind":"f","prolang":"13619","proname":"backfill_shared_refresh_v2","prorows":0,"pronargs":2,"proowner":"16388","proconfig":["search_path=\"\""],"proretset":false,"prosecdef":false,"prorettype":"2278","prosqlbody":null,"prosupport":"-","proargmodes":null,"proargnames":["p_run","p_keys"],"proargtypes":["25","3802"],"proisstrict":false,"proparallel":"u","protrftypes":null,"provariadic":"0","provolatile":"v","proleakproof":false,"pronamespace":"15984556","proallargtypes":null,"proargdefaults":null,"pronargdefaults":0}$shared_metadata$::jsonb;
 v_replacement constant text := $shared_field_replacement$CREATE OR REPLACE FUNCTION astra_ingestion_v1.backfill_shared_refresh_v2(p_run text, p_keys jsonb)
 RETURNS void
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
BEGIN
 -- backfill_shared_refresh_bounded_keys_v2: bind each immutable archive lookup
 -- to one supplied key before joining compact intermediates. OFFSET0 keeps the
 -- parameterized key restriction from being flattened into a run-wide join.
 WITH keys AS MATERIALIZED(SELECT value record_key FROM jsonb_array_elements_text(p_keys)),
 versions AS MATERIALIZED(SELECT v.* FROM keys k CROSS JOIN LATERAL(
  SELECT v.* FROM astra_ingestion_v1.backfill_shared_versions_v2 v
  WHERE v.run_id=p_run AND v.record_key=k.record_key OFFSET 0) v),
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
  WHERE o.run_id=p_run AND o.record_key=k.record_key OFFSET 0) o GROUP BY k.record_key)
 INSERT INTO astra_ingestion_v1.backfill_shared_records_v2
 SELECT p_run,c.record_key,c.row_sha256,c.provider,c.record_type,c.kind,c.record_group,c.provider_record_id,c.identity_basis,
  CASE WHEN c.record_type='ACTION' AND c.conflicts ?| ARRAY['ticker','symbol','initiating_symbol'] THEN NULL ELSE c.symbol END,
  CASE WHEN c.conflicts ? c.primary_date_field THEN NULL ELSE c.market_date END,c.clean_axes,c.primary_date_field,
  CASE WHEN c.in_target THEN 'TARGET' WHEN c.last_date<'2025-09-01'::date THEN 'SUPPORT' WHEN c.first_date>'2026-07-31'::date THEN 'AFTER_TARGET'
   WHEN c.first_date IS NOT NULL THEN 'BOUNDARY_SUPPORT' ELSE 'UNKNOWN_DATE' END,
  COALESCE(c.first_date<'2025-09-01'::date AND c.last_date>='2025-09-01'::date OR c.first_date<='2026-07-31'::date AND c.last_date>'2026-07-31'::date,false),
  COALESCE(NOT c.in_target AND c.first_date<'2025-09-01'::date AND c.last_date>'2026-07-31'::date,false),
  c.versions,c.candidates,c.ordered,o.n,c.conflicts,c.states,c.delivery_families,c.task_id,c.page_no,c.record_ordinal
 FROM dated c JOIN occurrences o USING(record_key)
 ON CONFLICT(run_id,record_key) DO UPDATE SET row_sha256=EXCLUDED.row_sha256,kind=EXCLUDED.kind,record_group=EXCLUDED.record_group,
  provider_record_id=EXCLUDED.provider_record_id,identity_basis=EXCLUDED.identity_basis,symbol=EXCLUDED.symbol,market_date=EXCLUDED.market_date,
  date_axes=EXCLUDED.date_axes,primary_date_field=EXCLUDED.primary_date_field,period=EXCLUDED.period,boundary_crossing=EXCLUDED.boundary_crossing,boundary_support=EXCLUDED.boundary_support,
  source_versions=EXCLUDED.source_versions,current_candidate_versions=EXCLUDED.current_candidate_versions,ordered_versions=EXCLUDED.ordered_versions,
  source_occurrences=EXCLUDED.source_occurrences,conflict_fields=EXCLUDED.conflict_fields,field_states=EXCLUDED.field_states,delivery_families=EXCLUDED.delivery_families,
  task_id=EXCLUDED.task_id,page_no=EXCLUDED.page_no,record_ordinal=EXCLUDED.record_ordinal;

 DELETE FROM astra_ingestion_v1.backfill_shared_links_v2 l USING jsonb_array_elements_text(p_keys) k WHERE l.run_id=p_run AND l.record_key=k.value;
 WITH keys AS MATERIALIZED(SELECT DISTINCT value record_key FROM jsonb_array_elements_text(p_keys)),
 scoped_versions AS MATERIALIZED(SELECT v.* FROM keys k CROSS JOIN LATERAL(
  SELECT v.record_key,v.row_sha256,v.version_timestamp FROM astra_ingestion_v1.backfill_shared_versions_v2 v
  WHERE v.run_id=p_run AND v.record_key=k.record_key OFFSET 0) v),
 scoped_records AS MATERIALIZED(SELECT r.* FROM keys k CROSS JOIN LATERAL(
  SELECT r.record_key,r.ordered_versions,r.current_candidate_versions FROM astra_ingestion_v1.backfill_shared_records_v2 r
  WHERE r.run_id=p_run AND r.record_key=k.record_key OFFSET 0) r),
 scoped_links AS MATERIALIZED(SELECT l.* FROM keys k CROSS JOIN LATERAL(
  SELECT l.record_key,l.row_sha256,l.security_symbol,l.link_role FROM astra_ingestion_v1.backfill_shared_version_links_v2 l
  WHERE l.run_id=p_run AND l.record_key=k.record_key OFFSET 0) l),
 vstat AS MATERIALIZED(SELECT record_key,max(version_timestamp) latest FROM scoped_versions GROUP BY record_key),
 links AS MATERIALIZED(SELECT l.record_key,l.security_symbol,l.link_role,count(*) observed_versions,
  count(*) FILTER(WHERE NOT r.ordered_versions OR v.version_timestamp=s.latest) current_versions
  FROM scoped_links l JOIN scoped_records r USING(record_key)
  JOIN scoped_versions v ON v.record_key=l.record_key AND v.row_sha256=l.row_sha256
  JOIN vstat s ON s.record_key=l.record_key
  GROUP BY l.record_key,l.security_symbol,l.link_role)
 INSERT INTO astra_ingestion_v1.backfill_shared_links_v2
 SELECT p_run,l.record_key,l.security_symbol,l.link_role,l.observed_versions,l.current_versions,
  CASE WHEN l.current_versions=r.current_candidate_versions THEN 'PRESENT_IN_ALL_CURRENT_PROVIDER_VERSIONS'
   WHEN l.current_versions=0 THEN 'RETAINED_OLDER_PROVIDER_VERSION_LINK' ELSE 'CONFLICTING_PROVIDER_RECORD_LINK_VERSIONS' END,
  COALESCE(m.members,'[]'),CASE WHEN m.n=1 THEN 'UNRESOLVED_FROZEN_ANCHOR_CANDIDATE' WHEN m.n>1 THEN 'AMBIGUOUS_FROZEN_ANCHOR_CANDIDATES' ELSE 'OUTSIDE_FROZEN_ANCHOR_SET' END
 FROM links l JOIN scoped_records r ON r.record_key=l.record_key
 LEFT JOIN LATERAL(SELECT count(*) n,jsonb_agg(member_id ORDER BY member_id) members FROM astra_ingestion_v1.backfill_members_v2 m WHERE m.run_id=p_run AND m.anchor_ticker=l.security_symbol) m ON true;
END $function$
$shared_field_replacement$;
 v_before text;v_before_metadata jsonb;v_after_metadata jsonb;
 v_pin jsonb;v_pin_source text;v_pin_metadata jsonb;
 v_catalog_before jsonb;v_catalog_after jsonb;
BEGIN
 IF current_setting('statement_timeout')<>'8s' OR current_setting('lock_timeout')<>'3s'
  OR current_setting('transaction_read_only')<>'off' OR current_setting('transaction_isolation')<>'read committed' THEN
  RAISE EXCEPTION 'Shared field cache replacement requires reviewed writable RC 8s/3s bounds';
 END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(706314020261028);
 PERFORM 1 FROM astra_ingestion_v1.backfill_runs_v2
 WHERE id='fixed3000-20250901-20260731-v1-20261030' FOR SHARE;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2
 WHERE id='fixed3000-20250901-20260731-v1-20261030' AND status='ACTIVE' AND fence=1
  AND cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
  AND cohort_manifest_sha256='4134b415e2c26fcde9fced749c0d54ef51376e23f0d2f8c6ce9ef562f9fab99f'
  AND metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
  AND (metadata->>'implementation_lease_until')::timestamptz>clock_timestamp())
 OR (SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2
  WHERE run_id='fixed3000-20250901-20260731-v1-20261030')<>3000 THEN
 RAISE EXCEPTION 'Shared field cache owner, lease, status, fence, cohort or members changed';
 END IF;
 SELECT pg_get_functiondef(p.oid),to_jsonb(p)-'prosrc' INTO STRICT v_before,v_before_metadata
 FROM pg_proc p WHERE p.oid='astra_ingestion_v1.backfill_shared_refresh_v2(text,jsonb)'::regprocedure;
 IF encode(sha256(convert_to(v_before,'UTF8')),'hex')<>'b18a30c47e13a9738f111ff739e8cda53120e882eaa7e7e0427144372ab8dbc4'
  OR v_before_metadata IS DISTINCT FROM v_expected_metadata THEN
  RAISE EXCEPTION 'Shared field cache exact source or metadata differs; reconcile before replay';
 END IF;
 FOR v_pin IN SELECT value FROM jsonb_array_elements(v_pins) LOOP
 SELECT pg_get_functiondef(p.oid),CASE WHEN v_pin->>'metadata_kind'='full' THEN to_jsonb(p)-'prosrc'
  ELSE jsonb_build_object('acl',p.proacl,'owner',p.proowner::text,'config',p.proconfig,'security_definer',p.prosecdef) END
 INTO STRICT v_pin_source,v_pin_metadata FROM pg_proc p WHERE p.oid=(v_pin->>'signature')::regprocedure;
 IF encode(sha256(convert_to(v_pin_source,'UTF8')),'hex') IS DISTINCT FROM v_pin->>'sha256'
  OR v_pin_metadata IS DISTINCT FROM v_pin->'metadata' THEN
  RAISE EXCEPTION 'Shared field cache immutable source or metadata pin differs';
 END IF;
 END LOOP;
 IF encode(sha256(convert_to(v_replacement,'UTF8')),'hex')<>'7f538bf47cb5e74050c20266e01cbe9d6521c1a65663aaf2e0fe38d62041f1a4' THEN
  RAISE EXCEPTION 'Shared field cache reviewed replacement bytes differ';
 END IF;
 -- SHARED_FIELD_CACHE_BEFORE_CATALOG_SNAPSHOT
 SELECT jsonb_build_object(
 'namespace',(SELECT to_jsonb(n) FROM pg_namespace n WHERE n.oid='astra_ingestion_v1'::regnamespace),
 'functions',(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.oid) FROM pg_proc p
  WHERE p.pronamespace='astra_ingestion_v1'::regnamespace
   AND p.oid<>'astra_ingestion_v1.backfill_shared_refresh_v2(text,jsonb)'::regprocedure),
 'relations',(SELECT jsonb_agg(jsonb_build_object('oid',c.oid::text,'name',c.relname,
  'namespace',c.relnamespace::text,'kind',c.relkind,'owner',c.relowner::text,'acl',c.relacl,
  'rls',c.relrowsecurity,'force_rls',c.relforcerowsecurity,'method',c.relam::text,'options',c.reloptions)
  ORDER BY c.oid) FROM pg_class c WHERE c.relnamespace='astra_ingestion_v1'::regnamespace),
 'indexes',(SELECT jsonb_agg(jsonb_build_object('catalog',to_jsonb(i),'definition',pg_get_indexdef(i.indexrelid))
  ORDER BY i.indexrelid) FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid
  WHERE c.relnamespace='astra_ingestion_v1'::regnamespace),
 'constraints',(SELECT jsonb_agg(to_jsonb(c) ORDER BY c.oid) FROM pg_constraint c
  WHERE c.connamespace='astra_ingestion_v1'::regnamespace),
 'triggers',(SELECT jsonb_agg(to_jsonb(t) ORDER BY t.oid) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
  WHERE c.relnamespace='astra_ingestion_v1'::regnamespace),
 'policies',(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.oid) FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid
  WHERE c.relnamespace='astra_ingestion_v1'::regnamespace),
 'roles',(SELECT jsonb_agg(to_jsonb(r) ORDER BY r.oid) FROM pg_roles r
  WHERE r.rolname IN ('astra_ingestion_rpc_owner_v1','astra_ingestion_monitor_owner_v1')),
 'role_memberships',(SELECT jsonb_agg(to_jsonb(m) ORDER BY m.roleid,m.member,m.grantor) FROM pg_auth_members m
  WHERE m.roleid IN (SELECT oid FROM pg_roles WHERE rolname IN ('astra_ingestion_rpc_owner_v1','astra_ingestion_monitor_owner_v1'))
   OR m.member IN (SELECT oid FROM pg_roles WHERE rolname IN ('astra_ingestion_rpc_owner_v1','astra_ingestion_monitor_owner_v1')))
) INTO v_catalog_before;
 EXECUTE v_replacement;
 -- SHARED_FIELD_CACHE_AFTER_REPLACEMENT
 SELECT to_jsonb(p)-'prosrc' INTO STRICT v_after_metadata FROM pg_proc p
 WHERE p.oid='astra_ingestion_v1.backfill_shared_refresh_v2(text,jsonb)'::regprocedure;
 SELECT jsonb_build_object(
 'namespace',(SELECT to_jsonb(n) FROM pg_namespace n WHERE n.oid='astra_ingestion_v1'::regnamespace),
 'functions',(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.oid) FROM pg_proc p
  WHERE p.pronamespace='astra_ingestion_v1'::regnamespace
   AND p.oid<>'astra_ingestion_v1.backfill_shared_refresh_v2(text,jsonb)'::regprocedure),
 'relations',(SELECT jsonb_agg(jsonb_build_object('oid',c.oid::text,'name',c.relname,
  'namespace',c.relnamespace::text,'kind',c.relkind,'owner',c.relowner::text,'acl',c.relacl,
  'rls',c.relrowsecurity,'force_rls',c.relforcerowsecurity,'method',c.relam::text,'options',c.reloptions)
  ORDER BY c.oid) FROM pg_class c WHERE c.relnamespace='astra_ingestion_v1'::regnamespace),
 'indexes',(SELECT jsonb_agg(jsonb_build_object('catalog',to_jsonb(i),'definition',pg_get_indexdef(i.indexrelid))
  ORDER BY i.indexrelid) FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid
  WHERE c.relnamespace='astra_ingestion_v1'::regnamespace),
 'constraints',(SELECT jsonb_agg(to_jsonb(c) ORDER BY c.oid) FROM pg_constraint c
  WHERE c.connamespace='astra_ingestion_v1'::regnamespace),
 'triggers',(SELECT jsonb_agg(to_jsonb(t) ORDER BY t.oid) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
  WHERE c.relnamespace='astra_ingestion_v1'::regnamespace),
 'policies',(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.oid) FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid
  WHERE c.relnamespace='astra_ingestion_v1'::regnamespace),
 'roles',(SELECT jsonb_agg(to_jsonb(r) ORDER BY r.oid) FROM pg_roles r
  WHERE r.rolname IN ('astra_ingestion_rpc_owner_v1','astra_ingestion_monitor_owner_v1')),
 'role_memberships',(SELECT jsonb_agg(to_jsonb(m) ORDER BY m.roleid,m.member,m.grantor) FROM pg_auth_members m
  WHERE m.roleid IN (SELECT oid FROM pg_roles WHERE rolname IN ('astra_ingestion_rpc_owner_v1','astra_ingestion_monitor_owner_v1'))
   OR m.member IN (SELECT oid FROM pg_roles WHERE rolname IN ('astra_ingestion_rpc_owner_v1','astra_ingestion_monitor_owner_v1')))
) INTO v_catalog_after;
 IF v_after_metadata IS DISTINCT FROM v_before_metadata OR v_after_metadata IS DISTINCT FROM v_expected_metadata
  OR v_catalog_after IS DISTINCT FROM v_catalog_before
  OR pg_get_functiondef('astra_ingestion_v1.backfill_shared_refresh_v2(text,jsonb)'::regprocedure) IS DISTINCT FROM v_replacement THEN
  RAISE EXCEPTION 'Shared field cache changed unexpected source, metadata, OID, ACL or catalog';
 END IF;
 FOR v_pin IN SELECT value FROM jsonb_array_elements(v_pins) LOOP
 SELECT pg_get_functiondef(p.oid),CASE WHEN v_pin->>'metadata_kind'='full' THEN to_jsonb(p)-'prosrc'
  ELSE jsonb_build_object('acl',p.proacl,'owner',p.proowner::text,'config',p.proconfig,'security_definer',p.prosecdef) END
 INTO STRICT v_pin_source,v_pin_metadata FROM pg_proc p WHERE p.oid=(v_pin->>'signature')::regprocedure;
 IF encode(sha256(convert_to(v_pin_source,'UTF8')),'hex') IS DISTINCT FROM v_pin->>'sha256'
  OR v_pin_metadata IS DISTINCT FROM v_pin->'metadata' THEN
  RAISE EXCEPTION 'Shared field cache immutable source or metadata pin differs';
 END IF;
 END LOOP;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2
 WHERE id='fixed3000-20250901-20260731-v1-20261030' AND status='ACTIVE' AND fence=1
  AND cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
  AND cohort_manifest_sha256='4134b415e2c26fcde9fced749c0d54ef51376e23f0d2f8c6ce9ef562f9fab99f'
  AND metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
  AND (metadata->>'implementation_lease_until')::timestamptz>clock_timestamp())
 OR (SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2
  WHERE run_id='fixed3000-20250901-20260731-v1-20261030')<>3000 THEN
 RAISE EXCEPTION 'Shared field cache owner, lease, status, fence, cohort or members changed';
 END IF;
END $shared_field_cache_forward$;
COMMIT;
