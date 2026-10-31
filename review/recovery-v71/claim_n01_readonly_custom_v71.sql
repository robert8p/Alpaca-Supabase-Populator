-- Executes a SELECT for one observed family, not a claim or provider request.
-- Original predicates, q.* projection and candidate ordering are preserved.
-- Only INTO and FOR UPDATE are removed; no row lock or task mutation occurs.
-- READ ONLY enforces no data writes even if an invoked helper unexpectedly drifts.
-- This is internal diagnostic timing, not authenticated RPC/lock-path timing.
-- Current family snapshot is N01 at 2026-10-30T12:23:40Z; failed family is UNKNOWN.
-- Reconcile this observation against current progress before executing once.
BEGIN READ ONLY;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $guard$
BEGIN
 IF encode(sha256(convert_to(pg_get_functiondef('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure),'UTF8')),'hex')<>'136871b8ca305ae69c661541d9c2684e71b1d5e6fe84a6ec9b8b594b1da56d02'
  OR encode(sha256(convert_to(pg_get_functiondef('astra_ingestion_v1.rpc_dispatch(text,jsonb)'::regprocedure),'UTF8')),'hex')<>'a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520' THEN
  RAISE EXCEPTION 'Live claim or authentication source changed; reconcile before diagnostic'; END IF;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2 WHERE id='fixed3000-20250901-20260731-v1-20261030' AND status='ACTIVE' AND fence=1
  AND cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec') THEN
  RAISE EXCEPTION 'Fixed active run/fence changed; reconcile before diagnostic'; END IF;
END $guard$;
SET LOCAL plan_cache_mode='force_custom_plan';
PREPARE replacement_claim_measure_v71_n01(text,text,jsonb,timestamptz) AS
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
   ORDER BY q.priority,q.next_retry_at,q.created_at,q.id LIMIT 1;
EXPLAIN (ANALYZE TRUE, BUFFERS TRUE, TIMING FALSE, SETTINGS TRUE, FORMAT JSON) EXECUTE replacement_claim_measure_v71_n01('fixed3000-20250901-20260731-v1-20261030','N01','["alpaca_reference","alpaca_stock_bars","alpaca_news","alpaca_actions","alpaca_option_contracts","alpaca_option_bars","derive_daily","derive_intraday","derive_breadth","retained_reuse","retained_identity","retained_massive_archive"]'::jsonb,'2026-10-30T12:23:40Z'::timestamptz);
DEALLOCATE replacement_claim_measure_v71_n01;
ROLLBACK;

