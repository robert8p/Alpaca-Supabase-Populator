-- Canonical minute delivery uses one source per fixed security/session.
-- Original pages and retained market rows remain unchanged; only compact counts
-- are projected. A partial repair cannot displace a qualified retained session.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);

CREATE TABLE astra_ingestion_v1.backfill_minute_sessions_v2 (
 run_id text NOT NULL,task_id text NOT NULL REFERENCES astra_ingestion_v1.backfill_tasks_v2(id),
 member_id text NOT NULL,symbol text NOT NULL,asset_key text NOT NULL,market_date date NOT NULL,
 source_type text NOT NULL CHECK(source_type IN('RETAINED','ACQUIRED')),
 query_complete boolean NOT NULL,
 raw_rth bigint NOT NULL,raw_pre bigint NOT NULL,raw_post bigint NOT NULL,
 qualified_rth bigint NOT NULL,qualified_pre bigint NOT NULL,qualified_post bigint NOT NULL,
 usable_rth bigint NOT NULL,usable_pre bigint NOT NULL,usable_post bigint NOT NULL,
 last_verified_page integer NOT NULL,source_verified_at timestamptz NOT NULL,
 PRIMARY KEY(task_id,market_date)
);
CREATE INDEX backfill_minute_sessions_identity_v2 ON astra_ingestion_v1.backfill_minute_sessions_v2(run_id,member_id,asset_key,market_date);
CREATE TABLE astra_ingestion_v1.backfill_minute_projection_v2 (
 task_id text PRIMARY KEY REFERENCES astra_ingestion_v1.backfill_tasks_v2(id),
 last_verified_page integer NOT NULL,projected_at timestamptz NOT NULL DEFAULT clock_timestamp()
);

CREATE FUNCTION astra_ingestion_v1.backfill_minute_account_v2(p_task_id text) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' SET TimeZone='UTC' SET statement_timeout='8s' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2; parent astra_ingestion_v1.backfill_tasks_v2;
 v astra_ingestion_v1.backfill_readbacks_v2; v_asset text; v_member text; v_symbol text;
 v_complete boolean; v_max integer; v_added integer;
