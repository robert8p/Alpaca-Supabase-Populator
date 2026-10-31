-- Source observations, physical receipts and selected derived output are
-- different units. Project each verified page once; reports never parse raw
-- archives or multiply raw/split input series into daily output counts.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);
DO $preflight$ BEGIN
 IF to_regclass('astra_ingestion_v1.backfill_identity_output_validity_v2') IS NULL THEN
  RAISE EXCEPTION 'Progressive identity output-validity view must be installed first'; END IF;
END $preflight$;

CREATE TABLE astra_ingestion_v1.backfill_nonminute_pages_v2 (
 task_id text NOT NULL,page_no integer NOT NULL,run_id text NOT NULL,family text NOT NULL,
 kind text NOT NULL,provider text NOT NULL,observation_role text NOT NULL CHECK(observation_role IN('SOURCE','DERIVED','POINTER')),
 source_variant text NOT NULL,body_sha256 text NOT NULL,physical_records bigint NOT NULL,
 target_records bigint NOT NULL,support_records bigint NOT NULL,after_target_records bigint NOT NULL,unknown_date_records bigint NOT NULL,
 target_first_date date,target_last_date date,support_first_date date,support_last_date date,after_target_first_date date,after_target_last_date date,
 page_has_quality_findings boolean NOT NULL,field_counts jsonb NOT NULL CHECK(jsonb_typeof(field_counts)='array'),
 projected_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(task_id,page_no),FOREIGN KEY(task_id,page_no) REFERENCES astra_ingestion_v1.backfill_readbacks_v2(task_id,page_no),
 CHECK(physical_records=target_records+support_records+after_target_records+unknown_date_records)
);
CREATE INDEX backfill_nonminute_pages_run_v2 ON astra_ingestion_v1.backfill_nonminute_pages_v2(run_id,family,task_id,page_no);
CREATE TRIGGER backfill_nonminute_projection_immutable_v2 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.backfill_nonminute_pages_v2
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.backfill_evidence_guard_v2();
CREATE TABLE astra_ingestion_v1.backfill_nonminute_projection_cursor_v2 (
 singleton boolean PRIMARY KEY DEFAULT true CHECK(singleton),verified_at timestamptz NOT NULL,
 task_id text NOT NULL,page_no integer NOT NULL
);
INSERT INTO astra_ingestion_v1.backfill_nonminute_projection_cursor_v2 VALUES(true,'-infinity','',-1);
CREATE INDEX backfill_readback_projection_order_v2 ON astra_ingestion_v1.backfill_readbacks_v2(verified_at,task_id,page_no);

