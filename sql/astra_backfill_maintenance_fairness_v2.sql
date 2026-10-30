-- Let the existing scheduled maintainer wait briefly for a busy worker.
-- No new scheduler, role, credential, provider path or task scope is introduced.
BEGIN;
SET LOCAL statement_timeout='30s';
-- Installation can queue behind one existing ten-second gateway operation;
-- the installed maintainer still waits at most its original two seconds.
SET LOCAL lock_timeout='10s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);
DO $maintenance$
DECLARE d text;
 old_guard text:=' IF NOT pg_try_advisory_xact_lock(706314020261028) THEN RETURN jsonb_build_object(''state'',''BUSY''); END IF;';
 new_guard text:=E' -- backfill_bounded_maintenance_wait_v2: existing two-second lock timeout.\n BEGIN\n  PERFORM pg_advisory_xact_lock(706314020261028);\n EXCEPTION WHEN lock_not_available THEN\n  RETURN jsonb_build_object(''state'',''BUSY'',''reason'',''BOUNDED_WORKER_LOCK_WAIT_EXHAUSTED'');\n END;';
BEGIN
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure) INTO STRICT d;
 IF strpos(d,'backfill_bounded_maintenance_wait_v2')>0 OR strpos(d,old_guard)=0
 OR NOT EXISTS(SELECT 1 FROM pg_proc WHERE oid='astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure
  AND prosecdef AND proconfig @> ARRAY['lock_timeout=2s','statement_timeout=8s']) THEN
  RAISE EXCEPTION 'Maintenance baseline differs or forward is already installed; reconcile before replay';
 END IF;
 EXECUTE replace(d,old_guard,new_guard);
 UPDATE astra_ingestion_v1.backfill_runs_v2 SET metadata=metadata||jsonb_build_object(
  'maintenance_lock_policy',jsonb_build_object('version','BOUNDED_EXISTING_WORKER_LOCK_WAIT_V2',
   'maximum_lock_wait_seconds',2,'operation_timeout_seconds',8,'applied_at',clock_timestamp(),
   'substantive_progress_counter_changed',false))
 WHERE id='fixed3000-20250901-20260731-v1-20261030';
END $maintenance$;
COMMIT;