BEGIN
 SELECT * INTO STRICT t FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=p_task_id;
 IF t.family NOT IN('P01','P02') OR t.kind NOT IN('retained_reuse','alpaca_stock_bars')
 OR COALESCE(t.scope->>'timeframe','1Min')<>'1Min' THEN RETURN jsonb_build_object('state','NOT_MINUTE_SOURCE'); END IF;
 IF jsonb_array_length(COALESCE(t.scope->'member_ids','[]'))<>1 THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Minute accounting requires an explicit single fixed member'; END IF;
 v_member:=t.scope#>>'{member_ids,0}';v_symbol:=COALESCE(t.scope->>'symbol',t.scope#>>'{symbols,0}');
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_members_v2 m WHERE m.run_id=t.run_id AND m.member_id=v_member AND m.anchor_ticker=v_symbol) THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Minute source differs from its frozen provider anchor'; END IF;
 IF t.scope ? 'reuse_parent' THEN SELECT * INTO STRICT parent FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=t.scope->>'reuse_parent'; END IF;
 v_asset:=COALESCE(t.scope->>'alpaca_asset_id',parent.scope->>'alpaca_asset_id',
  (SELECT CASE WHEN count(*)=1 THEN min(i.alpaca_asset_id::text) END FROM reference.alpaca_fixed_window_instruments_v1 i WHERE i.symbol=v_symbol),'ANCHOR_SYMBOL:'||v_symbol);
 SELECT max(page_no) INTO v_max FROM astra_ingestion_v1.backfill_readbacks_v2 WHERE task_id=t.id;
 IF v_max IS NULL THEN RETURN jsonb_build_object('state','READBACK_REQUIRED'); END IF;
 IF t.kind='retained_reuse' THEN
  SELECT * INTO STRICT v FROM astra_ingestion_v1.backfill_readbacks_v2 WHERE task_id=t.id AND page_no=0;
  IF v.retained_source_verification->'passed' IS DISTINCT FROM 'true'::jsonb THEN
   RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Retained session counts require successful source verification'; END IF;
  INSERT INTO astra_ingestion_v1.backfill_minute_sessions_v2
   (run_id,task_id,member_id,symbol,asset_key,market_date,source_type,query_complete,
    raw_rth,raw_pre,raw_post,qualified_rth,qualified_pre,qualified_post,usable_rth,usable_pre,usable_post,last_verified_page,source_verified_at)
  SELECT t.run_id,t.id,v_member,v_symbol,v_asset,(e->>'market_date')::date,'RETAINED',false,
   (e->>'rth_count')::bigint,(e->>'pre_count')::bigint,(e->>'post_count')::bigint,
   (e->>'qualified_rth_count')::bigint,(e->>'qualified_pre_count')::bigint,(e->>'qualified_post_count')::bigint,
   (e->>'usable_rth_count')::bigint,(e->>'usable_pre_count')::bigint,(e->>'usable_post_count')::bigint,v_max,v.verified_at
  FROM jsonb_array_elements(v.retained_source_verification->'session_coverage') e
  ON CONFLICT(task_id,market_date) DO NOTHING;
 ELSE
  IF (t.scope->>'end')::timestamptz-(t.scope->>'start')::timestamptz>interval '32 days' THEN
   RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Minute accounting unit must fit32 days'; END IF;
  SELECT t.status IN('INGESTED','NO_DATA_RETURNED','IDENTITY_OR_QUALITY_UNRESOLVED')
   AND EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_pages_v2 p WHERE p.task_id=t.id AND p.cursor_out IS NULL
     AND p.raw_body::jsonb ? 'next_page_token' AND p.raw_body::jsonb->'next_page_token'='null'::jsonb)
   AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_pages_v2 p WHERE p.task_id=t.id
     AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_readbacks_v2 b WHERE b.task_id=p.task_id AND b.page_no=p.page_no)) INTO v_complete;
  WITH bars AS MATERIALIZED (
   SELECT x.symbol,x.market_date,x.session,astra_ingestion_v1.backfill_stamp_v2(x.source_row->>'t') stamp,
    count(DISTINCT x.source_row)=1 AND bool_and(astra_ingestion_v1.backfill_bar_usable_v2(x.source_row)) usable
   FROM astra_ingestion_v1.backfill_pages_v2 p JOIN astra_ingestion_v1.backfill_readbacks_v2 b USING(task_id,page_no)
   CROSS JOIN LATERAL astra_ingestion_v1.backfill_page_rows_v2(p.task_id,p.page_no) x
   WHERE p.task_id=t.id AND x.symbol=v_symbol AND x.session IN('RTH','PRE','POST')
   GROUP BY x.symbol,x.market_date,x.session,astra_ingestion_v1.backfill_stamp_v2(x.source_row->>'t')
  ), days AS (
   SELECT DISTINCT (e->>'date')::date market_date FROM jsonb_array_elements(COALESCE(t.scope->'calendar','[]')) e
   WHERE (e->>'date')::date BETWEEN ((t.scope->>'start')::timestamptz AT TIME ZONE 'America/New_York')::date
    AND ((t.scope->>'end')::timestamptz AT TIME ZONE 'America/New_York')::date
  )
  INSERT INTO astra_ingestion_v1.backfill_minute_sessions_v2
   (run_id,task_id,member_id,symbol,asset_key,market_date,source_type,query_complete,
    raw_rth,raw_pre,raw_post,qualified_rth,qualified_pre,qualified_post,usable_rth,usable_pre,usable_post,last_verified_page,source_verified_at)
  SELECT t.run_id,t.id,v_member,v_symbol,v_asset,d.market_date,'ACQUIRED',v_complete
   AND (t.scope->>'start')::timestamptz<=((d.market_date+time '04:00') AT TIME ZONE 'America/New_York')
   AND (t.scope->>'end')::timestamptz>=((d.market_date+time '19:59') AT TIME ZONE 'America/New_York'),
   count(*) FILTER(WHERE b.session='RTH'),count(*) FILTER(WHERE b.session='PRE'),count(*) FILTER(WHERE b.session='POST'),
   count(*) FILTER(WHERE b.session='RTH'),count(*) FILTER(WHERE b.session='PRE'),count(*) FILTER(WHERE b.session='POST'),
   count(*) FILTER(WHERE b.session='RTH' AND b.usable),count(*) FILTER(WHERE b.session='PRE' AND b.usable),count(*) FILTER(WHERE b.session='POST' AND b.usable),
   v_max,clock_timestamp() FROM days d LEFT JOIN bars b ON b.market_date=d.market_date GROUP BY d.market_date
  ON CONFLICT(task_id,market_date) DO UPDATE SET query_complete=EXCLUDED.query_complete,
   raw_rth=EXCLUDED.raw_rth,raw_pre=EXCLUDED.raw_pre,raw_post=EXCLUDED.raw_post,
   qualified_rth=EXCLUDED.qualified_rth,qualified_pre=EXCLUDED.qualified_pre,qualified_post=EXCLUDED.qualified_post,
   usable_rth=EXCLUDED.usable_rth,usable_pre=EXCLUDED.usable_pre,usable_post=EXCLUDED.usable_post,
   last_verified_page=EXCLUDED.last_verified_page,source_verified_at=EXCLUDED.source_verified_at;
 END IF;
 GET DIAGNOSTICS v_added=ROW_COUNT;
 INSERT INTO astra_ingestion_v1.backfill_minute_projection_v2(task_id,last_verified_page) VALUES(t.id,v_max)
 ON CONFLICT(task_id) DO UPDATE SET last_verified_page=EXCLUDED.last_verified_page,projected_at=clock_timestamp();
 RETURN jsonb_build_object('state','MINUTE_SESSIONS_PROJECTED','task_id',t.id,'sessions',v_added,'last_verified_page',v_max);
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_minute_readback_trigger_v2() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN PERFORM astra_ingestion_v1.backfill_minute_account_v2(NEW.task_id);RETURN NEW; END $$;
CREATE TRIGGER backfill_minute_readback_v2 AFTER INSERT ON astra_ingestion_v1.backfill_readbacks_v2
 FOR EACH ROW EXECUTE FUNCTION astra_ingestion_v1.backfill_minute_readback_trigger_v2();

