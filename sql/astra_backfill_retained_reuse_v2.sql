-- Bounded pointers/readback over the already retained Alpaca raw SIP estate.
-- No source rows are copied or modified. Apply after the replacement runtime.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);

DO $admission$
BEGIN
 IF pg_catalog.to_regprocedure('astra_ingestion_v1.backfill_reuse_read_v2(jsonb)') IS NOT NULL
 OR pg_catalog.to_regclass('astra_ingestion_v1.backfill_tasks_v2') IS NULL
 OR pg_catalog.to_regclass('market_fixed_20250901_20260831.alpaca_sip_bars_1m') IS NULL
 OR pg_catalog.to_regclass('reference.alpaca_fixed_window_instruments_v1') IS NULL
 OR pg_catalog.to_regclass('market_provenance.alpaca_populator_jobs_v1') IS NULL THEN
   RAISE EXCEPTION 'Retained reuse baseline absent or already installed; reconcile before applying';
 END IF;
END $admission$;

CREATE FUNCTION astra_ingestion_v1.backfill_reuse_read_v2(p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path='' SET TimeZone='UTC' SET statement_timeout='8s' SET lock_timeout='1s' AS $fn$
DECLARE
 t astra_ingestion_v1.backfill_tasks_v2%ROWTYPE;
 active_task astra_ingestion_v1.backfill_tasks_v2%ROWTYPE;
 source_task astra_ingestion_v1.backfill_tasks_v2%ROWTYPE;
 r astra_ingestion_v1.backfill_runs_v2%ROWTYPE;
 m astra_ingestion_v1.backfill_members_v2%ROWTYPE;
 i reference.alpaca_fixed_window_instruments_v1%ROWTYPE;
 c jsonb:=p_payload->'claim';
 v_start timestamptz;
 v_end timestamptz;
 v_after timestamptz;
 v_mode text:=COALESCE(p_payload->>'mode','summary');
 v_limit int:=GREATEST(1,LEAST(COALESCE((p_payload->>'limit')::int,2000),2000));
 v_result jsonb;
 v_count int;
BEGIN
 -- Existing worker RPC authenticates before dispatch. Readback additionally
 -- binds the live claim, generation, fence, immutable scope and frozen member.
 -- This helper cannot write; a later commit must recheck the current fence.
 IF pg_catalog.jsonb_typeof(c) IS DISTINCT FROM 'object' OR v_mode NOT IN ('summary','material') THEN
   RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Invalid retained-read request';
 END IF;
 SELECT * INTO t FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=c->>'id';
 IF NOT FOUND OR t.run_id IS DISTINCT FROM c->>'run_id' OR t.status<>'RUNNING'
 OR t.owner IS DISTINCT FROM c->>'owner' OR t.generation::text IS DISTINCT FROM c->>'generation'
 OR t.run_fence::text IS DISTINCT FROM c->>'run_fence' OR t.page_no::text IS DISTINCT FROM c->>'page_no'
 OR t.lease_until IS NULL OR t.attempt_deadline IS NULL
 OR t.lease_until<=pg_catalog.clock_timestamp() OR t.attempt_deadline<=pg_catalog.clock_timestamp() THEN
   RAISE EXCEPTION USING ERRCODE='AI001',MESSAGE='Retained-read claim, family or lease is not current';
 END IF;
 active_task:=t;
 IF t.kind IN ('derive_daily','derive_intraday') AND lower(t.provider)='derived'
 AND t.family IN ('D01','D02','D03','D04','D05') AND v_mode='material' THEN
   IF p_payload->>'source_task_id' IS NULL OR NOT (p_payload->>'source_task_id'=ANY(t.dependencies)) THEN
     RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Retained material must be a direct immutable dependency'; END IF;
   SELECT * INTO source_task FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=p_payload->>'source_task_id';
   IF NOT FOUND OR source_task.run_id<>t.run_id OR source_task.kind<>'retained_reuse'
   OR lower(source_task.provider)<>'reuse'
   OR source_task.status NOT IN ('INGESTED','IDENTITY_OR_QUALITY_UNRESOLVED')
   OR source_task.scope->'member_ids' IS DISTINCT FROM t.scope->'member_ids' THEN
     RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Retained dependency is not committed for the same frozen member'; END IF;
   t:=source_task;
 ELSIF t.kind<>'retained_reuse' OR lower(t.provider)<>'reuse'
 OR t.family NOT IN ('P01','P02','D01','D02') THEN
   RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Task kind cannot access retained source material';
 END IF;
 SELECT * INTO STRICT r FROM astra_ingestion_v1.backfill_runs_v2 WHERE id=t.run_id;
 IF r.status<>'ACTIVE' OR r.fence<>active_task.run_fence
 OR r.cohort_sha256<>'2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
 OR r.target_start<>'2025-09-01'::date OR r.target_end<>'2026-07-31'::date
 OR jsonb_typeof(t.scope->'member_ids') IS DISTINCT FROM 'array'
 OR jsonb_array_length(t.scope->'member_ids')<>1 THEN
   RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Retained-read frozen replacement scope differs';
 END IF;
 SELECT * INTO STRICT m FROM astra_ingestion_v1.backfill_members_v2
  WHERE run_id=t.run_id AND member_id=t.scope#>>'{member_ids,0}';
 SELECT * INTO STRICT i FROM reference.alpaca_fixed_window_instruments_v1
  WHERE instrument_key=(t.scope->>'instrument_key')::int;
 IF i.alpaca_asset_id::text IS DISTINCT FROM t.scope->>'alpaca_asset_id'
 OR i.symbol IS DISTINCT FROM t.scope->>'symbol' OR i.symbol IS DISTINCT FROM m.anchor_ticker THEN
   RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Retained provider security and frozen anchor differ';
 END IF;
 -- Anchor equality permits raw-source reuse only. It does not prove a dated
 -- historical company/security mapping; this limitation is always returned.
 v_start:=(t.scope->>'start')::timestamptz;
 v_end:=(t.scope->>'end_exclusive')::timestamptz;
 IF v_start IS NULL OR v_end IS NULL OR NOT pg_catalog.isfinite(v_start) OR NOT pg_catalog.isfinite(v_end)
 OR v_start>=v_end OR v_end-v_start>interval '32 days'
 OR v_start<('2025-08-04 00:00:00'::timestamp AT TIME ZONE 'America/New_York')
 OR v_end>('2026-08-01 00:00:00'::timestamp AT TIME ZONE 'America/New_York')
 OR date_trunc('month',v_start AT TIME ZONE 'America/New_York')<>
    date_trunc('month',(v_end-interval '1 microsecond') AT TIME ZONE 'America/New_York') THEN
   RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Retained-read range must fit one admitted calendar month';
 END IF;
 IF p_payload->>'after' IS NOT NULL THEN
   v_after:=(p_payload->>'after')::timestamptz;
   IF NOT pg_catalog.isfinite(v_after) OR v_after<v_start OR v_after>=v_end THEN
    RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Retained-read cursor is outside the immutable range'; END IF;
 END IF;
 -- A derivation can read only the intersection of its own input window and
 -- its committed retained dependency. The caller cannot widen either scope.
 IF active_task.kind IN ('derive_daily','derive_intraday') THEN
   IF active_task.scope->>'input_start' IS NOT NULL THEN
     v_start:=GREATEST(v_start,(active_task.scope->>'input_start')::date::timestamp AT TIME ZONE 'America/New_York');
   END IF;
   IF active_task.scope->>'target_end' IS NOT NULL THEN
     v_end:=LEAST(v_end,((active_task.scope->>'target_end')::date+1)::timestamp AT TIME ZONE 'America/New_York');
   END IF;
   IF v_after IS NOT NULL AND (v_after<v_start OR v_after>=v_end) THEN
     RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Retained material cursor is outside derived input scope'; END IF;
 END IF;
 IF v_mode='summary' AND v_after IS NOT NULL THEN
   RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='A retained summary must cover its whole immutable range';
 END IF;

 WITH bounded AS MATERIALIZED (
  SELECT b.instrument_key,b.bar_ts,b.session_label::text AS session_label,
    b.open,b.high,b.low,b.close,b.volume,b.trade_count,b.vwap,b.loaded_by_job_id,b.source_loaded_at
  FROM market_fixed_20250901_20260831.alpaca_sip_bars_1m b
  WHERE b.instrument_key=i.instrument_key AND b.bar_ts>=v_start AND b.bar_ts<v_end
    AND (v_after IS NULL OR b.bar_ts>v_after)
  ORDER BY b.bar_ts LIMIT CASE WHEN v_mode='summary' THEN 40001 ELSE v_limit+1 END
 ), measured AS MATERIALIZED (
  SELECT b.*,j.id AS provenance_job_id,
   COALESCE(j.config->>'feed'='sip' AND j.config->>'adjustment'='raw'
    AND j.config->'timeframes' @> '["1Min"]'::jsonb
    AND (j.config->>'start_date')::date<=(b.bar_ts AT TIME ZONE 'America/New_York')::date
    AND (j.config->>'end_date')::date>=(b.bar_ts AT TIME ZONE 'America/New_York')::date,false) AS qualifying_profile,
   COALESCE(b.open>0 AND b.high>0 AND b.low>0 AND b.close>0 AND b.volume>=0
    AND b.high>=GREATEST(b.open,b.close,b.low) AND b.low<=LEAST(b.open,b.close,b.high)
    AND b.open NOT IN ('Infinity'::float8,'-Infinity'::float8,'NaN'::float8)
    AND b.high NOT IN ('Infinity'::float8,'-Infinity'::float8,'NaN'::float8)
    AND b.low NOT IN ('Infinity'::float8,'-Infinity'::float8,'NaN'::float8)
    AND b.close NOT IN ('Infinity'::float8,'-Infinity'::float8,'NaN'::float8),false) AS valid_ohlcv,
   encode(sha256(convert_to(to_jsonb(b)::text,'UTF8')),'hex') AS row_sha256
  FROM bounded b LEFT JOIN market_provenance.alpaca_populator_jobs_v1 j ON j.id=b.loaded_by_job_id
 ), selected AS MATERIALIZED (
  SELECT * FROM measured ORDER BY bar_ts LIMIT CASE WHEN v_mode='summary' THEN 40001 ELSE v_limit END
 )
 SELECT jsonb_build_object(
   'record_count',count(*),'qualifying_profile_count',count(*) FILTER(WHERE qualifying_profile),
   'valid_ohlcv_count',count(*) FILTER(WHERE valid_ohlcv),
   'usable_source_count',count(*) FILTER(WHERE qualifying_profile AND valid_ohlcv),
   'first_bar',min(bar_ts),'last_bar',max(bar_ts),
   'source_digest',encode(sha256(convert_to(COALESCE(string_agg(row_sha256,'' ORDER BY bar_ts),''),'UTF8')),'hex'),
   'digest_algorithm','sha256-concatenated-ordered-postgres-jsonb-row-sha256-v1',
   'rth_count',count(*) FILTER(WHERE session_label='regular'),
   'pre_count',count(*) FILTER(WHERE session_label='premarket'),
   'post_count',count(*) FILTER(WHERE session_label='postmarket'),
   'qualified_rth_count',count(*) FILTER(WHERE qualifying_profile AND session_label='regular'),
   'qualified_pre_count',count(*) FILTER(WHERE qualifying_profile AND session_label='premarket'),
   'qualified_post_count',count(*) FILTER(WHERE qualifying_profile AND session_label='postmarket'),
   'usable_rth_count',count(*) FILTER(WHERE qualifying_profile AND valid_ohlcv AND session_label='regular'),
   'usable_pre_count',count(*) FILTER(WHERE qualifying_profile AND valid_ohlcv AND session_label='premarket'),
   'usable_post_count',count(*) FILTER(WHERE qualifying_profile AND valid_ohlcv AND session_label='postmarket'),
   'overnight_count',count(*) FILTER(WHERE session_label='overnight'),
   'unknown_session_count',count(*) FILTER(WHERE session_label NOT IN ('regular','premarket','postmarket','overnight') OR session_label IS NULL),
   'source_job_ids',COALESCE(jsonb_agg(DISTINCT loaded_by_job_id) FILTER(WHERE loaded_by_job_id IS NOT NULL),'[]'),
   'source_loaded_at_min',min(source_loaded_at),'source_loaded_at_max',max(source_loaded_at),
   'session_coverage',CASE WHEN v_mode='summary' THEN (
     SELECT COALESCE(jsonb_agg(z ORDER BY z.market_date),'[]') FROM (
       SELECT (bar_ts AT TIME ZONE 'America/New_York')::date AS market_date,
        count(*) AS record_count,count(*) FILTER(WHERE qualifying_profile) AS qualifying_profile_count,
        count(*) FILTER(WHERE qualifying_profile AND valid_ohlcv) AS usable_source_count,
        count(*) FILTER(WHERE session_label='regular') AS rth_count,
        count(*) FILTER(WHERE session_label='premarket') AS pre_count,
        count(*) FILTER(WHERE session_label='postmarket') AS post_count,
        count(*) FILTER(WHERE qualifying_profile AND session_label='regular') AS qualified_rth_count,
        count(*) FILTER(WHERE qualifying_profile AND session_label='premarket') AS qualified_pre_count,
        count(*) FILTER(WHERE qualifying_profile AND session_label='postmarket') AS qualified_post_count,
        count(*) FILTER(WHERE qualifying_profile AND valid_ohlcv AND session_label='regular') AS usable_rth_count,
        count(*) FILTER(WHERE qualifying_profile AND valid_ohlcv AND session_label='premarket') AS usable_pre_count,
        count(*) FILTER(WHERE qualifying_profile AND valid_ohlcv AND session_label='postmarket') AS usable_post_count,
        min(bar_ts) AS first_bar,max(bar_ts) AS last_bar
       FROM selected GROUP BY 1) z) ELSE '[]'::jsonb END,
   'days_without_retained_rows',CASE WHEN v_mode='summary' THEN (
     SELECT COALESCE(jsonb_agg(e->>'date' ORDER BY e->>'date'),'[]')
     FROM jsonb_array_elements(COALESCE(t.scope->'calendar','[]'::jsonb)) e
     WHERE (e->>'date')::date>=(v_start AT TIME ZONE 'America/New_York')::date
       AND (e->>'date')::date<=((v_end-interval '1 microsecond') AT TIME ZONE 'America/New_York')::date
       AND NOT EXISTS(SELECT 1 FROM selected s WHERE (s.bar_ts AT TIME ZONE 'America/New_York')::date=(e->>'date')::date)
   ) ELSE '[]'::jsonb END,
   'days_with_unqualified_profile',CASE WHEN v_mode='summary' THEN (
     SELECT COALESCE(jsonb_agg(z.market_date ORDER BY z.market_date),'[]') FROM (
       SELECT DISTINCT (bar_ts AT TIME ZONE 'America/New_York')::date AS market_date FROM selected WHERE NOT qualifying_profile) z
   ) ELSE '[]'::jsonb END,
   'days_with_invalid_ohlcv',CASE WHEN v_mode='summary' THEN (
     SELECT COALESCE(jsonb_agg(z.market_date ORDER BY z.market_date),'[]') FROM (
       SELECT DISTINCT (bar_ts AT TIME ZONE 'America/New_York')::date AS market_date FROM selected WHERE NOT valid_ohlcv) z
   ) ELSE '[]'::jsonb END,
   'has_more',CASE WHEN v_mode='material' THEN (SELECT count(*) FROM bounded)>v_limit ELSE false END,
   'next_after',CASE WHEN v_mode='material' AND (SELECT count(*) FROM bounded)>v_limit THEN max(bar_ts) END,
   'rows',CASE WHEN v_mode='material' THEN COALESCE(jsonb_agg(jsonb_build_object(
     'symbol',i.symbol,'timestamp',bar_ts,'market_date',(bar_ts AT TIME ZONE 'America/New_York')::date,
     'session',CASE session_label WHEN 'regular' THEN 'RTH' WHEN 'premarket' THEN 'PRE' WHEN 'postmarket' THEN 'POST' ELSE 'OUTSIDE_SUPPORTED_SESSION' END,
     'timeframe','1Min','feed','sip','adjustment','raw','saved_session_label',session_label,
     'source',jsonb_build_object('t',bar_ts,'o',open,'h',high,'l',low,'c',close,'v',volume,'n',trade_count,'vw',vwap),
     'instrument_key',instrument_key,'alpaca_asset_id',i.alpaca_asset_id,'loaded_by_job_id',loaded_by_job_id,
     'source_loaded_at',source_loaded_at,'source_row_sha256',row_sha256,
     'provenance_qualified',qualifying_profile,'valid_ohlcv',valid_ohlcv,
     'support_history',(bar_ts AT TIME ZONE 'America/New_York')::date<'2025-09-01'::date,
     'mapping_state','IDENTITY_OR_QUALITY_UNRESOLVED') ORDER BY bar_ts),'[]') ELSE '[]'::jsonb END
 ) INTO v_result FROM selected;
 v_count:=(v_result->>'record_count')::int;
 IF v_mode='summary' AND v_count>40000 THEN
   RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Retained summary exceeded40000 rows; split its date unit';
 END IF;
 RETURN v_result||jsonb_build_object(
   'state',CASE WHEN v_count=0 THEN 'NO_RETAINED_ROWS' ELSE 'RETAINED_SOURCE_READ' END,
   'mode',v_mode,'task_id',active_task.id,'source_task_id',t.id,'run_id',t.run_id,'member_id',m.member_id,
   'source_relation','market_fixed_20250901_20260831.alpaca_sip_bars_1m',
   'source_project','oxzabweahkoimtevbbny','original_source_project','mnmkxjirpwbptdnvjmpw',
   'instrument_key',i.instrument_key,'alpaca_asset_id',i.alpaca_asset_id,'symbol',i.symbol,
   'start',v_start,'end_exclusive',v_end,'observed_at',clock_timestamp(),
   'provider','Alpaca','feed','sip','adjustment','raw','timeframe','1Min',
   'mapping_state','IDENTITY_OR_QUALITY_UNRESOLVED',
   'mapping_reason','POST_WINDOW_ANCHOR_SYMBOL_MATCH_IS_NOT_HISTORICAL_IDENTITY_PROOF',
   'calendar_available',COALESCE(jsonb_typeof(t.scope->'calendar')='array',false),
   'coverage_state','UNKNOWN_PROVIDER_OBSERVATION_DENOMINATOR',
   'source_reference_provenance',i.provenance);
END $fn$;

-- Remove default grants before exposing the one fixed reader to the existing
-- capability owner. No PUBLIC, anon, authenticated or service-role entry point.
DO $acl$
DECLARE g record;
BEGIN
 REVOKE ALL ON FUNCTION astra_ingestion_v1.backfill_reuse_read_v2(jsonb) FROM PUBLIC;
 FOR g IN SELECT DISTINCT r.rolname FROM pg_proc p
   CROSS JOIN LATERAL aclexplode(p.proacl) a JOIN pg_roles r ON r.oid=a.grantee
   WHERE p.oid='astra_ingestion_v1.backfill_reuse_read_v2(jsonb)'::regprocedure AND a.grantee<>p.proowner
 LOOP EXECUTE format('REVOKE ALL ON FUNCTION astra_ingestion_v1.backfill_reuse_read_v2(jsonb) FROM %I',g.rolname); END LOOP;
END $acl$;
GRANT EXECUTE ON FUNCTION astra_ingestion_v1.backfill_reuse_read_v2(jsonb) TO astra_ingestion_rpc_owner_v1;

DO $wire$
DECLARE d text; b text;
BEGIN
 SELECT pg_get_functiondef('astra_ingestion_v1.rpc_dispatch(text,jsonb)'::regprocedure) INTO STRICT d;
 IF strpos(d,'backfill_reuse_read')>0 OR strpos(d,'''backfill_work'')')=0 THEN
   RAISE EXCEPTION 'Retained-reader worker allowlist differs or is already wired'; END IF;
 d:=replace(d,'''backfill_work'')','''backfill_work'',''backfill_reuse_read'')');
 EXECUTE d;
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure) INTO STRICT b;
 IF strpos(b,'backfill_retained_reader_v2')>0 OR strpos(b,'BEGIN'||chr(10)||' IF p_operation=''backfill_status'' THEN')=0 THEN
   RAISE EXCEPTION 'Retained-reader dispatch baseline differs or is already wired'; END IF;
 b:=replace(b,'BEGIN'||chr(10)||' IF p_operation=''backfill_status'' THEN',
  'BEGIN'||chr(10)||' -- backfill_retained_reader_v2: invoked only after existing worker authentication.'||chr(10)||
  ' IF p_operation=''backfill_reuse_read'' THEN RETURN astra_ingestion_v1.backfill_reuse_read_v2(p_payload); END IF;'||chr(10)||
  ' IF p_operation=''backfill_status'' THEN');
 EXECUTE b;
END $wire$;
COMMIT;