-- Types describe value-level validation, never identity or point-in-time
-- certification. Missing catalogue fields remain visible even when the entire
-- provider page or derived row omitted that field.
CREATE FUNCTION astra_ingestion_v1.backfill_nonminute_field_spec_v2(p_family text,p_kind text) RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path='' AS $$
 SELECT CASE
 WHEN p_kind='derive_daily' AND p_family='D02' THEN '{"raw_close":"positive","raw_volume":"nonnegative","dollar_volume":"nonnegative","adjusted_close":"positive","adjusted_volume":"nonnegative","source_code":"meta_text","daily_basis":"meta_text","adjustment_basis":"meta_text","availability":"meta_text","coverage_flags":"meta_object"}'::jsonb
 WHEN p_kind='derive_daily' AND p_family='D03' THEN '{"raw_ret_1d":"number","raw_ret_5d":"number","raw_ret_20d":"number","raw_ret_60d":"number","adjusted_ret_1d":"number","adjusted_ret_5d":"number","adjusted_ret_20d":"number","adjusted_ret_60d":"number","provider_split_ret_1d":"number","provider_split_ret_5d":"number","provider_split_ret_20d":"number","provider_split_ret_60d":"number"}'::jsonb
 WHEN p_kind='derive_daily' AND p_family='D04' THEN '{"realized_log_vol_20d":"nonnegative","relative_volume_20d":"nonnegative","volume_z20":"number","input_coverage":"meta_object","raw_realized_log_vol_20d":"nonnegative","raw_relative_volume_20d":"nonnegative","raw_volume_z20":"number"}'::jsonb
 WHEN p_kind='derive_daily' AND p_family='D05' THEN '{"daily_amihud":"nonnegative","amihud_mean_20d":"nonnegative","raw_daily_amihud":"nonnegative","raw_amihud_mean_20d":"nonnegative","valid_window_count":"nonnegative","units":"meta_text"}'::jsonb
 WHEN p_kind='derive_breadth' THEN '{"cohort_id":"meta_text","company_aggregation_rule":"meta_text","cohort_company_count":"nonnegative","eligible_company_count":"nonnegative","excluded_company_count":"nonnegative","eligibility_unknown_company_count":"nonnegative","valid_company_count":"nonnegative","observed_company_count":"nonnegative","missing_company_count":"nonnegative","quality_unresolved_representatives":"nonnegative","advancing":"nonnegative","declining":"nonnegative","unchanged":"nonnegative","coverage":"number","pct_advancing":"number","advance_decline_ratio":"nonnegative","equal_weight_ret_1d":"number","median_ret_1d":"number","dispersion_ret_1d":"nonnegative","raw_valid_company_count":"nonnegative","raw_advancing":"nonnegative","raw_declining":"nonnegative","raw_unchanged":"nonnegative"}'::jsonb
 WHEN p_kind IN('alpaca_stock_bars','alpaca_option_bars') THEN '{"t":"timestamp","o":"positive","h":"positive","l":"positive","c":"positive","v":"nonnegative","n":"nonnegative","vw":"positive"}'::jsonb
 WHEN p_kind='alpaca_reference' THEN '{"id":"text","symbol":"text","class":"text","exchange":"text","status":"text"}'::jsonb
 WHEN p_kind='massive_reference' THEN '{"ticker":"text","cik":"text","composite_figi":"text","share_class_figi":"text","primary_exchange":"text","type":"text","currency_name":"text","list_date":"date"}'::jsonb
 WHEN p_kind='alpaca_news' THEN '{"id":"identifier","headline":"text","created_at":"timestamp","updated_at":"timestamp","symbols":"array","content":"text","url":"text","author":"text"}'::jsonb
 WHEN p_kind='massive_news' THEN '{"id":"identifier","title":"text","published_utc":"timestamp","tickers":"array","description":"text","article_url":"text","author":"text"}'::jsonb
 WHEN p_kind='alpaca_actions' THEN '{"id":"identifier","symbol":"text","process_date":"date"}'::jsonb
 WHEN p_kind='massive_dividends' THEN '{"ticker":"text","cash_amount":"nonnegative","declaration_date":"date","ex_dividend_date":"date","record_date":"date","pay_date":"date","currency":"text"}'::jsonb
 WHEN p_kind='massive_splits' THEN '{"ticker":"text","execution_date":"date","split_from":"positive","split_to":"positive"}'::jsonb
 WHEN p_kind='massive_short_volume' THEN '{"ticker":"text","date":"date","total_volume":"nonnegative","short_volume":"nonnegative","exempt_volume":"nonnegative","non_exempt_volume":"nonnegative","short_volume_ratio":"nonnegative"}'::jsonb
 WHEN p_kind='massive_short_interest' THEN '{"ticker":"text","settlement_date":"date","short_interest":"nonnegative","avg_daily_volume":"nonnegative","days_to_cover":"nonnegative","publication_time":"timestamp"}'::jsonb
 WHEN p_kind='alpaca_option_contracts' THEN '{"id":"identifier","symbol":"text","underlying_symbol":"text","expiration_date":"date","strike_price":"positive","type":"text","status":"text"}'::jsonb
 ELSE '{}'::jsonb END
$$;

CREATE FUNCTION astra_ingestion_v1.backfill_nonminute_field_value_v2(p_row jsonb,p_role text,p_field text) RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path='' AS $$
 SELECT CASE WHEN p_role='DERIVED' THEN CASE WHEN p_field='coverage_flags' THEN p_row->'quality_flags' ELSE p_row->'values'->p_field END
  WHEN p_field='publication_time' THEN COALESCE(NULLIF(p_row->'published_at','null'::jsonb),p_row->'publication_date')
  ELSE p_row->p_field END
$$;

