-- Keep million-task monitoring bounded and avoid materializing task scope archives.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);
CREATE OR REPLACE VIEW astra_ingestion_v1.backfill_family_status_v2 WITH(security_invoker=true) AS
 WITH mapped_tasks AS (
  SELECT t.id,t.run_id,t.family,t.status,t.next_retry_at,m.delivery_family FROM astra_ingestion_v1.backfill_tasks_v2 t
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

DO $wire$
DECLARE d text; count_guard text:=$count_guard$ IF (SELECT count(*) FROM astra_ingestion_v1.backfill_plan_units_v2 WHERE run_id=r.id AND recorded_at<=v_plan.sealed_at)<>v_plan.expected_task_count THEN
  RETURN jsonb_build_object('state','EXPECTED_PLAN_UNITS_DIFFER'); END IF;$count_guard$; pending_guard text:=$pending_guard$ IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 WHERE run_id=r.id AND status IN ('PENDING','RUNNING','RETRY_WAIT')) THEN
  RETURN jsonb_build_object('state','WORK_REMAINS'); END IF;$pending_guard$;
BEGIN
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_try_finalize_v2(text)'::regprocedure) INTO STRICT d;
 IF strpos(d,'bounded_delivery_completion_check_v2')>0 OR strpos(d,count_guard)=0 OR strpos(d,pending_guard)=0 THEN
  RAISE EXCEPTION 'Unexpected finalizer baseline for bounded completion checks'; END IF;
 d:=replace(d,count_guard,'');
 d:=replace(d,pending_guard,pending_guard||chr(10)||' -- bounded_delivery_completion_check_v2: whole-plan count only after runnable work is exhausted.'||chr(10)||count_guard);
 EXECUTE d;
END $wire$;
COMMIT;
