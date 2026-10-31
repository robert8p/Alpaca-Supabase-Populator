-- Preserve all delivery semantics while separating planned work from actual pages.
-- The old shared mapped_tasks CTE materialized the entire plan twice per report.
-- No receipt, task, stored projection, privilege, formula or report wrapper is changed.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);

DO $preflight$
DECLARE d text;
BEGIN
 IF to_regclass('astra_ingestion_v1.backfill_family_receipt_status_v2') IS NULL
  OR to_regclass('astra_ingestion_v1.backfill_nonminute_family_counts_v2') IS NULL
  OR to_regclass('astra_ingestion_v1.backfill_s02_canonical_v2') IS NULL THEN
  RAISE EXCEPTION 'Family report performance requires the qualified stage3 delivery views';
 END IF;
 SELECT pg_get_viewdef('astra_ingestion_v1.backfill_family_receipt_status_v2'::regclass,true) INTO d;
 IF strpos(d,'WITH mapped_tasks AS')=0 OR strpos(d,'reused_feature_records')=0
  OR strpos(d,'qualified_feature_records')=0 OR strpos(d,'usable_feature_records')=0 THEN
  RAISE EXCEPTION 'Family receipt report baseline differs or this forward is already installed';
 END IF;
 SELECT pg_get_viewdef('astra_ingestion_v1.backfill_nonminute_selected_tasks_v2'::regclass,true) INTO d;
 IF strpos(d,'row_number() OVER')=0 OR strpos(d,'revision_link_valid')=0 THEN
  RAISE EXCEPTION 'Selected non-minute revision baseline differs';
 END IF;
END $preflight$;

CREATE OR REPLACE VIEW astra_ingestion_v1.backfill_family_receipt_status_v2 WITH(security_invoker=true) AS
 WITH task_counts AS (
  SELECT t.run_id,t.family,t.status,
   t.family='P01' AND t.kind IN('alpaca_stock_bars','retained_reuse')
    AND COALESCE(t.scope->>'timeframe','1Min')='1Min' minute_alias,
   count(*) units,min(t.next_retry_at) next_retry_at
  FROM astra_ingestion_v1.backfill_tasks_v2 t
  GROUP BY t.run_id,t.family,t.status,
   t.family='P01' AND t.kind IN('alpaca_stock_bars','retained_reuse')
    AND COALESCE(t.scope->>'timeframe','1Min')='1Min'
 ), units AS (
  SELECT n.run_id,m.delivery_family,sum(n.units)::bigint planned_units,
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
   COALESCE(sum(n.units) FILTER(WHERE n.status='PENDING'),0)::bigint pending_units,
   min(n.next_retry_at) FILTER(WHERE n.status='RETRY_WAIT') next_retry_at
  FROM task_counts n
  CROSS JOIN LATERAL(SELECT n.family delivery_family UNION ALL SELECT 'P02' WHERE n.minute_alias) m
  GROUP BY n.run_id,m.delivery_family
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
  COALESCE(o.usable_minute_records,0) usable_minute_records,u.next_retry_at,
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

-- Keep every projected task in one ranked relation, then expose selection as
-- a value. Filtering rank=1 in a second joined view grossly underestimates its
-- cardinality and can rerun the complete selection for every output page.
-- Eligible revisions sort before ineligible ones; the original complete /
-- created_at / task_id order is unchanged within the eligible candidates.
CREATE OR REPLACE VIEW astra_ingestion_v1.backfill_nonminute_effective_pages_v2 WITH(security_invoker=true) AS
 WITH candidates AS (
  SELECT c.*,c.observation_role='DERIVED' AND c.revision_link_valid
   AND (c.original_revision OR c.query_complete) revision_eligible
  FROM astra_ingestion_v1.backfill_nonminute_task_coverage_v2 c
 ), ranked AS (
  SELECT c.*,row_number() OVER(PARTITION BY c.run_id,c.family,c.root_task_id ORDER BY
   c.revision_eligible DESC,c.query_complete DESC,c.created_at DESC,c.task_id DESC) selection_rank
  FROM candidates c
 ), choices AS (
  SELECT r.*,r.revision_eligible AND r.selection_rank=1 chosen_row FROM ranked r
 ), selected AS (
  -- A task can have both ordinary and pointer pages. The old selected-task
  -- join copied its chosen derived row to every role group of that task;
  -- preserve that behavior without reexecuting the entire revision ranking.
  SELECT r.*,bool_or(r.chosen_row) OVER task_rows chosen_revision,
   max(r.root_task_id) FILTER(WHERE r.chosen_row) OVER task_rows selected_root_task_id,
   bool_or(r.identity_material_current) FILTER(WHERE r.chosen_row) OVER task_rows selected_identity_material_current,
   bool_or(r.identity_invalidated) FILTER(WHERE r.chosen_row) OVER task_rows selected_identity_invalidated,
   max(r.invalidation_reason) FILTER(WHERE r.chosen_row) OVER task_rows selected_invalidation_reason
  FROM choices r WINDOW task_rows AS(PARTITION BY r.run_id,r.task_id)
 )
 SELECT p.*,c.query_complete,
  c.selected_root_task_id root_task_id,c.selected_identity_material_current identity_material_current,
  COALESCE(c.selected_identity_invalidated,false) identity_invalidated,
  c.selected_invalidation_reason invalidation_reason,
  p.observation_role='SOURCE' OR (p.observation_role='DERIVED' AND c.chosen_revision) selected_output
 FROM astra_ingestion_v1.backfill_nonminute_pages_v2 p
 JOIN selected c ON c.task_id=p.task_id AND c.run_id=p.run_id;
COMMIT;