CREATE FUNCTION astra_ingestion_v1.backfill_nonminute_field_reason_v2(v jsonb,p_type text,p_reason text) RETURNS text
LANGUAGE plpgsql IMMUTABLE SET search_path='' AS $$
DECLARE n double precision; typ text:=replace(p_type,'meta_',''); s text:=v#>>'{}';
BEGIN
 IF NULLIF(p_reason,'') IS NOT NULL THEN RETURN p_reason; END IF;
 IF v IS NULL THEN RETURN 'FIELD_NOT_RETURNED'; END IF;
 IF v='null'::jsonb THEN RETURN 'NULL_WITHOUT_RECORDED_REASON'; END IF;
 IF typ IN('number','positive','nonnegative') THEN
  IF jsonb_typeof(v) NOT IN('number','string') OR length(s)>100 OR s !~ '^[+-]?([0-9]+([.][0-9]*)?|[.][0-9]+)([eE][+-]?[0-9]+)?$' THEN RETURN 'INVALID_NUMERIC_VALUE'; END IF;
  n:=s::double precision;
  IF n IN('Infinity'::double precision,'-Infinity'::double precision,'NaN'::double precision) OR (typ='positive' AND n<=0) OR (typ='nonnegative' AND n<0) THEN RETURN 'INVALID_NUMERIC_VALUE'; END IF;
 ELSIF typ='timestamp' THEN IF astra_ingestion_v1.backfill_stamp_v2(s) IS NULL THEN RETURN 'INVALID_OR_UNQUALIFIED_TIMESTAMP'; END IF;
 ELSIF typ='date' THEN IF astra_ingestion_v1.backfill_date_v2(s) IS NULL THEN RETURN 'INVALID_DATE'; END IF;
 ELSIF typ='text' THEN IF jsonb_typeof(v)<>'string' OR btrim(s)='' THEN RETURN 'EMPTY_OR_INVALID_TEXT'; END IF;
 ELSIF typ='identifier' THEN IF jsonb_typeof(v) NOT IN('number','string') OR btrim(s)='' THEN RETURN 'EMPTY_OR_INVALID_IDENTIFIER'; END IF;
 ELSIF typ IN('object','array') THEN IF jsonb_typeof(v)<>typ THEN RETURN 'INVALID_STRUCTURE'; END IF;
 ELSE RETURN 'UNDECLARED_FIELD_VALIDATION'; END IF;
 RETURN NULL;
EXCEPTION WHEN invalid_text_representation OR numeric_value_out_of_range THEN RETURN 'INVALID_NUMERIC_VALUE';
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_nonminute_project_page_v2(p_task_id text,p_page_no integer) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' SET statement_timeout='8s' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2;p astra_ingestion_v1.backfill_pages_v2;
 role text;variant text;spec jsonb; v_inserted integer;
