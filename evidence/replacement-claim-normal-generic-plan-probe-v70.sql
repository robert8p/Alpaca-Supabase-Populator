-- Plain EXPLAIN only: the exact normal candidate is planned, not executed.
-- FOR UPDATE is retained only to show its LockRows plan; no task row is locked.
-- READ ONLY, eight-second statement and three-second lock deadlines remain.
-- This bypasses outer authentication and its advisory lock and performs no claim.
-- Parameters are the saved 2026-10-30 11:00:49.547058 UTC metadata snapshot.
-- The failed family at10:53:28 is unknown: the loop may visit all16 families.
-- Planning uses whatever indexes/statistics are installed at probe time.
-- Expected result is one EXPLAIN JSON document: estimates only, no actual timing.
BEGIN;
SET TRANSACTION READ ONLY;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $guard$
DECLARE actual text; expected text := $candidate$  SELECT q.* INTO t FROM astra_ingestion_v1.backfill_tasks_v2 q JOIN astra_ingestion_v1.backfill_runs_v2 rr ON rr.id=q.run_id
   WHERE q.run_id=v_fair_run AND q.family=v_fair_pick.family
    AND q.status IN ('PENDING','RUNNING','RETRY_WAIT') AND rr.status='ACTIVE' AND rr.fence=q.run_fence AND q.kind IN (SELECT jsonb_array_elements_text(v_supported))
    AND q.next_retry_at<=v_now AND q.page_attempts<8
    AND (q.status IN ('PENDING','RETRY_WAIT') OR (q.status='RUNNING' AND q.lease_until<=v_now))
    AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_provider_dependencies_v2 d WHERE d.run_id=q.run_id AND d.provider=q.provider AND d.state='BLOCKED_EXTERNAL')
    AND NOT EXISTS(SELECT 1 FROM unnest(q.dependencies) dep LEFT JOIN astra_ingestion_v1.backfill_tasks_v2 d ON d.id=dep
      WHERE d.id IS NULL OR d.run_id<>q.run_id OR d.status NOT IN ('INGESTED','NO_DATA_RETURNED','NOT_APPLICABLE','PROVIDER_LIMITATION','IDENTITY_OR_QUALITY_UNRESOLVED'))
    AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 gap WHERE gap.run_id=q.run_id AND gap.scope ? 'reuse_parent' AND gap.scope->>'reuse_parent'=ANY(q.dependencies) AND gap.status NOT IN ('INGESTED','NO_DATA_RETURNED','NOT_APPLICABLE','PROVIDER_LIMITATION','IDENTITY_OR_QUALITY_UNRESOLVED'))
    AND (q.kind<>'derive_breadth' OR astra_ingestion_v1.backfill_breadth_ready_v2(q.id))
    AND (SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2 m WHERE m.run_id=v_fair_run)=3000 /* backfill_claim_member_count_once_v2 */
   ORDER BY q.priority,q.next_retry_at,q.created_at,q.id LIMIT 1 FOR UPDATE OF q;$candidate$;
BEGIN
 SELECT prosrc INTO STRICT actual FROM pg_proc
 WHERE oid='astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure;
 IF length(actual)-length(replace(actual,expected,''))<>length(expected) THEN
  RAISE EXCEPTION 'Normal claim candidate differs from the saved live query; reconcile before probing';
 END IF;
END $guard$;
SET LOCAL plan_cache_mode='force_generic_plan';
PREPARE replacement_claim_normal_plan_v70_generic(text,text,jsonb,timestamptz) AS
SELECT q.* FROM astra_ingestion_v1.backfill_tasks_v2 q JOIN astra_ingestion_v1.backfill_runs_v2 rr ON rr.id=q.run_id
   WHERE q.run_id=$1 AND q.family=$2
    AND q.status IN ('PENDING','RUNNING','RETRY_WAIT') AND rr.status='ACTIVE' AND rr.fence=q.run_fence AND q.kind IN (SELECT jsonb_array_elements_text($3))
    AND q.next_retry_at<=$4 AND q.page_attempts<8
    AND (q.status IN ('PENDING','RETRY_WAIT') OR (q.status='RUNNING' AND q.lease_until<=$4))
    AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_provider_dependencies_v2 d WHERE d.run_id=q.run_id AND d.provider=q.provider AND d.state='BLOCKED_EXTERNAL')
    AND NOT EXISTS(SELECT 1 FROM unnest(q.dependencies) dep LEFT JOIN astra_ingestion_v1.backfill_tasks_v2 d ON d.id=dep
      WHERE d.id IS NULL OR d.run_id<>q.run_id OR d.status NOT IN ('INGESTED','NO_DATA_RETURNED','NOT_APPLICABLE','PROVIDER_LIMITATION','IDENTITY_OR_QUALITY_UNRESOLVED'))
    AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 gap WHERE gap.run_id=q.run_id AND gap.scope ? 'reuse_parent' AND gap.scope->>'reuse_parent'=ANY(q.dependencies) AND gap.status NOT IN ('INGESTED','NO_DATA_RETURNED','NOT_APPLICABLE','PROVIDER_LIMITATION','IDENTITY_OR_QUALITY_UNRESOLVED'))
    AND (q.kind<>'derive_breadth' OR astra_ingestion_v1.backfill_breadth_ready_v2(q.id))
    AND (SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2 m WHERE m.run_id=$1)=3000 /* backfill_claim_member_count_once_v2 */
   ORDER BY q.priority,q.next_retry_at,q.created_at,q.id LIMIT 1 FOR UPDATE OF q;
EXPLAIN (FORMAT JSON, SETTINGS TRUE) EXECUTE replacement_claim_normal_plan_v70_generic('fixed3000-20250901-20260731-v1-20261030','CTX06','["alpaca_reference","alpaca_stock_bars","alpaca_news","alpaca_actions","alpaca_option_contracts","alpaca_option_bars","derive_daily","derive_intraday","derive_breadth","retained_reuse","retained_identity","retained_massive_archive"]','2026-10-30 11:00:49.547058+00');
DEALLOCATE replacement_claim_normal_plan_v70_generic;
ROLLBACK;
