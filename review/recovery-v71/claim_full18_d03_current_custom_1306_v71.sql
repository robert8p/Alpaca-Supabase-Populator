-- Current full-capability observation, not a reconstruction of the failed request.
-- D03 is the next family in the saved rotation, not a proven failed family.
-- Execute once only after root reconciles ownership, progress and source pins.
-- READ ONLY and a repeatable snapshot prohibit mutations and keep guards coherent.
-- The exact normal SELECT retains every filter/order/limit and q.* projection;
-- only its PL/pgSQL INTO target and FOR UPDATE are removed.
-- Results contain a plan, not raw task payloads, credentials or source bodies.
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $guard$
BEGIN
 IF encode(sha256(convert_to(pg_get_functiondef('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure),'UTF8')),'hex')<>'136871b8ca305ae69c661541d9c2684e71b1d5e6fe84a6ec9b8b594b1da56d02'
  OR encode(sha256(convert_to(pg_get_functiondef('astra_ingestion_v1.rpc_dispatch(text,jsonb)'::regprocedure),'UTF8')),'hex')<>'a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520' THEN
  RAISE EXCEPTION 'Installed claim/auth source changed; reconcile before current-capability diagnostic';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2
  WHERE id='fixed3000-20250901-20260731-v1-20261030' AND status='ACTIVE' AND fence=1
   AND cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
   AND metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
   AND (metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()) THEN
  RAISE EXCEPTION 'Existing owner, lease or fixed active run changed; reconcile before diagnostic';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_family_turn_v2
  WHERE run_id='fixed3000-20250901-20260731-v1-20261030' AND next_family_index=7
   AND claim_turns=4187 AND last_claimed_task_id='backfill-plan-c6dfa8452841bb6998b059e208b5be721ca85947c6bd5dd0b9391e4efd50c056'
   AND changed_at='2026-10-30T13:03:32.794473+00:00'::timestamptz) THEN
  RAISE EXCEPTION 'Family rotation progressed since retained snapshot; refresh evidence before diagnostic';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_workers_v2
  WHERE worker_id='17e73b52-6f6c-43b4-a797-97d37be6f379' AND source_revision='3ee4db2a79c081ffb65ef0d7ec2a04228d69fb1d'
   AND observed_at='2026-10-30T13:03:32.794473+00:00'::timestamptz
   AND supported_kinds='["alpaca_reference","alpaca_stock_bars","alpaca_news","alpaca_actions","alpaca_option_contracts","alpaca_option_bars","massive_reference","massive_news","massive_dividends","massive_splits","massive_short_volume","massive_short_interest","derive_daily","derive_intraday","derive_breadth","retained_reuse","retained_identity","retained_massive_archive"]'::jsonb) THEN
  RAISE EXCEPTION 'Retained worker capability observation changed; refresh evidence before diagnostic';
 END IF;
END $guard$;
SET LOCAL plan_cache_mode='force_custom_plan';
PREPARE full18_d03_current_custom_1306_v71(text,text,jsonb,timestamptz) AS
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
EXPLAIN (ANALYZE TRUE,BUFFERS TRUE,TIMING FALSE,SETTINGS TRUE,FORMAT JSON) EXECUTE full18_d03_current_custom_1306_v71('fixed3000-20250901-20260731-v1-20261030','D03','["alpaca_reference","alpaca_stock_bars","alpaca_news","alpaca_actions","alpaca_option_contracts","alpaca_option_bars","massive_reference","massive_news","massive_dividends","massive_splits","massive_short_volume","massive_short_interest","derive_daily","derive_intraday","derive_breadth","retained_reuse","retained_identity","retained_massive_archive"]'::jsonb,'2026-10-30 13:06:42.509058+00'::timestamptz);
DEALLOCATE full18_d03_current_custom_1306_v71;
ROLLBACK;