BEGIN
 SELECT * INTO STRICT t FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=p_task_id;
 IF t.family IN('P01','P02','D01','REF03') THEN RETURN jsonb_build_object('state','SEPARATE_MINUTE_OR_AUDIT_ACCOUNTING'); END IF;
 IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_nonminute_pages_v2 WHERE task_id=t.id AND page_no=p_page_no) THEN RETURN jsonb_build_object('state','ALREADY_PROJECTED'); END IF;
 SELECT pg.* INTO p FROM astra_ingestion_v1.backfill_pages_v2 pg JOIN astra_ingestion_v1.backfill_readbacks_v2 b USING(task_id,page_no)
  WHERE pg.task_id=t.id AND pg.page_no=p_page_no AND pg.body_sha256=b.body_sha256 AND b.body_sha256=b.readback_sha256 AND pg.record_count=b.actual_records;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Non-minute projection requires independently verified immutable page evidence'; END IF;
 role:=CASE WHEN lower(t.provider)='reuse' OR p.raw_body::jsonb#>>'{rows,0,record_type}' IN('RETAINED_REFERENCE_SOURCE_POINTER','DERIVED_RETAINED_SOURCE_POINTER','RETAINED_SOURCE_POINTER') THEN 'POINTER'
  WHEN lower(t.provider)='derived' THEN 'DERIVED' ELSE 'SOURCE' END;
 variant:=CASE WHEN t.kind='alpaca_stock_bars' AND t.scope->>'timeframe'='1Day' THEN 'ALPACA_1DAY_'||upper(COALESCE(t.scope->>'adjustment','raw'))
  WHEN role='DERIVED' THEN t.family||'_DERIVED_OUTPUT' ELSE t.kind END;
 spec:=CASE WHEN role='POINTER' THEN '{}'::jsonb ELSE astra_ingestion_v1.backfill_nonminute_field_spec_v2(t.family,t.kind) END;
 WITH rows AS MATERIALIZED(
  SELECT x.source_row,COALESCE(x.market_date,CASE WHEN t.kind='massive_reference' THEN astra_ingestion_v1.backfill_date_v2(t.scope->>'asof') END) d
  FROM astra_ingestion_v1.backfill_page_rows_v2(t.id,p_page_no) x
 ), dated AS MATERIALIZED(
  SELECT *,CASE WHEN d BETWEEN '2025-09-01'::date AND '2026-07-31'::date THEN 'TARGET'
   WHEN d<'2025-09-01'::date THEN 'SUPPORT' WHEN d>'2026-07-31'::date THEN 'AFTER_TARGET' ELSE 'UNKNOWN_DATE' END period FROM rows
 ), fields AS MATERIALIZED(
  SELECT d.period,f.key field,f.value datatype,v.value,
   astra_ingestion_v1.backfill_nonminute_field_reason_v2(v.value,f.value,
    COALESCE(d.source_row#>>ARRAY['null_reasons',f.key],
     CASE WHEN f.key='publication_time' AND (v.value IS NULL OR v.value='null'::jsonb) THEN 'PUBLICATION_TIMESTAMP_NOT_SUPPLIED'
      WHEN f.key='eligible_company_count' AND (v.value IS NULL OR v.value='null'::jsonb) THEN 'ELIGIBLE_COMPANY_DENOMINATOR_UNKNOWN' END)) reason
  FROM dated d CROSS JOIN jsonb_each_text(spec) f
  CROSS JOIN LATERAL(SELECT astra_ingestion_v1.backfill_nonminute_field_value_v2(d.source_row,role,f.key) value) v
 ), counts AS(
  SELECT period,field,datatype,(value IS NOT NULL AND value<>'null'::jsonb) nonnull,reason,count(*) n
  FROM fields GROUP BY period,field,datatype,(value IS NOT NULL AND value<>'null'::jsonb),reason
 )
 INSERT INTO astra_ingestion_v1.backfill_nonminute_pages_v2(task_id,page_no,run_id,family,kind,provider,observation_role,source_variant,body_sha256,physical_records,
  target_records,support_records,after_target_records,unknown_date_records,target_first_date,target_last_date,support_first_date,support_last_date,after_target_first_date,after_target_last_date,
  page_has_quality_findings,field_counts)
 SELECT t.id,p_page_no,t.run_id,t.family,t.kind,t.provider,role,variant,p.body_sha256,count(*),
  count(*) FILTER(WHERE period='TARGET'),count(*) FILTER(WHERE period='SUPPORT'),count(*) FILTER(WHERE period='AFTER_TARGET'),count(*) FILTER(WHERE period='UNKNOWN_DATE'),
  min(d) FILTER(WHERE period='TARGET'),max(d) FILTER(WHERE period='TARGET'),min(d) FILTER(WHERE period='SUPPORT'),max(d) FILTER(WHERE period='SUPPORT'),min(d) FILTER(WHERE period='AFTER_TARGET'),max(d) FILTER(WHERE period='AFTER_TARGET'),
  jsonb_array_length(p.quality)>0,
  (SELECT COALESCE(jsonb_agg(jsonb_build_object('period',period,'field',field,'datatype',datatype,'nonnull',nonnull,'reason',reason,'records',n) ORDER BY period,field,reason),'[]') FROM counts)
 FROM dated ON CONFLICT(task_id,page_no) DO NOTHING;
 GET DIAGNOSTICS v_inserted=ROW_COUNT;
 RETURN jsonb_build_object('state','NONMINUTE_PAGE_PROJECTED','task_id',t.id,'page_no',p_page_no,'inserted',v_inserted);
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_nonminute_readback_trigger_v2() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
BEGIN PERFORM astra_ingestion_v1.backfill_nonminute_project_page_v2(NEW.task_id,NEW.page_no);RETURN NEW; END $$;
CREATE TRIGGER backfill_nonminute_readback_v2 AFTER INSERT ON astra_ingestion_v1.backfill_readbacks_v2
 FOR EACH ROW EXECUTE FUNCTION astra_ingestion_v1.backfill_nonminute_readback_trigger_v2();

