-- Full fixed-cohort task admission inside the existing authenticated worker.
-- Cursor advancement and deterministic task insertion are one transaction.
-- This is a bounded planner, not a second executor or a programme deadline.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);

DO $admission$
BEGIN
 IF to_regprocedure('astra_ingestion_v1.backfill_plan_next_v2(jsonb)') IS NOT NULL
 OR to_regprocedure('astra_ingestion_v1.backfill_seal_plan_v2(text,bigint,text,jsonb)') IS NULL
 OR to_regclass('reference.alpaca_fixed_window_instruments_v1') IS NULL THEN
  RAISE EXCEPTION 'Full planner requires retained reference and delivery baseline, and must not be replayed';
 END IF;
END $admission$;

CREATE FUNCTION astra_ingestion_v1.backfill_plan_task_id_v2(p_run text,p_key text) RETURNS text
LANGUAGE sql IMMUTABLE SET search_path='' AS $$
 SELECT 'backfill-plan-'||encode(sha256(convert_to('fixed3000-plan-v2.1:'||p_run||':'||p_key,'UTF8')),'hex')
$$;

CREATE FUNCTION astra_ingestion_v1.backfill_plan_insert_v2(
 p_run text,p_fence bigint,p_key text,p_family text,p_provider text,p_kind text,
 p_scope jsonb,p_dependencies text[] DEFAULT '{}',p_priority int DEFAULT 100) RETURNS integer
LANGUAGE plpgsql VOLATILE SET search_path='' AS $$
DECLARE v_id text:=astra_ingestion_v1.backfill_plan_task_id_v2(p_run,p_key); v_added integer;
 v_scope jsonb:=p_scope||jsonb_build_object('plan_static',true,'planner_version','fixed3000-plan-v2.1');
BEGIN
 INSERT INTO astra_ingestion_v1.backfill_tasks_v2(id,run_id,family,provider,kind,scope,dependencies,priority,run_fence)
 VALUES(v_id,p_run,p_family,p_provider,p_kind,v_scope,p_dependencies,p_priority,p_fence)
 ON CONFLICT(id) DO NOTHING;
 GET DIAGNOSTICS v_added=ROW_COUNT;
 IF v_added=0 AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 t
  WHERE t.id=v_id AND t.run_id=p_run AND t.family=p_family AND t.provider=p_provider
  AND t.kind=p_kind AND t.scope=v_scope AND t.dependencies=p_dependencies) THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Deterministic plan task differs from its retained definition';
 END IF;
 RETURN v_added;
END $$;

CREATE FUNCTION astra_ingestion_v1.backfill_plan_next_v2(p_payload jsonb) RETURNS jsonb
LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path='' SET TimeZone='UTC' SET statement_timeout='8s' SET lock_timeout='1s' AS $planner$
DECLARE
 r astra_ingestion_v1.backfill_runs_v2;
 m astra_ingestion_v1.backfill_members_v2;
 v_run text:=COALESCE(p_payload->>'run_id','fixed3000-20250901-20260731-v1-20261030');
 v_limit int:=GREATEST(1,LEAST(COALESCE((p_payload->>'member_limit')::int,1),5));
 v_next int; v_breadth int; v_phase text; v_added int:=0; v_members int:=0; v_expected bigint;
 v_calendar jsonb; v_month_calendar jsonb; v_target_dates jsonb; v_map jsonb; v_workflow jsonb; v_snapshot jsonb;
 v_scope jsonb; v_base jsonb; v_key text; v_source_id text; v_raw_id text; v_split_id text;
 v_anchor_count int; v_instrument int; v_asset text; v_month date; v_first date; v_last date;
 v_input date; v_entry jsonb; v_day date; v_family text; v_adjustment text; v_status text;
 v_count bigint; v_hash text; v_calendar_hash text; v_fallback boolean;
 v_after int; v_result jsonb; v_supported jsonb:=COALESCE(p_payload->'supported_kinds','[]'::jsonb);
