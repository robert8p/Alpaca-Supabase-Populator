-- Reuse the original, hash-verified compact D01 cache without copying its arrays.
-- This is an optional fast path on existing derive_intraday tasks. A miss writes nothing.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);

DO $admission$
BEGIN
 IF to_regprocedure('astra_ingestion_v1.backfill_reuse_commit_v2(jsonb)') IS NULL
 OR to_regprocedure('astra_ingestion_v1.backfill_feature_reuse_commit_v2(jsonb)') IS NOT NULL
 OR to_regclass('astra_shared_equity_features_20260928_v1.feature_session_cache_remediated_v1') IS NULL THEN
  RAISE EXCEPTION 'Feature reuse baseline differs or is already installed'; END IF;
END $admission$;

CREATE FUNCTION astra_ingestion_v1.backfill_feature_reuse_summary_v2(p_task_id text)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path='' SET TimeZone='UTC' SET statement_timeout='8s' AS $$
DECLARE
 t astra_ingestion_v1.backfill_tasks_v2;
 r astra_ingestion_v1.backfill_runs_v2;
 m astra_ingestion_v1.backfill_members_v2;
 s astra_ingestion_v1.backfill_tasks_v2;
 p astra_ingestion_v1.backfill_pages_v2;
 i reference.alpaca_fixed_window_instruments_v1;
 c astra_shared_equity_features_20260928_v1.feature_session_cache_remediated_v1;
 v_day date; v_calendar jsonb; v_open timestamptz; v_close timestamptz;
 v_sources text[]; v_identity bytea; v_identity_anchor text; v_result jsonb;
 v_raw_count int; v_profile_count int; v_usable_count int; v_aligned_count int;
 v_source_hash bytea; v_profile_hash text; v_minutes smallint[]; v_jobs jsonb;
 v_output_hash bytea; v_builder_hash text; v_grid_hash text; v_hash_function_hash text;
 v_miss jsonb:=jsonb_build_object('state','CACHE_NOT_REUSABLE','new_market_rows_written',0);