CREATE FUNCTION astra_ingestion_v1.backfill_nonminute_project_pending_v2(p_limit integer DEFAULT 2) RETURNS integer
LANGUAGE plpgsql VOLATILE SECURITY DEFINER SET search_path='' SET statement_timeout='8s' AS $$
DECLARE c astra_ingestion_v1.backfill_nonminute_projection_cursor_v2;x record;n integer:=0;
BEGIN
 SELECT * INTO STRICT c FROM astra_ingestion_v1.backfill_nonminute_projection_cursor_v2 WHERE singleton FOR UPDATE;
 FOR x IN SELECT verified_at,task_id,page_no FROM astra_ingestion_v1.backfill_readbacks_v2
  WHERE (verified_at,task_id,page_no)>(c.verified_at,c.task_id,c.page_no)
  ORDER BY verified_at,task_id,page_no LIMIT GREATEST(1,LEAST(p_limit,8)) LOOP
  PERFORM astra_ingestion_v1.backfill_nonminute_project_page_v2(x.task_id,x.page_no);
  UPDATE astra_ingestion_v1.backfill_nonminute_projection_cursor_v2 SET verified_at=x.verified_at,task_id=x.task_id,page_no=x.page_no WHERE singleton;
  n:=n+1;
 END LOOP;
 RETURN n;
END $$;

-- Only projected tasks are visited. A partial replacement cannot displace a
-- completed output. identity_refresh_of names the immutable original root.
CREATE VIEW astra_ingestion_v1.backfill_nonminute_task_coverage_v2 WITH(security_invoker=true) AS
 WITH pages AS(
  SELECT task_id,run_id,family,observation_role,count(*) projected_pages,min(page_no) first_page,max(page_no) last_page,
   sum(physical_records) physical_records FROM astra_ingestion_v1.backfill_nonminute_pages_v2 GROUP BY task_id,run_id,family,observation_role
 ) SELECT p.*,t.created_at,COALESCE(t.scope->>'identity_refresh_of',t.id) root_task_id,
  t.scope->>'identity_refresh_of' IS NULL original_revision,
  (t.scope->>'identity_refresh_of' IS NULL OR (root.id IS NOT NULL AND root.scope->>'identity_refresh_of' IS NULL)) revision_link_valid,
  t.status IN('INGESTED','NO_DATA_RETURNED','IDENTITY_OR_QUALITY_UNRESOLVED') AND t.cursor IS NULL
   AND p.first_page=0 AND p.last_page+1=p.projected_pages AND p.projected_pages=t.page_no query_complete,
  i.identity_material_current,COALESCE(i.identity_invalidated,false) identity_invalidated,i.invalidation_reason
 FROM pages p JOIN astra_ingestion_v1.backfill_tasks_v2 t ON t.id=p.task_id AND t.run_id=p.run_id
 LEFT JOIN astra_ingestion_v1.backfill_tasks_v2 root ON root.id=t.scope->>'identity_refresh_of' AND root.run_id=t.run_id AND root.family=t.family AND root.kind=t.kind
 LEFT JOIN astra_ingestion_v1.backfill_identity_output_validity_v2 i ON i.task_id=t.id;

CREATE VIEW astra_ingestion_v1.backfill_nonminute_selected_tasks_v2 WITH(security_invoker=true) AS
 SELECT task_id,run_id,family,root_task_id,query_complete,identity_material_current,identity_invalidated,invalidation_reason
 FROM(
  SELECT c.*,row_number() OVER(PARTITION BY run_id,family,root_task_id ORDER BY query_complete DESC,created_at DESC,task_id DESC) rank
  FROM astra_ingestion_v1.backfill_nonminute_task_coverage_v2 c WHERE observation_role='DERIVED' AND revision_link_valid AND (original_revision OR query_complete)
 ) selected WHERE rank=1;

CREATE VIEW astra_ingestion_v1.backfill_nonminute_effective_pages_v2 WITH(security_invoker=true) AS
 SELECT p.*,c.query_complete,s.root_task_id,s.identity_material_current,
  COALESCE(s.identity_invalidated,false) identity_invalidated,s.invalidation_reason,
  p.observation_role='SOURCE' OR (p.observation_role='DERIVED' AND s.task_id IS NOT NULL) selected_output
 FROM astra_ingestion_v1.backfill_nonminute_pages_v2 p
 JOIN astra_ingestion_v1.backfill_nonminute_task_coverage_v2 c ON c.task_id=p.task_id
 LEFT JOIN astra_ingestion_v1.backfill_nonminute_selected_tasks_v2 s ON s.task_id=p.task_id;

