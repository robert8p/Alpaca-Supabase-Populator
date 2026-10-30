-- Preserve one family turn when normal one-second provider pacing refuses it.
-- Long provider waits continue rotating through other eligible families.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);

DO $wire$
DECLARE d text;
 original text:='    RETURN jsonb_build_object(''state'',''request_deferred'',''task_id'',t.id,''page_no'',t.page_no,''next_retry_at'',to_timestamp(v_not_before));';
 replacement text;
BEGIN
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure) INTO STRICT d;
 IF to_regclass('astra_ingestion_v1.backfill_family_turn_v2') IS NULL
  OR strpos(d,'backfill_paid_provider_pacing_v2')=0
  OR strpos(d,'backfill_family_fairness_hook_v2')=0
  OR strpos(d,'backfill_due_recovery_priority_v2')=0
  OR strpos(d,'backfill_short_pacing_fairness_v2')>0
  OR (length(d)-length(replace(d,original,'')))/length(original)<>1 THEN
  RAISE EXCEPTION 'Short pacing fairness requires the current paid pacing/family/recovery runtime and applies once';
 END IF;
 replacement:=$hook$
    -- backfill_short_pacing_fairness_v2: a refused request has not served this family.
    -- The existing worker waits two seconds after request_deferred. Retaining
    -- this turn only for <=1 second is bounded; long Retry-After waits rotate.
    IF v_not_before>v_epoch AND v_not_before<=v_epoch+1.0 THEN
     UPDATE astra_ingestion_v1.backfill_family_turn_v2 ft
      SET next_family_index=array_position(ARRAY['REF01','REF03','P01','P02','D01','D02','D03','D04','D05','N01','N02','N03','S01','S02','CTX02','CTX06'],t.family),
       changed_at=v_now
      WHERE ft.run_id=t.run_id AND ft.last_claimed_task_id=t.id AND ft.last_family=t.family
       AND EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2 rr
        WHERE rr.id=t.run_id AND rr.status='ACTIVE' AND rr.fence=t.run_fence);
    END IF;
$hook$||original;
 EXECUTE replace(d,original,replacement);
END $wire$;

UPDATE astra_ingestion_v1.backfill_runs_v2
 SET metadata=metadata||jsonb_build_object('family_scheduling_policy',
  COALESCE(metadata->'family_scheduling_policy','{}'::jsonb)||jsonb_build_object(
   'version','fixed3000-family-round-robin-v2.3',
   'short_pacing_turn_policy','Retain the just-claimed family turn only for a positive shared pacing delay of at most one second',
   'short_pacing_maximum_seconds',1,
   'short_pacing_guard','Current active run and fence; last_claimed_task_id and last_family still match the deferred task',
   'long_wait_policy','Preserve the exact provider deadline and continue normal family rotation',
   'preserved_accounting','Claim turns, task attempts, refunded page attempts, reservations, committed records, pages and useful progress are unchanged by the cursor adjustment',
   'short_pacing_applied_at',clock_timestamp()))
 WHERE id='fixed3000-20250901-20260731-v1-20261030';
COMMIT;