BEGIN
 SELECT * INTO t FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=p_task_id;
 IF NOT FOUND OR t.kind<>'derive_intraday' OR t.family<>'D01' OR lower(t.provider)<>'derived' THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='D01 cache requires an immutable intraday derivation'; END IF;
 SELECT * INTO STRICT r FROM astra_ingestion_v1.backfill_runs_v2 WHERE id=t.run_id;
 IF r.cohort_sha256<>'2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
 OR r.target_start<>'2025-09-01'::date OR r.target_end<>'2026-07-31'::date
 OR jsonb_typeof(t.scope->'member_ids') IS DISTINCT FROM 'array'
 OR jsonb_array_length(t.scope->'member_ids')<>1 THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='D01 cache frozen scope differs'; END IF;
 IF t.scope->>'target_start' IS NULL OR t.scope->>'target_end' IS DISTINCT FROM t.scope->>'target_start' THEN
  RETURN v_miss||jsonb_build_object('reason','ONE_TARGET_SESSION_REQUIRED'); END IF;
 v_day:=(t.scope->>'target_start')::date;
 IF v_day<r.target_start OR v_day>r.target_end THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='D01 cache date is outside the frozen target'; END IF;
 SELECT * INTO STRICT m FROM astra_ingestion_v1.backfill_members_v2
  WHERE run_id=t.run_id AND member_id=t.scope#>>'{member_ids,0}';
 SELECT e INTO v_calendar FROM jsonb_array_elements(COALESCE(t.scope->'calendar','[]')) e WHERE e->>'date'=v_day::text;
 IF v_calendar IS NULL OR v_calendar->>'open' IS NULL OR v_calendar->>'close' IS NULL THEN
  RETURN v_miss||jsonb_build_object('reason','ACTUAL_SESSION_CALENDAR_REQUIRED'); END IF;
 v_open:=(v_day+(v_calendar->>'open')::time) AT TIME ZONE 'America/New_York';
 v_close:=(v_day+(v_calendar->>'close')::time) AT TIME ZONE 'America/New_York';
 IF v_close<=v_open OR v_close-v_open>interval '8 hours' THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Invalid D01 exchange session'; END IF;
 SELECT array_agg(z.id ORDER BY z.id) INTO v_sources FROM (
  SELECT q.id FROM astra_ingestion_v1.backfill_tasks_v2 q
  WHERE q.id=ANY(t.dependencies) AND q.run_id=t.run_id AND q.kind='retained_reuse'
   AND lower(q.provider)='reuse' AND q.status IN ('INGESTED','IDENTITY_OR_QUALITY_UNRESOLVED')
   AND q.scope->'member_ids'=t.scope->'member_ids'
   AND (q.scope->>'start')::timestamptz<=v_open AND (q.scope->>'end_exclusive')::timestamptz>=v_close
  LIMIT 2) z;
 IF COALESCE(cardinality(v_sources),0)<>1 THEN
  RETURN v_miss||jsonb_build_object('reason','ONE_COMMITTED_RETAINED_DEPENDENCY_REQUIRED'); END IF;
 SELECT * INTO STRICT s FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=v_sources[1];
 -- Any repair query supersedes this old session, even a genuine empty response.
 IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 gap
   WHERE gap.run_id=t.run_id AND gap.scope ? 'reuse_parent' AND gap.scope->>'reuse_parent'=s.id
    AND EXISTS(SELECT 1 FROM jsonb_array_elements(COALESCE(gap.scope->'calendar','[]')) e WHERE e->>'date'=v_day::text)) THEN
  RETURN v_miss||jsonb_build_object('reason','SESSION_HAS_PROVIDER_REPAIR_CHILD'); END IF;
 SELECT * INTO p FROM astra_ingestion_v1.backfill_pages_v2 WHERE task_id=s.id AND page_no=0;
 IF NOT FOUND OR p.record_count<>1 OR p.raw_body::jsonb#>>'{rows,0,record_type}' IS DISTINCT FROM 'RETAINED_SOURCE_POINTER'
 OR p.body_sha256 IS DISTINCT FROM encode(sha256(convert_to(p.raw_body,'UTF8')),'hex') THEN
  RETURN v_miss||jsonb_build_object('reason','COMMITTED_SOURCE_POINTER_REQUIRED'); END IF;
 SELECT * INTO i FROM reference.alpaca_fixed_window_instruments_v1 WHERE instrument_key=(s.scope->>'instrument_key')::int;
 IF NOT FOUND OR i.alpaca_asset_id::text IS DISTINCT FROM s.scope->>'alpaca_asset_id'
 OR i.symbol IS DISTINCT FROM s.scope->>'symbol' OR i.symbol IS DISTINCT FROM m.anchor_ticker
 OR NOT COALESCE(t.scope->'symbols' @> jsonb_build_array(i.symbol),false) THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='D01 cache provider security and frozen member differ'; END IF;
 SELECT * INTO c FROM astra_shared_equity_features_20260928_v1.feature_session_cache_remediated_v1
  WHERE instrument_key=i.instrument_key AND session_date=v_day;
 IF NOT FOUND THEN RETURN v_miss||jsonb_build_object('reason','CACHE_ROW_ABSENT'); END IF;
 SELECT h.identity_contract_sha256,h.identity_anchor INTO v_identity,v_identity_anchor
 FROM astra_shared_equity_features_20260928_v1.shared_identity_contract_remediated_v1 h
 WHERE h.instrument_key=i.instrument_key AND h.session_date=v_day;
 IF v_identity IS NULL OR v_identity IS DISTINCT FROM c.identity_contract_sha256 THEN
  RETURN v_miss||jsonb_build_object('reason','IDENTITY_CONTRACT_HASH_MISMATCH'); END IF;
 IF c.regular_open IS DISTINCT FROM v_open OR c.regular_close IS DISTINCT FROM v_close
 OR c.expected_grid_rows IS DISTINCT FROM (extract(epoch FROM v_close-v_open)/60)::integer
 OR COALESCE(c.aligned_source_rows,0)<1 OR cardinality(c.minute_indices) IS DISTINCT FROM c.aligned_source_rows
 OR cardinality(c.validity_codes) IS DISTINCT FROM c.aligned_source_rows
 OR cardinality(c.dependency_source_observed_at) IS DISTINCT FROM c.aligned_source_rows
 OR array_ndims(c.coefficient_values) IS DISTINCT FROM 2 OR array_length(c.coefficient_values,1) IS DISTINCT FROM c.aligned_source_rows
 OR array_length(c.coefficient_values,2) IS DISTINCT FROM 17 THEN
  RETURN v_miss||jsonb_build_object('reason','CACHE_ARRAY_OR_SESSION_SHAPE_MISMATCH'); END IF;
 SELECT encode(sha256(convert_to(pg_get_functiondef('astra_shared_equity_features_20260928_v1.compute_feature_sessions_remediated_v1(integer,integer,date,date,boolean)'::regprocedure),'UTF8')),'hex'),
  encode(sha256(convert_to(pg_get_functiondef('astra_shared_equity_features_20260928_v1.feature_grid_remediated_v1(integer,date,timestamptz,boolean)'::regprocedure),'UTF8')),'hex'),
  encode(sha256(convert_to(pg_get_functiondef('astra_shared_equity_features_20260928_v1.compact_output_hash_remediated_v1(bytea,bytea,smallint[],smallint[],timestamptz[],double precision[],integer,integer,integer,integer)'::regprocedure),'UTF8')),'hex')
 INTO v_builder_hash,v_grid_hash,v_hash_function_hash;
 IF v_builder_hash<>'019b86197174c682febb88a546a0ff956c058347e99b6dc0dbdd430e090fb552'
 OR v_grid_hash<>'5f45e08dce40aa5cc138fa9b5819b25d049bacea574d50ceb2f943d8ff02b251'
 OR v_hash_function_hash<>'3d2af9589f2171964f77ecb2a5739e7417d12775833c0b3c884a61438689dae5' THEN
  RETURN v_miss||jsonb_build_object('reason','RECOVERED_FORMULA_SOURCE_VERSION_CHANGED'); END IF;
 WITH bounded AS MATERIALIZED(
  SELECT b.* FROM market_fixed_20250901_20260831.alpaca_sip_bars_1m b
  WHERE b.instrument_key=i.instrument_key AND b.bar_ts>=v_open AND b.bar_ts<v_close ORDER BY b.bar_ts LIMIT 1001
 ), measured AS MATERIALIZED(
  SELECT b.*,j.config,j.status,
   COALESCE(j.config->>'feed'='sip' AND j.config->>'adjustment'='raw' AND j.config->'timeframes' @> '["1Min"]'::jsonb
    AND (j.config->>'start_date')::date<=v_day AND (j.config->>'end_date')::date>=v_day,false) profile_ok,
   sha256(convert_to(jsonb_build_array(b.instrument_key,b.bar_ts,b.open,b.high,b.low,b.close,b.volume,b.trade_count,b.vwap,b.source_loaded_at,b.loaded_by_job_id)::text,'UTF8')) row_sha256
  FROM bounded b LEFT JOIN market_provenance.alpaca_populator_jobs_v1 j ON j.id=b.loaded_by_job_id
 )
 SELECT count(*),count(*) FILTER(WHERE profile_ok),
  count(*) FILTER(WHERE bar_ts=date_trunc('minute',bar_ts)),
  sha256(COALESCE(string_agg(row_sha256,''::bytea ORDER BY bar_ts),''::bytea)),
  array_agg((extract(epoch FROM bar_ts-v_open)/60)::smallint ORDER BY bar_ts) FILTER(WHERE bar_ts=date_trunc('minute',bar_ts)),
  COALESCE(jsonb_agg(DISTINCT loaded_by_job_id ORDER BY loaded_by_job_id),'[]'),
  encode(sha256(convert_to(COALESCE(jsonb_agg(DISTINCT jsonb_build_object('id',loaded_by_job_id,'config',config,'status',status)
   ORDER BY jsonb_build_object('id',loaded_by_job_id,'config',config,'status',status)),'[]')::text,'UTF8')),'hex')
 INTO v_raw_count,v_profile_count,v_aligned_count,v_source_hash,v_minutes,v_jobs,v_profile_hash FROM measured;
 IF v_raw_count>1000 OR v_raw_count=0 OR v_profile_count<>v_raw_count THEN
  RETURN v_miss||jsonb_build_object('reason','RETAINED_SOURCE_PROFILE_NOT_FULLY_QUALIFIED'); END IF;
 IF v_source_hash IS DISTINCT FROM c.source_rows_sha256 OR v_raw_count<>c.retained_source_rows
 OR v_aligned_count<>c.aligned_source_rows OR v_minutes IS DISTINCT FROM c.minute_indices THEN
  RETURN v_miss||jsonb_build_object('reason','RAW_SOURCE_HASH_OR_GRID_MISMATCH'); END IF;
 v_output_hash:=astra_shared_equity_features_20260928_v1.compact_output_hash_remediated_v1(
  c.source_rows_sha256,c.identity_contract_sha256,c.minute_indices,c.validity_codes,c.dependency_source_observed_at,
  c.coefficient_values,c.retained_source_rows,c.unaligned_source_rows,c.invalid_ohlc_rows,c.invalid_volume_rows);
 IF v_output_hash IS DISTINCT FROM c.output_sha256 THEN
  RETURN v_miss||jsonb_build_object('reason','CACHE_OUTPUT_HASH_MISMATCH'); END IF;
 SELECT count(*) FILTER(WHERE (flags&1)=1 AND (flags&2)=2) INTO v_usable_count FROM unnest(c.validity_codes) flags;
 RETURN jsonb_build_object('state','CACHE_REUSABLE','family','D01','task_id',t.id,'run_id',t.run_id,
  'member_id',m.member_id,'symbol',i.symbol,'instrument_key',i.instrument_key,'alpaca_asset_id',i.alpaca_asset_id,
  'market_date',v_day,'regular_open',v_open,'regular_close',v_close,
  'source_relation','market_fixed_20250901_20260831.alpaca_sip_bars_1m',
  'cache_relation','astra_shared_equity_features_20260928_v1.feature_session_cache_remediated_v1',
  'formula_version','compact_intraday_float64_v1','formula_builder_sha256',v_builder_hash,
  'formula_grid_sha256',v_grid_hash,'formula_hash_function_sha256',v_hash_function_hash,
  'source_digest',encode(v_source_hash,'hex'),'source_digest_algorithm','sha256-ordered-binary-sha256-jsonb-array-source-rows-v1',
  'identity_contract_sha256',encode(v_identity,'hex'),'output_sha256',encode(v_output_hash,'hex'),
  'source_profile_sha256',v_profile_hash,'source_job_ids',v_jobs,'cache_built_at',c.built_at,
  'source_task_id',s.id,'source_page_no',p.page_no,'source_pointer_sha256',p.body_sha256,
  'source_rows',v_raw_count,'reused_feature_rows',c.expected_grid_rows,'qualifying_feature_rows',v_aligned_count,
  'usable_feature_rows',v_usable_count,'missing_scheduled_rows',c.expected_grid_rows-v_aligned_count,
  'unaligned_source_rows',c.unaligned_source_rows,'invalid_ohlc_rows',c.invalid_ohlc_rows,'invalid_volume_rows',c.invalid_volume_rows,
  'coefficient_count',17,'coefficient_order',jsonb_build_array('return_1m','return_5m','return_10m','return_20m','return_60m','return_120m',
   'realized_vol_5m','realized_vol_20m','realized_vol_60m','range_20m_pct','volume_mean_20m','volume_sd_20m',
   'dollar_volume_mean_20m','sma_close_5m','sma_close_20m','sma_close_60m','session_vwap_proxy'),
  'covered_feature_categories',jsonb_build_array('provider_interval','availability_assumed_ts','ohlcv','dollar_volume','rolling_returns',
   'realized_volatility','candle_geometry','rolling_range_20m','volume_relative_20m','dollar_volume_mean_20m','sma_close',
   'session_vwap_proxy','trend_primitives','session_position','liquidity_quality','quality_flags'),
  'unavailable_feature_categories',jsonb_build_array('microstructure_primitives','scenario10_frozen_factor_inputs'),
  'mapping_state','IDENTITY_OR_QUALITY_UNRESOLVED','mapping_reason','POST_WINDOW_ANCHOR_SYMBOL_MATCH_IS_NOT_HISTORICAL_IDENTITY_PROOF',
  'retained_identity_anchor',v_identity_anchor,'original_historical_receipt_recovered',false,
  'expected_bar_slots_are_not_a_trade_denominator',true,'new_market_rows_written',0);
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_feature_reuse_commit_v2(p_payload jsonb)
RETURNS jsonb LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE t astra_ingestion_v1.backfill_tasks_v2; p astra_ingestion_v1.backfill_pages_v2;
 s jsonb; pointer jsonb; raw text; committed jsonb;