CREATE VIEW astra_ingestion_v1.backfill_nonminute_family_counts_v2 WITH(security_invoker=true) AS
 SELECT run_id,family,count(*) projected_pages,sum(physical_records) physical_receipt_records,
  sum(physical_records) FILTER(WHERE observation_role='SOURCE') source_observation_records,
  sum(physical_records) FILTER(WHERE source_variant='ALPACA_1DAY_RAW') raw_daily_source_records,
  sum(physical_records) FILTER(WHERE source_variant='ALPACA_1DAY_SPLIT') split_daily_source_records,
  sum(physical_records) FILTER(WHERE observation_role='POINTER') physical_pointer_records,
  sum(physical_records) FILTER(WHERE observation_role='DERIVED') all_derived_version_records,
  sum(physical_records) FILTER(WHERE observation_role='DERIVED' AND selected_output) selected_derived_records,
  sum(physical_records) FILTER(WHERE observation_role='DERIVED' AND NOT selected_output) superseded_or_incomplete_revision_records,
  sum(physical_records) FILTER(WHERE selected_output AND identity_invalidated) identity_invalidated_output_records,
  sum(physical_records) FILTER(WHERE selected_output AND (family NOT IN('D02','D03','D04','D05','CTX06') OR observation_role='DERIVED')) logical_output_records,
  sum(target_records) FILTER(WHERE selected_output AND (family NOT IN('D02','D03','D04','D05','CTX06') OR observation_role='DERIVED')) target_records,
  sum(support_records) FILTER(WHERE selected_output AND (family NOT IN('D02','D03','D04','D05','CTX06') OR observation_role='DERIVED')) support_records,
  sum(after_target_records) FILTER(WHERE selected_output AND (family NOT IN('D02','D03','D04','D05','CTX06') OR observation_role='DERIVED')) after_target_records,
  sum(unknown_date_records) FILTER(WHERE selected_output AND (family NOT IN('D02','D03','D04','D05','CTX06') OR observation_role='DERIVED')) unknown_date_records
 FROM astra_ingestion_v1.backfill_nonminute_effective_pages_v2 GROUP BY run_id,family;

CREATE VIEW astra_ingestion_v1.backfill_nonminute_variants_v2 WITH(security_invoker=true) AS
 SELECT run_id,family,observation_role,source_variant,count(*) projected_pages,sum(physical_records) physical_records,
  sum(physical_records) FILTER(WHERE selected_output) selected_records,
  sum(target_records) target_records,sum(support_records) support_records,sum(after_target_records) after_target_records,sum(unknown_date_records) unknown_date_records,
  min(target_first_date) target_first_date,max(target_last_date) target_last_date,min(support_first_date) support_first_date,max(support_last_date) support_last_date,
  min(after_target_first_date) after_target_first_date,max(after_target_last_date) after_target_last_date,
  count(*) FILTER(WHERE page_has_quality_findings) pages_with_quality_findings,
  count(*) FILTER(WHERE NOT query_complete) pages_of_incomplete_queries
 FROM astra_ingestion_v1.backfill_nonminute_effective_pages_v2 GROUP BY run_id,family,observation_role,source_variant;

CREATE VIEW astra_ingestion_v1.backfill_nonminute_field_coverage_v2 WITH(security_invoker=true) AS
 WITH cells AS(
  SELECT p.run_id,p.family,p.observation_role,p.source_variant,f->>'period' period,f->>'field' field,f->>'datatype' datatype,
   (f->>'records')::bigint records,(f->>'nonnull')::boolean nonnull,
   CASE WHEN p.identity_invalidated AND f->>'reason' IS NULL THEN 'CURRENT_IDENTITY_EVIDENCE_CHANGED_RECOMPUTE_PENDING' ELSE f->>'reason' END reason
  FROM astra_ingestion_v1.backfill_nonminute_effective_pages_v2 p CROSS JOIN LATERAL jsonb_array_elements(p.field_counts) f
  WHERE p.selected_output AND p.observation_role IN('SOURCE','DERIVED')
 ), by_reason AS(
  SELECT run_id,family,observation_role,source_variant,period,field,datatype,nonnull,reason,sum(records) records
  FROM cells GROUP BY run_id,family,observation_role,source_variant,period,field,datatype,nonnull,reason
 ), reasons AS(
  SELECT run_id,family,observation_role,source_variant,period,field,reason,sum(records) records
  FROM by_reason WHERE reason IS NOT NULL GROUP BY run_id,family,observation_role,source_variant,period,field,reason
 ) SELECT b.run_id,b.family,b.observation_role,b.source_variant,b.period,b.field,b.datatype,
  CASE WHEN b.datatype LIKE 'meta_%' THEN 'METADATA' ELSE 'DATA' END field_role,
  sum(b.records) observed_field_slots,sum(b.records) FILTER(WHERE b.nonnull) nonnull_values,
  COALESCE(sum(b.records) FILTER(WHERE b.reason IS NULL),0) usable_values,
  COALESCE(sum(b.records) FILTER(WHERE NOT b.nonnull),0) missing_values,
  COALESCE(sum(b.records) FILTER(WHERE b.nonnull AND b.reason IS NOT NULL),0) unusable_present_values,
  (SELECT COALESCE(jsonb_object_agg(r.reason,r.records),'{}') FROM reasons r WHERE (r.run_id,r.family,r.observation_role,r.source_variant,r.period,r.field)=(b.run_id,b.family,b.observation_role,b.source_variant,b.period,b.field)) null_or_unusable_reasons,
  NULL::bigint expected_applicable_field_slots,NULL::numeric coverage_fraction,
  'VALUE_LEVEL_VALIDATION_WITH_RECORDED_NULL_REASONS_NOT_A_UNIVERSAL_COVERAGE_CERTIFICATE'::text usability_basis
 FROM by_reason b GROUP BY b.run_id,b.family,b.observation_role,b.source_variant,b.period,b.field,b.datatype;

