-- Bound runtime status work by task groups and distinct pending kinds.
-- Reporting freshness is now coherent with the existing returned observed_at:
-- a worker expiring during this report remains fresh as of that timestamp.
-- Strict >, JSONB ? semantics, and every claim/admission predicate stay intact.
BEGIN;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $repair$
DECLARE d text;s text;old_branch text;namespace text;start_at integer;end_at integer;
 new_branch text:=$branch$ IF p_operation='backfill_status' THEN
  -- backfill_runtime_status_asof_v2: report freshness uses its advertised v_now.
  -- Claim admission retains its existing live-clock checks unchanged.
  WITH fresh_workers AS MATERIALIZED (
   SELECT supported_kinds FROM astra_ingestion_v1.backfill_workers_v2
   WHERE observed_at>v_now-interval '10 minutes'
  )
  SELECT COALESCE(jsonb_agg(x),'[]') INTO v_result FROM (
   SELECT to_jsonb(r) || astra_ingestion_v1.backfill_identity_progress_v2(r.id) || jsonb_build_object(
    'members',(SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2 m WHERE m.run_id=r.id),
    'tasks',summary.tasks,
    'unsupported_pending_kinds',summary.unsupported_pending_kinds,
    'provider_dependencies',(SELECT COALESCE(jsonb_agg(to_jsonb(d)),'[]') FROM astra_ingestion_v1.backfill_provider_dependencies_v2 d WHERE d.run_id=r.id),
    'next_retry_at',(SELECT min(next_retry_at) FROM astra_ingestion_v1.backfill_tasks_v2 st WHERE st.run_id=r.id AND status='RETRY_WAIT')) AS x
   FROM (SELECT * FROM astra_ingestion_v1.backfill_runs_v2
    WHERE p_payload->>'run_id' IS NULL OR id=p_payload->>'run_id' ORDER BY created_at DESC LIMIT 20) r
   CROSS JOIN LATERAL (
    WITH task_groups AS MATERIALIZED (
     SELECT family,kind,provider,status,count(*) tasks,sum(records_committed) records,max(last_progress_at) last_progress_at
     FROM astra_ingestion_v1.backfill_tasks_v2 WHERE run_id=r.id GROUP BY family,kind,provider,status
    ), pending_kinds AS MATERIALIZED (
     SELECT DISTINCT kind FROM task_groups WHERE status IN ('PENDING','RETRY_WAIT')
    )
    SELECT (SELECT COALESCE(jsonb_agg(z),'[]') FROM task_groups z) tasks,
     (SELECT COALESCE(jsonb_agg(DISTINCT k.kind),'[]') FROM pending_kinds k
      WHERE NOT EXISTS(SELECT 1 FROM fresh_workers w WHERE w.supported_kinds ? k.kind)) unsupported_pending_kinds
   ) summary
   ORDER BY r.created_at DESC
  ) q;
  RETURN jsonb_build_object('runs',v_result,'observed_at',v_now);
$branch$;
BEGIN
 PERFORM pg_catalog.pg_advisory_xact_lock(706314020261028);
 SELECT pg_get_functiondef(p.oid),p.prosrc,n.nspname INTO STRICT d,s,namespace
 FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace
 WHERE p.oid='astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure;
 IF strpos(s,'backfill_runtime_status_asof_v2')>0 THEN
  RAISE EXCEPTION 'Runtime status rewrite already installed; reconcile before replay';
 END IF;
 start_at:=strpos(s,$start$ IF p_operation='backfill_status' THEN$start$);
 end_at:=strpos(s,$end$ ELSIF p_operation='backfill_claim' THEN$end$);
 IF start_at=0 OR end_at<=start_at THEN RAISE EXCEPTION 'Runtime status boundaries changed';END IF;
 old_branch:=substring(s FROM start_at FOR end_at-start_at);
 IF encode(sha256(convert_to(replace(old_branch,namespace,'astra'||'_ingestion_v1'),'UTF8')),'hex')
  <>'ce0465543cc8c06bffa53070be02849adf80454bf0776042a9d32a2f2ae488b2' THEN
  RAISE EXCEPTION 'Runtime status differs from the independently verified live baseline';
 END IF;
 -- pg_get_functiondef preserves signature, volatility, SECURITY mode and config;
 -- CREATE OR REPLACE retains the function OID, owner and existing ACL.
 EXECUTE replace(d,old_branch,new_branch);
END $repair$;
COMMIT;
