-- Conservative paid-plan pacing for this replacement runtime only.
-- Existing shared Retry-After deadlines and every legacy job limit are retained.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);

DO $pacing$
DECLARE d text;
 old_line text:='UPDATE astra_ingestion_v1.source_limits SET next_request_at=v_epoch+CASE WHEN t.provider=''Alpaca'' THEN 2 ELSE 12 END WHERE id=lower(t.provider);';
 new_line text:='-- backfill_paid_provider_pacing_v2: at most one reservation per second/provider; an existing later deadline still wins.'||chr(10)||
  '   UPDATE astra_ingestion_v1.source_limits SET next_request_at=v_epoch+1 WHERE id=lower(t.provider);';
BEGIN
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure) INTO STRICT d;
 IF strpos(d,'backfill_paid_provider_pacing_v2')>0
  OR (length(d)-length(replace(d,old_line,'')))/length(old_line)<>1 THEN
  RAISE EXCEPTION 'Replacement pacing baseline differs or the migration is already installed; reconcile before retry';
 END IF;
 -- Change only the delay assigned after a successful replacement reservation.
 -- The preceding SELECT FOR UPDATE, later-deadline guard, outer authenticated
 -- advisory lock, per-task attempt/refund logic and cumulative counters remain.
 EXECUTE replace(d,old_line,new_line);
END $pacing$;

UPDATE astra_ingestion_v1.backfill_runs_v2
 SET metadata=metadata||jsonb_build_object('provider_pacing_policy',jsonb_build_object(
  'version','fixed3000-paid-provider-pacing-v2.1',
  'minimum_interval_seconds',jsonb_build_object('Alpaca',1,'Massive',1),
  'application_maximum_reservations_per_minute_per_provider',60,
  'worker_topology','Existing worker service only; no extra workers or instances provisioned',
  'coordination','Existing authenticated RPC advisory lock706314020261028 and shared source_limits row lock',
  'retry_after_policy','Preserve any later stored provider deadline; honour finite Retry-After without reducing it to this baseline',
  'legacy_policy','Original job quotas, deadlines, counters and dispatcher are unchanged',
  'provider_plans',jsonb_build_object(
   'Alpaca',jsonb_build_object('name','Algo Trader Plus','source_ref','https://alpaca.markets/data','application_interval_seconds',1),
   'Massive',jsonb_build_object('name','Stocks Starter','source_ref','https://massive.com/pricing?product=stocks',
    'published_plan_description','Unlimited API Calls','source_verified_by','Controlling engineering owner',
    'source_verified_date','2026-10-30','application_interval_seconds',1)),
  'applied_at',clock_timestamp()))
 WHERE id='fixed3000-20250901-20260731-v1-20261030';

-- Deliberately no UPDATE of source_limits here: a persisted429/Retry-After
-- deadline is evidence, not a baseline setting to reset during deployment.
COMMIT;
