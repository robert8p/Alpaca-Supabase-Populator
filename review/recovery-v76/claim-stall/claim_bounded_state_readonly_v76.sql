-- One read-only state snapshot. The root's completed cursor plans are not repeated.
-- 57014 identifies the cancellation location, not the time consumed by this cursor.
-- The preceding identity discover/refresh helpers may consume cumulative budget.
-- No claim/identity/maintenance helper, provider, advisory lock or DML is invoked.
BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL transaction_read_only=on;
SET LOCAL transaction_isolation='repeatable read';
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $claim_bounded_state_readonly_v76$
DECLARE
 r astra_ingestion_v1.backfill_runs_v2%ROWTYPE;
 x record; v_members bigint; v_active integer;
 v_indexes jsonb; v_stats jsonb; v_workers jsonb; v_dependencies jsonb;
 v_turn jsonb; v_samples jsonb; v_result jsonb; v_family_index_valid boolean;
 v_started timestamptz:=clock_timestamp();
BEGIN
 IF current_setting('transaction_read_only')<>'on'
  OR current_setting('transaction_isolation')<>'repeatable read'
  OR current_setting('statement_timeout')<>'8s'
  OR current_setting('lock_timeout')<>'3s' THEN
  RAISE EXCEPTION 'Claim diagnostic requires read-only repeatable-read 8s/3s bounds';
 END IF;
 FOR x IN SELECT * FROM (VALUES
  ('public.astra_ingestion_rpc_v1(text,jsonb)','566d2248b8addac92a5dc2659233fb50f12ae1c55869fc278555da6cbd1ffffb'),
  ('astra_ingestion_v1.rpc_dispatch(text,jsonb)','a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520'),
  ('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)','28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44'),
  ('astra_ingestion_v1.backfill_identity_discover_pending_v2()','faf5e83a8f7baf717cfd9054948ed62a8fbda7aa432a1f671d895fe77db37618'),
  ('astra_ingestion_v1.backfill_identity_refresh_pending_v2(integer)','87ebac87ea08bea09b98f01ae123ed698e8252bcd6ff6abeb1cec3abf6ba5e25')
 ) p(signature,sha256) LOOP
  IF encode(sha256(convert_to(pg_get_functiondef(to_regprocedure(x.signature)),'UTF8')),'hex')
    IS DISTINCT FROM x.sha256 THEN
   RAISE EXCEPTION 'Claim diagnostic source changed; reconcile first';
  END IF;
 END LOOP;
 SELECT * INTO STRICT r FROM astra_ingestion_v1.backfill_runs_v2
 WHERE id='fixed3000-20250901-20260731-v1-20261030';
 SELECT count(*) INTO v_members FROM (SELECT 1 FROM astra_ingestion_v1.backfill_members_v2
  WHERE run_id=r.id LIMIT 3001) m;
 SELECT count(*) INTO v_active FROM (SELECT id FROM astra_ingestion_v1.backfill_runs_v2
  WHERE status='ACTIVE' LIMIT 2) a;
 IF r.status IS DISTINCT FROM 'ACTIVE' OR r.fence IS DISTINCT FROM 1
  OR r.metadata->>'implementation_owner' IS DISTINCT FROM 'root-replacement-20261030T042603Z'
  OR r.cohort_sha256 IS DISTINCT FROM '2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
  OR v_members<>3000 OR v_active<>1 THEN
  RAISE EXCEPTION 'Claim diagnostic scope, owner, fence, active-run uniqueness or membership changed';
 END IF;
 -- Expiry is observed, not renewed. Pure observation does not acquire authority.
 SELECT jsonb_agg(jsonb_build_object('name',n.name,'oid',c.oid,'valid',i.indisvalid,
  'ready',i.indisready,'live',i.indislive,'method',am.amname,
  'definition',pg_get_indexdef(c.oid),'estimated_pages',c.relpages,
  'index_scans',s.idx_scan,'tuples_read',s.idx_tup_read,'tuples_fetched',s.idx_tup_fetch)
  ORDER BY n.name) INTO v_indexes
 FROM (VALUES('backfill_tasks_provider_v2'),('backfill_tasks_family_turn_v2'),
  ('backfill_tasks_recovery_turn_v2'),('backfill_tasks_runnable_v2')) n(name)
 LEFT JOIN pg_namespace ns ON ns.nspname='astra_ingestion_v1'
 LEFT JOIN pg_class c ON c.relnamespace=ns.oid AND c.relname=n.name
 LEFT JOIN pg_index i ON i.indexrelid=c.oid
 LEFT JOIN pg_am am ON am.oid=c.relam
 LEFT JOIN pg_stat_all_indexes s ON s.indexrelid=c.oid;
 SELECT EXISTS(SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
  JOIN pg_namespace ns ON ns.oid=c.relnamespace
  WHERE ns.nspname='astra_ingestion_v1' AND c.relname='backfill_tasks_family_turn_v2'
   AND i.indrelid='astra_ingestion_v1.backfill_tasks_v2'::regclass
   AND i.indisvalid AND i.indisready AND i.indislive
   AND pg_get_indexdef(c.oid)=$definition$CREATE INDEX backfill_tasks_family_turn_v2 ON astra_ingestion_v1.backfill_tasks_v2 USING btree (run_id, family, priority, next_retry_at, created_at, id) WHERE (status = ANY (ARRAY['PENDING'::text, 'RUNNING'::text, 'RETRY_WAIT'::text]))$definition$)
 INTO v_family_index_valid;
 SELECT jsonb_agg(jsonb_build_object('relation',c.relname,'estimated_rows',c.reltuples,
  'estimated_pages',c.relpages,'estimated_live_tuples',s.n_live_tup,'estimated_dead_tuples',s.n_dead_tup,
  'modified_since_analyze',s.n_mod_since_analyze,'last_analyze',s.last_analyze,
  'last_autoanalyze',s.last_autoanalyze,'last_vacuum',s.last_vacuum,'last_autovacuum',s.last_autovacuum)
  ORDER BY c.relname) INTO v_stats
 FROM pg_class c JOIN pg_namespace ns ON ns.oid=c.relnamespace
 LEFT JOIN pg_stat_all_tables s ON s.relid=c.oid
 WHERE ns.nspname='astra_ingestion_v1' AND c.relname IN
  ('backfill_tasks_v2','backfill_workers_v2','backfill_identity_discovered_members_v2',
   'backfill_identity_refresh_v2','backfill_identity_source_members_v2');
 WITH bounded AS MATERIALIZED (
  SELECT worker_id,source_revision,supported_kinds,capability_revision,observed_at
  FROM astra_ingestion_v1.backfill_workers_v2 ORDER BY worker_id LIMIT 257
 ), shown AS (
  SELECT worker_id,source_revision,supported_kinds,capability_revision,observed_at,
   observed_at>v_started-interval '10 minutes' AS observed_within_claim_freshness_window
  FROM bounded ORDER BY observed_at DESC,worker_id LIMIT 8
 )
 SELECT jsonb_build_object('worker_rows_inspected',(SELECT count(*) FROM bounded),
  'worker_population_complete',(SELECT count(*)<257 FROM bounded),
  'latest_eight_within_bounded_population',COALESCE((SELECT jsonb_agg(to_jsonb(w) ORDER BY observed_at DESC,worker_id) FROM shown w),'[]'::jsonb),
  'registration_can_be_rolled_back_by_failed_claim',true) INTO v_workers;
 SELECT COALESCE(jsonb_agg(jsonb_build_object('provider',d.provider,'state',d.state,'code',d.code,
  'observed_at',d.observed_at,'resolved_at',d.resolved_at,'blocked_worker',d.blocked_worker,
  'blocked_revision',d.blocked_revision) ORDER BY d.provider),'[]'::jsonb)
 INTO v_dependencies FROM astra_ingestion_v1.backfill_provider_dependencies_v2 d
 WHERE d.run_id=r.id AND d.provider IN('Alpaca','Massive');
 SELECT jsonb_build_object('next_family_index',next_family_index,'last_family',last_family,
  'last_claimed_task_id',last_claimed_task_id,'claim_turns',claim_turns,'changed_at',changed_at)
 INTO v_turn FROM astra_ingestion_v1.backfill_family_turn_v2 WHERE run_id=r.id;
 v_samples:='[]'::jsonb;
 IF v_family_index_valid THEN
  -- Exactly two ordered queue heads per family; no filtering that forces a full
  -- family scan, dependency traversal, breadth helper or claim lock acquisition.
  WITH families AS (
   SELECT family FROM unnest(ARRAY['REF01','REF03','P01','P02','D01','D02','D03','D04',
    'D05','N01','N02','N03','S01','S02','CTX02','CTX06']) AS f(family)
  ), sampled AS MATERIALIZED (
   SELECT q.* FROM families f CROSS JOIN LATERAL (
    SELECT id,family,kind,provider,status,run_fence,priority,next_retry_at,created_at,
     owner,generation,lease_until,attempt_deadline,page_attempts,page_no,
     requests_reserved,records_committed,last_progress_at,cardinality(dependencies) dependency_count,
     left(error_code,120) error_code
    FROM astra_ingestion_v1.backfill_tasks_v2 q
    WHERE q.run_id=r.id AND q.family=f.family AND q.status IN('PENDING','RUNNING','RETRY_WAIT')
    ORDER BY q.priority,q.next_retry_at,q.created_at,q.id LIMIT 2
   ) q
  )
  SELECT COALESCE(jsonb_agg(to_jsonb(q)||jsonb_build_object(
    'retry_due',q.next_retry_at<=v_started,'attempt_budget_available',q.page_attempts<8,
    'run_fence_matches',q.run_fence=r.fence,
    'lease_condition_ready',(q.status IN('PENDING','RETRY_WAIT') OR
      (q.status='RUNNING' AND q.lease_until<=v_started)),
    'full_claimability_evaluated',false)
    ORDER BY q.family,q.priority,q.next_retry_at,q.created_at,q.id),'[]'::jsonb)
  INTO v_samples FROM sampled q;
 END IF;
 v_result:=jsonb_build_object('probe','claim-bounded-state-readonly-v76',
  'started_at',v_started,'finished_at',clock_timestamp(),
  'source_pins_matched',5,'plan_count',0,
  'run',jsonb_build_object('id',r.id,'status',r.status,'fence',r.fence,
   'owner',r.metadata->>'implementation_owner','lease_until',r.metadata->>'implementation_lease_until',
   'lease_currently_valid',COALESCE((r.metadata->>'implementation_lease_until')::timestamptz>clock_timestamp(),false),
   'pages_committed',r.pages_committed,'physical_records_or_pointers',r.records_committed,
   'requests_reserved',r.requests_reserved,'source_bytes',r.source_bytes,
   'last_progress_at',r.last_progress_at,'planning_complete',r.metadata->'planning_complete'),
  'provider_dependencies',v_dependencies,'workers',v_workers,'family_turn',v_turn,
  'family_queue_heads',v_samples,'family_samples_admitted_by_exact_index',v_family_index_valid,
  'indexes',v_indexes,'relation_statistics_estimates',v_stats,
  'limits',jsonb_build_array('Cancellation location is not cursor elapsed-time attribution.',
    'Preceding identity discover/refresh calls and gate wait can consume the invocation budget.',
    'Root-retained cursor plans are not repeated or timed by this state snapshot.',
    'Two queue heads per family do not prove total runnable population or absence.',
    'Dependencies, reuse gaps and breadth readiness are not evaluated; no full claimability claim.',
    'Worker registrations can roll back with a failed claim; stale registration alone does not prove missing credentials.',
    'Statistics are estimates; run counters are physical accounting, not coverage or a new readback proof.'),
  'application_helpers_invoked',false,'explicit_locks_acquired',false,'mutations',false);
 RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='CLAIM_BOUNDED_STATE_READONLY_V76',DETAIL=v_result::text;
END $claim_bounded_state_readonly_v76$;
ROLLBACK;