BEGIN
 SELECT * INTO p FROM astra_ingestion_v1.backfill_pages_v2
  WHERE task_id=p_payload#>>'{claim,id}' AND page_no=(p_payload#>>'{claim,page_no}')::int;
 IF FOUND THEN
  IF p.run_id IS DISTINCT FROM p_payload#>>'{claim,run_id}' OR p.generation::text IS DISTINCT FROM p_payload#>>'{claim,generation}'
  OR p.run_fence::text IS DISTINCT FROM p_payload#>>'{claim,run_fence}'
  OR p.raw_body::jsonb#>>'{rows,0,record_type}' IS DISTINCT FROM 'DERIVED_RETAINED_SOURCE_POINTER' THEN
   RAISE EXCEPTION USING ERRCODE='AI001',MESSAGE='Feature pointer acknowledgement differs from claim'; END IF;
  RETURN jsonb_build_object('state','already_committed','task_id',p.task_id,'page_no',p.page_no,
   'body_sha256',p.body_sha256,'record_count',p.record_count,'reused_feature_rows',p.raw_body::jsonb->'reused_feature_rows');
 END IF;
 t:=astra_ingestion_v1.backfill_owned_v2(p_payload->'claim');
 s:=astra_ingestion_v1.backfill_feature_reuse_summary_v2(t.id);
 IF s->>'state'<>'CACHE_REUSABLE' THEN RETURN s; END IF;
 pointer:=(s-'state')||jsonb_build_object('record_type','DERIVED_RETAINED_SOURCE_POINTER');
 raw:=astra_ingestion_v1.rpc_canonical(jsonb_build_object('rows',jsonb_build_array(pointer),
  'reused_feature_rows',s->'reused_feature_rows','formula_version',s->'formula_version','receipt_kind','DERIVED_RETAINED_SOURCE_POINTER'));
 committed:=astra_ingestion_v1.backfill_dispatch_v2('backfill_commit',jsonb_build_object('claim',p_payload->'claim',
  'raw_body',raw,'body_sha256',encode(sha256(convert_to(raw,'UTF8')),'hex'),'http_status',200,'request_id',NULL,
  'fetched_at',clock_timestamp(),'request',jsonb_build_object('provider','DERIVED','method','VERIFIED_RETAINED_CACHE',
    'formula_version',s->'formula_version','source_task_id',s->'source_task_id','source_digest',s->'source_digest'),
  'records',jsonb_build_array(pointer),'next_cursor',NULL,'terminal_state','IDENTITY_OR_QUALITY_UNRESOLVED',
  'quality',jsonb_build_array(jsonb_build_object('state','IDENTITY_OR_QUALITY_UNRESOLVED','reason',s->>'mapping_reason',
    'scope','company_attribution','original_formula_version_preserved',true),
    jsonb_build_object('state','IDENTITY_OR_QUALITY_UNRESOLVED','reason','OPTIONAL_RESEARCH_OR_MICROSTRUCTURE_INPUTS_NOT_REUSED',
    'fields',s->'unavailable_feature_categories','scope','affected_derived_field_only')),
  'headers','{}'::jsonb,'adapter_version','fixed3000-compact-intraday-pointer-v2.1'));
 RETURN committed||jsonb_build_object('reused_feature_rows',s->'reused_feature_rows','qualifying_feature_rows',s->'qualifying_feature_rows',
  'usable_feature_rows',s->'usable_feature_rows','formula_version',s->'formula_version','new_market_rows_written',0);
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_feature_reuse_verify_v2(p_task_id text,p_page_no integer)
RETURNS jsonb LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path='' SET TimeZone='UTC' SET statement_timeout='8s' AS $$
DECLARE p astra_ingestion_v1.backfill_pages_v2; t astra_ingestion_v1.backfill_tasks_v2;
 pointer jsonb; actual jsonb; mismatches jsonb:='[]'; k text;
