-- Queryable fixed-cohort delivery, independent readback and supervised recovery.
-- This is a forward extension of the existing authenticated controller/runtime.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);

DO $preflight$
BEGIN
 IF to_regclass('astra_ingestion_v1.backfill_runs_v2') IS NULL OR to_regclass('astra_ingestion_v1.backfill_readbacks_v2') IS NOT NULL THEN
  RAISE EXCEPTION 'Delivery requires the installed replacement runtime and must be applied once'; END IF;
END $preflight$;

CREATE TABLE astra_ingestion_v1.backfill_family_catalogue_v2 (
 family text PRIMARY KEY,
 title text NOT NULL,
 shared_source_family text,
 completion_basis text NOT NULL
);
INSERT INTO astra_ingestion_v1.backfill_family_catalogue_v2 VALUES
 ('REF01','Identity and reference observations',NULL,'TASKS'),
 ('REF03','Source lineage, quality, exceptions and recovery audit',NULL,'CONTINUOUS_AUDIT'),
 ('P01','Regular-session one-minute equity bars','P01','RTH_SOURCE_ROWS'),
 ('P02','Extended-session one-minute equity bars','P01','PRE_POST_SOURCE_ROWS'),
 ('D01','Intraday technical features',NULL,'TASKS'),
 ('D02','Daily closing price and volume',NULL,'TASKS'),
 ('D03','Daily returns',NULL,'TASKS'),
 ('D04','Daily volatility and volume measures',NULL,'TASKS'),
 ('D05','Daily Amihud illiquidity',NULL,'TASKS'),
 ('N01','News observations',NULL,'TASKS'),
 ('N02','Corporate actions',NULL,'TASKS'),
 ('N03','Executed splits and share-unit adjustments',NULL,'TASKS'),
 ('S01','Daily short-sale volume',NULL,'TASKS'),
 ('S02','Twice-monthly short-interest observations',NULL,'TASKS'),
 ('CTX02','Options observations',NULL,'TASKS'),
 ('CTX06','Fixed-cohort breadth context',NULL,'TASKS');