CREATE FUNCTION astra_ingestion_v1.backfill_minute_account_pending_v2(p_limit integer DEFAULT 2) RETURNS integer
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' SET statement_timeout='8s' AS $$
DECLARE x record; n integer:=0;
BEGIN
 FOR x IN SELECT DISTINCT v.task_id FROM astra_ingestion_v1.backfill_readbacks_v2 v
  JOIN astra_ingestion_v1.backfill_tasks_v2 t ON t.id=v.task_id
  LEFT JOIN astra_ingestion_v1.backfill_minute_projection_v2 s ON s.task_id=v.task_id
  WHERE t.family IN('P01','P02') AND t.kind IN('retained_reuse','alpaca_stock_bars') AND COALESCE(t.scope->>'timeframe','1Min')='1Min'
   AND (s.task_id IS NULL OR s.last_verified_page<v.page_no) LIMIT GREATEST(1,LEAST(p_limit,8))
 LOOP PERFORM astra_ingestion_v1.backfill_minute_account_v2(x.task_id);n:=n+1;END LOOP;
 RETURN n;
END $$;

CREATE VIEW astra_ingestion_v1.backfill_canonical_minute_sessions_v2 WITH(security_invoker=true) AS
 SELECT s.* FROM (
  SELECT a.*,row_number() OVER(PARTITION BY run_id,member_id,asset_key,market_date ORDER BY
   CASE WHEN source_type='ACQUIRED' AND query_complete THEN 0
    WHEN source_type='RETAINED' AND qualified_rth+qualified_pre+qualified_post>0 THEN 1
    WHEN source_type='ACQUIRED' THEN 2 ELSE 3 END,
   qualified_rth+qualified_pre+qualified_post DESC,task_id COLLATE "C") canonical_rank
  FROM astra_ingestion_v1.backfill_minute_sessions_v2 a
 ) s WHERE canonical_rank=1;