BEGIN
 SELECT * INTO p FROM astra_ingestion_v1.backfill_pages_v2 WHERE task_id=p_task_id AND page_no=p_page_no;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='AI004',MESSAGE='Committed feature pointer absent'; END IF;
 SELECT * INTO STRICT t FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=p.task_id;
 IF t.run_id<>p.run_id OR t.status NOT IN ('INGESTED','IDENTITY_OR_QUALITY_UNRESOLVED') OR t.page_no<=p.page_no
 OR t.kind<>'derive_intraday' OR t.family<>'D01' OR lower(t.provider)<>'derived'
 OR p.record_count<>1 OR p.cursor_out IS NOT NULL OR p.body_sha256 IS DISTINCT FROM encode(sha256(convert_to(p.raw_body,'UTF8')),'hex') THEN
  RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Committed feature pointer envelope differs'; END IF;
 PERFORM astra_ingestion_v1.rpc_json_unique(p.raw_body::json);
 IF jsonb_typeof(p.raw_body::jsonb->'rows') IS DISTINCT FROM 'array' OR jsonb_array_length(p.raw_body::jsonb->'rows')<>1
 OR p.records_sha256 IS DISTINCT FROM encode(sha256(convert_to(astra_ingestion_v1.rpc_canonical(p.raw_body::jsonb->'rows'),'UTF8')),'hex') THEN
  RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Committed feature pointer record digest differs'; END IF;
 pointer:=p.raw_body::jsonb#>'{rows,0}';
 IF pointer->>'record_type' IS DISTINCT FROM 'DERIVED_RETAINED_SOURCE_POINTER'
 OR pointer->'reused_feature_rows' IS DISTINCT FROM p.raw_body::jsonb->'reused_feature_rows'
 OR pointer->'formula_version' IS DISTINCT FROM p.raw_body::jsonb->'formula_version' THEN
  RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Committed feature pointer identity differs'; END IF;
 actual:=astra_ingestion_v1.backfill_feature_reuse_summary_v2(t.id);
 IF actual->>'state' IS DISTINCT FROM 'CACHE_REUSABLE' THEN
  RETURN actual||jsonb_build_object('passed',false,'state','FEATURE_REUSE_SOURCE_MISMATCH','receipt_record_count',1,
   'reused_feature_rows',0,'qualifying_feature_rows',0,'usable_feature_rows',0,
   'mismatched_fields',jsonb_build_array(actual->>'reason'),'pointer_body_sha256',p.body_sha256); END IF;
 FOR k IN SELECT jsonb_object_keys(actual-'state') LOOP
  IF actual->k IS DISTINCT FROM pointer->k THEN mismatches:=mismatches||jsonb_build_array(k); END IF;
 END LOOP;
 RETURN (actual-'state')||jsonb_build_object('passed',jsonb_array_length(mismatches)=0,
  'state',CASE WHEN jsonb_array_length(mismatches)=0 THEN 'FEATURE_REUSE_SOURCE_VERIFIED' ELSE 'FEATURE_REUSE_SOURCE_MISMATCH' END,
  'receipt_record_count',1,'mismatched_fields',mismatches,'pointer_body_sha256',p.body_sha256,
  'verification_kind','COMMITTED_COMPACT_FEATURE_SOURCE_READBACK_V1');