CREATE TABLE astra_ingestion_v1.backfill_readbacks_v2 (
 task_id text NOT NULL,
 page_no integer NOT NULL,
 run_id text NOT NULL,
 body_sha256 text NOT NULL,
 readback_sha256 text NOT NULL CHECK(body_sha256=readback_sha256),
 expected_records integer NOT NULL,
 actual_records integer NOT NULL CHECK(expected_records=actual_records),
 target_records integer NOT NULL,
 support_records integer NOT NULL,
 unknown_date_records integer NOT NULL,
 rth_records integer NOT NULL,
 pre_records integer NOT NULL,
 post_records integer NOT NULL,
 unclassified_session_records integer NOT NULL,
 usable_rth_records integer NOT NULL DEFAULT 0,
 usable_pre_records integer NOT NULL DEFAULT 0,
 usable_post_records integer NOT NULL DEFAULT 0,
 reused_records bigint NOT NULL DEFAULT 0,
 reused_qualified_records bigint NOT NULL DEFAULT 0,
 reused_usable_records bigint NOT NULL DEFAULT 0,
 retained_source_verification jsonb,
 verified_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 verified_by text NOT NULL DEFAULT current_user,
 method text NOT NULL DEFAULT 'INDEPENDENT_TRANSACTION_RAW_HASH_AND_SOURCE_COUNT_V2',
 PRIMARY KEY(task_id,page_no),
 FOREIGN KEY(task_id,page_no) REFERENCES astra_ingestion_v1.backfill_pages_v2(task_id,page_no)
);
CREATE INDEX backfill_readbacks_run_v2 ON astra_ingestion_v1.backfill_readbacks_v2(run_id,task_id,page_no);
CREATE TABLE astra_ingestion_v1.backfill_audit_v2 (
 id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
 run_id text NOT NULL REFERENCES astra_ingestion_v1.backfill_runs_v2(id),
 task_id text,
 generation bigint,
 action text NOT NULL,
 source_revision text,
 evidence jsonb NOT NULL,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX backfill_audit_run_v2 ON astra_ingestion_v1.backfill_audit_v2(run_id,id);
CREATE TABLE astra_ingestion_v1.backfill_plan_units_v2 (
 run_id text NOT NULL REFERENCES astra_ingestion_v1.backfill_runs_v2(id),
 task_id text PRIMARY KEY REFERENCES astra_ingestion_v1.backfill_tasks_v2(id),
 family text NOT NULL,
 definition_sha256 text NOT NULL,
 target_period daterange,
 representative_map_sha256 text,
 representative_map_valid boolean,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE INDEX backfill_plan_units_run_v2 ON astra_ingestion_v1.backfill_plan_units_v2(run_id,task_id);
CREATE TABLE astra_ingestion_v1.backfill_plan_coverage_v2 (
 run_id text NOT NULL,
 family text NOT NULL,
 member_id text NOT NULL,
 covered_dates datemultirange NOT NULL DEFAULT '{}'::datemultirange,
 task_count bigint NOT NULL,
 PRIMARY KEY(run_id,family,member_id)
);
CREATE TABLE astra_ingestion_v1.backfill_plan_manifests_v2 (
 run_id text PRIMARY KEY REFERENCES astra_ingestion_v1.backfill_runs_v2(id),
 expected_task_count bigint NOT NULL CHECK(expected_task_count>0),
 expected_plan_sha256 text NOT NULL CHECK(expected_plan_sha256 ~ '^[0-9a-f]{64}$'),
 workflow_plan jsonb NOT NULL,
 required_trading_dates datemultirange NOT NULL,
 required_calendar_dates datemultirange NOT NULL,
 sealed_at timestamptz NOT NULL DEFAULT clock_timestamp()
);
CREATE UNIQUE INDEX backfill_recovery_once_per_evidence_v2 ON astra_ingestion_v1.backfill_audit_v2(task_id,source_revision,(evidence->>'recovery_key'))
 WHERE action='SUPERVISED_RECOVERY';
CREATE TRIGGER backfill_readback_immutable_v2 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.backfill_readbacks_v2
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.backfill_evidence_guard_v2();
CREATE TRIGGER backfill_audit_immutable_v2 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.backfill_audit_v2
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.backfill_evidence_guard_v2();
CREATE TRIGGER backfill_exception_immutable_v2 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.backfill_exceptions_v2
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.backfill_evidence_guard_v2();
CREATE TRIGGER backfill_plan_units_immutable_v2 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.backfill_plan_units_v2
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.backfill_evidence_guard_v2();
CREATE TRIGGER backfill_plan_manifest_immutable_v2 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.backfill_plan_manifests_v2
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.backfill_evidence_guard_v2();

CREATE FUNCTION astra_ingestion_v1.backfill_stamp_v2(v text) RETURNS timestamptz
LANGUAGE plpgsql IMMUTABLE SET search_path='' AS $$
BEGIN
 IF v IS NULL OR v !~ '^\d{4}-\d{2}-\d{2}T.*(Z|[+-]\d{2}:\d{2})$' THEN RETURN NULL; END IF;
 RETURN v::timestamptz;
EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN RETURN NULL;
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_date_v2(v text) RETURNS date
LANGUAGE plpgsql IMMUTABLE SET search_path='' AS $$
BEGIN
 IF v IS NULL OR v !~ '^\d{4}-\d{2}-\d{2}' THEN RETURN NULL; END IF;
 RETURN left(v,10)::date;
EXCEPTION WHEN invalid_datetime_format OR datetime_field_overflow THEN RETURN NULL;
END $$;

-- A view projection reads each immutable original once. No second bar archive.
CREATE FUNCTION astra_ingestion_v1.backfill_page_rows_v2(p_task_id text,p_page_no integer)
RETURNS TABLE(record_ordinal bigint,symbol text,market_date date,session text,target_window boolean,record_group text,source_row jsonb)
LANGUAGE plpgsql STABLE SET search_path='' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2; p astra_ingestion_v1.backfill_pages_v2;
 b jsonb; v_row jsonb; v_rows jsonb; v_array jsonb; v_symbol text; v_group text;
 v_stamp timestamptz; v_local timestamp; v_calendar jsonb; v_day jsonb; v_ordinal bigint:=0;
BEGIN
 SELECT * INTO t FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=p_task_id;
 SELECT * INTO p FROM astra_ingestion_v1.backfill_pages_v2 WHERE task_id=p_task_id AND page_no=p_page_no;
 IF NOT FOUND THEN RETURN; END IF;
 b:=p.raw_body::jsonb;
 IF t.kind IN ('alpaca_stock_bars','alpaca_option_bars') THEN
  SELECT COALESCE(jsonb_object_agg(e->>'date',e),'{}') INTO v_calendar FROM jsonb_array_elements(COALESCE(t.scope->'calendar','[]')) e;
  FOR v_symbol,v_array IN SELECT key,value FROM jsonb_each(COALESCE(NULLIF(b->'bars','null'::jsonb),'{}')) ORDER BY key LOOP
   FOR v_row IN SELECT value FROM jsonb_array_elements(v_array) LOOP
    v_ordinal:=v_ordinal+1;record_ordinal:=v_ordinal;symbol:=v_symbol;source_row:=v_row;record_group:='bars';
    v_stamp:=astra_ingestion_v1.backfill_stamp_v2(v_row->>'t');v_local:=v_stamp AT TIME ZONE 'America/New_York';market_date:=v_local::date;
    target_window:=market_date BETWEEN '2025-09-01'::date AND '2026-07-31'::date;
    IF t.kind='alpaca_option_bars' OR t.scope->>'timeframe'='1Day' THEN session:='DAILY';
    ELSE
     v_day:=v_calendar->market_date::text;
     session:=CASE WHEN v_stamp IS NULL THEN 'INVALID_TIMESTAMP'
      WHEN v_day IS NULL THEN 'CALENDAR_UNRESOLVED'
      WHEN v_local::time>='04:00'::time AND v_local::time<(v_day->>'open')::time THEN 'PRE'
      WHEN v_local::time>=(v_day->>'open')::time AND v_local::time<(v_day->>'close')::time THEN 'RTH'
      WHEN v_local::time>=(v_day->>'close')::time AND v_local::time<'20:00'::time THEN 'POST'
      ELSE 'OUTSIDE_SUPPORTED_SESSION' END;
    END IF;
    RETURN NEXT;
   END LOOP;
  END LOOP;
  RETURN;
 ELSIF t.kind='alpaca_actions' THEN
  FOR v_group,v_array IN SELECT key,value FROM jsonb_each(COALESCE(NULLIF(b->'corporate_actions','null'::jsonb),'{}')) ORDER BY key LOOP
   FOR v_row IN SELECT value FROM jsonb_array_elements(v_array) LOOP
    v_ordinal:=v_ordinal+1;record_ordinal:=v_ordinal;symbol:=COALESCE(v_row->>'symbol',v_row->>'initiating_symbol');record_group:=v_group;source_row:=v_row;
    market_date:=astra_ingestion_v1.backfill_date_v2(v_row->>'process_date');session:=NULL;target_window:=market_date BETWEEN '2025-09-01'::date AND '2026-07-31'::date;
    RETURN NEXT;
   END LOOP;
  END LOOP;
  RETURN;
 ELSIF t.kind='alpaca_reference' THEN v_rows:=jsonb_build_array(b);
 ELSIF t.kind='alpaca_news' THEN v_rows:=COALESCE(NULLIF(b->'news','null'::jsonb),'[]');
 ELSIF t.kind='alpaca_option_contracts' THEN v_rows:=COALESCE(NULLIF(b->'option_contracts','null'::jsonb),'[]');
 ELSIF t.provider='Massive' THEN v_rows:=CASE WHEN jsonb_typeof(b->'results')='object' THEN jsonb_build_array(b->'results') ELSE COALESCE(NULLIF(b->'results','null'::jsonb),'[]') END;
 ELSE v_rows:=COALESCE(b->'rows',b->'records','[]'); END IF;
 FOR v_row IN SELECT value FROM jsonb_array_elements(v_rows) LOOP
  v_ordinal:=v_ordinal+1;record_ordinal:=v_ordinal;symbol:=COALESCE(v_row->>'symbol',v_row->>'ticker',CASE WHEN jsonb_array_length(COALESCE(t.scope->'symbols','[]'))=1 THEN t.scope#>>'{symbols,0}' END);
  source_row:=v_row;record_group:=t.kind;session:=NULL;
  market_date:=astra_ingestion_v1.backfill_date_v2(COALESCE(v_row->>'market_date',v_row->>'date',v_row->>'settlement_date',v_row->>'ex_dividend_date',v_row->>'execution_date',v_row->>'created_at',v_row->>'published_utc'));
  target_window:=market_date BETWEEN '2025-09-01'::date AND '2026-07-31'::date;
  RETURN NEXT;
 END LOOP;
END $$;

CREATE VIEW astra_ingestion_v1.backfill_source_records_v2 WITH(security_invoker=true) AS
 SELECT p.run_id,t.family,t.kind,t.provider,t.id task_id,p.page_no,x.record_ordinal,
  t.scope->'member_ids' member_ids,x.symbol,x.market_date,x.session,x.target_window,
  COALESCE(t.scope->>'identity_status','UNRESOLVED_PROVIDER_ANCHOR') identity_status,
  COALESCE(t.scope->>'adjustment',CASE WHEN t.kind='alpaca_option_bars' THEN 'PROVIDER_OPTION_CONTRACT' END) price_basis,
  x.record_group,x.source_row,p.body_sha256,p.fetched_at,p.committed_at,p.quality,
  jsonb_build_object('task_id',p.task_id,'page_no',p.page_no,'record_ordinal',x.record_ordinal,'body_sha256',p.body_sha256) lineage
 FROM astra_ingestion_v1.backfill_pages_v2 p JOIN astra_ingestion_v1.backfill_tasks_v2 t ON t.id=p.task_id
 CROSS JOIN LATERAL astra_ingestion_v1.backfill_page_rows_v2(p.task_id,p.page_no) x;

CREATE VIEW astra_ingestion_v1.backfill_family_p01_v2 WITH(security_invoker=true) AS
 SELECT * FROM astra_ingestion_v1.backfill_source_records_v2 WHERE kind='alpaca_stock_bars' AND session='RTH' AND target_window;
CREATE VIEW astra_ingestion_v1.backfill_family_p02_v2 WITH(security_invoker=true) AS
 SELECT run_id,'P02'::text family,kind,provider,task_id,page_no,record_ordinal,member_ids,symbol,market_date,session,target_window,
  identity_status,price_basis,record_group,source_row,body_sha256,fetched_at,committed_at,quality,lineage
 FROM astra_ingestion_v1.backfill_source_records_v2 WHERE kind='alpaca_stock_bars' AND session IN ('PRE','POST') AND target_window;
DO $family_views$
DECLARE f text;
BEGIN
 FOREACH f IN ARRAY ARRAY['REF01','D01','D02','D03','D04','D05','N01','N02','N03','S01','S02','CTX02','CTX06'] LOOP
  EXECUTE format('CREATE VIEW astra_ingestion_v1.backfill_family_%s_v2 WITH(security_invoker=true) AS SELECT * FROM astra_ingestion_v1.backfill_source_records_v2 WHERE family=%L',lower(f),f);
 END LOOP;
END $family_views$;
CREATE VIEW astra_ingestion_v1.backfill_family_ref03_v2 WITH(security_invoker=true) AS
 SELECT p.run_id,'REF03'::text family,'SOURCE_PAGE'::text evidence_type,p.task_id,p.page_no,p.committed_at recorded_at,
  jsonb_build_object('provider',p.provider,'request',p.request,'body_sha256',p.body_sha256,'record_count',p.record_count,'quality',p.quality,'adapter_version',p.adapter_version) evidence
 FROM astra_ingestion_v1.backfill_pages_v2 p
 UNION ALL SELECT e.run_id,'REF03','EXCEPTION',e.task_id,e.page_no,e.recorded_at,to_jsonb(e) FROM astra_ingestion_v1.backfill_exceptions_v2 e
 UNION ALL SELECT a.run_id,'REF03',a.action,a.task_id,NULL,a.recorded_at,to_jsonb(a) FROM astra_ingestion_v1.backfill_audit_v2 a
 UNION ALL SELECT v.run_id,'REF03','INDEPENDENT_READBACK',v.task_id,v.page_no,v.verified_at,to_jsonb(v) FROM astra_ingestion_v1.backfill_readbacks_v2 v;

CREATE FUNCTION astra_ingestion_v1.backfill_recheck_page_v2(p_task_id text,p_page_no integer) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE p astra_ingestion_v1.backfill_pages_v2; v_hash text; v_counts record; v_saved astra_ingestion_v1.backfill_readbacks_v2; v_reuse jsonb; v_sessions record;
BEGIN
 SELECT * INTO p FROM astra_ingestion_v1.backfill_pages_v2 WHERE task_id=p_task_id AND page_no=p_page_no;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='AI004',MESSAGE='Readback page does not exist'; END IF;
 IF p.committed_at>=transaction_timestamp() THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Independent readback requires a subsequent transaction'; END IF;
 v_hash:=encode(sha256(convert_to(p.raw_body,'UTF8')),'hex');
 SELECT count(*)::int total,count(*) FILTER(WHERE target_window)::int target,
  count(*) FILTER(WHERE market_date<'2025-09-01'::date)::int support,
  count(*) FILTER(WHERE market_date IS NULL)::int unknown_date,
  count(*) FILTER(WHERE target_window AND session='RTH')::int rth,
  count(*) FILTER(WHERE target_window AND session='PRE')::int pre,
  count(*) FILTER(WHERE target_window AND session='POST')::int post,
  count(*) FILTER(WHERE target_window AND session='RTH' AND astra_ingestion_v1.backfill_bar_usable_v2(source_row))::int urth,
  count(*) FILTER(WHERE target_window AND session='PRE' AND astra_ingestion_v1.backfill_bar_usable_v2(source_row))::int upre,
  count(*) FILTER(WHERE target_window AND session='POST' AND astra_ingestion_v1.backfill_bar_usable_v2(source_row))::int upost,
  count(*) FILTER(WHERE session IN ('INVALID_TIMESTAMP','CALENDAR_UNRESOLVED','OUTSIDE_SUPPORTED_SESSION'))::int unclassified
 INTO v_counts FROM astra_ingestion_v1.backfill_page_rows_v2(p.task_id,p.page_no);
 IF v_hash<>p.body_sha256 OR v_counts.total<>p.record_count THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Independent stored-source hash or count mismatch'; END IF;
 IF lower(p.provider)='reuse' THEN
  IF to_regprocedure('astra_ingestion_v1.backfill_reuse_verify_v2(text,integer)') IS NULL THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Fixed retained-source verifier is required before pointer readback'; END IF;
  v_reuse:=astra_ingestion_v1.backfill_reuse_verify_v2(p.task_id,p.page_no);
  IF v_reuse->'passed' IS DISTINCT FROM 'true'::jsonb THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Retained pointer source digest or aggregate readback differs'; END IF;
  SELECT COALESCE(sum((e->>'record_count')::int) FILTER(WHERE (e->>'market_date')::date BETWEEN '2025-09-01'::date AND '2026-07-31'::date),0)::int target,
   COALESCE(sum((e->>'record_count')::int) FILTER(WHERE (e->>'market_date')::date<'2025-09-01'::date),0)::int support,
   COALESCE(sum((e->>'qualified_rth_count')::int) FILTER(WHERE (e->>'market_date')::date BETWEEN '2025-09-01'::date AND '2026-07-31'::date),0)::int rth,
   COALESCE(sum((e->>'qualified_pre_count')::int) FILTER(WHERE (e->>'market_date')::date BETWEEN '2025-09-01'::date AND '2026-07-31'::date),0)::int pre,
   COALESCE(sum((e->>'qualified_post_count')::int) FILTER(WHERE (e->>'market_date')::date BETWEEN '2025-09-01'::date AND '2026-07-31'::date),0)::int post,
   COALESCE(sum((e->>'usable_rth_count')::int) FILTER(WHERE (e->>'market_date')::date BETWEEN '2025-09-01'::date AND '2026-07-31'::date),0)::int urth,
   COALESCE(sum((e->>'usable_pre_count')::int) FILTER(WHERE (e->>'market_date')::date BETWEEN '2025-09-01'::date AND '2026-07-31'::date),0)::int upre,
   COALESCE(sum((e->>'usable_post_count')::int) FILTER(WHERE (e->>'market_date')::date BETWEEN '2025-09-01'::date AND '2026-07-31'::date),0)::int upost
   INTO v_sessions FROM jsonb_array_elements(v_reuse->'session_coverage') e;
  v_counts.target:=v_sessions.target;v_counts.support:=v_sessions.support;v_counts.unknown_date:=0;
  v_counts.rth:=v_sessions.rth;v_counts.pre:=v_sessions.pre;v_counts.post:=v_sessions.post;
  v_counts.urth:=v_sessions.urth;v_counts.upre:=v_sessions.upre;v_counts.upost:=v_sessions.upost;
  v_counts.unclassified:=COALESCE((v_reuse->>'unknown_session_count')::int,0);
 END IF;
 INSERT INTO astra_ingestion_v1.backfill_readbacks_v2(task_id,page_no,run_id,body_sha256,readback_sha256,expected_records,actual_records,target_records,support_records,unknown_date_records,rth_records,pre_records,post_records,unclassified_session_records,
  usable_rth_records,usable_pre_records,usable_post_records,reused_records,reused_qualified_records,reused_usable_records,retained_source_verification)
 VALUES(p.task_id,p.page_no,p.run_id,p.body_sha256,v_hash,p.record_count,v_counts.total,v_counts.target,v_counts.support,v_counts.unknown_date,v_counts.rth,v_counts.pre,v_counts.post,v_counts.unclassified,
  v_counts.urth,v_counts.upre,v_counts.upost,COALESCE((v_reuse->>'reused_records')::bigint,0),COALESCE((v_reuse->>'qualifying_profile_count')::bigint,0),COALESCE((v_reuse->>'usable_source_count')::bigint,0),v_reuse)
 ON CONFLICT(task_id,page_no) DO NOTHING;
 SELECT * INTO v_saved FROM astra_ingestion_v1.backfill_readbacks_v2 WHERE task_id=p.task_id AND page_no=p.page_no;
 RETURN to_jsonb(v_saved)||jsonb_build_object('state','VERIFIED');
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_bar_usable_v2(v jsonb) RETURNS boolean
LANGUAGE plpgsql IMMUTABLE SET search_path='' AS $$
DECLARE k text; o numeric; h numeric; l numeric; c numeric;
BEGIN
 FOREACH k IN ARRAY ARRAY['o','h','l','c','v'] LOOP
  IF jsonb_typeof(v->k) IS DISTINCT FROM 'number' THEN RETURN false; END IF;
 END LOOP;
 o:=(v->>'o')::numeric;h:=(v->>'h')::numeric;l:=(v->>'l')::numeric;c:=(v->>'c')::numeric;
 RETURN o>0 AND h>0 AND l>0 AND c>0 AND (v->>'v')::numeric>=0 AND h>=GREATEST(o,c,l) AND l<=LEAST(o,c,h);
EXCEPTION WHEN numeric_value_out_of_range OR invalid_text_representation THEN RETURN false;
END $$;

CREATE VIEW astra_ingestion_v1.backfill_family_status_v2 WITH(security_invoker=true) AS
 WITH mapped_tasks AS (
  SELECT t.*,m.delivery_family FROM astra_ingestion_v1.backfill_tasks_v2 t
  CROSS JOIN LATERAL (SELECT t.family delivery_family UNION ALL SELECT 'P02' WHERE t.family='P01' AND t.kind IN ('alpaca_stock_bars','retained_reuse') AND COALESCE(t.scope->>'timeframe','1Min')='1Min') m
 ), units AS (
  SELECT run_id,delivery_family,count(*) planned_units,
   count(*) FILTER(WHERE status IN ('INGESTED','NO_DATA_RETURNED','NOT_APPLICABLE','PROVIDER_LIMITATION','IDENTITY_OR_QUALITY_UNRESOLVED')) terminal_units,
   count(*) FILTER(WHERE status='INGESTED') ingested_units,
   count(*) FILTER(WHERE status='NO_DATA_RETURNED') no_data_units,
   count(*) FILTER(WHERE status='NOT_APPLICABLE') not_applicable_units,
   count(*) FILTER(WHERE status='PROVIDER_LIMITATION') provider_limited_units,
   count(*) FILTER(WHERE status='IDENTITY_OR_QUALITY_UNRESOLVED') unresolved_units,
   count(*) FILTER(WHERE status='OPERATIONAL_ERROR') operational_error_units,
   count(*) FILTER(WHERE status='BLOCKED_EXTERNAL') blocked_units,
   count(*) FILTER(WHERE status='RETRY_WAIT') retry_wait_units,
   count(*) FILTER(WHERE status='RUNNING') running_units,
   count(*) FILTER(WHERE status='PENDING') pending_units,
   min(next_retry_at) FILTER(WHERE status='RETRY_WAIT') next_retry_at
  FROM mapped_tasks GROUP BY run_id,delivery_family
 ), observations AS (
  SELECT t.run_id,t.delivery_family,count(p.task_id) archived_pages,count(v.task_id) verified_pages,
   COALESCE(sum(CASE WHEN t.delivery_family='P01' THEN v.rth_records WHEN t.delivery_family='P02' THEN v.pre_records+v.post_records ELSE p.record_count END),0) committed_records,
   COALESCE(sum(v.target_records),0) dated_target_records,COALESCE(sum(v.support_records),0) support_records,
   COALESCE(sum(v.unknown_date_records),0) unknown_date_records,
   COALESCE(sum(v.unclassified_session_records),0) unclassified_session_records,
   COALESCE(sum(v.reused_records),0) referenced_existing_records,
   COALESCE(sum(v.reused_qualified_records),0) referenced_qualifying_records,
   COALESCE(sum(v.reused_usable_records),0) referenced_usable_records,
   COALESCE(sum(CASE WHEN t.delivery_family='P01' THEN v.usable_rth_records WHEN t.delivery_family='P02' THEN v.usable_pre_records+v.usable_post_records ELSE 0 END),0) usable_minute_records
  FROM mapped_tasks t LEFT JOIN astra_ingestion_v1.backfill_pages_v2 p ON p.task_id=t.id
   LEFT JOIN astra_ingestion_v1.backfill_readbacks_v2 v ON v.task_id=p.task_id AND v.page_no=p.page_no
  GROUP BY t.run_id,t.delivery_family
 ), audits AS (SELECT run_id,count(*) evidence_records FROM astra_ingestion_v1.backfill_family_ref03_v2 GROUP BY run_id)
 SELECT r.id run_id,c.family,c.title,c.completion_basis,c.shared_source_family,
  COALESCE(u.planned_units,0) planned_units,COALESCE(u.terminal_units,0) terminal_units,
  COALESCE(u.ingested_units,0) ingested_units,COALESCE(u.no_data_units,0) no_data_units,
  COALESCE(u.not_applicable_units,0) not_applicable_units,COALESCE(u.provider_limited_units,0) provider_limited_units,
  COALESCE(u.unresolved_units,0) unresolved_units,COALESCE(u.operational_error_units,0) operational_error_units,
  COALESCE(u.blocked_units,0) blocked_units,COALESCE(u.retry_wait_units,0) retry_wait_units,
  COALESCE(u.running_units,0) running_units,COALESCE(u.pending_units,0) pending_units,
  COALESCE(o.archived_pages,0) archived_pages,COALESCE(o.verified_pages,0) verified_pages,
  CASE WHEN c.family='REF03' THEN COALESCE(a.evidence_records,0) ELSE COALESCE(o.committed_records,0) END committed_records,
  COALESCE(o.dated_target_records,0) dated_target_records,COALESCE(o.support_records,0) support_records,
  COALESCE(o.unknown_date_records,0) unknown_date_records,COALESCE(o.unclassified_session_records,0) unclassified_session_records,
  COALESCE(o.referenced_existing_records,0) referenced_existing_records,
  COALESCE(o.referenced_qualifying_records,0) referenced_qualifying_records,
  COALESCE(o.referenced_usable_records,0) referenced_usable_records,
  COALESCE(o.usable_minute_records,0) usable_minute_records,
  u.next_retry_at,
  CASE WHEN c.family='REF03' THEN 'CONTINUOUS_AUDIT'
   WHEN COALESCE(u.planned_units,0)=0 THEN 'NOT_PLANNED'
   WHEN COALESCE(u.operational_error_units,0)>0 THEN 'PARTIAL_OPERATIONAL_FAILURE'
   WHEN COALESCE(u.blocked_units,0)>0 THEN 'BLOCKED_EXTERNAL'
   WHEN u.terminal_units<u.planned_units THEN 'IN_PROGRESS'
   WHEN o.verified_pages<o.archived_pages THEN 'READBACK_PENDING'
   WHEN u.no_data_units+u.not_applicable_units+u.provider_limited_units+u.unresolved_units>0 THEN 'COMPLETE_WITH_DOCUMENTED_GAPS'
   ELSE 'COMPLETE' END work_completion,
  'OBSERVED_COUNTS_ONLY_NO_UNIVERSAL_COVERAGE_CERTIFICATE'::text coverage_basis,
  false counts_are_additive_across_families
 FROM astra_ingestion_v1.backfill_runs_v2 r CROSS JOIN astra_ingestion_v1.backfill_family_catalogue_v2 c
 LEFT JOIN units u ON u.run_id=r.id AND u.delivery_family=c.family
 LEFT JOIN observations o ON o.run_id=r.id AND o.delivery_family=c.family
 LEFT JOIN audits a ON a.run_id=r.id;

CREATE FUNCTION astra_ingestion_v1.backfill_delivery_status_v2(p_run_id text DEFAULT NULL) RETURNS jsonb
LANGUAGE sql STABLE SET search_path='' AS $$
 SELECT jsonb_build_object('runs',COALESCE(jsonb_agg(x),'[]'),'observed_at',clock_timestamp()) FROM (
  SELECT r.id run_id,r.status run_status,r.cohort_policy,r.cohort_sha256,r.target_start,r.target_end,
   r.metadata->'planning_complete'='true'::jsonb planning_complete,r.last_progress_at,
   jsonb_build_object('requests_reserved',r.requests_reserved,'physical_pages',r.pages_committed,'physical_source_and_derived_records',r.records_committed,'source_bytes',r.source_bytes) physical_totals,
   (SELECT count(*) FROM astra_ingestion_v1.backfill_pages_v2 p WHERE p.run_id=r.id AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_readbacks_v2 v WHERE v.task_id=p.task_id AND v.page_no=p.page_no)) required_readbacks_remaining,
   (SELECT jsonb_agg(to_jsonb(f) ORDER BY f.family) FROM astra_ingestion_v1.backfill_family_status_v2 f WHERE f.run_id=r.id) families,
   (SELECT COALESCE(jsonb_agg(to_jsonb(d)),'[]') FROM astra_ingestion_v1.backfill_provider_dependencies_v2 d WHERE d.run_id=r.id) provider_dependencies,
   (SELECT COALESCE(jsonb_agg(z),'[]') FROM (SELECT t.id,t.family,t.kind,t.status,t.error_code,t.error_message,t.generation,t.page_attempts,t.next_retry_at,t.source_revision,
     CASE WHEN t.status='RETRY_WAIT' THEN 'Persisted retry; worker may claim after next_retry_at'
      WHEN t.error_code='MISSING_PROVIDER_CREDENTIAL' THEN 'Restore provider configuration and advertise changed capability_revision'
      WHEN t.status IN ('OPERATIONAL_ERROR','BLOCKED_EXTERNAL') THEN 'Repair and deploy; call backfill_recover with exact task generation, repair revision and verification evidence'
      WHEN t.status='RUNNING' THEN 'Current finite lease, or automatic stale-lease takeover'
      ELSE 'Configured worker claim or dependency completion' END executable_next_action
     FROM astra_ingestion_v1.backfill_tasks_v2 t WHERE t.run_id=r.id AND t.status IN ('OPERATIONAL_ERROR','BLOCKED_EXTERNAL','RETRY_WAIT') ORDER BY t.created_at,t.id LIMIT 100) z) outstanding_actions
  FROM astra_ingestion_v1.backfill_runs_v2 r WHERE p_run_id IS NULL OR r.id=p_run_id ORDER BY r.created_at DESC LIMIT 20
 ) x
$$;

CREATE FUNCTION astra_ingestion_v1.backfill_try_finalize_v2(p_run_id text) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE r astra_ingestion_v1.backfill_runs_v2; v_state text; v_gaps boolean; v_coverage_unknown boolean; v_plan astra_ingestion_v1.backfill_plan_manifests_v2;
BEGIN
 SELECT * INTO r FROM astra_ingestion_v1.backfill_runs_v2 WHERE id=p_run_id FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='AI004',MESSAGE='Replacement run does not exist'; END IF;
 IF r.status IN ('COMPLETE','COMPLETE_WITH_DOCUMENTED_GAPS','SUPERSEDED','PAUSED') THEN RETURN jsonb_build_object('state',r.status); END IF;
 IF r.metadata->'planning_complete' IS DISTINCT FROM 'true'::jsonb THEN RETURN jsonb_build_object('state','PLANNING_INCOMPLETE'); END IF;
 SELECT * INTO v_plan FROM astra_ingestion_v1.backfill_plan_manifests_v2 WHERE run_id=r.id;
 IF NOT FOUND THEN RETURN jsonb_build_object('state','FULL_PLAN_NOT_SEALED'); END IF;
 IF (SELECT count(*) FROM astra_ingestion_v1.backfill_plan_units_v2 WHERE run_id=r.id AND recorded_at<=v_plan.sealed_at)<>v_plan.expected_task_count THEN
  RETURN jsonb_build_object('state','EXPECTED_PLAN_UNITS_DIFFER'); END IF;
 IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 WHERE run_id=r.id AND status IN ('PENDING','RUNNING','RETRY_WAIT')) THEN
  RETURN jsonb_build_object('state','WORK_REMAINS'); END IF;
 IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_family_status_v2 WHERE run_id=r.id AND family<>'REF03' AND planned_units=0) THEN
  RETURN jsonb_build_object('state','REQUIRED_FAMILY_NOT_PLANNED'); END IF;
 IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 WHERE run_id=r.id AND status='OPERATIONAL_ERROR') THEN v_state:='PARTIAL_OPERATIONAL_FAILURE';
 ELSIF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 WHERE run_id=r.id AND status='BLOCKED_EXTERNAL') THEN v_state:='BLOCKED_EXTERNAL';
 ELSIF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_pages_v2 p WHERE p.run_id=r.id AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_readbacks_v2 v WHERE v.task_id=p.task_id AND v.page_no=p.page_no)) THEN
  RETURN jsonb_build_object('state','READBACK_PENDING');
 ELSE
  v_coverage_unknown:=r.metadata->'applicable_data_coverage_established' IS DISTINCT FROM 'true'::jsonb
   OR jsonb_typeof(r.metadata->'coverage_evidence') IS DISTINCT FROM 'object'
   OR COALESCE(r.metadata#>>'{coverage_evidence,report_sha256}','') !~ '^[0-9a-f]{64}$'
   OR length(COALESCE(r.metadata#>>'{coverage_evidence,evidence_ref}',''))<8
   OR r.metadata#>>'{coverage_evidence,cohort_sha256}' IS DISTINCT FROM r.cohort_sha256
   OR r.metadata#>>'{coverage_evidence,instruction_sha256}' IS DISTINCT FROM r.instruction_sha256
   OR astra_ingestion_v1.backfill_stamp_v2(r.metadata#>>'{coverage_evidence,verified_at}') IS NULL
   OR astra_ingestion_v1.backfill_stamp_v2(r.metadata#>>'{coverage_evidence,verified_at}')<COALESCE(r.last_progress_at,r.created_at)
   OR astra_ingestion_v1.backfill_stamp_v2(r.metadata#>>'{coverage_evidence,verified_at}')>clock_timestamp();
  SELECT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 WHERE run_id=r.id AND status<>'INGESTED')
   OR EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_readbacks_v2 WHERE run_id=r.id AND unclassified_session_records>0) INTO v_gaps;
  v_state:=CASE WHEN v_gaps OR v_coverage_unknown THEN 'COMPLETE_WITH_DOCUMENTED_GAPS' ELSE 'COMPLETE' END;
 END IF;
 IF r.status<>v_state THEN
  UPDATE astra_ingestion_v1.backfill_runs_v2 SET status=v_state,metadata=metadata||jsonb_build_object('work_disposition',v_state,'work_disposition_at',clock_timestamp(),'coverage_policy','Observed source and calculation outcomes remain distinct from research coverage certification','coverage_disposition_reason',CASE WHEN v_coverage_unknown THEN 'APPLICABLE_DATA_COVERAGE_NOT_ESTABLISHED' WHEN v_gaps THEN 'DOCUMENTED_UNIT_OR_SESSION_GAPS' ELSE 'APPLICABLE_DATA_COVERAGE_EVIDENCED' END) WHERE id=r.id;
  INSERT INTO astra_ingestion_v1.backfill_audit_v2(run_id,action,evidence) VALUES(r.id,'RUN_DISPOSITION',jsonb_build_object('state',v_state,'planning_complete',true,'fixed_member_count',3000,'coverage_unknown',v_coverage_unknown,'coverage_evidence',r.metadata->'coverage_evidence'));
 END IF;
 RETURN jsonb_build_object('state',v_state);
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_recover_v2(p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2; r astra_ingestion_v1.backfill_runs_v2; v_revision text; v_kind text; v_evidence jsonb; v_key text; v_last_attempt timestamptz; v_observed timestamptz;
BEGIN
 v_revision:=p_payload->>'repair_revision';v_kind:=p_payload->>'repair_kind';v_evidence:=p_payload->'evidence';
 v_key:=COALESCE(v_evidence->>'recovery_key',v_revision);
 IF length(COALESCE(v_revision,'')) NOT BETWEEN 1 AND 100 OR v_kind NOT IN ('ADAPTER_FIX','TRANSPORT_RECHECK','CREDENTIAL_RECONFIGURED')
  OR jsonb_typeof(v_evidence) IS DISTINCT FROM 'object' OR length(COALESCE(v_evidence->>'verification',''))<10 OR octet_length(v_evidence::text)>65536 THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Recovery needs a concrete repair revision, kind and verification evidence'; END IF;
 SELECT * INTO t FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=p_payload->>'task_id' AND run_id=p_payload->>'run_id' FOR UPDATE;
 IF NOT FOUND OR t.generation::text IS DISTINCT FROM p_payload->>'expected_generation' OR t.status NOT IN ('OPERATIONAL_ERROR','BLOCKED_EXTERNAL') THEN
  RAISE EXCEPTION USING ERRCODE='AI001',MESSAGE='Recovery task generation or operational disposition changed'; END IF;
 SELECT * INTO r FROM astra_ingestion_v1.backfill_runs_v2 WHERE id=t.run_id FOR UPDATE;
 IF r.status NOT IN ('ACTIVE','PARTIAL_OPERATIONAL_FAILURE','BLOCKED_EXTERNAL') OR r.fence<>t.run_fence THEN
  RAISE EXCEPTION USING ERRCODE='AI001',MESSAGE='Stopped or superseded run cannot be recovered'; END IF;
 IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_provider_dependencies_v2 WHERE run_id=t.run_id AND provider=t.provider AND state='BLOCKED_EXTERNAL') THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Repair the provider capability dependency before task recovery'; END IF;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_workers_v2 w WHERE w.source_revision=v_revision AND w.observed_at>clock_timestamp()-interval '10 minutes' AND w.supported_kinds ? t.kind) THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Exact repair revision is not deployed with the required worker capability'; END IF;
 IF v_kind='ADAPTER_FIX' AND v_revision IS NOT DISTINCT FROM t.source_revision THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='An adapter repair must deploy a changed source revision'; END IF;
 IF v_kind='TRANSPORT_RECHECK' AND t.error_code NOT IN ('SOURCE_TRANSPORT_ERROR','SOURCE_READ_TIMEOUT','ATTEMPT_BUDGET_EXHAUSTED','SOURCE_HTTP_ERROR') THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='This error requires a concrete adapter or credential repair'; END IF;
 IF v_kind='TRANSPORT_RECHECK' THEN
  v_observed:=astra_ingestion_v1.backfill_stamp_v2(v_evidence->>'observed_at');
  IF v_observed IS NULL OR v_observed<clock_timestamp()-interval '15 minutes' OR v_observed>clock_timestamp()+interval '1 minute'
   OR COALESCE(v_evidence->>'provider_status_evidence_sha256','') !~ '^[0-9a-f]{64}$'
   OR COALESCE(v_evidence->>'recovery_key','') !~ '^[A-Za-z0-9_.:-]{8,160}$' THEN
   RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Transient recovery needs fresh timestamped provider evidence and a unique recovery key'; END IF;
  SELECT max(recorded_at) INTO v_last_attempt FROM astra_ingestion_v1.backfill_audit_v2 WHERE task_id=t.id AND action='SUPERVISED_RECOVERY' AND evidence->>'repair_kind'='TRANSPORT_RECHECK';
  IF v_last_attempt>clock_timestamp()-interval '15 minutes' OR (SELECT count(*) FROM astra_ingestion_v1.backfill_audit_v2 WHERE task_id=t.id AND action='SUPERVISED_RECOVERY' AND evidence->>'repair_kind'='TRANSPORT_RECHECK')>=3 THEN
   RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Finite transient recovery cooldown or three-recovery budget is not satisfied'; END IF;
 END IF;
 IF v_kind='CREDENTIAL_RECONFIGURED' AND t.error_code NOT IN ('BLOCKED_EXTERNAL','AUTHENTICATION_FAILED','MISSING_CREDENTIAL','MISSING_PROVIDER_CREDENTIAL','PROVIDER_FORBIDDEN') THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Credential recovery does not resolve this operational error'; END IF;
 IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_audit_v2 WHERE task_id=t.id AND action='SUPERVISED_RECOVERY' AND source_revision=v_revision AND evidence->>'recovery_key'=v_key) THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='This exact recovery revision has already been attempted; diagnose before another retry'; END IF;
 INSERT INTO astra_ingestion_v1.backfill_audit_v2(run_id,task_id,generation,action,source_revision,evidence)
 VALUES(t.run_id,t.id,t.generation,'SUPERVISED_RECOVERY',v_revision,v_evidence||jsonb_build_object('recovery_key',v_key,'repair_kind',v_kind,'previous_error',t.error_code,'preserved_page_no',t.page_no,'preserved_cursor',t.cursor,'cumulative_attempts',t.attempts));
 UPDATE astra_ingestion_v1.backfill_runs_v2 SET status='ACTIVE' WHERE id=t.run_id;
 UPDATE astra_ingestion_v1.backfill_tasks_v2 SET status='PENDING',page_attempts=0,next_retry_at=clock_timestamp(),error_code=NULL,error_message=NULL WHERE id=t.id;
 RETURN jsonb_build_object('state','RECOVERY_QUEUED','task_id',t.id,'page_no',t.page_no,'cursor',t.cursor,'repair_revision',v_revision);
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_maintain_v2(p_limit integer DEFAULT 2) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' SET statement_timeout='8s' SET lock_timeout='2s' AS $$
DECLARE p record; r record; v_readbacks integer:=0; v_errors integer:=0; v_final jsonb:='[]'; v_result jsonb;
BEGIN
 IF NOT pg_try_advisory_xact_lock(706314020261028) THEN RETURN jsonb_build_object('state','BUSY'); END IF;
 FOR p IN SELECT pg.task_id,pg.page_no,pg.run_id FROM astra_ingestion_v1.backfill_pages_v2 pg
  JOIN astra_ingestion_v1.backfill_runs_v2 rr ON rr.id=pg.run_id
  WHERE rr.status IN ('ACTIVE','PARTIAL_OPERATIONAL_FAILURE','BLOCKED_EXTERNAL') AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_readbacks_v2 v WHERE v.task_id=pg.task_id AND v.page_no=pg.page_no)
   AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_audit_v2 a WHERE a.task_id=pg.task_id AND a.action='READBACK_FAILURE' AND a.evidence->>'page_no'=pg.page_no::text)
  ORDER BY pg.committed_at,pg.task_id,pg.page_no LIMIT GREATEST(1,LEAST(p_limit,8))
 LOOP
  BEGIN
   PERFORM astra_ingestion_v1.backfill_recheck_page_v2(p.task_id,p.page_no);v_readbacks:=v_readbacks+1;
  EXCEPTION WHEN OTHERS THEN
   v_errors:=v_errors+1;
   IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_audit_v2 a WHERE a.task_id=p.task_id AND a.action='READBACK_FAILURE' AND a.evidence->>'page_no'=p.page_no::text) THEN
    INSERT INTO astra_ingestion_v1.backfill_audit_v2(run_id,task_id,action,evidence) VALUES(p.run_id,p.task_id,'READBACK_FAILURE',jsonb_build_object('page_no',p.page_no,'sqlstate',SQLSTATE,'reason',left(SQLERRM,500)));
   END IF;
  END;
 END LOOP;
 FOR r IN SELECT id FROM astra_ingestion_v1.backfill_runs_v2 WHERE status IN ('ACTIVE','PARTIAL_OPERATIONAL_FAILURE','BLOCKED_EXTERNAL') LOOP
  v_result:=astra_ingestion_v1.backfill_try_finalize_v2(r.id);v_final:=v_final||jsonb_build_array(jsonb_build_object('run_id',r.id,'result',v_result));
 END LOOP;
 RETURN jsonb_build_object('state','OBSERVED','verified_pages',v_readbacks,'readback_errors',v_errors,'runs',v_final);
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_delivery_dispatch_v2(p_operation text,p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE v_result jsonb; v_verified jsonb; v_finalize jsonb;
BEGIN
 IF p_operation='backfill_delivery_status' THEN RETURN astra_ingestion_v1.backfill_delivery_status_v2(p_payload->>'run_id');
 ELSIF p_operation='backfill_status' THEN
  RETURN astra_ingestion_v1.backfill_dispatch_v2(p_operation,p_payload)||jsonb_build_object('delivery',astra_ingestion_v1.backfill_delivery_status_v2(p_payload->>'run_id'));
 ELSIF p_operation='backfill_finalize' THEN RETURN astra_ingestion_v1.backfill_try_finalize_v2(p_payload->>'run_id');
 ELSIF p_operation='backfill_recover' THEN RETURN astra_ingestion_v1.backfill_recover_v2(p_payload);
 ELSIF p_operation='backfill_maintain' THEN RETURN astra_ingestion_v1.backfill_maintain_v2(COALESCE((p_payload->>'limit')::integer,2));
 ELSIF p_operation='backfill_plan_snapshot' THEN RETURN astra_ingestion_v1.backfill_plan_snapshot_v2(p_payload->>'run_id',COALESCE((p_payload->>'limit')::integer,500));
 ELSIF p_operation='backfill_seal_plan' THEN RETURN astra_ingestion_v1.backfill_seal_plan_v2(p_payload->>'run_id',(p_payload->>'expected_task_count')::bigint,p_payload->>'expected_plan_sha256',p_payload->'workflow_plan');
 ELSIF p_operation='backfill_verify' THEN
  v_result:=astra_ingestion_v1.backfill_dispatch_v2(p_operation,p_payload);
  IF v_result->>'state'='committed' THEN
   v_verified:=astra_ingestion_v1.backfill_recheck_page_v2(v_result->>'task_id',(v_result->>'page_no')::integer);
   v_finalize:=astra_ingestion_v1.backfill_try_finalize_v2(p_payload#>>'{claim,run_id}');
   IF p_payload->'include_raw'='false'::jsonb THEN v_result:=v_result-'raw_body'; END IF;
   RETURN v_result||jsonb_build_object('verification',v_verified,'run_disposition',v_finalize);
  END IF;
  RETURN v_result;
 END IF;
 RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Unsupported delivery operation';
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_task_definition_sha256_v2(t astra_ingestion_v1.backfill_tasks_v2) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path='' AS $$
 SELECT encode(sha256(convert_to(astra_ingestion_v1.rpc_canonical(jsonb_build_object('id',t.id,'run_id',t.run_id,'family',t.family,'provider',t.provider,'kind',t.kind,'scope',t.scope,'dependencies',to_jsonb(t.dependencies))),'UTF8')),'hex')
$$;

CREATE FUNCTION astra_ingestion_v1.backfill_snapshot_task_v2(p_task_id text) RETURNS boolean
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2; v_start date; v_end date; v_period daterange; v_member text; v_family text;
 v_added integer; v_map jsonb; v_map_hash text; v_map_valid boolean;
BEGIN
 SELECT * INTO STRICT t FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=p_task_id;
 IF (t.kind='alpaca_option_bars' AND t.scope ? 'enumeration_parent') OR t.scope ? 'reuse_parent' THEN RETURN false; END IF;
 IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_plan_units_v2 WHERE task_id=t.id) THEN RETURN false; END IF;
 v_start:=astra_ingestion_v1.backfill_date_v2(t.scope->>'target_start');v_end:=astra_ingestion_v1.backfill_date_v2(t.scope->>'target_end');
 IF v_start IS NOT NULL AND v_end IS NOT NULL AND v_start<=v_end AND t.scope->>'market_timezone'='America/New_York'
  AND GREATEST(v_start,'2025-09-01'::date)<=LEAST(v_end,'2026-07-31'::date) THEN
  v_period:=daterange(GREATEST(v_start,'2025-09-01'::date),LEAST(v_end,'2026-07-31'::date)+1,'[)');
 END IF;
 IF t.family='CTX06' THEN
  v_map:=t.scope->'representative_security';v_map_valid:=false;
  IF jsonb_typeof(v_map)='object' THEN
   v_map_hash:=encode(sha256(convert_to(astra_ingestion_v1.rpc_canonical(v_map),'UTF8')),'hex');
   SELECT count(*)=3000 AND bool_and(m.member_id IS NOT NULL AND jsonb_typeof(x.value)='object' AND length(COALESCE(x.value->>'symbol',''))>0
    AND (NOT x.value ? 'eligible' OR jsonb_typeof(x.value->'eligible') IN ('boolean','null'))) INTO v_map_valid
    FROM jsonb_each(v_map) x LEFT JOIN astra_ingestion_v1.backfill_members_v2 m ON m.run_id=t.run_id AND m.member_id=x.key;
  END IF;
 END IF;
 INSERT INTO astra_ingestion_v1.backfill_plan_units_v2(run_id,task_id,family,definition_sha256,target_period,representative_map_sha256,representative_map_valid)
 VALUES(t.run_id,t.id,t.family,astra_ingestion_v1.backfill_task_definition_sha256_v2(t),v_period,v_map_hash,v_map_valid) ON CONFLICT(task_id) DO NOTHING;
 GET DIAGNOSTICS v_added=ROW_COUNT;
 IF v_added=0 THEN RETURN false; END IF;
 FOR v_family IN SELECT t.family UNION ALL SELECT 'P02' WHERE t.family='P01' AND t.kind IN ('alpaca_stock_bars','retained_reuse') LOOP
  FOR v_member IN SELECT jsonb_array_elements_text(COALESCE(t.scope->'member_ids','[]')) WHERE t.family NOT IN ('REF03','CTX06')
   UNION ALL SELECT '__COHORT__' WHERE t.family='CTX06'
  LOOP
   INSERT INTO astra_ingestion_v1.backfill_plan_coverage_v2(run_id,family,member_id,covered_dates,task_count)
   VALUES(t.run_id,v_family,v_member,CASE WHEN v_period IS NULL THEN '{}'::datemultirange ELSE datemultirange(v_period) END,1)
   ON CONFLICT(run_id,family,member_id) DO UPDATE SET covered_dates=astra_ingestion_v1.backfill_plan_coverage_v2.covered_dates+EXCLUDED.covered_dates,task_count=astra_ingestion_v1.backfill_plan_coverage_v2.task_count+1;
  END LOOP;
 END LOOP;
 RETURN true;
END $$;
CREATE FUNCTION astra_ingestion_v1.backfill_snapshot_insert_v2() RETURNS trigger
LANGUAGE plpgsql SET search_path='' AS $$ BEGIN PERFORM astra_ingestion_v1.backfill_snapshot_task_v2(NEW.id);RETURN NEW;END $$;
CREATE TRIGGER backfill_static_plan_snapshot_v2 AFTER INSERT ON astra_ingestion_v1.backfill_tasks_v2
 FOR EACH ROW EXECUTE FUNCTION astra_ingestion_v1.backfill_snapshot_insert_v2();

CREATE FUNCTION astra_ingestion_v1.backfill_plan_snapshot_v2(p_run_id text,p_limit integer DEFAULT 500) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE t record; v_count integer:=0;
BEGIN
 FOR t IN SELECT q.id FROM astra_ingestion_v1.backfill_tasks_v2 q WHERE q.run_id=p_run_id
  AND NOT ((q.kind='alpaca_option_bars' AND q.scope ? 'enumeration_parent') OR q.scope ? 'reuse_parent')
  AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_plan_units_v2 p WHERE p.task_id=q.id)
  ORDER BY q.id LIMIT GREATEST(1,LEAST(p_limit,500))
 LOOP IF astra_ingestion_v1.backfill_snapshot_task_v2(t.id) THEN v_count:=v_count+1;END IF;END LOOP;
 RETURN jsonb_build_object('snapshotted',v_count,'more',EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 q WHERE q.run_id=p_run_id
  AND NOT ((q.kind='alpaca_option_bars' AND q.scope ? 'enumeration_parent') OR q.scope ? 'reuse_parent')
  AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_plan_units_v2 p WHERE p.task_id=q.id)));
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_plan_coverage_check_v2(p_run_id text,p_trading datemultirange,p_calendar datemultirange) RETURNS jsonb
LANGUAGE sql STABLE SET search_path='' AS $$
 SELECT jsonb_build_object('missing_member_date_workflows',COALESCE(jsonb_agg(z),'[]')) FROM (
  SELECT f.family,m.member_id,
   (CASE WHEN f.family IN ('P01','P02','D01','D02','D03','D04','D05','S01') THEN p_trading ELSE p_calendar END-COALESCE(c.covered_dates,'{}'::datemultirange))::text missing_dates
  FROM astra_ingestion_v1.backfill_family_catalogue_v2 f CROSS JOIN astra_ingestion_v1.backfill_members_v2 m
  LEFT JOIN astra_ingestion_v1.backfill_plan_coverage_v2 c ON c.run_id=m.run_id AND c.member_id=m.member_id AND c.family=f.family
  WHERE m.run_id=p_run_id AND f.family NOT IN ('REF03','CTX06')
   AND NOT COALESCE(c.covered_dates,'{}'::datemultirange) @> CASE WHEN f.family IN ('P01','P02','D01','D02','D03','D04','D05','S01') THEN p_trading ELSE p_calendar END
  UNION ALL SELECT 'CTX06','__COHORT__',(p_trading-COALESCE(c.covered_dates,'{}'::datemultirange))::text
   FROM (SELECT 1) x LEFT JOIN astra_ingestion_v1.backfill_plan_coverage_v2 c ON c.run_id=p_run_id AND c.family='CTX06' AND c.member_id='__COHORT__'
   WHERE NOT COALESCE(c.covered_dates,'{}'::datemultirange) @> p_trading
  LIMIT 100
 ) z
