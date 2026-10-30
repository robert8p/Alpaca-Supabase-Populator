-- Atomically retain qualified source pointers and admit only scoped missing-data acquisition.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);

CREATE FUNCTION astra_ingestion_v1.backfill_reuse_commit_v2(p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2; existing astra_ingestion_v1.backfill_pages_v2;
 s jsonb; pointer jsonb; quality jsonb; raw text; committed jsonb;
 child_scope jsonb; child_id text; children jsonb:='[]'; day text;
 query_start timestamptz; query_end timestamptz; gaps jsonb; parent_calendar jsonb;
BEGIN
 -- A lost acknowledgement is reconciled by reading the immutable receipt.
 SELECT * INTO existing FROM astra_ingestion_v1.backfill_pages_v2
  WHERE task_id=p_payload#>>'{claim,id}' AND page_no=(p_payload#>>'{claim,page_no}')::int;
 IF FOUND THEN
  IF existing.run_id IS DISTINCT FROM p_payload#>>'{claim,run_id}'
   OR existing.generation::text IS DISTINCT FROM p_payload#>>'{claim,generation}'
   OR existing.run_fence::text IS DISTINCT FROM p_payload#>>'{claim,run_fence}' THEN
    RAISE EXCEPTION USING ERRCODE='AI001',MESSAGE='Reuse acknowledgement belongs to another claim'; END IF;
  RETURN jsonb_build_object('state','already_committed','task_id',existing.task_id,'page_no',existing.page_no,
   'body_sha256',existing.body_sha256,'record_count',existing.record_count,
   'reused_records',existing.raw_body::jsonb->'reused_records');
 END IF;
 t:=astra_ingestion_v1.backfill_owned_v2(p_payload->'claim');
 IF t.kind<>'retained_reuse' OR lower(t.provider)<>'reuse' THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='A retained-source task is required'; END IF;
 s:=astra_ingestion_v1.backfill_reuse_read_v2(jsonb_build_object('claim',p_payload->'claim','mode','summary'));
 IF s->>'calendar_available' IS DISTINCT FROM 'true' THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Actual exchange calendar is required before planning retained-source gaps'; END IF;
 pointer:=(s-'rows'-'mode'-'state'-'next_after'-'has_more')||jsonb_build_object(
  'record_type','RETAINED_SOURCE_POINTER','reused_records',(s->>'record_count')::int,
  'source_original_unchanged',true,'new_market_rows_written',0);
 quality:=jsonb_build_array(jsonb_build_object('state','IDENTITY_OR_QUALITY_UNRESOLVED',
  'reason',s->>'mapping_reason','scope','company_attribution','source_preserved',true),
  jsonb_build_object('state','IDENTITY_OR_QUALITY_UNRESOLVED','reason','UNKNOWN_PROVIDER_OBSERVATION_DENOMINATOR',
  'scope','observation_coverage','expected_bar_slots_are_not_a_trade_denominator',true));
 IF (s->>'record_count')::int<>(s->>'qualifying_profile_count')::int THEN
  quality:=quality||jsonb_build_array(jsonb_build_object('state','IDENTITY_OR_QUALITY_UNRESOLVED',
    'reason','RETAINED_ROWS_WITH_UNQUALIFIED_PROVIDER_PROFILE','affected_records',
     (s->>'record_count')::int-(s->>'qualifying_profile_count')::int));
 END IF;
 IF (s->>'record_count')::int<>(s->>'valid_ohlcv_count')::int THEN
  quality:=quality||jsonb_build_array(jsonb_build_object('state','IDENTITY_OR_QUALITY_UNRESOLVED',
    'reason','RETAINED_INVALID_OHLCV_REQUIRES_PROVIDER_REPAIR','affected_records',
     (s->>'record_count')::int-(s->>'valid_ohlcv_count')::int));
 END IF;
 raw:=astra_ingestion_v1.rpc_canonical(jsonb_build_object('rows',jsonb_build_array(pointer),
  'reused_records',(s->>'record_count')::int,'receipt_kind','RETAINED_SOURCE_POINTER'));
 committed:=astra_ingestion_v1.backfill_dispatch_v2('backfill_commit',jsonb_build_object(
  'claim',p_payload->'claim','raw_body',raw,'body_sha256',encode(sha256(convert_to(raw,'UTF8')),'hex'),
  'http_status',200,'request_id',NULL,'fetched_at',s->'observed_at',
  'request',jsonb_build_object('provider','REUSE','method','FIXED_RETAINED_READ',
    'source_relation',s->'source_relation','instrument_key',s->'instrument_key',
    'start',s->'start','end_exclusive',s->'end_exclusive'),
  'records',jsonb_build_array(pointer),'next_cursor',NULL,
  'terminal_state','IDENTITY_OR_QUALITY_UNRESOLVED','quality',quality,'headers','{}'::jsonb,
  'adapter_version','fixed3000-retained-pointer-v2.1'));

 -- Existing observations are never relabelled provider-empty. Missing retained
 -- ranges become real Alpaca work in the same transaction as the pointer.
 IF (s->>'record_count')::int=0 THEN gaps:='["WHOLE_SCOPE"]'::jsonb;
 ELSE
  SELECT COALESCE(jsonb_agg(d ORDER BY d),'[]') INTO gaps FROM (
   SELECT DISTINCT value d FROM jsonb_array_elements_text(
    COALESCE(s->'days_without_retained_rows','[]')||COALESCE(s->'days_with_unqualified_profile','[]')||
    COALESCE(s->'days_with_invalid_ohlcv','[]')) a(value)
  ) z;
 END IF;
 FOR day IN SELECT jsonb_array_elements_text(gaps) LOOP
  IF day='WHOLE_SCOPE' THEN
   query_start:=(t.scope->>'start')::timestamptz;
   query_end:=(t.scope->>'end_exclusive')::timestamptz-interval '1 microsecond';
   parent_calendar:=t.scope->'calendar';
  ELSE
   query_start:=(day::date+time '04:00') AT TIME ZONE 'America/New_York';
   query_end:=((day::date+time '20:00') AT TIME ZONE 'America/New_York')-interval '1 microsecond';
   SELECT COALESCE(jsonb_agg(x),'[]') INTO parent_calendar FROM jsonb_array_elements(t.scope->'calendar') x WHERE x->>'date'=day;
  END IF;
  child_scope:=jsonb_build_object('symbols',jsonb_build_array(t.scope->>'symbol'),
    'member_ids',t.scope->'member_ids','start',to_char(query_start AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
    'end',to_char(query_end AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
    'timeframe','1Min','feed','sip','adjustment','raw',
    'asof',COALESCE(t.scope->>'asof','2026-08-03'),'calendar',parent_calendar,
    'target_start',t.scope->'target_start','target_end',t.scope->'target_end',
    'market_timezone','America/New_York','identity_status','UNRESOLVED_PROVIDER_ANCHOR',
    'reuse_parent',t.id,'gap_reason',CASE WHEN day='WHOLE_SCOPE' THEN 'NO_RETAINED_ROWS' ELSE 'RETAINED_SESSION_MISSING_OR_UNQUALIFIED' END);
  child_id:='backfill-gap-'||encode(sha256(convert_to(t.run_id||':'||astra_ingestion_v1.rpc_canonical(child_scope),'UTF8')),'hex');
  INSERT INTO astra_ingestion_v1.backfill_tasks_v2(id,run_id,family,provider,kind,scope,priority,run_fence)
   VALUES(child_id,t.run_id,'P01','Alpaca','alpaca_stock_bars',child_scope,t.priority+1,t.run_fence)
   ON CONFLICT(id) DO NOTHING;
  children:=children||jsonb_build_array(child_id);
 END LOOP;
 RETURN committed||jsonb_build_object('reused_records',(s->>'record_count')::int,
  'qualifying_reused_records',(s->>'qualifying_profile_count')::int,'provider_children',children,
  'new_market_rows_written',0);
END $$;

REVOKE ALL ON FUNCTION astra_ingestion_v1.backfill_reuse_commit_v2(jsonb) FROM PUBLIC;
DO $acl$
DECLARE g record;
BEGIN
 FOR g IN SELECT DISTINCT r.rolname FROM pg_proc p CROSS JOIN LATERAL aclexplode(p.proacl) a JOIN pg_roles r ON r.oid=a.grantee
  WHERE p.oid='astra_ingestion_v1.backfill_reuse_commit_v2(jsonb)'::regprocedure AND a.grantee<>p.proowner LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION astra_ingestion_v1.backfill_reuse_commit_v2(jsonb) FROM %I',g.rolname);
 END LOOP;
END $acl$;
GRANT EXECUTE ON FUNCTION astra_ingestion_v1.backfill_reuse_commit_v2(jsonb) TO astra_ingestion_rpc_owner_v1;

DO $wire$
DECLARE d text; b text; old_filter text; new_filter text;
BEGIN
 SELECT pg_get_functiondef('astra_ingestion_v1.rpc_dispatch(text,jsonb)'::regprocedure) INTO STRICT d;
 IF strpos(d,'''backfill_reuse_read''')=0 OR strpos(d,'''backfill_reuse_commit''')>0 THEN
  RAISE EXCEPTION 'Retained commit wiring baseline differs; reconcile before applying'; END IF;
 d:=replace(d,'''backfill_reuse_read''','''backfill_reuse_read'',''backfill_reuse_commit''');
 EXECUTE d;
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure) INTO STRICT b;
 b:=replace(b,' IF p_operation=''backfill_reuse_read'' THEN',
  ' IF p_operation=''backfill_reuse_commit'' THEN RETURN astra_ingestion_v1.backfill_reuse_commit_v2(p_payload); END IF;'||chr(10)||
  ' IF p_operation=''backfill_reuse_read'' THEN');
 -- A calculation waits for generated gap-acquisition children as well as the
 -- immutable retained parent named in its original dependency list.
 old_filter:='    AND (SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2 m WHERE m.run_id=q.run_id)=3000';
 new_filter:='    AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 gap WHERE gap.run_id=q.run_id AND gap.scope ? ''reuse_parent'' AND gap.scope->>''reuse_parent''=ANY(q.dependencies) AND gap.status NOT IN (''INGESTED'',''NO_DATA_RETURNED'',''NOT_APPLICABLE'',''PROVIDER_LIMITATION'',''IDENTITY_OR_QUALITY_UNRESOLVED''))'||chr(10)||old_filter;
 IF strpos(b,old_filter)=0 THEN RAISE EXCEPTION 'Retained dependency claim baseline differs'; END IF;
 b:=replace(b,old_filter,new_filter);
 b:=replace(b,'pg.task_id=ANY(t.dependencies) AND pg.run_id=t.run_id',
  '(pg.task_id=ANY(t.dependencies) OR pg.task_id IN (SELECT gap.id FROM astra_ingestion_v1.backfill_tasks_v2 gap WHERE gap.run_id=t.run_id AND gap.scope ? ''reuse_parent'' AND gap.scope->>''reuse_parent''=ANY(t.dependencies))) AND pg.run_id=t.run_id');
 EXECUTE b;
END $wire$;
CREATE INDEX backfill_reuse_children_v2 ON astra_ingestion_v1.backfill_tasks_v2(run_id,(scope->>'reuse_parent')) WHERE scope ? 'reuse_parent';
COMMIT;