END $$;

-- Bounded material view over the original source/cache. No arrays or market rows
-- are persisted again. Unsupported optional microstructure is explicitly null.
CREATE FUNCTION astra_ingestion_v1.backfill_feature_reuse_values_v2(p_task_id text,p_page_no integer)
RETURNS TABLE(record jsonb) LANGUAGE plpgsql STABLE SECURITY DEFINER
SET search_path='' SET TimeZone='UTC' SET statement_timeout='8s' AS $$
DECLARE verified jsonb;
BEGIN
 verified:=astra_ingestion_v1.backfill_feature_reuse_verify_v2(p_task_id,p_page_no);
 IF verified->>'passed' IS DISTINCT FROM 'true' THEN RETURN; END IF;
 RETURN QUERY SELECT jsonb_build_object('member_id',verified->'member_id','symbol',verified->'symbol',
  'market_date',g.session_date,'timestamp',g.provider_interval_start,'formula_version','compact_intraday_float64_v1',
  'input_count',CASE WHEN g.bar_present THEN 1 ELSE 0 END,'support_history',false,
  'values',(to_jsonb(g)-ARRAY['session_date','provider','instrument_id','provider_symbol','source_feed','quality_flags',
    'instrument_key','alpaca_asset_id','identity_anchor','currency_code','dependency_source_observed_at',
    'identity_recorded_at','built_at','micro_version_recorded_at','research_eligible','live_eligible','formula_version',
    'archive_value_identity_eligible'])||
    jsonb_build_object('microstructure_available',false,'micro_trade_count',NULL,'micro_quote_count',NULL,
      'micro_avg_spread_bps',NULL,'micro_last_spread_bps',NULL,'micro_trade_imbalance',NULL,'micro_quote_size_imbalance',NULL,'microprice_dislocation_bps',NULL,
      'availability_policy','ARCHIVED_FINAL_BAR_PLUS_ONE_SECOND_PROXY_NOT_OBSERVED_RECEIPT'),
  'quality_flags',(g.quality_flags-ARRAY['identity_eligible','research_eligible','live_eligible','historical_use_mode'])||jsonb_build_object('identity_status','UNRESOLVED_PROVIDER_ANCHOR',
    'cache_source_verified',true,'original_formula_version_preserved',true,'microstructure_available',false),
  'retained_cache_quality_flags',g.quality_flags,
  'null_reasons',jsonb_build_object('microstructure_primitives','OUTSIDE_QUALIFIED_SOURCE_SCOPE',
    'scenario10_frozen_factor_inputs','RESEARCH_ONLY_COMPONENT_PRESERVED_NOT_RECOMPUTED')||
    COALESCE((SELECT jsonb_object_agg(k,CASE WHEN k LIKE 'micro%' THEN 'OUTSIDE_QUALIFIED_SOURCE_SCOPE'
      WHEN k LIKE 'return_%' OR k LIKE 'realized_vol_%' OR k LIKE 'sma_%' OR k IN ('volume_mean_20m','volume_rel_20m','volume_z_20m','dollar_volume_mean_20m','range_20m_pct','coverage_20m')
       THEN 'INSUFFICIENT_OR_INVALID_CONSECUTIVE_SESSION_INPUTS'
      ELSE 'MISSING_OR_INVALID_RETAINED_INPUT' END)
     FROM jsonb_each(to_jsonb(g)) j(k,val) WHERE val='null'::jsonb AND k NOT IN ('provider_symbol','instrument_id','identity_anchor','identity_recorded_at','micro_version_recorded_at')),'{}'::jsonb),
  'source_lineage',jsonb_build_object('task_id',p_task_id,'page_no',p_page_no,'source_digest',verified->'source_digest',
    'output_sha256',verified->'output_sha256','identity_contract_sha256',verified->'identity_contract_sha256'))
 FROM astra_shared_equity_features_20260928_v1.feature_grid_remediated_v1(
   (verified->>'instrument_key')::int,(verified->>'market_date')::date,NULL,false) g;
