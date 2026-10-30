-- Preserve the exact fixed-cohort claim guard while evaluating its count once
-- per candidate query, instead of once per unsupported queued task.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);

DO $repair$
DECLARE d text;
 old_guard text:='AND (SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2 m WHERE m.run_id=q.run_id)=3000';
 new_guard text:='AND (SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2 m WHERE m.run_id=v_fair_run)=3000 /* backfill_claim_member_count_once_v2 */';
 run_guard text:='q.run_id=v_fair_run AND q.family=v_fair_pick.family';
BEGIN
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure) INTO STRICT d;
 IF strpos(d,'backfill_claim_member_count_once_v2')>0
  OR strpos(d,'backfill_family_fairness_hook_v2')=0
  OR strpos(d,'backfill_due_recovery_priority_v2')=0
  OR (length(d)-length(replace(d,old_guard,'')))/length(old_guard)<>2
  OR (length(d)-length(replace(d,run_guard,'')))/length(run_guard)<>2 THEN
  RAISE EXCEPTION 'Claim performance repair requires both unchanged run-bound recovery and normal candidate guards; reconcile before applying';
 END IF;
 -- Each candidate already requires q.run_id=v_fair_run. This replaces an
 -- equivalent correlated subquery with a scalar InitPlan. All task fences,
 -- dependencies, gap children, breadth readiness, retry times, capabilities,
 -- ordering, locking, current roles and function configuration are retained.
 EXECUTE replace(d,old_guard,new_guard);
END $repair$;
COMMIT;
