-- Estimated plan only; this does not execute the inner status aggregation.
-- Read-only diagnostic of the exact inner backfill_status SELECT used by the
-- dashboard's empty payload. This deliberately excludes the appended delivery
-- report and the outer RPC lock. It is not an authentication or concurrency test.
-- Expected installed status-branch SHA256: ce0465543cc8c06bffa53070be02849adf80454bf0776042a9d32a2f2ae488b2
-- Source: original runtime status branch plus the installed identity-progress
-- projection; subsequent known forwards leave this branch unchanged.
-- Return: one estimated EXPLAIN JSON document with no actual timings/rows.
-- Source/catalog guards execute, but EXPLAIN itself does not run the SELECT.
-- Existing eight-second statement and three-second lock deadlines are retained.
BEGIN;
SET TRANSACTION READ ONLY;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';

DO $guard$
DECLARE source text; actual text; start_at integer; end_at integer;
BEGIN
 SELECT prosrc INTO STRICT source FROM pg_proc
  WHERE oid='astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure;
 start_at:=strpos(source,$start$ IF p_operation='backfill_status' THEN$start$);
 end_at:=strpos(source,$end$ ELSIF p_operation='backfill_claim' THEN$end$);
 IF start_at=0 OR end_at<=start_at THEN
  RAISE EXCEPTION 'Status branch boundaries changed; reconcile before probing';
 END IF;
 actual:=substring(source FROM start_at FOR end_at-start_at);
 IF encode(sha256(convert_to(actual,'UTF8')),'hex')<>'ce0465543cc8c06bffa53070be02849adf80454bf0776042a9d32a2f2ae488b2' THEN
  RAISE EXCEPTION 'Status branch differs from the known installed source; do not run this probe';
 END IF;
 IF EXISTS(SELECT 1 FROM pg_proc WHERE oid='astra_ingestion_v1.backfill_identity_progress_v2(text)'::regprocedure AND provolatile<>'s') THEN
  RAISE EXCEPTION 'Identity status projection is no longer STABLE';
 END IF;
END $guard$;

EXPLAIN (FORMAT JSON)
SELECT COALESCE(jsonb_agg(x),'[]') FROM (
   SELECT to_jsonb(r) || astra_ingestion_v1.backfill_identity_progress_v2(r.id) || jsonb_build_object(
    'members',(SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2 m WHERE m.run_id=r.id),
    'tasks',(SELECT COALESCE(jsonb_agg(z),'[]') FROM (SELECT family,kind,provider,status,count(*) tasks,sum(records_committed) records,max(last_progress_at) last_progress_at
       FROM astra_ingestion_v1.backfill_tasks_v2 WHERE run_id=r.id GROUP BY family,kind,provider,status) z),
    'unsupported_pending_kinds',(SELECT COALESCE(jsonb_agg(DISTINCT st.kind),'[]') FROM astra_ingestion_v1.backfill_tasks_v2 st WHERE st.run_id=r.id AND st.status IN ('PENDING','RETRY_WAIT')
       AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_workers_v2 w WHERE w.observed_at>clock_timestamp()-interval '10 minutes' AND w.supported_kinds ? st.kind)),
    'provider_dependencies',(SELECT COALESCE(jsonb_agg(to_jsonb(d)),'[]') FROM astra_ingestion_v1.backfill_provider_dependencies_v2 d WHERE d.run_id=r.id),
    'next_retry_at',(SELECT min(next_retry_at) FROM astra_ingestion_v1.backfill_tasks_v2 st WHERE st.run_id=r.id AND status='RETRY_WAIT')) AS x
   FROM astra_ingestion_v1.backfill_runs_v2 r WHERE ('{}'::jsonb->>'run_id') IS NULL OR r.id=('{}'::jsonb->>'run_id') ORDER BY r.created_at DESC LIMIT 20
  ) q;

ROLLBACK;