END $$;

CREATE VIEW astra_ingestion_v1.backfill_retained_feature_values_v2 WITH(security_invoker=true) AS
 SELECT p.run_id,p.task_id,p.page_no,t.scope#>>'{member_ids,0}' AS member_id,
  (t.scope->>'target_start')::date AS market_date,v.record
 FROM astra_ingestion_v1.backfill_pages_v2 p JOIN astra_ingestion_v1.backfill_tasks_v2 t ON t.id=p.task_id AND t.run_id=p.run_id
 CROSS JOIN LATERAL astra_ingestion_v1.backfill_feature_reuse_values_v2(p.task_id,p.page_no) v
 WHERE t.kind='derive_intraday' AND t.family='D01'
  AND p.raw_body::jsonb#>>'{rows,0,record_type}'='DERIVED_RETAINED_SOURCE_POINTER';

-- One physical pointer represents a full scheduled feature grid. Independent
-- readback verifies the original cache before publishing separate logical counts.
ALTER TABLE astra_ingestion_v1.backfill_readbacks_v2
 ADD COLUMN reused_feature_records integer NOT NULL DEFAULT 0,
 ADD COLUMN qualified_feature_records integer NOT NULL DEFAULT 0,
 ADD COLUMN usable_feature_records integer NOT NULL DEFAULT 0,
 ADD COLUMN retained_feature_verification jsonb;