-- Detailed selected output remains linked to the unchanged physical receipt.
-- This view is for explicit data queries, never the routine status projection.
CREATE VIEW astra_ingestion_v1.backfill_nonminute_selected_records_v2 WITH(security_invoker=true) AS
 SELECT x.*,p.observation_role,p.source_variant,p.root_task_id,p.query_complete,
  p.identity_material_current,p.identity_invalidated,p.invalidation_reason
 FROM astra_ingestion_v1.backfill_source_records_v2 x JOIN astra_ingestion_v1.backfill_nonminute_effective_pages_v2 p USING(task_id,page_no)
 WHERE p.selected_output AND (x.family NOT IN('D02','D03','D04','D05','CTX06') OR p.observation_role='DERIVED');

-- Preserve the current minute/cache wrapper and its relation OID. The new
-- report adds source/derived detail and corrects overlapping non-minute counts.
DO $report$
DECLARE old_def text;cols text;
BEGIN
 SELECT pg_get_viewdef('astra_ingestion_v1.backfill_family_status_v2'::regclass,true) INTO STRICT old_def;
 SELECT string_agg(CASE
  WHEN a.attname IN('committed_records','dated_target_records','support_records','unknown_date_records') THEN
   format('CASE WHEN old.family NOT IN(''P01'',''P02'',''D01'',''REF03'') THEN COALESCE(n.%I,0)::%s ELSE old.%I END AS %I',
    CASE a.attname WHEN 'committed_records' THEN 'logical_output_records' WHEN 'dated_target_records' THEN 'target_records' ELSE a.attname END,
    format_type(a.atttypid,a.atttypmod),a.attname,a.attname)
  ELSE format('old.%I',a.attname) END,',' ORDER BY a.attnum) INTO cols
 FROM pg_attribute a WHERE a.attrelid='astra_ingestion_v1.backfill_family_status_v2'::regclass AND a.attnum>0 AND NOT a.attisdropped;
 EXECUTE 'CREATE OR REPLACE VIEW astra_ingestion_v1.backfill_family_status_v2 WITH(security_invoker=true) AS WITH old AS ('||rtrim(old_def,';')||'), variants AS ('||
  'SELECT run_id,family,jsonb_agg(to_jsonb(v)-''run_id''-''family'' ORDER BY observation_role,source_variant) entries FROM astra_ingestion_v1.backfill_nonminute_variants_v2 v GROUP BY run_id,family),'||
  'fields AS (SELECT run_id,family,jsonb_agg(to_jsonb(f)-''run_id''-''family'' ORDER BY observation_role,source_variant,period,field) entries FROM astra_ingestion_v1.backfill_nonminute_field_coverage_v2 f GROUP BY run_id,family)'||
  'SELECT '||cols||',CASE WHEN old.family IN(''P01'',''P02'',''D01'',''REF03'') THEN NULL::jsonb ELSE jsonb_build_object('||
  '''version'',''fixed3000-nonminute-coverage-v2.1'',''projected_verified_pages'',COALESCE(n.projected_pages,0),''projection_pending_verified_pages'',GREATEST(0,old.verified_pages-COALESCE(n.projected_pages,0)),'||
  '''physical_receipt_records'',COALESCE(n.physical_receipt_records,0),''source_observation_records'',COALESCE(n.source_observation_records,0),'||
  '''raw_daily_source_records'',COALESCE(n.raw_daily_source_records,0),''split_daily_source_records'',COALESCE(n.split_daily_source_records,0),''physical_pointer_records'',COALESCE(n.physical_pointer_records,0),'||
  '''all_derived_version_records'',COALESCE(n.all_derived_version_records,0),''selected_derived_records'',COALESCE(n.selected_derived_records,0),''superseded_or_incomplete_revision_records'',COALESCE(n.superseded_or_incomplete_revision_records,0),'||
  '''identity_invalidated_output_records'',COALESCE(n.identity_invalidated_output_records,0),''logical_output_records'',COALESCE(n.logical_output_records,0),'||
  '''target_records'',COALESCE(n.target_records,0),''support_records'',COALESCE(n.support_records,0),''after_target_records'',COALESCE(n.after_target_records,0),''unknown_date_records'',COALESCE(n.unknown_date_records,0),'||
  '''expected_applicable_records'',NULL,''coverage_fraction'',NULL,''denominator_state'',''UNKNOWN_APPLICABLE_OBSERVATION_DENOMINATOR'','||
  '''source_count_basis'',''PHYSICAL_PROVIDER_RECORD_OCCURRENCES_NOT_GLOBAL_UNIQUE_EVENTS'',''derived_count_basis'',''ONE_SELECTED_VERIFIED_REVISION_PER_ORIGINAL_TASK_ROOT_NOT_A_GLOBAL_DISTINCT_SECURITY_DATE_CERTIFICATE'','||
  '''counts_additive_across_roles'',false,''field_validation_basis'',''Declared value types and explicit NULL reasons; identity-invalidated versions are blocked. This does not certify historical availability or all research qualification.'','||
  '''variants'',COALESCE(variants.entries,''[]''::jsonb),''fields'',COALESCE(fields.entries,''[]''::jsonb)) END nonminute_coverage'||
  ' FROM old LEFT JOIN astra_ingestion_v1.backfill_nonminute_family_counts_v2 n ON n.run_id=old.run_id AND n.family=old.family'||
  ' LEFT JOIN variants ON variants.run_id=old.run_id AND variants.family=old.family LEFT JOIN fields ON fields.run_id=old.run_id AND fields.family=old.family';
