-- Resume due retries and expired leases before fresh work within each family.
-- Forward-only extension of the already-installed durable family rotation.
BEGIN;
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);

DO $preflight$ BEGIN
 IF to_regclass('astra_ingestion_v1.backfill_family_turn_v2') IS NULL
  OR to_regclass('astra_ingestion_v1.backfill_tasks_recovery_turn_v2') IS NOT NULL THEN
  RAISE EXCEPTION 'Recovery priority requires installed family fairness and must not be replayed';
 END IF;
END $preflight$;

CREATE INDEX backfill_tasks_recovery_turn_v2
 ON astra_ingestion_v1.backfill_tasks_v2(run_id,family,priority,next_retry_at,created_at,id)
 WHERE status IN ('RETRY_WAIT','RUNNING');

DO $wire$
DECLARE d text; candidate text; recovery text; replacement text; start_at integer; end_at integer;
 start_marker text:='  SELECT q.* INTO t FROM astra_ingestion_v1.backfill_tasks_v2 q JOIN astra_ingestion_v1.backfill_runs_v2 rr ON rr.id=q.run_id';
 end_marker text:='   ORDER BY q.priority,q.next_retry_at,q.created_at,q.id LIMIT 1 FOR UPDATE OF q;';
 status_marker text:='AND q.status IN (''PENDING'',''RUNNING'',''RETRY_WAIT'')';
BEGIN
 SELECT pg_get_functiondef('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure) INTO STRICT d;
 IF strpos(d,'backfill_family_fairness_hook_v2')=0 OR strpos(d,'backfill_due_recovery_priority_v2')>0
  OR strpos(d,'q.run_id=v_fair_run AND q.family=v_fair_pick.family')=0
  OR strpos(d,'backfill_breadth_ready_v2(q.id)')=0
  OR strpos(d,'gap.scope->>''reuse_parent''=ANY(q.dependencies)')=0 THEN
  RAISE EXCEPTION 'Unexpected family-fairness runtime; reconcile current definition before recovery prioritization';
 END IF;
 start_at:=strpos(d,start_marker);
 IF start_at=0 THEN RAISE EXCEPTION 'Installed family candidate query is absent'; END IF;
 end_at:=strpos(substr(d,start_at),end_marker);
 IF end_at=0 THEN RAISE EXCEPTION 'Installed candidate ordering is absent'; END IF;
 candidate:=substr(d,start_at,end_at+length(end_marker)-1);
 IF strpos(candidate,status_marker)=0 OR strpos(substr(d,start_at+length(candidate)),start_marker)>0
  OR strpos(candidate,'q.next_retry_at<=v_now')=0 OR strpos(candidate,'q.lease_until<=v_now')=0 THEN
  RAISE EXCEPTION 'Installed candidate/retry/lease guards differ; refusing an ambiguous patch';
 END IF;
 -- Retain every original eligibility condition. The additional status filter
 -- only isolates recovery work for the smaller partial index; live leases,
 -- future retry times, dependencies, provider configuration and fences still gate it.
 recovery:=replace(candidate,status_marker,'AND q.status IN (''RETRY_WAIT'',''RUNNING'')');
 replacement:='  -- backfill_due_recovery_priority_v2: recovery first, then the unchanged normal candidate.'||chr(10)||
  recovery||chr(10)||'  IF NOT FOUND THEN'||chr(10)||candidate||chr(10)||'  END IF;';
 d:=replace(d,candidate,replacement);
 d:=replace(d,'one coherent queue, at most16 indexed family probes.',
  'one coherent queue, at most16 families and32 indexed candidate probes.');
 EXECUTE d;
END $wire$;

UPDATE astra_ingestion_v1.backfill_runs_v2
 SET metadata=metadata||jsonb_build_object('family_scheduling_policy',
  COALESCE(metadata->'family_scheduling_policy','{}'::jsonb)||jsonb_build_object(
   'version','fixed3000-family-round-robin-v2.2',
   'maximum_family_probes_per_claim',16,'maximum_candidate_probes_per_claim',32,
   'within_family_recovery_order','Eligible RETRY_WAIT or expired RUNNING lease before fresh PENDING; priority,next_retry_at,created_at,id within each probe',
   'recovery_preserves','Original retry timestamps, provider pacing, lease/run fences, attempts, immutable scope, reservations and committed counters',
   'recovery_priority_applied_at',clock_timestamp()))
 WHERE id='fixed3000-20250901-20260731-v1-20261030';
COMMIT;