DO $delivery$
DECLARE d text; v text; v_target text;
BEGIN
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_recheck_page_v2(text,integer)'::regprocedure) INTO STRICT d;
 IF strpos(d,'v_reuse jsonb; v_sessions record;')=0 OR strpos(d,'retained_source_verification)')=0
  OR strpos(d,'v_reuse)')=0 THEN RAISE EXCEPTION 'Feature readback baseline differs'; END IF;
 d:=replace(d,'v_reuse jsonb; v_sessions record;','v_reuse jsonb; v_sessions record; v_feature jsonb;');
 d:=replace(d,' IF lower(p.provider)=''reuse'' THEN',$feature$
 IF p.raw_body::jsonb#>>'{rows,0,record_type}'='DERIVED_RETAINED_SOURCE_POINTER' THEN
  v_feature:=astra_ingestion_v1.backfill_feature_reuse_verify_v2(p.task_id,p.page_no);
  IF v_feature->'passed' IS DISTINCT FROM 'true'::jsonb THEN
   RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Retained feature source readback differs'; END IF;
  v_counts.target:=(v_feature->>'reused_feature_rows')::int;
  v_counts.support:=0;v_counts.unknown_date:=0;
 END IF;
 IF lower(p.provider)='reuse' THEN$feature$);
 d:=replace(d,'retained_source_verification)',
  'retained_source_verification,reused_feature_records,qualified_feature_records,usable_feature_records,retained_feature_verification)');
 d:=replace(d,'v_reuse)',
  'v_reuse,COALESCE((v_feature->>''reused_feature_rows'')::int,0),COALESCE((v_feature->>''qualifying_feature_rows'')::int,0),COALESCE((v_feature->>''usable_feature_rows'')::int,0),v_feature)');
 EXECUTE d;
 -- pg_get_viewdef normalizes CASE syntax. Preserve independently installed
 -- minute-overlap accounting and add only the D01 result branch.
 v_target:=CASE WHEN to_regclass('astra_ingestion_v1.backfill_family_receipt_status_v2') IS NOT NULL
   THEN 'astra_ingestion_v1.backfill_family_receipt_status_v2' ELSE 'astra_ingestion_v1.backfill_family_status_v2' END;
 SELECT pg_get_viewdef(v_target::regclass,true) INTO STRICT v;
 IF strpos(v,'ELSE p.record_count')=0 THEN RAISE EXCEPTION 'Feature accounting branch differs'; END IF;
 v:=replace(v,'ELSE p.record_count',
  'WHEN t.delivery_family = ''D01'' AND COALESCE(v.reused_feature_records,0)>0 THEN v.reused_feature_records ELSE p.record_count');
 v:=replace(v,'sum(v.reused_records)','sum(CASE WHEN t.delivery_family=''D01'' THEN v.reused_feature_records ELSE v.reused_records END)');
 v:=replace(v,'sum(v.reused_qualified_records)','sum(CASE WHEN t.delivery_family=''D01'' THEN v.qualified_feature_records ELSE v.reused_qualified_records END)');
 v:=replace(v,'sum(v.reused_usable_records)','sum(CASE WHEN t.delivery_family=''D01'' THEN v.usable_feature_records ELSE v.reused_usable_records END)');
 EXECUTE 'CREATE OR REPLACE VIEW '||v_target||' WITH(security_invoker=true) AS '||v;
END $delivery$;