$$;

CREATE FUNCTION astra_ingestion_v1.backfill_seal_plan_v2(p_run_id text,p_expected_count bigint,p_expected_sha256 text,p_workflow_plan jsonb) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE r astra_ingestion_v1.backfill_runs_v2; v_count bigint; v_hash text; v_trading datemultirange; v_calendar datemultirange; v_missing jsonb;
BEGIN
 SELECT * INTO STRICT r FROM astra_ingestion_v1.backfill_runs_v2 WHERE id=p_run_id FOR UPDATE;
 IF r.status<>'ACTIVE' OR EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_plan_manifests_v2 WHERE run_id=r.id) THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Only an active unsealed replacement plan may be sealed'; END IF;
 IF jsonb_typeof(p_workflow_plan) IS DISTINCT FROM 'object' OR length(COALESCE(p_workflow_plan->>'version',''))=0
  OR p_workflow_plan->>'target_start' IS DISTINCT FROM '2025-09-01' OR p_workflow_plan->>'target_end' IS DISTINCT FROM '2026-07-31'
  OR p_workflow_plan->>'market_timezone' IS DISTINCT FROM 'America/New_York' OR length(COALESCE(p_workflow_plan->>'representative_policy',''))=0
  OR jsonb_typeof(p_workflow_plan->'session_dates') IS DISTINCT FROM 'array' THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Plan sealing requires explicit fixed-window, calendar and representative policy evidence'; END IF;
 SELECT range_agg(daterange(d,d+1,'[)')) INTO v_trading FROM (SELECT DISTINCT value::date d FROM jsonb_array_elements_text(p_workflow_plan->'session_dates')) x;
 IF (SELECT count(DISTINCT value) FROM jsonb_array_elements_text(p_workflow_plan->'session_dates'))<>230
  OR (SELECT encode(sha256(convert_to(string_agg(value,E'\n' ORDER BY value),'UTF8')),'hex') FROM (SELECT DISTINCT value FROM jsonb_array_elements_text(p_workflow_plan->'session_dates')) s)
     <>'acb2972a35b3458a6a41dfeaca34abea14cd0c228183b9dca602cb59deb0d9d6'
  OR EXISTS(SELECT 1 FROM jsonb_array_elements_text(p_workflow_plan->'session_dates') d WHERE d::date<r.target_start OR d::date>r.target_end) THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Frozen target exchange calendar must contain the retained 230 sessions'; END IF;
 v_calendar:=datemultirange(daterange(r.target_start,r.target_end+1,'[)'));
 IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 q WHERE q.run_id=r.id
  AND NOT ((q.kind='alpaca_option_bars' AND q.scope ? 'enumeration_parent') OR q.scope ? 'reuse_parent')
  AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_plan_units_v2 p WHERE p.task_id=q.id)) THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Static task snapshots are incomplete; continue bounded backfill_plan_snapshot'; END IF;
 SELECT count(*),encode(sha256(convert_to(COALESCE(string_agg(task_id||':'||definition_sha256,E'\n' ORDER BY task_id COLLATE "C"),''),'UTF8')),'hex')
 INTO v_count,v_hash FROM astra_ingestion_v1.backfill_plan_units_v2 WHERE run_id=r.id;
 IF v_count IS DISTINCT FROM p_expected_count OR v_hash IS DISTINCT FROM p_expected_sha256 THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Stored task count/hash differs from the expected complete workflow manifest'; END IF;
 v_missing:=astra_ingestion_v1.backfill_plan_coverage_check_v2(r.id,v_trading,v_calendar);
 IF jsonb_array_length(v_missing->'missing_member_date_workflows')>0 THEN
  RETURN jsonb_build_object('state','INCOMPLETE_MEMBER_DATE_WORKFLOWS','evidence',v_missing); END IF;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_plan_units_v2 WHERE run_id=r.id AND family='CTX06')
  OR EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_plan_units_v2 WHERE run_id=r.id AND family='CTX06' AND representative_map_valid IS DISTINCT FROM true) THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Every breadth unit needs an explicit representative map for the exact 3000 frozen companies'; END IF;
 INSERT INTO astra_ingestion_v1.backfill_plan_manifests_v2(run_id,expected_task_count,expected_plan_sha256,workflow_plan,required_trading_dates,required_calendar_dates)
 VALUES(r.id,v_count,v_hash,p_workflow_plan,v_trading,v_calendar);
 UPDATE astra_ingestion_v1.backfill_runs_v2 SET metadata=metadata||jsonb_build_object('planning_complete',true,'expected_static_task_count',v_count,'expected_plan_sha256',v_hash,'workflow_plan',p_workflow_plan) WHERE id=r.id;
 INSERT INTO astra_ingestion_v1.backfill_audit_v2(run_id,action,evidence) VALUES(r.id,'FULL_PLAN_SEALED',jsonb_build_object('expected_task_count',v_count,'expected_plan_sha256',v_hash,'cohort_sha256',r.cohort_sha256));
 RETURN jsonb_build_object('state','FULL_PLAN_SEALED','expected_task_count',v_count,'expected_plan_sha256',v_hash);