CREATE FUNCTION astra_ingestion_v1.backfill_retained_session_rows_v2(p_task_id text,p_day date)
RETURNS TABLE(record_ordinal bigint,symbol text,market_date date,session text,target_window boolean,record_group text,source_row jsonb)
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' SET TimeZone='UTC' SET statement_timeout='8s' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2; proof jsonb;
BEGIN
 SELECT * INTO STRICT t FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=p_task_id;
 IF t.kind<>'retained_reuse' OR NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_minute_sessions_v2 s WHERE s.task_id=t.id AND s.market_date=p_day AND s.source_type='RETAINED') THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Verified retained source session is required'; END IF;
 proof:=astra_ingestion_v1.backfill_reuse_verify_v2(t.id,0);
 IF proof->'passed' IS DISTINCT FROM 'true'::jsonb THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Retained source changed after independent verification'; END IF;
 RETURN QUERY
 SELECT row_number() OVER(ORDER BY b.bar_ts),t.scope->>'symbol',p_day,
  CASE b.session_label::text WHEN 'regular' THEN 'RTH' WHEN 'premarket' THEN 'PRE' WHEN 'postmarket' THEN 'POST' END,
  p_day BETWEEN '2025-09-01'::date AND '2026-07-31'::date,'retained_bars'::text,
  jsonb_build_object('t',b.bar_ts,'o',b.open,'h',b.high,'l',b.low,'c',b.close,'v',b.volume,'n',b.trade_count,'vw',b.vwap,
   'source_loaded_at',b.source_loaded_at,'loaded_by_job_id',b.loaded_by_job_id,'instrument_key',b.instrument_key,'alpaca_asset_id',t.scope->'alpaca_asset_id')
 FROM market_fixed_20250901_20260831.alpaca_sip_bars_1m b
 JOIN market_provenance.alpaca_populator_jobs_v1 j ON j.id=b.loaded_by_job_id
 WHERE b.instrument_key=(t.scope->>'instrument_key')::int
  AND b.bar_ts>=GREATEST((t.scope->>'start')::timestamptz,p_day::timestamp AT TIME ZONE 'America/New_York')
  AND b.bar_ts<LEAST((t.scope->>'end_exclusive')::timestamptz,(p_day+1)::timestamp AT TIME ZONE 'America/New_York')
  AND b.session_label::text IN('regular','premarket','postmarket')
  AND j.config->>'feed'='sip' AND j.config->>'adjustment'='raw' AND j.config->'timeframes' @> '["1Min"]'::jsonb
  AND (j.config->>'start_date')::date<=p_day AND (j.config->>'end_date')::date>=p_day
 ORDER BY b.bar_ts LIMIT 2000;
END $$;

-- A conflicting duplicate remains available in original pages. Canonical
-- analytical values are NULL with an explicit reason instead of choosing one.
CREATE FUNCTION astra_ingestion_v1.backfill_acquired_session_rows_v2(p_task_id text,p_day date)
RETURNS SETOF astra_ingestion_v1.backfill_source_records_v2
LANGUAGE plpgsql STABLE SET search_path='' AS $$
DECLARE g record; r astra_ingestion_v1.backfill_source_records_v2;
BEGIN
 FOR g IN
  SELECT (array_agg(x ORDER BY x.page_no,x.record_ordinal))[1] chosen,
   count(DISTINCT x.source_row) versions,
   jsonb_agg(x.lineage ORDER BY x.page_no,x.record_ordinal) all_lineage
  FROM astra_ingestion_v1.backfill_source_records_v2 x
  JOIN astra_ingestion_v1.backfill_readbacks_v2 v ON v.task_id=x.task_id AND v.page_no=x.page_no
  WHERE x.task_id=p_task_id AND x.market_date=p_day AND x.session IN('RTH','PRE','POST')
  GROUP BY x.symbol,astra_ingestion_v1.backfill_stamp_v2(x.source_row->>'t')
 LOOP
  r:=g.chosen;
  r.lineage:=r.lineage||jsonb_build_object('all_source_receipts',g.all_lineage,'source_value_versions',g.versions);
  IF g.versions>1 THEN
   r.source_row:=jsonb_build_object('t',r.source_row->'t','o',NULL,'h',NULL,'l',NULL,'c',NULL,'v',NULL,'n',NULL,'vw',NULL,
    'null_reason','CONFLICTING_PROVIDER_DUPLICATE');
   r.record_group:='UNRESOLVED_PROVIDER_DUPLICATE';
   r.quality:=r.quality||jsonb_build_array(jsonb_build_object('state','IDENTITY_OR_QUALITY_UNRESOLVED','reason','CONFLICTING_PROVIDER_DUPLICATE','versions',g.versions));
  END IF;
  RETURN NEXT r;
 END LOOP;
END $$;