-- Keep the stable per-family destination: expand a verified pointer into actual
-- feature rows and never expose that pointer as if it were a minute observation.
CREATE OR REPLACE VIEW astra_ingestion_v1.backfill_family_d01_v2 WITH(security_invoker=true) AS
 SELECT * FROM astra_ingestion_v1.backfill_source_records_v2
 WHERE family='D01' AND source_row->>'record_type' IS DISTINCT FROM 'DERIVED_RETAINED_SOURCE_POINTER'
 UNION ALL
 SELECT p.run_id,'D01'::text,t.kind,t.provider,t.id,p.page_no,
  row_number() OVER(PARTITION BY p.task_id,p.page_no ORDER BY v.record->>'timestamp'),
  t.scope->'member_ids',v.record->>'symbol',(v.record->>'market_date')::date,'RTH'::text,true,
  'UNRESOLVED_PROVIDER_ANCHOR'::text,'raw'::text,'derived_retained_cache'::text,v.record,
  p.body_sha256,p.fetched_at,p.committed_at,p.quality,
  jsonb_build_object('task_id',p.task_id,'page_no',p.page_no,'body_sha256',p.body_sha256,
    'formula_version','compact_intraday_float64_v1','source_digest',v.record#>'{source_lineage,source_digest}',
    'output_sha256',v.record#>'{source_lineage,output_sha256}')
 FROM astra_ingestion_v1.backfill_pages_v2 p JOIN astra_ingestion_v1.backfill_tasks_v2 t ON t.id=p.task_id AND t.run_id=p.run_id
 CROSS JOIN LATERAL astra_ingestion_v1.backfill_feature_reuse_values_v2(p.task_id,p.page_no) v
 WHERE t.kind='derive_intraday' AND t.family='D01'
  AND p.raw_body::jsonb#>>'{rows,0,record_type}'='DERIVED_RETAINED_SOURCE_POINTER';

DO $acl$
DECLARE g record; f regprocedure;
BEGIN
 FOR f IN SELECT p.oid::regprocedure FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
  WHERE n.nspname='astra_ingestion_v1' AND p.proname IN ('backfill_feature_reuse_summary_v2','backfill_feature_reuse_commit_v2',
   'backfill_feature_reuse_verify_v2','backfill_feature_reuse_values_v2') LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION %s FROM PUBLIC',f);
  FOR g IN SELECT DISTINCT r.rolname FROM pg_proc p CROSS JOIN LATERAL aclexplode(p.proacl) a JOIN pg_roles r ON r.oid=a.grantee
   WHERE p.oid=f AND a.grantee<>p.proowner LOOP EXECUTE format('REVOKE ALL ON FUNCTION %s FROM %I',f,g.rolname); END LOOP;
  EXECUTE format('GRANT EXECUTE ON FUNCTION %s TO astra_ingestion_rpc_owner_v1',f);
 END LOOP;
 REVOKE ALL ON astra_ingestion_v1.backfill_retained_feature_values_v2 FROM PUBLIC;
 FOR g IN SELECT DISTINCT r.rolname FROM pg_class c CROSS JOIN LATERAL aclexplode(c.relacl) a JOIN pg_roles r ON r.oid=a.grantee
  WHERE c.oid='astra_ingestion_v1.backfill_retained_feature_values_v2'::regclass AND a.grantee<>c.relowner LOOP
  EXECUTE format('REVOKE ALL ON astra_ingestion_v1.backfill_retained_feature_values_v2 FROM %I',g.rolname); END LOOP;
 GRANT SELECT ON astra_ingestion_v1.backfill_retained_feature_values_v2 TO astra_ingestion_rpc_owner_v1;
END $acl$;

DO $wire$
DECLARE d text; b text; marker text:='''backfill_reuse_read''';
BEGIN
 SELECT pg_get_functiondef('astra_ingestion_v1.rpc_dispatch(text,jsonb)'::regprocedure) INTO STRICT d;
 IF strpos(d,'backfill_feature_reuse_commit')>0 OR (length(d)-length(replace(d,marker,'')))/length(marker)<>1 THEN
  RAISE EXCEPTION 'Feature reuse worker allowlist differs'; END IF;
 d:=replace(d,marker,marker||',''backfill_feature_reuse_commit'',''backfill_feature_reuse_verify'''); EXECUTE d;
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure) INTO STRICT b;
 IF strpos(b,'IF p_operation=''backfill_reuse_read'' THEN')=0 THEN RAISE EXCEPTION 'Feature reuse dispatch baseline differs'; END IF;
 b:=replace(b,'IF p_operation=''backfill_reuse_read'' THEN',
  'IF p_operation=''backfill_feature_reuse_commit'' THEN RETURN astra_ingestion_v1.backfill_feature_reuse_commit_v2(p_payload); END IF;'||chr(10)||
  ' IF p_operation=''backfill_feature_reuse_verify'' THEN RETURN astra_ingestion_v1.backfill_feature_reuse_verify_v2(p_payload->>''task_id'',(p_payload->>''page_no'')::int); END IF;'||chr(10)||
  ' IF p_operation=''backfill_reuse_read'' THEN'); EXECUTE b;
END $wire$;
COMMIT;
