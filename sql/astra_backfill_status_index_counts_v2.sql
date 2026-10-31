-- Read task status counts from existing compact indexes instead of every wide
-- scope-bearing heap row. Original receipts and all report wrappers stay intact.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);
DO $preflight$
DECLARE d text; namespace text;
BEGIN
 SELECT pg_get_viewdef('astra_ingestion_v1.backfill_family_receipt_status_v2'::regclass,true) INTO STRICT d;
 SELECT n.nspname INTO STRICT namespace FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
  WHERE c.oid='astra_ingestion_v1.backfill_family_receipt_status_v2'::regclass;
 IF encode(sha256(convert_to(replace(d,namespace,'astra'||'_ingestion_v1'),'UTF8')),'hex')
  <> '4282f5dc1f8d84ca81979d90fc6f4a49cce754b07ca06808046814267c45a990' THEN
  RAISE EXCEPTION 'Receipt-report definition differs from the independently read live baseline';
 END IF;
 IF strpos(d,'WITH task_counts AS')=0 OR strpos(d,'minute_alias')=0
  OR strpos(d,'task_status_counts')>0 OR strpos(d,'reused_feature_records')=0
  OR strpos(d,'qualified_feature_records')=0 OR strpos(d,'usable_feature_records')=0 THEN
  RAISE EXCEPTION 'Indexed task-count report requires the qualified receipt-report baseline and applies once';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM pg_index i WHERE i.indexrelid=to_regclass('astra_ingestion_v1.backfill_tasks_family_v2')
   AND i.indrelid='astra_ingestion_v1.backfill_tasks_v2'::regclass AND i.indisvalid AND i.indisready
   AND i.indpred IS NULL AND i.indexprs IS NULL
   AND pg_get_indexdef(i.indexrelid) LIKE '% USING btree (run_id, family, status)') THEN
  RAISE EXCEPTION 'Existing valid run/family/status covering index is required';
 END IF;
END $preflight$;