END $$;

-- Strip provider default grants, including identity sequences, before exposing
-- only the existing capability owner and its narrow monitored operation.
DO $acl$
DECLARE o record; g record; f record; t text;
BEGIN
 FOR o IN SELECT c.oid,c.relname,c.relkind,c.relowner,c.relacl FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname='astra_ingestion_v1' AND (c.relname IN ('backfill_family_catalogue_v2','backfill_readbacks_v2','backfill_audit_v2','backfill_plan_units_v2','backfill_plan_coverage_v2','backfill_plan_manifests_v2','backfill_exceptions_v2_id_seq','backfill_audit_v2_id_seq')
    OR c.relname='backfill_source_records_v2' OR c.relname LIKE 'backfill_family_%_v2') AND c.relkind IN ('r','v','S')
 LOOP
  EXECUTE format('REVOKE ALL ON %s astra_ingestion_v1.%I FROM PUBLIC',CASE WHEN o.relkind='S' THEN 'SEQUENCE' ELSE 'TABLE' END,o.relname);
  FOR g IN SELECT DISTINCT r.rolname FROM aclexplode(o.relacl) a JOIN pg_roles r ON r.oid=a.grantee WHERE a.grantee<>o.relowner LOOP
   EXECUTE format('REVOKE ALL ON %s astra_ingestion_v1.%I FROM %I',CASE WHEN o.relkind='S' THEN 'SEQUENCE' ELSE 'TABLE' END,o.relname,g.rolname);
  END LOOP;
  IF o.relkind='r' THEN
   EXECUTE format('ALTER TABLE astra_ingestion_v1.%I ENABLE ROW LEVEL SECURITY',o.relname);
   EXECUTE format('CREATE POLICY backfill_delivery_read ON astra_ingestion_v1.%I FOR SELECT TO astra_ingestion_rpc_owner_v1 USING(true)',o.relname);
  END IF;
  EXECUTE format('GRANT %s ON %s astra_ingestion_v1.%I TO astra_ingestion_rpc_owner_v1',CASE WHEN o.relkind='S' THEN 'USAGE' ELSE 'SELECT' END,CASE WHEN o.relkind='S' THEN 'SEQUENCE' ELSE 'TABLE' END,o.relname);
 END LOOP;
 FOREACH t IN ARRAY ARRAY['backfill_readbacks_v2','backfill_audit_v2','backfill_plan_units_v2','backfill_plan_coverage_v2','backfill_plan_manifests_v2'] LOOP
  EXECUTE format('GRANT INSERT ON astra_ingestion_v1.%I TO astra_ingestion_rpc_owner_v1',t);
  EXECUTE format('CREATE POLICY backfill_delivery_insert ON astra_ingestion_v1.%I FOR INSERT TO astra_ingestion_rpc_owner_v1 WITH CHECK(true)',t);
 END LOOP;
 GRANT UPDATE ON astra_ingestion_v1.backfill_plan_coverage_v2 TO astra_ingestion_rpc_owner_v1;
 CREATE POLICY backfill_delivery_update ON astra_ingestion_v1.backfill_plan_coverage_v2 FOR UPDATE TO astra_ingestion_rpc_owner_v1 USING(true) WITH CHECK(true);
 FOR f IN SELECT p.oid,p.proname,p.proowner,p.proacl,pg_get_function_identity_arguments(p.oid) args FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname='astra_ingestion_v1' AND p.proname IN ('backfill_stamp_v2','backfill_date_v2','backfill_bar_usable_v2','backfill_page_rows_v2','backfill_recheck_page_v2','backfill_delivery_status_v2','backfill_try_finalize_v2','backfill_recover_v2','backfill_maintain_v2','backfill_delivery_dispatch_v2','backfill_task_definition_sha256_v2','backfill_snapshot_task_v2','backfill_snapshot_insert_v2','backfill_plan_snapshot_v2','backfill_plan_coverage_check_v2','backfill_seal_plan_v2')
 LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION astra_ingestion_v1.%I(%s) FROM PUBLIC',f.proname,f.args);
  FOR g IN SELECT DISTINCT r.rolname FROM aclexplode(f.proacl) a JOIN pg_roles r ON r.oid=a.grantee WHERE a.grantee<>f.proowner LOOP
   EXECUTE format('REVOKE ALL ON FUNCTION astra_ingestion_v1.%I(%s) FROM %I',f.proname,f.args,g.rolname);
  END LOOP;
  EXECUTE format('GRANT EXECUTE ON FUNCTION astra_ingestion_v1.%I(%s) TO astra_ingestion_rpc_owner_v1',f.proname,f.args);
 END LOOP;