CREATE VIEW astra_ingestion_v1.backfill_canonical_minute_records_v2 WITH(security_invoker=true) AS
 SELECT p.run_id,'P01'::text family,t.kind,'Alpaca'::text provider,t.id task_id,p.page_no,x.record_ordinal,
  t.scope->'member_ids' member_ids,x.symbol,x.market_date,x.session,x.target_window,
  'IDENTITY_OR_QUALITY_UNRESOLVED'::text identity_status,'raw'::text price_basis,x.record_group,x.source_row,
  p.body_sha256,p.fetched_at,p.committed_at,p.quality,
  jsonb_build_object('task_id',p.task_id,'page_no',p.page_no,'body_sha256',p.body_sha256,'source_relation','market_fixed_20250901_20260831.alpaca_sip_bars_1m',
   'source_digest',p.raw_body::jsonb#>>'{rows,0,source_digest}','instrument_key',t.scope->'instrument_key','bar_ts',x.source_row->'t',
   'original_source_unchanged',true,'query_complete',false) lineage
 FROM astra_ingestion_v1.backfill_canonical_minute_sessions_v2 s
 JOIN astra_ingestion_v1.backfill_tasks_v2 t ON t.id=s.task_id
 JOIN astra_ingestion_v1.backfill_pages_v2 p ON p.task_id=t.id AND p.page_no=0
 CROSS JOIN LATERAL astra_ingestion_v1.backfill_retained_session_rows_v2(t.id,s.market_date) x
 WHERE s.source_type='RETAINED'
 UNION ALL
 SELECT
  x.run_id,'P01'::text,x.kind,x.provider,x.task_id,x.page_no,x.record_ordinal,x.member_ids,x.symbol,x.market_date,x.session,x.target_window,
  x.identity_status,x.price_basis,x.record_group,x.source_row,x.body_sha256,x.fetched_at,x.committed_at,x.quality,
  x.lineage||jsonb_build_object('query_complete',s.query_complete,'canonical_source_policy','COMPLETED_FRESH_THEN_QUALIFIED_RETAINED_THEN_PARTIAL_FRESH')
 FROM astra_ingestion_v1.backfill_canonical_minute_sessions_v2 s
 CROSS JOIN LATERAL astra_ingestion_v1.backfill_acquired_session_rows_v2(s.task_id,s.market_date) x
 WHERE s.source_type='ACQUIRED' AND x.session IN('RTH','PRE','POST');

CREATE OR REPLACE VIEW astra_ingestion_v1.backfill_family_p01_v2 WITH(security_invoker=true) AS
 SELECT * FROM astra_ingestion_v1.backfill_canonical_minute_records_v2 WHERE session='RTH' AND target_window;
CREATE OR REPLACE VIEW astra_ingestion_v1.backfill_family_p02_v2 WITH(security_invoker=true) AS
 SELECT run_id,'P02'::text family,kind,provider,task_id,page_no,record_ordinal,member_ids,symbol,market_date,session,target_window,
  identity_status,price_basis,record_group,source_row,body_sha256,fetched_at,committed_at,quality,lineage
 FROM astra_ingestion_v1.backfill_canonical_minute_records_v2 WHERE session IN('PRE','POST') AND target_window;

CREATE VIEW astra_ingestion_v1.backfill_minute_family_counts_v2 WITH(security_invoker=true) AS
 SELECT s.run_id,f.family,
  COALESCE(sum(f.qualified) FILTER(WHERE s.market_date BETWEEN '2025-09-01'::date AND '2026-07-31'::date),0) committed_records,
  COALESCE(sum(f.qualified) FILTER(WHERE s.market_date<'2025-09-01'::date),0) support_records,
  COALESCE(sum(f.raw) FILTER(WHERE s.source_type='RETAINED' AND s.market_date BETWEEN '2025-09-01'::date AND '2026-07-31'::date),0) referenced_existing_records,
  COALESCE(sum(f.qualified) FILTER(WHERE s.source_type='RETAINED' AND s.market_date BETWEEN '2025-09-01'::date AND '2026-07-31'::date),0) referenced_qualifying_records,
  COALESCE(sum(f.usable) FILTER(WHERE s.source_type='RETAINED' AND s.market_date BETWEEN '2025-09-01'::date AND '2026-07-31'::date),0) referenced_usable_records,
  COALESCE(sum(f.usable) FILTER(WHERE s.market_date BETWEEN '2025-09-01'::date AND '2026-07-31'::date),0) usable_minute_records
 FROM astra_ingestion_v1.backfill_canonical_minute_sessions_v2 s
 CROSS JOIN LATERAL (VALUES('P01',s.raw_rth,s.qualified_rth,s.usable_rth),('P02',s.raw_pre+s.raw_post,s.qualified_pre+s.qualified_post,s.usable_pre+s.usable_post)) f(family,raw,qualified,usable)
 GROUP BY s.run_id,f.family;