END $report$;

DO $acl$
DECLARE o record;g record;f record;
BEGIN
 FOR o IN SELECT c.oid,c.relname,c.relowner,c.relacl,c.relkind FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE n.nspname='astra_ingestion_v1' AND c.relname LIKE 'backfill_nonminute_%_v2' AND c.relkind IN('r','v') LOOP
  EXECUTE format('REVOKE ALL ON TABLE astra_ingestion_v1.%I FROM PUBLIC',o.relname);
  FOR g IN SELECT DISTINCT r.rolname FROM aclexplode(o.relacl) a JOIN pg_roles r ON r.oid=a.grantee WHERE a.grantee<>o.relowner LOOP
   EXECUTE format('REVOKE ALL ON TABLE astra_ingestion_v1.%I FROM %I',o.relname,g.rolname);END LOOP;
  IF o.relkind='r' THEN EXECUTE format('ALTER TABLE astra_ingestion_v1.%I ENABLE ROW LEVEL SECURITY',o.relname);
   EXECUTE format('CREATE POLICY nonminute_coverage_read_v2 ON astra_ingestion_v1.%I FOR SELECT TO astra_ingestion_rpc_owner_v1 USING(true)',o.relname);END IF;
  EXECUTE format('GRANT SELECT ON TABLE astra_ingestion_v1.%I TO astra_ingestion_rpc_owner_v1',o.relname);
 END LOOP;
 FOR f IN SELECT p.oid,p.proname,p.proowner,p.proacl,pg_get_function_identity_arguments(p.oid) args FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname='astra_ingestion_v1' AND p.proname LIKE 'backfill_nonminute_%_v2' LOOP
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
 IF strpos(d,'backfill_nonminute_project_pending_v2')>0 OR strpos(d,' FOR p IN SELECT pg.task_id')=0 THEN RAISE EXCEPTION 'Non-minute maintenance baseline differs or is already installed'; END IF;
 d:=replace(d,' FOR p IN SELECT pg.task_id',E' PERFORM astra_ingestion_v1.backfill_nonminute_project_pending_v2(2);\n FOR p IN SELECT pg.task_id');
 EXECUTE d;
END $monitor$;
COMMIT;