BEGIN
 -- Same transaction lock as the authenticated existing RPC; no lease can be
 -- advanced by a competing planner between its insertions and checkpoint.
 PERFORM pg_advisory_xact_lock(706314020261028);
 SELECT * INTO STRICT r FROM astra_ingestion_v1.backfill_runs_v2 WHERE id=v_run FOR UPDATE;
 IF r.status<>'ACTIVE' THEN RETURN jsonb_build_object('state','PLANNING_PAUSED','run_id',r.id,'run_status',r.status,'plan_complete',false); END IF;
 IF r.metadata->'planning_complete'='true'::jsonb THEN
  RETURN jsonb_build_object('state','FULL_PLAN_SEALED','run_id',r.id,'plan_complete',true,
   'expected_task_count',r.metadata->'expected_static_task_count','expected_plan_sha256',r.metadata->'expected_plan_sha256');
 END IF;
 IF r.cohort_sha256<>'2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
 OR r.cohort_manifest_sha256<>'4134b415e2c26fcde9fced749c0d54ef51376e23f0d2f8c6ce9ef562f9fab99f'
 OR r.target_start<>'2025-09-01'::date OR r.target_end<>'2026-07-31'::date THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Planner accepts only the frozen replacement cohort and dates';
 END IF;
 SELECT count(*),encode(sha256(convert_to(string_agg(member_id,E'\n' ORDER BY selection_order,member_id),'UTF8')),'hex')
 INTO v_count,v_hash FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id=r.id;
 IF v_count<>3000 OR v_hash<>'a83310df6a6465ce8d37ffd5352095f6e38d91a3204afd8807fff39092cfd85e' THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Frozen actual 3000-member list differs; selection cannot be reopened';
 END IF;
 SELECT jsonb_agg(jsonb_build_object('date',e->>'date','open',e->>'open','close',e->>'close') ORDER BY e->>'date')
 INTO v_calendar FROM jsonb_array_elements(r.scope#>'{calendar,sessions}') e;
 v_calendar_hash:=encode(sha256(convert_to(astra_ingestion_v1.rpc_canonical(v_calendar),'UTF8')),'hex');
 IF v_calendar IS NULL OR jsonb_array_length(v_calendar)<>290 OR v_calendar_hash<>'8483822a5553f0d270d87d1ff69c9a30d512d9ea8f660036664aebbf70053d49'
 OR r.scope->>'daily_support_start' IS DISTINCT FROM '2025-06-05'
 OR r.scope->>'intraday_support_start' IS DISTINCT FROM '2025-08-04' THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Exact retained 290-session calendar and support history required';
 END IF;
 SELECT jsonb_agg(e->>'date' ORDER BY e->>'date') INTO v_target_dates FROM jsonb_array_elements(v_calendar) e
 WHERE e->>'date' BETWEEN '2025-09-01' AND '2026-07-31';
 v_workflow:=jsonb_build_object('version','fixed3000-plan-v2.1','target_start','2025-09-01','target_end','2026-07-31',
  'market_timezone','America/New_York','session_dates',v_target_dates,'cohort_classification','RETROSPECTIVE_FIXED_COHORT',
  'representative_policy','ONE_FROZEN_COMPANY_ONE_EXPLICIT_ANCHOR_SECURITY; ELIGIBILITY_UNKNOWN_UNTIL_EVIDENCED',
  'daily_support_start','2025-06-05','intraday_support_start','2025-08-04','calendar_sha256',v_calendar_hash,
  'formula_manifest_sha256','e0b0835ad53ef7b71d072184bbb1576b3cd8f514c523361fa31865f71a0c8a65',
  'families',jsonb_build_array('REF01','REF03','P01','P02','D01','D02','D03','D04','D05','N01','N02','N03','S01','S02','CTX02','CTX06'),
  'REF03',jsonb_build_object('mode','CONTINUOUS_AUDIT','scope','All replacement tasks/pages/exceptions/readbacks/recovery',
   'destination','astra_ingestion_v1.backfill_family_ref03_v2'),
  'P02',jsonb_build_object('mode','SHARED_P01_SOURCE_RETRIEVAL','sessions',jsonb_build_array('PRE','POST')),
  'event_policy','Retain all supplied action dates and boundary events; no ex-date-only archive restriction',
  'news_policy','All calendar dates, prefer Massive; separately retained Alpaca alternative if Massive worker configuration unavailable',
  'short_interest_policy','Settlement-date selection; actual publication/retrieval availability retained separately',
  'options_policy','Active and inactive underlying contracts; expiry Sep2025 through2099; dynamic individual-contract daily pages',
  'programme_expires_at',NULL);
 IF r.metadata->>'planner_version' IS NULL THEN
  v_snapshot:=astra_ingestion_v1.backfill_plan_snapshot_v2(r.id,500);
  IF v_snapshot->'more'='true'::jsonb THEN
   RETURN jsonb_build_object('state','SNAPSHOTTING_EXISTING_TASKS','plan_complete',false,'snapshot',v_snapshot);
  END IF;
  SELECT count(*) INTO v_expected FROM astra_ingestion_v1.backfill_plan_units_v2 WHERE run_id=r.id;
  r.metadata:=r.metadata||jsonb_build_object('planner_version','fixed3000-plan-v2.1','planner_phase','MEMBERS',
   'planner_next_selection_order',1,'planner_next_breadth_index',0,'planner_expected_static_count',v_expected,
   'planner_preexisting_static_count',v_expected,'workflow_plan',v_workflow);
 ELSIF r.metadata->>'planner_version'<>'fixed3000-plan-v2.1' THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Existing planner version differs; retain and explicitly reconcile its checkpoint';
 END IF;
 v_next:=(r.metadata->>'planner_next_selection_order')::int;
 v_breadth:=(r.metadata->>'planner_next_breadth_index')::int;
 v_phase:=r.metadata->>'planner_phase';
 v_expected:=(r.metadata->>'planner_expected_static_count')::bigint;
 IF jsonb_typeof(v_supported)<>'array' THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Worker supported kinds must be an explicit array'; END IF;
 v_fallback:=v_supported ? 'alpaca_news' AND NOT (v_supported ? 'massive_news');

 IF v_phase='MEMBERS' THEN
  FOR m IN SELECT * FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id=r.id AND selection_order>=v_next
   ORDER BY selection_order LIMIT v_limit
  LOOP
   v_base:=jsonb_build_object('member_ids',jsonb_build_array(m.member_id),'symbols',jsonb_build_array(m.anchor_ticker),
    'symbol',m.anchor_ticker,'market_timezone','America/New_York','target_start','2025-09-01','target_end','2026-07-31',
    'identity_status','UNRESOLVED_PROVIDER_ANCHOR','asof','2026-08-03','cohort_classification','RETROSPECTIVE_FIXED_COHORT');
   v_key:=m.member_id||':';
   -- Daily raw/split series are fetched once per member for all required support.
   FOREACH v_adjustment IN ARRAY ARRAY['raw','split'] LOOP
    v_scope:=v_base||jsonb_build_object('timeframe','1Day','feed','sip','adjustment',v_adjustment,
     'start','2025-06-05T04:00:00Z','end','2026-08-01T03:59:59.999999Z','input_start','2025-06-05',
     'calendar',v_calendar,'daily_basis','ALPACA_PROVIDER_DAILY_NOT_ASSERTED_RTH','governing_date','MARKET_DATE',
     'support_history_policy','Observations before2025-09-01 retained as support history');
    v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'daily-source:'||v_adjustment,'D02','Alpaca','alpaca_stock_bars',v_scope,'{}',20);
   END LOOP;
   v_raw_id:=astra_ingestion_v1.backfill_plan_task_id_v2(r.id,v_key||'daily-source:raw');
   v_split_id:=astra_ingestion_v1.backfill_plan_task_id_v2(r.id,v_key||'daily-source:split');
   v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'reference:alpaca','REF01','Alpaca','alpaca_reference',
    v_base||jsonb_build_object('reference_policy','CURRENT_PROVIDER_IDENTIFIERS_NOT_HISTORICAL_PROOF'),'{}',10);
   SELECT count(*),min(instrument_key),min(alpaca_asset_id::text) INTO v_anchor_count,v_instrument,v_asset
    FROM reference.alpaca_fixed_window_instruments_v1 WHERE symbol=m.anchor_ticker AND alpaca_asset_id IS NOT NULL;
   -- Twelve monthly minute-source units cover Aug support plus all11 targetmonths.
   FOR v_month IN SELECT d::date FROM generate_series('2025-08-01'::date,'2026-07-01'::date,interval '1 month') d LOOP
    v_first:=GREATEST(v_month,'2025-08-04'::date);v_last:=(v_month+interval '1 month')::date-1;
    SELECT jsonb_agg(e ORDER BY e->>'date') INTO v_month_calendar FROM jsonb_array_elements(v_calendar) e
     WHERE (e->>'date')::date BETWEEN v_first AND v_last;
    v_scope:=v_base||jsonb_build_object('source_month',v_month::text,'target_start',v_first::text,'target_end',v_last::text,
     'input_start',v_first::text,'calendar',COALESCE(v_month_calendar,'[]'::jsonb),'feed','sip','timeframe','1Min','adjustment','raw',
     'start',to_char(v_first::timestamp AT TIME ZONE 'America/New_York' AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"'),
     'end_exclusive',to_char((v_last+1)::timestamp AT TIME ZONE 'America/New_York' AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"'),
     'support_history',v_last<'2025-09-01'::date,'governing_date','MARKET_SESSION',
     'shared_families',jsonb_build_array('P01','P02'),'identity_mapping_basis','POST_WINDOW_PROVIDER_ANCHOR_ONLY');
    IF v_anchor_count=1 THEN
     v_scope:=v_scope||jsonb_build_object('instrument_key',v_instrument,'alpaca_asset_id',v_asset,
      'reuse_policy','VERIFY_RETAINED_SOURCE_AND_ADMIT_ONLY_MISSING_OR_UNQUALIFIED_RANGES');
     v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'minutes:'||v_month::text,'P01','REUSE','retained_reuse',v_scope,'{}',30);
    ELSE
     v_scope:=v_scope||jsonb_build_object('end',to_char(((v_last+1)::timestamp AT TIME ZONE 'America/New_York')-interval '1 microsecond','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
      'retained_reference_state',CASE WHEN v_anchor_count=0 THEN 'NO_MATCHING_RETAINED_PROVIDER_ANCHOR' ELSE 'AMBIGUOUS_RETAINED_PROVIDER_ANCHOR' END);
     v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'minutes:'||v_month::text,'P01','Alpaca','alpaca_stock_bars',v_scope,'{}',30);
    END IF;
    IF v_month<'2025-09-01'::date THEN CONTINUE; END IF;
    v_source_id:=astra_ingestion_v1.backfill_plan_task_id_v2(r.id,v_key||'minutes:'||v_month::text);
    FOR v_entry IN SELECT e FROM jsonb_array_elements(v_month_calendar) e LOOP
     v_day:=(v_entry->>'date')::date;
     v_scope:=v_base||jsonb_build_object('target_start',v_day::text,'target_end',v_day::text,'input_start',v_day::text,
      'source_month',v_month::text,'calendar',jsonb_build_array(v_entry),'governing_date','MARKET_SESSION',
      'formula_version','fixed3000-derived-v2.1','prefer_retained_formula_cache',true,
      'retained_formula_policy','Preserve original qualifying formula version and lineage when equivalent cache is available');
     v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'D01:'||v_day::text,'D01','DERIVED','derive_intraday',v_scope,ARRAY[v_source_id],160);
    END LOOP;
    -- The last60 actual preceding sessions, plus current month, are sufficient
    -- for all recovered daily horizons. Missing observations are never filled.
    SELECT min((x.e->>'date')::date) INTO v_input FROM (SELECT e FROM jsonb_array_elements(v_calendar) e
     WHERE (e->>'date')::date<v_month ORDER BY e->>'date' DESC LIMIT 60) x;
    SELECT jsonb_agg(e ORDER BY e->>'date') INTO v_month_calendar FROM jsonb_array_elements(v_calendar) e
     WHERE (e->>'date')::date BETWEEN v_input AND v_last;
    FOREACH v_family IN ARRAY ARRAY['D02','D03','D04','D05'] LOOP
     v_scope:=v_base||jsonb_build_object('target_start',v_month::text,'target_end',v_last::text,'input_start',v_input::text,
      'source_month',v_month::text,'calendar',v_month_calendar,'governing_date','MARKET_SESSION',
      'formula_version','fixed3000-derived-v2.1','prefer_retained_formula_cache',true);
     v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||v_family||':'||v_month::text,v_family,'DERIVED','derive_daily',v_scope,ARRAY[v_raw_id,v_split_id],100);
    END LOOP;
    v_scope:=v_base||jsonb_build_object('target_start',v_month::text,'target_end',v_last::text,'asof',v_month::text,
     'governing_date','REFERENCE_AS_OF','reference_policy','DATED_PROVIDER_SNAPSHOT_ATTRIBUTION_REMAINS_EXPLICIT');
    v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'reference:massive:'||v_month::text,'REF01','Massive','massive_reference',v_scope,'{}',40);
    v_scope:=v_base||jsonb_build_object('target_start',v_month::text,'target_end',v_last::text,
     'start',to_char(v_month::timestamp AT TIME ZONE 'America/New_York' AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"'),
     'end',to_char(((v_last+1)::timestamp AT TIME ZONE 'America/New_York')-interval '1 microsecond','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
     'governing_date','PUBLICATION_TIMESTAMP','include_weekends_holidays',true,'archive_scope','MASSIVE_ENTITLED_ARCHIVE',
     'permitted_alternative','alpaca_news');
    v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'news:massive:'||v_month::text,'N01','Massive','massive_news',v_scope,'{}',50);
    IF v_fallback THEN
     v_scope:=v_scope||jsonb_build_object('archive_scope','ALPACA_ENTITLED_ARCHIVE',
      'alternative_reason','MASSIVE_WORKER_CONFIGURATION_UNAVAILABLE','does_not_complete_primary_archive',true,
      'primary_task_id',astra_ingestion_v1.backfill_plan_task_id_v2(r.id,v_key||'news:massive:'||v_month::text));
     v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'news:alpaca:'||v_month::text,'N01','Alpaca','alpaca_news',v_scope,'{}',51);
    END IF;
   END LOOP;
   v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'reference:massive:2026-07-31','REF01','Massive','massive_reference',
    v_base||jsonb_build_object('asof','2026-07-31','governing_date','REFERENCE_AS_OF'),'{}',40);
   v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'dividends:massive','N02','Massive','massive_dividends',
    v_base||jsonb_build_object('governing_date','DECLARATION_EX_RECORD_PAYMENT_EFFECTIVE_SEPARATE','archive_date_filter','UNBOUNDED_PROVIDER_EVENT_HISTORY','retain_boundary_crossing_events',true),'{}',45);
   v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'splits:massive','N03','Massive','massive_splits',
    v_base||jsonb_build_object('governing_date','EXECUTION_EFFECTIVE_DATE','archive_date_filter','UNBOUNDED_PROVIDER_EVENT_HISTORY','retain_boundary_crossing_events',true),'{}',45);
   v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'actions:alpaca','N02','Alpaca','alpaca_actions',
    v_base||jsonb_build_object('start','2025-06-05','end',(r.created_at AT TIME ZONE 'America/New_York')::date::text,
     'governing_date','PROVIDER_PROCESS_DATE_WITH_SUPPLIED_ACTION_DATES_RETAINED','retain_boundary_crossing_events',true,
     'shared_families',jsonb_build_array('N02','N03')),'{}',45);
   v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'short-volume','S01','Massive','massive_short_volume',
    v_base||jsonb_build_object('start','2025-09-01','end','2026-07-31','governing_date','REPORTING_DATE',
     'reporting_scope','PROVIDER_FINRA_OFF_EXCHANGE_NOT_TOTAL_MARKET'),'{}',60);
   v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'short-interest','S02','Massive','massive_short_interest',
    v_base||jsonb_build_object('start','2025-09-01','end','2026-07-31','governing_date','SETTLEMENT_DATE',
     'publication_date_filter','NONE','retain_later_publications',true,'availability_policy','ACTUAL_PUBLICATION_WHEN_SUPPLIED_ELSE_RETRIEVAL_UPPER_BOUND'),'{}',60);
   FOREACH v_status IN ARRAY ARRAY['active','inactive'] LOOP
    v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'options:'||v_status,'CTX02','Alpaca','alpaca_option_contracts',
     v_base||jsonb_build_object('status',v_status,'expiration_start','2025-09-01','expiration_end','2099-12-31',
      'governing_date','CONTRACT_EXPIRY_REFERENCE_AND_DAILY_MARKET_DATE','include_adjusted_contracts',true,
      'historical_enumeration_completeness','UNKNOWN_UNTIL_PROVIDER_REFERENCE_EXHAUSTED'),'{}',70);
   END LOOP;
   v_next:=m.selection_order+1;v_members:=v_members+1;
  END LOOP;
  IF v_next>3000 THEN v_phase:='BREADTH'; END IF;
 ELSIF v_phase='BREADTH' THEN
  SELECT jsonb_object_agg(member_id,jsonb_build_object('symbol',anchor_ticker,'eligible',NULL) ORDER BY selection_order)
   INTO v_map FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id=r.id;
  v_after:=v_breadth;
  FOR v_entry IN SELECT e FROM jsonb_array_elements(v_calendar) e WHERE e->>'date' BETWEEN '2025-09-01' AND '2026-07-31'
   ORDER BY e->>'date' OFFSET v_after LIMIT v_limit
  LOOP
   v_day:=(v_entry->>'date')::date;
   v_scope:=jsonb_build_object('target_start',v_day::text,'target_end',v_day::text,'input_start',v_day::text,
    'market_timezone','America/New_York','calendar',jsonb_build_array(v_entry),'source_family','D03',
    'source_month',date_trunc('month',v_day)::date::text,'representative_security',v_map,
    'representative_policy',v_workflow->'representative_policy','governing_date','MARKET_SESSION',
    'formula_version','fixed3000-derived-v2.1','cohort_classification','RETROSPECTIVE_FIXED_COHORT');
   v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,'CTX06:'||v_day::text,'CTX06','DERIVED','derive_breadth',v_scope,'{}',250);
   v_breadth:=v_breadth+1;
  END LOOP;
  IF v_breadth=230 THEN v_phase:='SEAL'; END IF;
 ELSIF v_phase='SEAL' THEN
  v_snapshot:=astra_ingestion_v1.backfill_plan_snapshot_v2(r.id,500);
  IF v_snapshot->'more'='true'::jsonb THEN RETURN jsonb_build_object('state','SNAPSHOTTING_EXISTING_TASKS','plan_complete',false,'snapshot',v_snapshot); END IF;
  SELECT count(*),encode(sha256(convert_to(COALESCE(string_agg(task_id||':'||definition_sha256,E'\n' ORDER BY task_id COLLATE "C"),''),'UTF8')),'hex')
   INTO v_count,v_hash FROM astra_ingestion_v1.backfill_plan_units_v2 WHERE run_id=r.id;
  IF v_count<>v_expected THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Actual static plan count differs from transactionally admitted expected count'; END IF;
  v_result:=astra_ingestion_v1.backfill_seal_plan_v2(r.id,v_expected,v_hash,v_workflow);
  RETURN v_result||jsonb_build_object('run_id',r.id,'plan_complete',v_result->>'state'='FULL_PLAN_SEALED',
   'planned_members',3000,'next_selection_order',3001,'breadth_sessions',230);
 ELSE
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Unknown persisted planner phase';
 END IF;
 v_expected:=v_expected+v_added;
 UPDATE astra_ingestion_v1.backfill_runs_v2 SET metadata=r.metadata||jsonb_build_object(
  'planner_phase',v_phase,'planner_next_selection_order',v_next,'planner_next_breadth_index',v_breadth,
  'planner_expected_static_count',v_expected,'workflow_plan',v_workflow,'planner_last_progress_at',clock_timestamp()),
  last_progress_at=CASE WHEN v_added>0 THEN clock_timestamp() ELSE last_progress_at END WHERE id=r.id;
 RETURN jsonb_build_object('state','PLAN_ADVANCED','run_id',r.id,'phase',v_phase,'plan_complete',false,
  'members_admitted_this_call',v_members,'planned_members',v_next-1,'next_selection_order',v_next,
  'breadth_sessions',v_breadth,'inserted_tasks',v_added,'expected_static_task_count',v_expected);