ALTER VIEW astra_ingestion_v1.backfill_family_status_v2 RENAME TO backfill_family_receipt_status_v2;
DO $wrapper$
DECLARE columns text;
BEGIN
 SELECT string_agg(CASE
  WHEN a.attname IN('committed_records','support_records','referenced_existing_records','referenced_qualifying_records','referenced_usable_records','usable_minute_records')
   THEN format('CASE WHEN old.family IN(''P01'',''P02'') THEN COALESCE(m.%I,0)::%s ELSE old.%I END AS %I',a.attname,format_type(a.atttypid,a.atttypmod),a.attname,a.attname)
  WHEN a.attname='dated_target_records' THEN format('CASE WHEN old.family IN(''P01'',''P02'') THEN COALESCE(m.committed_records,0)::%s ELSE old.dated_target_records END AS dated_target_records',format_type(a.atttypid,a.atttypmod))
  ELSE format('old.%I',a.attname) END,',' ORDER BY a.attnum) INTO columns
 FROM pg_attribute a WHERE a.attrelid='astra_ingestion_v1.backfill_family_receipt_status_v2'::regclass AND a.attnum>0 AND NOT a.attisdropped;
 EXECUTE 'CREATE VIEW astra_ingestion_v1.backfill_family_status_v2 WITH(security_invoker=true) AS SELECT '||columns||
  ' FROM astra_ingestion_v1.backfill_family_receipt_status_v2 old LEFT JOIN astra_ingestion_v1.backfill_minute_family_counts_v2 m ON m.run_id=old.run_id AND m.family=old.family';
END $wrapper$;

DO $acl$
DECLARE o record; g record; f record;
BEGIN
 FOR o IN SELECT c.oid,c.relname,c.relowner,c.relacl,c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname='astra_ingestion_v1' AND c.relname IN('backfill_minute_sessions_v2','backfill_minute_projection_v2','backfill_canonical_minute_sessions_v2','backfill_canonical_minute_records_v2','backfill_minute_family_counts_v2','backfill_family_status_v2') LOOP
  EXECUTE format('REVOKE ALL ON TABLE astra_ingestion_v1.%I FROM PUBLIC',o.relname);
  FOR g IN SELECT DISTINCT r.rolname FROM aclexplode(o.relacl) a JOIN pg_roles r ON r.oid=a.grantee WHERE a.grantee<>o.relowner LOOP
   EXECUTE format('REVOKE ALL ON TABLE astra_ingestion_v1.%I FROM %I',o.relname,g.rolname);END LOOP;
  IF o.relkind='r' THEN EXECUTE format('ALTER TABLE astra_ingestion_v1.%I ENABLE ROW LEVEL SECURITY',o.relname);
   EXECUTE format('CREATE POLICY backfill_minute_read_v2 ON astra_ingestion_v1.%I FOR SELECT TO astra_ingestion_rpc_owner_v1 USING(true)',o.relname);END IF;
  EXECUTE format('GRANT SELECT ON TABLE astra_ingestion_v1.%I TO astra_ingestion_rpc_owner_v1',o.relname);
 END LOOP;
 FOR f IN SELECT p.oid,p.proname,p.proowner,p.proacl,pg_get_function_identity_arguments(p.oid) args FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname='astra_ingestion_v1' AND p.proname IN('backfill_minute_account_v2','backfill_minute_readback_trigger_v2','backfill_minute_account_pending_v2','backfill_retained_session_rows_v2','backfill_acquired_session_rows_v2') LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION astra_ingestion_v1.%I(%s) FROM PUBLIC',f.proname,f.args);
  FOR g IN SELECT DISTINCT r.rolname FROM aclexplode(f.proacl) a JOIN pg_roles r ON r.oid=a.grantee WHERE a.grantee<>f.proowner LOOP
   EXECUTE format('REVOKE ALL ON FUNCTION astra_ingestion_v1.%I(%s) FROM %I',f.proname,f.args,g.rolname);END LOOP;
  EXECUTE format('GRANT EXECUTE ON FUNCTION astra_ingestion_v1.%I(%s) TO astra_ingestion_rpc_owner_v1',f.proname,f.args);
 END LOOP;
END $acl$;
DO $monitor$
DECLARE d text;
BEGIN
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure) INTO STRICT d;
 IF strpos(d,'backfill_minute_account_pending_v2')>0 THEN RAISE EXCEPTION 'Minute accounting extension already installed';END IF;
 d:=replace(d,' FOR p IN SELECT pg.task_id',E' PERFORM astra_ingestion_v1.backfill_minute_account_pending_v2(2);\n FOR p IN SELECT pg.task_id');
 EXECUTE d;
END $monitor$;
COMMIT;