END $acl$;
GRANT CREATE ON SCHEMA astra_ingestion_v1 TO astra_ingestion_rpc_owner_v1;
ALTER FUNCTION astra_ingestion_v1.backfill_maintain_v2(integer) OWNER TO astra_ingestion_rpc_owner_v1;
REVOKE CREATE ON SCHEMA astra_ingestion_v1 FROM astra_ingestion_rpc_owner_v1;

DO $wire$
DECLARE d text; m text;
BEGIN
 SELECT pg_get_functiondef('astra_ingestion_v1.rpc_dispatch(text,jsonb)'::regprocedure) INTO STRICT d;
 IF strpos(d,'backfill_runtime_dispatch_v2')=0 OR strpos(d,'backfill_delivery_dispatch_hook_v2')>0 THEN RAISE EXCEPTION 'Unexpected dispatcher version for delivery extension'; END IF;
 IF strpos(d,$api$p_operation IN ('list_jobs','get_job','submit_job','control_job','backfill_status')$api$)=0
  OR strpos(d,$worker$'backfill_material','backfill_work'$worker$)=0 THEN RAISE EXCEPTION 'Capability allowlists changed; reconcile delivery extension'; END IF;
 d:=replace(d,$api$p_operation IN ('list_jobs','get_job','submit_job','control_job','backfill_status')$api$,$api2$p_operation IN ('list_jobs','get_job','submit_job','control_job','backfill_status','backfill_delivery_status')$api2$);
 d:=replace(d,$worker$'backfill_material','backfill_work'$worker$,$worker2$'backfill_material','backfill_work','backfill_delivery_status','backfill_finalize','backfill_recover','backfill_maintain','backfill_plan_snapshot','backfill_seal_plan'$worker2$);
 d:=replace(d,$before$    IF p_operation LIKE 'backfill_%' THEN$before$,$hook$
    -- backfill_delivery_dispatch_hook_v2: same capability guard and transaction lock.
    IF p_operation IN ('backfill_status','backfill_verify','backfill_delivery_status','backfill_finalize','backfill_recover','backfill_maintain','backfill_plan_snapshot','backfill_seal_plan') THEN
      RETURN jsonb_build_object('ok',true,'result',astra_ingestion_v1.backfill_delivery_dispatch_v2(p_operation,p_payload));
    END IF;
    IF p_operation LIKE 'backfill_%' THEN$hook$);
 EXECUTE d;
 -- Add one bounded operation to the already scheduled observer. Its role can
 -- invoke this helper, but obtains no unrestricted data mutation capability.
 IF to_regprocedure('astra_ingestion_v1.monitor_tick_v1()') IS NOT NULL THEN
  SELECT pg_get_functiondef('astra_ingestion_v1.monitor_tick_v1()'::regprocedure) INTO STRICT m;
  IF strpos(m,'backfill_delivery_monitor_hook_v2')=0 THEN
   IF strpos(m,'  SELECT COALESCE(next_request_at,0) INTO v_not_before')=0 THEN RAISE EXCEPTION 'Monitor source changed; reconcile before hooking'; END IF;
   m:=replace(m,'  SELECT COALESCE(next_request_at,0) INTO v_not_before',$monitor$
  -- backfill_delivery_monitor_hook_v2: bounded immutable readback and finalization.
  PERFORM astra_ingestion_v1.backfill_maintain_v2(2);
  SELECT COALESCE(next_request_at,0) INTO v_not_before$monitor$);
   EXECUTE m;
   GRANT EXECUTE ON FUNCTION astra_ingestion_v1.backfill_maintain_v2(integer) TO astra_ingestion_monitor_owner_v1;
  END IF;
 END IF;
END $wire$;
COMMIT;