CREATE OR REPLACE VIEW astra_ingestion_v1.backfill_family_receipt_status_v2 WITH(security_invoker=true) AS
 WITH task_status_counts AS (
  -- Native status counts use the existing covering(run_id,family,status) index.
  SELECT t.run_id,t.family delivery_family,t.status,count(*) units
  FROM astra_ingestion_v1.backfill_tasks_v2 t GROUP BY t.run_id,t.family,t.status
  UNION ALL
  -- Only qualifying minute-source tasks inspect their immutable JSON scope.
  SELECT t.run_id,'P02'::text delivery_family,t.status,count(*) units
  FROM astra_ingestion_v1.backfill_tasks_v2 t
  WHERE t.family='P01' AND t.kind IN('alpaca_stock_bars','retained_reuse')
   AND COALESCE(t.scope->>'timeframe','1Min')='1Min'
  GROUP BY t.run_id,t.status
 ), units AS (
  SELECT n.run_id,n.delivery_family,sum(n.units)::bigint planned_units,
   COALESCE(sum(n.units) FILTER(WHERE n.status IN('INGESTED','NO_DATA_RETURNED','NOT_APPLICABLE','PROVIDER_LIMITATION','IDENTITY_OR_QUALITY_UNRESOLVED')),0)::bigint terminal_units,
   COALESCE(sum(n.units) FILTER(WHERE n.status='INGESTED'),0)::bigint ingested_units,
   COALESCE(sum(n.units) FILTER(WHERE n.status='NO_DATA_RETURNED'),0)::bigint no_data_units,
   COALESCE(sum(n.units) FILTER(WHERE n.status='NOT_APPLICABLE'),0)::bigint not_applicable_units,
   COALESCE(sum(n.units) FILTER(WHERE n.status='PROVIDER_LIMITATION'),0)::bigint provider_limited_units,
   COALESCE(sum(n.units) FILTER(WHERE n.status='IDENTITY_OR_QUALITY_UNRESOLVED'),0)::bigint unresolved_units,
   COALESCE(sum(n.units) FILTER(WHERE n.status='OPERATIONAL_ERROR'),0)::bigint operational_error_units,
   COALESCE(sum(n.units) FILTER(WHERE n.status='BLOCKED_EXTERNAL'),0)::bigint blocked_units,
   COALESCE(sum(n.units) FILTER(WHERE n.status='RETRY_WAIT'),0)::bigint retry_wait_units,
   COALESCE(sum(n.units) FILTER(WHERE n.status='RUNNING'),0)::bigint running_units,
   COALESCE(sum(n.units) FILTER(WHERE n.status='PENDING'),0)::bigint pending_units
  FROM task_status_counts n GROUP BY n.run_id,n.delivery_family
 ), retry_dates AS (
  -- The report consumes retry deadlines only for RETRY_WAIT. Keep native P02
  -- and eligible P01 alias deadlines, including NULL when neither exists.
  SELECT d.run_id,d.delivery_family,min(d.next_retry_at) next_retry_at FROM (
   SELECT t.run_id,t.family delivery_family,min(t.next_retry_at) next_retry_at
   FROM astra_ingestion_v1.backfill_tasks_v2 t WHERE t.status='RETRY_WAIT'
   GROUP BY t.run_id,t.family
   UNION ALL
   SELECT t.run_id,'P02'::text delivery_family,min(t.next_retry_at) next_retry_at
   FROM astra_ingestion_v1.backfill_tasks_v2 t
   WHERE t.status='RETRY_WAIT' AND t.family='P01' AND t.kind IN('alpaca_stock_bars','retained_reuse')
    AND COALESCE(t.scope->>'timeframe','1Min')='1Min'
   GROUP BY t.run_id
  ) d GROUP BY d.run_id,d.delivery_family
 ), observations AS (
  SELECT p.run_id,m.delivery_family,count(p.task_id) archived_pages,count(v.task_id) verified_pages,
   COALESCE(sum(CASE WHEN m.delivery_family='P01' THEN v.rth_records
    WHEN m.delivery_family='P02' THEN v.pre_records+v.post_records
    WHEN m.delivery_family='D01' AND COALESCE(v.reused_feature_records,0)>0 THEN v.reused_feature_records
    ELSE p.record_count END),0) committed_records,
   COALESCE(sum(v.target_records),0) dated_target_records,COALESCE(sum(v.support_records),0) support_records,
   COALESCE(sum(v.unknown_date_records),0) unknown_date_records,
   COALESCE(sum(v.unclassified_session_records),0) unclassified_session_records,
   COALESCE(sum(CASE WHEN m.delivery_family='D01' THEN v.reused_feature_records ELSE v.reused_records END),0) referenced_existing_records,
   COALESCE(sum(CASE WHEN m.delivery_family='D01' THEN v.qualified_feature_records ELSE v.reused_qualified_records END),0) referenced_qualifying_records,
   COALESCE(sum(CASE WHEN m.delivery_family='D01' THEN v.usable_feature_records ELSE v.reused_usable_records END),0) referenced_usable_records,
   COALESCE(sum(CASE WHEN m.delivery_family='P01' THEN v.usable_rth_records WHEN m.delivery_family='P02' THEN v.usable_pre_records+v.usable_post_records ELSE 0 END),0) usable_minute_records
  FROM astra_ingestion_v1.backfill_pages_v2 p
  JOIN astra_ingestion_v1.backfill_tasks_v2 t ON t.id=p.task_id AND t.run_id=p.run_id
  CROSS JOIN LATERAL(SELECT t.family delivery_family UNION ALL SELECT 'P02'
   WHERE t.family='P01' AND t.kind IN('alpaca_stock_bars','retained_reuse') AND COALESCE(t.scope->>'timeframe','1Min')='1Min') m
  LEFT JOIN astra_ingestion_v1.backfill_readbacks_v2 v ON v.task_id=p.task_id AND v.page_no=p.page_no
  GROUP BY p.run_id,m.delivery_family
 ), audits AS(SELECT run_id,count(*) evidence_records FROM astra_ingestion_v1.backfill_family_ref03_v2 GROUP BY run_id)
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
  COALESCE(o.usable_minute_records,0) usable_minute_records,d.next_retry_at,
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
 LEFT JOIN retry_dates d ON d.run_id=r.id AND d.delivery_family=c.family
 LEFT JOIN observations o ON o.run_id=r.id AND o.delivery_family=c.family
 LEFT JOIN audits a ON a.run_id=r.id;

COMMIT;
