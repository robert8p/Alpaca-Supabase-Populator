CREATE OR REPLACE FUNCTION astra_ingestion_v1.backfill_recheck_page_v2(p_task_id text, p_page_no integer)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
DECLARE p astra_ingestion_v1.backfill_pages_v2; v_hash text; v_counts record; v_saved astra_ingestion_v1.backfill_readbacks_v2; v_reuse jsonb; v_sessions record; v_feature jsonb; v_identity jsonb;v_s02 jsonb;
BEGIN
 SELECT * INTO p FROM astra_ingestion_v1.backfill_pages_v2 WHERE task_id=p_task_id AND page_no=p_page_no;
 IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='AI004',MESSAGE='Readback page does not exist'; END IF;
 IF p.committed_at>=transaction_timestamp() THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Independent readback requires a subsequent transaction'; END IF;
 v_hash:=encode(sha256(convert_to(p.raw_body,'UTF8')),'hex');
 IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 st WHERE st.id=p.task_id AND st.kind='retained_massive_archive') THEN v_s02:=astra_ingestion_v1.backfill_massive_archive_verify_v2(p.task_id,p.page_no);END IF;
 IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 it WHERE it.id=p.task_id AND it.kind='retained_identity') THEN
  v_identity:=astra_ingestion_v1.backfill_identity_source_verify_v2(p.task_id,p.page_no);
  IF v_identity->'passed' IS DISTINCT FROM 'true'::jsonb THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Retained identity source readback differs'; END IF;
 END IF;
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

 IF p.raw_body::jsonb#>>'{rows,0,record_type}'='DERIVED_RETAINED_SOURCE_POINTER' THEN
  v_feature:=astra_ingestion_v1.backfill_feature_reuse_verify_v2(p.task_id,p.page_no);
  IF v_feature->'passed' IS DISTINCT FROM 'true'::jsonb THEN
   RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Retained feature source readback differs'; END IF;
  v_counts.target:=(v_feature->>'reused_feature_rows')::int;
  v_counts.support:=0;v_counts.unknown_date:=0;
 END IF;
 IF lower(p.provider)='reuse' AND EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 it WHERE it.id=p.task_id AND it.kind='retained_reuse') THEN
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
  usable_rth_records,usable_pre_records,usable_post_records,reused_records,reused_qualified_records,reused_usable_records,retained_source_verification,reused_feature_records,qualified_feature_records,usable_feature_records,retained_feature_verification,retained_identity_verification,retained_s02_verification)
 VALUES(p.task_id,p.page_no,p.run_id,p.body_sha256,v_hash,p.record_count,v_counts.total,v_counts.target,v_counts.support,v_counts.unknown_date,v_counts.rth,v_counts.pre,v_counts.post,v_counts.unclassified,
  v_counts.urth,v_counts.upre,v_counts.upost,COALESCE((v_reuse->>'reused_records')::bigint,0),COALESCE((v_reuse->>'qualifying_profile_count')::bigint,0),COALESCE((v_reuse->>'usable_source_count')::bigint,0),v_reuse,COALESCE((v_feature->>'reused_feature_rows')::int,0),COALESCE((v_feature->>'qualifying_feature_rows')::int,0),COALESCE((v_feature->>'usable_feature_rows')::int,0),v_feature,v_identity,v_s02)
 ON CONFLICT(task_id,page_no) DO NOTHING;
 SELECT * INTO v_saved FROM astra_ingestion_v1.backfill_readbacks_v2 WHERE task_id=p.task_id AND page_no=p.page_no;
 RETURN to_jsonb(v_saved)||jsonb_build_object('state','VERIFIED');
END $function$