END $planner$;

-- No new public table/function grants. Only the existing worker capability can
-- reach the fixed planner through the already authenticated RPC dispatcher.
DO $acl$
DECLARE f record; g record;
BEGIN
 FOR f IN SELECT p.oid,p.proname,p.proowner,p.proacl,pg_get_function_identity_arguments(p.oid) args
  FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='astra_ingestion_v1'
   AND p.proname IN ('backfill_plan_task_id_v2','backfill_plan_insert_v2','backfill_plan_next_v2') LOOP
  EXECUTE format('REVOKE ALL ON FUNCTION astra_ingestion_v1.%I(%s) FROM PUBLIC',f.proname,f.args);
  FOR g IN SELECT DISTINCT r.rolname FROM aclexplode(f.proacl) a JOIN pg_roles r ON r.oid=a.grantee WHERE a.grantee<>f.proowner LOOP
   EXECUTE format('REVOKE ALL ON FUNCTION astra_ingestion_v1.%I(%s) FROM %I',f.proname,f.args,g.rolname);
  END LOOP;
  EXECUTE format('GRANT EXECUTE ON FUNCTION astra_ingestion_v1.%I(%s) TO astra_ingestion_rpc_owner_v1',f.proname,f.args);
 END LOOP;
END $acl$;
DO $wire$
DECLARE d text;
BEGIN
 SELECT pg_get_functiondef('astra_ingestion_v1.rpc_dispatch(text,jsonb)'::regprocedure) INTO STRICT d;
 IF strpos(d,'''backfill_seal_plan''')=0 OR strpos(d,'backfill_full_plan_hook_v2')>0 THEN RAISE EXCEPTION 'Planner dispatcher baseline changed'; END IF;
 -- This replacement adds the worker allowlist entry and any delivery hook list;
 -- the dedicated branch precedes delivery dispatch and remains after auth.
 d:=replace(d,'''backfill_seal_plan''','''backfill_seal_plan'',''backfill_plan_next''');
 d:=replace(d,'    -- backfill_delivery_dispatch_hook_v2',$hook$
    -- backfill_full_plan_hook_v2: bounded static admission, same authenticated worker.
    IF p_operation='backfill_plan_next' THEN
      RETURN jsonb_build_object('ok',true,'result',astra_ingestion_v1.backfill_plan_next_v2(p_payload));
    END IF;
    -- backfill_delivery_dispatch_hook_v2$hook$);
 IF strpos(d,'backfill_full_plan_hook_v2')=0 THEN RAISE EXCEPTION 'Planner hook location absent'; END IF;
 EXECUTE d;
END $wire$;
COMMIT;
