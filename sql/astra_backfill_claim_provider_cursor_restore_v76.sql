-- v76 claim-provider cursor restore: exact one-query source replacement only.
-- Publish this additive repair and pass exact-head CI before root activation.
-- Existing global gate -> run FOR SHARE; 8s/3s bounds; no helper/provider/permission change.
-- Restore accepts any existing status under unchanged authority; it does not reactivate the run.
BEGIN;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $claim_cursor_restore$
DECLARE
 v_pins constant jsonb := $claim_pins$[{"metadata":{"oid":"15986030","proacl":["postgres=X/postgres","anon=X/postgres"],"proallargtypes":null,"proargdefaults":"({CONST :consttype 3802 :consttypmod -1 :constcollid 0 :constlen -1 :constbyval false :constisnull false :location -1 :constvalue 8 [ 32 0 0 0 0 0 0 32 ]})","proargmodes":null,"proargnames":["operation","payload"],"proargtypes":["25","3802"],"probin":null,"proconfig":["search_path=\"\"","statement_timeout=10s","lock_timeout=3s"],"procost":100,"proisstrict":false,"prokind":"f","prolang":"14","proleakproof":false,"proname":"astra_ingestion_rpc_v1","pronamespace":"2200","pronargdefaults":1,"pronargs":2,"proowner":"16388","proparallel":"u","proretset":false,"prorettype":"3802","prorows":0,"prosecdef":false,"prosqlbody":null,"prosupport":"-","protrftypes":null,"provariadic":"0","provolatile":"v"},"sha256":"566d2248b8addac92a5dc2659233fb50f12ae1c55869fc278555da6cbd1ffffb","signature":"public.astra_ingestion_rpc_v1(text,jsonb)"},{"metadata":{"oid":"15986028","proacl":["astra_ingestion_rpc_owner_v1=X/astra_ingestion_rpc_owner_v1","anon=X/astra_ingestion_rpc_owner_v1"],"proallargtypes":null,"proargdefaults":null,"proargmodes":null,"proargnames":["p_operation","p_payload"],"proargtypes":["25","3802"],"probin":null,"proconfig":["search_path=\"\"","statement_timeout=10s","lock_timeout=3s"],"procost":100,"proisstrict":false,"prokind":"f","prolang":"13619","proleakproof":false,"proname":"rpc_dispatch","pronamespace":"15984556","pronargdefaults":0,"pronargs":2,"proowner":"15985999","proparallel":"u","proretset":false,"prorettype":"3802","prorows":0,"prosecdef":true,"prosqlbody":null,"prosupport":"-","protrftypes":null,"provariadic":"0","provolatile":"v"},"sha256":"a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520","signature":"astra_ingestion_v1.rpc_dispatch(text,jsonb)"},{"metadata":{"oid":"16047703","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"proallargtypes":null,"proargdefaults":null,"proargmodes":null,"proargnames":null,"proargtypes":[],"probin":null,"proconfig":["search_path=\"\""],"procost":100,"proisstrict":false,"prokind":"f","prolang":"13619","proleakproof":false,"proname":"backfill_identity_discover_pending_v2","pronamespace":"15984556","pronargdefaults":0,"pronargs":0,"proowner":"16388","proparallel":"u","proretset":false,"prorettype":"23","prorows":0,"prosecdef":false,"prosqlbody":null,"prosupport":"-","protrftypes":null,"provariadic":"0","provolatile":"v"},"sha256":"faf5e83a8f7baf717cfd9054948ed62a8fbda7aa432a1f671d895fe77db37618","signature":"astra_ingestion_v1.backfill_identity_discover_pending_v2()"},{"metadata":{"oid":"16047730","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"proallargtypes":null,"proargdefaults":"({CONST :consttype 23 :consttypmod -1 :constcollid 0 :constlen 4 :constbyval true :constisnull false :location -1 :constvalue 4 [ 2 0 0 0 0 0 0 0 ]})","proargmodes":null,"proargnames":["p_limit"],"proargtypes":["23"],"probin":null,"proconfig":["search_path=\"\"","statement_timeout=8s"],"procost":100,"proisstrict":false,"prokind":"f","prolang":"13619","proleakproof":false,"proname":"backfill_identity_refresh_pending_v2","pronamespace":"15984556","pronargdefaults":1,"pronargs":1,"proowner":"16388","proparallel":"u","proretset":false,"prorettype":"23","prorows":0,"prosecdef":false,"prosqlbody":null,"prosupport":"-","protrftypes":null,"provariadic":"0","provolatile":"v"},"sha256":"87ebac87ea08bea09b98f01ae123ed698e8252bcd6ff6abeb1cec3abf6ba5e25","signature":"astra_ingestion_v1.backfill_identity_refresh_pending_v2(integer)"},{"metadata":{"oid":"16050105","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"proallargtypes":null,"proargdefaults":null,"proargmodes":null,"proargnames":["p_run","p_keys"],"proargtypes":["25","3802"],"probin":null,"proconfig":["search_path=\"\""],"procost":100,"proisstrict":false,"prokind":"f","prolang":"13619","proleakproof":false,"proname":"backfill_shared_refresh_v2","pronamespace":"15984556","pronargdefaults":0,"pronargs":2,"proowner":"16388","proparallel":"u","proretset":false,"prorettype":"2278","prorows":0,"prosecdef":false,"prosqlbody":null,"prosupport":"-","protrftypes":null,"provariadic":"0","provolatile":"v"},"sha256":"7f538bf47cb5e74050c20266e01cbe9d6521c1a65663aaf2e0fe38d62041f1a4","signature":"astra_ingestion_v1.backfill_shared_refresh_v2(text,jsonb)"},{"metadata_sha256":"4497ec91787767ee138d167beb19970a5289f9baec3d01c9eeda6962a8d0460d","oid":"16041463","sha256":"6c880114a645c8a9167d5260c4aeabf58a10617c4244cf0340be1d6cf4bf0ce7","signature":"astra_ingestion_v1.backfill_maintain_v2(integer)"},{"metadata_sha256":"437fe86234dcef0e89c0a5137707b3dc5da780c5a10dbd376f25e6c70e39a595","oid":"16041451","sha256":"0ccd4018d16e3ed3932176d2886fe78c2c1b442d70473d71e137d86e7b6dfb37","signature":"astra_ingestion_v1.backfill_recheck_page_v2(text,integer)"}]$claim_pins$::jsonb;
 v_expected_metadata constant jsonb := $claim_metadata${"oid":"16040232","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"proallargtypes":null,"proargdefaults":null,"proargmodes":null,"proargnames":["p_operation","p_payload"],"proargtypes":["25","3802"],"probin":null,"proconfig":["search_path=\"\""],"procost":100,"proisstrict":false,"prokind":"f","prolang":"13619","proleakproof":false,"proname":"backfill_dispatch_v2","pronamespace":"15984556","pronargdefaults":0,"pronargs":2,"proowner":"16388","proparallel":"u","proretset":false,"prorettype":"3802","prorows":0,"prosecdef":false,"prosqlbody":null,"prosupport":"-","protrftypes":null,"provariadic":"0","provolatile":"v"}$claim_metadata$::jsonb;
 v_replacement constant text := $claim_replacement$CREATE OR REPLACE FUNCTION astra_ingestion_v1.backfill_dispatch_v2(p_operation text, p_payload jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
DECLARE t astra_ingestion_v1.backfill_tasks_v2; p astra_ingestion_v1.backfill_pages_v2;
 v_now timestamptz:=clock_timestamp(); v_claim jsonb; v_owner text; v_lease int; v_supported jsonb; v_result jsonb;
 v_count int; v_hash text; v_raw text; v_cursor jsonb; v_state text; v_delay double precision; v_retry boolean; v_page int;
 v_parsed jsonb; v_source_rows jsonb; v_submitted_rows jsonb; v_source_cursor text; v_source_url text;
 v_members jsonb; v_contracts jsonb; v_symbols jsonb; v_child_scope jsonb; v_child_id text; v_record jsonb; v_group int; v_kind text;
 v_after_task text; v_after_page int; v_limit int; v_pages jsonb; v_last jsonb; v_more boolean;
 v_dependency record; v_capability_revision text; v_dependency_code text;
 v_not_before double precision; v_epoch double precision;
 v_fair_run text; v_fair_start integer; v_fair_pick record; v_fair_selected boolean;
BEGIN
 -- backfill_retained_reader_v2: invoked only after existing worker authentication.
 IF p_operation='backfill_reuse_commit' THEN RETURN astra_ingestion_v1.backfill_reuse_commit_v2(p_payload); END IF;
 -- backfill_retained_verify_v2: committed pointer, no fabricated live lease.
 IF p_operation='backfill_reuse_verify' THEN RETURN astra_ingestion_v1.backfill_reuse_verify_v2(p_payload->>'task_id',(p_payload->>'page_no')::integer); END IF;
 IF p_operation='backfill_feature_reuse_commit' THEN RETURN astra_ingestion_v1.backfill_feature_reuse_commit_v2(p_payload); END IF;
 IF p_operation='backfill_feature_reuse_verify' THEN RETURN astra_ingestion_v1.backfill_feature_reuse_verify_v2(p_payload->>'task_id',(p_payload->>'page_no')::int); END IF;
 IF p_operation='backfill_reuse_read' THEN RETURN astra_ingestion_v1.backfill_reuse_read_v2(p_payload); END IF;
 IF p_operation='backfill_breadth_material' THEN RETURN astra_ingestion_v1.backfill_breadth_material_v2(p_payload); END IF;
 IF p_operation='backfill_breadth_project' THEN RETURN astra_ingestion_v1.backfill_breadth_project_pending_v2(COALESCE((p_payload->>'limit')::integer,2)); END IF;
 IF p_operation='backfill_identity_material' THEN RETURN astra_ingestion_v1.backfill_identity_material_v2(p_payload); END IF;
 IF p_operation='backfill_identity_source_read' THEN RETURN astra_ingestion_v1.backfill_identity_source_read_v2(p_payload); END IF;
 IF p_operation='backfill_identity_source_commit' THEN RETURN astra_ingestion_v1.backfill_identity_source_commit_v2(p_payload); END IF;
 IF p_operation='backfill_identity_refresh' THEN RETURN jsonb_build_object('queued',astra_ingestion_v1.backfill_identity_refresh_pending_v2(COALESCE((p_payload->>'limit')::int,2))); END IF;
 IF p_operation='backfill_massive_archive_read' THEN RETURN astra_ingestion_v1.backfill_massive_archive_read_v2(p_payload);END IF;
 IF p_operation='backfill_massive_archive_commit' THEN RETURN astra_ingestion_v1.backfill_massive_archive_commit_v2(p_payload);END IF;
 IF p_operation='backfill_massive_archive_verify' THEN RETURN astra_ingestion_v1.backfill_massive_archive_verify_v2(p_payload->>'task_id',(p_payload->>'page_no')::int);END IF;
 IF p_operation='backfill_status' THEN
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
 ELSIF p_operation='backfill_claim' THEN
  PERFORM astra_ingestion_v1.backfill_identity_discover_pending_v2();
  PERFORM astra_ingestion_v1.backfill_identity_refresh_pending_v2(2);
  v_now:=clock_timestamp();
  v_owner:=p_payload->>'worker_id'; v_supported:=p_payload->'supported_kinds';
  IF v_owner IS NULL OR v_owner !~ '^[A-Za-z0-9_.:-]{1,160}$' OR jsonb_typeof(v_supported) IS DISTINCT FROM 'array' OR jsonb_array_length(v_supported)>32
   OR COALESCE(length(p_payload->>'source_revision'),0) NOT BETWEEN 1 AND 100 THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Invalid bounded worker capabilities'; END IF;
  v_lease:=GREATEST(30,LEAST(COALESCE((p_payload->>'lease_seconds')::int,120),300));
  v_capability_revision:=COALESCE(p_payload->>'capability_revision',encode(sha256(convert_to(p_payload->>'source_revision'||':'||astra_ingestion_v1.rpc_canonical(v_supported),'UTF8')),'hex'));
  IF length(v_capability_revision) NOT BETWEEN 1 AND 160 THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Invalid capability revision'; END IF;
  INSERT INTO astra_ingestion_v1.backfill_workers_v2(worker_id,source_revision,supported_kinds,capability_revision,observed_at)
   VALUES(v_owner,p_payload->>'source_revision',v_supported,v_capability_revision,v_now) ON CONFLICT(worker_id) DO UPDATE SET source_revision=EXCLUDED.source_revision,supported_kinds=EXCLUDED.supported_kinds,capability_revision=EXCLUDED.capability_revision,observed_at=v_now;
  -- Missing runtime configuration is one durable provider dependency; it does
  -- not consume attempts or request reservations for every waiting task.
  FOR v_dependency IN
   SELECT rr.id run_id,pp.provider FROM astra_ingestion_v1.backfill_runs_v2 rr CROSS JOIN (VALUES('Alpaca'),('Massive')) pp(provider)
   WHERE rr.status='ACTIVE' AND EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 st WHERE st.run_id=rr.id AND st.provider=pp.provider AND st.status IN ('PENDING','RETRY_WAIT','BLOCKED_EXTERNAL'))
  LOOP
   IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_workers_v2 w WHERE w.observed_at>v_now-interval '10 minutes'
    AND EXISTS(SELECT 1 FROM jsonb_array_elements_text(w.supported_kinds) k WHERE k LIKE lower(v_dependency.provider)||'_%')) THEN
    INSERT INTO astra_ingestion_v1.backfill_provider_dependencies_v2(run_id,provider,dependency,state,code,evidence)
     VALUES(v_dependency.run_id,v_dependency.provider,upper(v_dependency.provider)||'_WORKER_CREDENTIAL','BLOCKED_EXTERNAL','RUNTIME_CAPABILITY_UNAVAILABLE',jsonb_build_object('observed_at',v_now,'reason','No recently registered worker advertises this provider capability'))
     ON CONFLICT(run_id,provider) DO UPDATE SET state='BLOCKED_EXTERNAL',code=EXCLUDED.code,evidence=EXCLUDED.evidence,observed_at=v_now,resolved_at=NULL
      WHERE astra_ingestion_v1.backfill_provider_dependencies_v2.state='AVAILABLE';
   ELSE
    UPDATE astra_ingestion_v1.backfill_provider_dependencies_v2 d SET state='AVAILABLE',resolved_at=v_now,observed_at=v_now,
      evidence=d.evidence||jsonb_build_object('resolution','Changed configured worker capability observed','resolved_at',v_now)
     WHERE d.run_id=v_dependency.run_id AND d.provider=v_dependency.provider AND d.state='BLOCKED_EXTERNAL'
      AND EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_workers_v2 w WHERE w.observed_at>v_now-interval '10 minutes'
       AND (d.code='RUNTIME_CAPABILITY_UNAVAILABLE' OR w.worker_id IS DISTINCT FROM d.blocked_worker OR w.capability_revision IS DISTINCT FROM d.blocked_revision)
       AND EXISTS(SELECT 1 FROM jsonb_array_elements_text(w.supported_kinds) k WHERE k LIKE lower(d.provider)||'_%'));
    UPDATE astra_ingestion_v1.backfill_tasks_v2 st SET status='PENDING',next_retry_at=v_now,error_code=NULL,error_message=NULL
     WHERE st.run_id=v_dependency.run_id AND st.provider=v_dependency.provider AND st.status='BLOCKED_EXTERNAL' AND st.error_code='MISSING_PROVIDER_CREDENTIAL'
      AND EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_provider_dependencies_v2 d WHERE d.run_id=st.run_id AND d.provider=st.provider AND d.state='AVAILABLE');
   END IF;
  END LOOP;
  -- Exhaustion stays an operational failure, never a provider-gap terminal result.
  UPDATE astra_ingestion_v1.backfill_tasks_v2 SET status='OPERATIONAL_ERROR',owner=NULL,lease_until=NULL,error_code='ATTEMPT_BUDGET_EXHAUSTED',error_message='Eight bounded attempts exhausted; implementation recovery must diagnose before requeue'
   WHERE status='RUNNING' AND lease_until<=v_now AND page_attempts>=8;

  -- backfill_family_fairness_hook_v2: one coherent queue, at most16 families and32 indexed candidate probes.
  SELECT id INTO v_fair_run FROM astra_ingestion_v1.backfill_runs_v2 WHERE status='ACTIVE' ORDER BY created_at,id LIMIT 1;
  IF v_fair_run IS NULL THEN RETURN NULL; END IF;
  INSERT INTO astra_ingestion_v1.backfill_family_turn_v2(run_id) VALUES(v_fair_run) ON CONFLICT(run_id) DO NOTHING;
  SELECT next_family_index INTO STRICT v_fair_start FROM astra_ingestion_v1.backfill_family_turn_v2 WHERE run_id=v_fair_run FOR UPDATE;
  v_fair_selected:=false;
  FOR v_fair_pick IN
   SELECT family,ordinality::integer family_index
   FROM unnest(ARRAY['REF01','REF03','P01','P02','D01','D02','D03','D04','D05','N01','N02','N03','S01','S02','CTX02','CTX06']) WITH ORDINALITY f(family,ordinality)
   ORDER BY mod(ordinality::integer-v_fair_start+16,16)
  LOOP
  -- backfill_due_recovery_priority_v2: recovery first, then the unchanged normal candidate.
  SELECT q.* INTO t FROM astra_ingestion_v1.backfill_tasks_v2 q JOIN astra_ingestion_v1.backfill_runs_v2 rr ON rr.id=q.run_id
   WHERE q.run_id=v_fair_run AND q.family=v_fair_pick.family
    AND q.status IN ('RETRY_WAIT','RUNNING') AND rr.status='ACTIVE' AND rr.fence=q.run_fence AND q.kind = ANY(ARRAY(SELECT jsonb_array_elements_text(v_supported)))
    AND q.next_retry_at<=v_now AND q.page_attempts<8
    AND (q.status IN ('PENDING','RETRY_WAIT') OR (q.status='RUNNING' AND q.lease_until<=v_now))
    AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_provider_dependencies_v2 d WHERE d.run_id=q.run_id AND d.provider=q.provider AND d.state='BLOCKED_EXTERNAL')
    AND NOT EXISTS(SELECT 1 FROM unnest(q.dependencies) dep LEFT JOIN astra_ingestion_v1.backfill_tasks_v2 d ON d.id=dep
      WHERE d.id IS NULL OR d.run_id<>q.run_id OR d.status NOT IN ('INGESTED','NO_DATA_RETURNED','NOT_APPLICABLE','PROVIDER_LIMITATION','IDENTITY_OR_QUALITY_UNRESOLVED'))
    AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 gap WHERE gap.run_id=q.run_id AND gap.scope ? 'reuse_parent' AND gap.scope->>'reuse_parent'=ANY(q.dependencies) AND gap.status NOT IN ('INGESTED','NO_DATA_RETURNED','NOT_APPLICABLE','PROVIDER_LIMITATION','IDENTITY_OR_QUALITY_UNRESOLVED'))
    AND (q.kind<>'derive_breadth' OR astra_ingestion_v1.backfill_breadth_ready_v2(q.id))
    AND (SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2 m WHERE m.run_id=v_fair_run)=3000 /* backfill_claim_member_count_once_v2 */
   ORDER BY q.priority,q.next_retry_at,q.created_at,q.id LIMIT 1 FOR UPDATE OF q;
  IF NOT FOUND THEN
  SELECT q.* INTO t FROM astra_ingestion_v1.backfill_tasks_v2 q JOIN astra_ingestion_v1.backfill_runs_v2 rr ON rr.id=q.run_id
   WHERE q.run_id=v_fair_run AND q.family=v_fair_pick.family
    AND q.status IN ('PENDING','RUNNING','RETRY_WAIT') AND rr.status='ACTIVE' AND rr.fence=q.run_fence AND q.kind = ANY(ARRAY(SELECT jsonb_array_elements_text(v_supported)))
    AND q.next_retry_at<=v_now AND q.page_attempts<8
    AND (q.status IN ('PENDING','RETRY_WAIT') OR (q.status='RUNNING' AND q.lease_until<=v_now))
    AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_provider_dependencies_v2 d WHERE d.run_id=q.run_id AND d.provider=q.provider AND d.state='BLOCKED_EXTERNAL')
    AND NOT EXISTS(SELECT 1 FROM unnest(q.dependencies) dep LEFT JOIN astra_ingestion_v1.backfill_tasks_v2 d ON d.id=dep
      WHERE d.id IS NULL OR d.run_id<>q.run_id OR d.status NOT IN ('INGESTED','NO_DATA_RETURNED','NOT_APPLICABLE','PROVIDER_LIMITATION','IDENTITY_OR_QUALITY_UNRESOLVED'))
    AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 gap WHERE gap.run_id=q.run_id AND gap.scope ? 'reuse_parent' AND gap.scope->>'reuse_parent'=ANY(q.dependencies) AND gap.status NOT IN ('INGESTED','NO_DATA_RETURNED','NOT_APPLICABLE','PROVIDER_LIMITATION','IDENTITY_OR_QUALITY_UNRESOLVED'))
    AND (q.kind<>'derive_breadth' OR astra_ingestion_v1.backfill_breadth_ready_v2(q.id))
    AND (SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2 m WHERE m.run_id=v_fair_run)=3000 /* backfill_claim_member_count_once_v2 */
   ORDER BY q.priority,q.next_retry_at,q.created_at,q.id LIMIT 1 FOR UPDATE OF q;
  END IF;
   IF FOUND THEN
    v_fair_selected:=true;
    UPDATE astra_ingestion_v1.backfill_family_turn_v2
     SET next_family_index=(v_fair_pick.family_index%16)+1,last_family=t.family,last_claimed_task_id=t.id,
      claim_turns=claim_turns+1,changed_at=v_now WHERE run_id=v_fair_run;
    EXIT;
   END IF;
  END LOOP;
  IF NOT v_fair_selected THEN RETURN NULL; END IF;

  UPDATE astra_ingestion_v1.backfill_tasks_v2 SET status='RUNNING',owner=v_owner,generation=generation+1,lease_until=v_now+make_interval(secs=>v_lease),attempt_deadline=v_now+interval '5 minutes',
    page_limit=COALESCE(page_limit,CASE WHEN kind='massive_news' AND (cursor IS NULL OR cursor='null'::jsonb) THEN 100 ELSE astra_ingestion_v1.backfill_page_limit_cap_v2(kind) END),attempts=attempts+1,page_attempts=page_attempts+1,reserved_generation=NULL,reserved_page_no=NULL,reserved_at=NULL,source_revision=p_payload->>'source_revision'
   WHERE id=t.id RETURNING * INTO t;
  RETURN to_jsonb(t);
 END IF;
 v_claim:=p_payload->'claim';
 -- Readback never replays a mutation or requires a live lease; exact claim/run binding still applies.
 IF p_operation='backfill_verify' THEN
  SELECT * INTO t FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=v_claim->>'id' AND run_id=v_claim->>'run_id';
  IF NOT FOUND THEN RAISE EXCEPTION USING ERRCODE='AI004',MESSAGE='Replacement task not found'; END IF;
  v_page:=COALESCE((p_payload->>'page_no')::int,t.page_no-1);
  SELECT * INTO p FROM astra_ingestion_v1.backfill_pages_v2 WHERE task_id=t.id AND page_no=v_page;
  IF NOT FOUND THEN RETURN jsonb_build_object('state','not_committed','task_id',t.id,'page_no',v_page,'task_status',t.status,'next_page_no',t.page_no); END IF;
  RETURN jsonb_build_object('state','committed','task_id',t.id,'page_no',p.page_no,'body_sha256',p.body_sha256,
    'readback_sha256',encode(sha256(convert_to(p.raw_body,'UTF8')),'hex'),'records_sha256',p.records_sha256,'record_count',p.record_count,
    'next_cursor',p.cursor_out,'next_page_no',t.page_no,'task_status',t.status,'raw_body',p.raw_body,'request',p.request,'quality',p.quality,'adapter_version',p.adapter_version);
 END IF;
 -- A duplicate after a lost HTTP acknowledgement is an immutable matching-commit receipt, not a second write.
 IF p_operation='backfill_commit' AND v_claim->>'id' IS NOT NULL THEN
  SELECT * INTO p FROM astra_ingestion_v1.backfill_pages_v2 WHERE task_id=v_claim->>'id' AND page_no=(v_claim->>'page_no')::int;
  IF FOUND THEN
   IF p.run_id IS DISTINCT FROM v_claim->>'run_id' OR p.generation::text IS DISTINCT FROM v_claim->>'generation'
    OR p.run_fence::text IS DISTINCT FROM v_claim->>'run_fence' OR p.body_sha256 IS DISTINCT FROM p_payload->>'body_sha256' THEN
     RAISE EXCEPTION USING ERRCODE='AI001',MESSAGE='Existing replacement receipt differs from original commit'; END IF;
   RETURN jsonb_build_object('state','already_committed','task_id',p.task_id,'page_no',p.page_no,'body_sha256',p.body_sha256,'record_count',p.record_count,'next_cursor',p.cursor_out);
  END IF;
 END IF;
 t:=astra_ingestion_v1.backfill_owned_v2(v_claim);
 IF p_operation='backfill_work' THEN RETURN to_jsonb(t);
 ELSIF p_operation='backfill_reserve' THEN
  IF t.reserved_generation=t.generation AND t.reserved_page_no=t.page_no THEN RETURN jsonb_build_object('state','already_reserved','task_id',t.id,'page_no',t.page_no); END IF;
  IF t.provider IN ('Alpaca','Massive') THEN
   v_epoch:=extract(epoch FROM v_now);
   SELECT next_request_at INTO STRICT v_not_before FROM astra_ingestion_v1.source_limits WHERE id=lower(t.provider) FOR UPDATE;
   IF v_not_before>v_epoch THEN
    UPDATE astra_ingestion_v1.backfill_tasks_v2 SET status='RETRY_WAIT',owner=NULL,lease_until=NULL,next_retry_at=to_timestamp(v_not_before),page_attempts=GREATEST(0,page_attempts-1) WHERE id=t.id;

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
    RETURN jsonb_build_object('state','request_deferred','task_id',t.id,'page_no',t.page_no,'next_retry_at',to_timestamp(v_not_before));
   END IF;
   -- backfill_paid_provider_pacing_v2: at most one reservation per second/provider; an existing later deadline still wins.
   UPDATE astra_ingestion_v1.source_limits SET next_request_at=v_epoch+1 WHERE id=lower(t.provider);
  END IF;
  UPDATE astra_ingestion_v1.backfill_tasks_v2 SET reserved_generation=generation,reserved_page_no=page_no,reserved_at=v_now,
    requests_reserved=requests_reserved+CASE WHEN provider IN ('Alpaca','Massive') THEN 1 ELSE 0 END WHERE id=t.id;
  UPDATE astra_ingestion_v1.backfill_runs_v2 SET requests_reserved=requests_reserved+CASE WHEN t.provider IN ('Alpaca','Massive') THEN 1 ELSE 0 END WHERE id=t.run_id;
  RETURN jsonb_build_object('state','reserved','task_id',t.id,'page_no',t.page_no,'query_scope',t.scope,'cursor',t.cursor,'lease_until',t.lease_until);

 ELSIF p_operation='backfill_defer' THEN
  -- backfill_adaptive_page_dispatch_v2: already authenticated, locked and fenced.
  IF p_payload->>'code'='SOURCE_PAGE_TOO_LARGE' THEN
   p_payload:=astra_ingestion_v1.backfill_adapt_page_v2(t,p_payload);
   t:=astra_ingestion_v1.backfill_owned_v2(v_claim);
  END IF;
  v_retry:=COALESCE((p_payload->>'retryable')::boolean,false);
  IF length(COALESCE(p_payload->>'code','')) NOT BETWEEN 1 AND 120 OR octet_length(COALESCE(p_payload->'evidence','{}')::text)>4194304 THEN
    RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Invalid bounded failure evidence'; END IF;
  v_delay:=GREATEST(2,COALESCE((p_payload->>'retry_after')::double precision,0),LEAST(3600,power(2,GREATEST(1,t.page_attempts))));
  IF v_delay IN ('Infinity'::double precision,'-Infinity'::double precision,'NaN'::double precision) OR extract(epoch FROM v_now)+v_delay>253402300799 THEN
   RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Retry-After must be a finite representable interval'; END IF;
  v_state:=CASE WHEN v_retry AND t.page_attempts<8 THEN 'RETRY_WAIT'
    WHEN p_payload->>'code' IN ('BLOCKED_EXTERNAL','AUTHENTICATION_FAILED','MISSING_CREDENTIAL','MISSING_PROVIDER_CREDENTIAL','PROVIDER_FORBIDDEN') THEN 'BLOCKED_EXTERNAL' ELSE 'OPERATIONAL_ERROR' END;
  IF t.provider IN ('Alpaca','Massive') AND (p_payload#>>'{evidence,http_status}'='429' OR p_payload->>'code' IN ('SOURCE_RATE_LIMIT','PROVIDER_RATE_LIMIT')) THEN
   UPDATE astra_ingestion_v1.source_limits SET next_request_at=GREATEST(next_request_at,extract(epoch FROM v_now)+v_delay) WHERE id=lower(t.provider);
  END IF;
  v_dependency_code:=p_payload#>>'{evidence,dependency}';
  IF t.provider IN ('Alpaca','Massive') AND v_dependency_code=upper(t.provider)||'_WORKER_CREDENTIAL' THEN
   v_state:='BLOCKED_EXTERNAL';
   SELECT capability_revision INTO v_capability_revision FROM astra_ingestion_v1.backfill_workers_v2 WHERE worker_id=t.owner;
   INSERT INTO astra_ingestion_v1.backfill_provider_dependencies_v2(run_id,provider,dependency,state,code,evidence,blocked_worker,blocked_revision)
    VALUES(t.run_id,t.provider,v_dependency_code,v_state,'MISSING_PROVIDER_CREDENTIAL',COALESCE(p_payload->'evidence','{}'),t.owner,v_capability_revision)
    ON CONFLICT(run_id,provider) DO UPDATE SET state=EXCLUDED.state,code=EXCLUDED.code,evidence=EXCLUDED.evidence,blocked_worker=EXCLUDED.blocked_worker,blocked_revision=EXCLUDED.blocked_revision,observed_at=v_now,resolved_at=NULL;
  END IF;
  INSERT INTO astra_ingestion_v1.backfill_exceptions_v2(run_id,task_id,page_no,generation,state,code,message,evidence,next_retry_at)
   VALUES(t.run_id,t.id,t.page_no,t.generation,v_state,p_payload->>'code',left(COALESCE(p_payload->>'message','Operation failed'),1000),COALESCE(p_payload->'evidence','{}'),CASE WHEN v_state='RETRY_WAIT' THEN v_now+make_interval(secs=>v_delay) END);
  UPDATE astra_ingestion_v1.backfill_tasks_v2 SET status=v_state,owner=NULL,lease_until=NULL,next_retry_at=v_now+make_interval(secs=>v_delay),error_code=CASE WHEN v_dependency_code=upper(t.provider)||'_WORKER_CREDENTIAL' THEN 'MISSING_PROVIDER_CREDENTIAL' ELSE p_payload->>'code' END,error_message=left(p_payload->>'message',1000) WHERE id=t.id;
  RETURN jsonb_build_object('state',v_state,'task_id',t.id,'next_retry_at',CASE WHEN v_state='RETRY_WAIT' THEN v_now+make_interval(secs=>v_delay) END,'page_attempts',t.page_attempts);
 ELSIF p_operation='backfill_material' THEN
  UPDATE astra_ingestion_v1.backfill_tasks_v2 SET lease_until=LEAST(attempt_deadline,v_now+interval '120 seconds') WHERE id=t.id;
  v_after_task:=COALESCE(p_payload#>>'{after,task_id}',''); v_after_page:=COALESCE((p_payload#>>'{after,page_no}')::int,-1); v_limit:=GREATEST(1,LEAST(COALESCE((p_payload->>'limit')::int,2),4));
  SELECT COALESCE(jsonb_agg(x ORDER BY task_id,page_no),'[]') INTO v_pages FROM (
   SELECT pg.task_id,pg.page_no,jsonb_build_object('id',d.id,'kind',d.kind,'family',d.family,'provider',d.provider,'scope',d.scope,'cursor',pg.cursor_in) AS task,
    pg.raw_body,pg.body_sha256,pg.request,pg.record_count,pg.quality,pg.adapter_version
   FROM astra_ingestion_v1.backfill_pages_v2 pg JOIN astra_ingestion_v1.backfill_tasks_v2 d ON d.id=pg.task_id
   WHERE (pg.task_id=ANY(t.dependencies) OR pg.task_id IN (SELECT gap.id FROM astra_ingestion_v1.backfill_tasks_v2 gap WHERE gap.run_id=t.run_id AND gap.scope ? 'reuse_parent' AND gap.scope->>'reuse_parent'=ANY(t.dependencies))) AND pg.run_id=t.run_id AND (pg.task_id,pg.page_no)>(v_after_task,v_after_page)
   ORDER BY pg.task_id,pg.page_no LIMIT v_limit
  ) x;
  IF jsonb_array_length(v_pages)>0 THEN v_last:=v_pages->(jsonb_array_length(v_pages)-1); v_after_task:=v_last->>'task_id';v_after_page:=(v_last->>'page_no')::int; END IF;
  SELECT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_pages_v2 pg WHERE (pg.task_id=ANY(t.dependencies) OR pg.task_id IN (SELECT gap.id FROM astra_ingestion_v1.backfill_tasks_v2 gap WHERE gap.run_id=t.run_id AND gap.scope ? 'reuse_parent' AND gap.scope->>'reuse_parent'=ANY(t.dependencies))) AND pg.run_id=t.run_id AND (pg.task_id,pg.page_no)>(v_after_task,v_after_page)) INTO v_more;
  RETURN jsonb_build_object('pages',v_pages,'next_after',CASE WHEN v_more THEN jsonb_build_object('task_id',v_after_task,'page_no',v_after_page) END,'complete',NOT v_more,
    'dependency_states',(SELECT COALESCE(jsonb_agg(jsonb_build_object('id',id,'status',status,'error_code',error_code)),'[]') FROM astra_ingestion_v1.backfill_tasks_v2 WHERE id=ANY(t.dependencies)));
 ELSIF p_operation<>'backfill_commit' THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Unsupported replacement operation';
 END IF;
 IF t.provider IN ('Alpaca','Massive') AND (t.reserved_generation IS DISTINCT FROM t.generation OR t.reserved_page_no IS DISTINCT FROM t.page_no) THEN
   RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Page request must be durably reserved before dispatch'; END IF;
 v_raw:=p_payload->>'raw_body'; v_hash:=encode(sha256(convert_to(v_raw,'UTF8')),'hex');
 IF v_raw IS NULL OR octet_length(v_raw)>4194304 OR v_hash IS DISTINCT FROM p_payload->>'body_sha256'
  OR jsonb_typeof(p_payload->'records') IS DISTINCT FROM 'array' OR jsonb_array_length(p_payload->'records')>100000
  OR (p_payload->>'http_status')::int<>200 OR NOT astra_ingestion_v1.backfill_request_valid_v2(t,p_payload->'request')
  OR length(COALESCE(p_payload->>'adapter_version','')) NOT BETWEEN 1 AND 100
 THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Replacement source digest, request scope or page shape is invalid'; END IF;
 PERFORM astra_ingestion_v1.rpc_json_unique(v_raw::json);
 v_parsed:=v_raw::jsonb;
 IF t.kind IN ('alpaca_stock_bars','alpaca_option_bars') THEN
   SELECT COALESCE(jsonb_agg(b.value ORDER BY b.value::text),'[]') INTO v_source_rows
     FROM jsonb_each(COALESCE(NULLIF(v_parsed->'bars','null'::jsonb),'{}')) s CROSS JOIN LATERAL jsonb_array_elements(s.value) b;
 ELSIF t.kind='alpaca_reference' THEN v_source_rows:=jsonb_build_array(v_parsed);
 ELSIF t.kind='alpaca_option_contracts' THEN
   SELECT COALESCE(jsonb_agg(value ORDER BY value::text),'[]') INTO v_source_rows FROM jsonb_array_elements(COALESCE(NULLIF(v_parsed->'option_contracts','null'::jsonb),'[]'));
 ELSIF t.kind='alpaca_news' THEN
   SELECT COALESCE(jsonb_agg(value ORDER BY value::text),'[]') INTO v_source_rows FROM jsonb_array_elements(COALESCE(NULLIF(v_parsed->'news','null'::jsonb),'[]'));
 ELSIF t.kind='alpaca_actions' THEN
   SELECT COALESCE(jsonb_agg(b.value ORDER BY b.value::text),'[]') INTO v_source_rows
     FROM jsonb_each(COALESCE(NULLIF(v_parsed->'corporate_actions','null'::jsonb),'{}')) s CROSS JOIN LATERAL jsonb_array_elements(s.value) b;
 ELSIF t.provider='Massive' THEN
   SELECT COALESCE(jsonb_agg(value ORDER BY value::text),'[]') INTO v_source_rows FROM jsonb_array_elements(
      CASE WHEN jsonb_typeof(v_parsed->'results')='object' THEN jsonb_build_array(v_parsed->'results') ELSE COALESCE(NULLIF(v_parsed->'results','null'::jsonb),'[]') END);
 ELSE
   v_source_rows:=COALESCE(v_parsed->'rows',v_parsed->'records');
 END IF;
 IF t.provider IN ('Alpaca','Massive') THEN
   SELECT COALESCE(jsonb_agg(value->'source' ORDER BY (value->'source')::text),'[]') INTO v_submitted_rows FROM jsonb_array_elements(p_payload->'records');
 ELSE v_submitted_rows:=p_payload->'records'; END IF;
 IF v_source_rows IS DISTINCT FROM v_submitted_rows THEN
   RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Normalized source rows do not match the original retained page'; END IF;
 v_count:=jsonb_array_length(p_payload->'records'); v_cursor:=NULLIF(p_payload->'next_cursor','null'::jsonb);
 IF t.provider='Alpaca' AND t.kind<>'alpaca_reference' THEN
  IF NOT (v_parsed ? 'next_page_token') THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Original source pagination field is missing'; END IF;
  IF NULLIF(v_parsed->'next_page_token','null'::jsonb) IS DISTINCT FROM v_cursor THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Retained source continuation differs from the proposed checkpoint'; END IF;
 ELSIF t.provider='Massive' THEN
  v_source_url:=v_parsed->>'next_url';v_source_cursor:=NULL;
  IF v_source_url IS NOT NULL THEN
   IF strpos(v_source_url,'https://api.massive.com'||(p_payload#>>'{request,path}')||'?')<>1
    AND strpos(v_source_url,'https://api.polygon.io'||(p_payload#>>'{request,path}')||'?')<>1 THEN
     RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Untrusted provider pagination origin or path'; END IF;
   SELECT astra_ingestion_v1.backfill_uri_component_v2(substr(kv,strpos(kv,'=')+1)) INTO v_source_cursor
    FROM unnest(string_to_array(split_part(v_source_url,'?',2),'&')) kv WHERE split_part(kv,'=',1)='cursor';
   IF v_source_cursor IS NULL THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Source continuation cursor missing'; END IF;
  END IF;
  IF v_source_cursor IS DISTINCT FROM v_cursor#>>'{}' THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Retained source continuation differs from the proposed checkpoint'; END IF;
 END IF;
 IF v_cursor IS NOT NULL AND (jsonb_typeof(v_cursor)<>'string' OR length(v_cursor#>>'{}') NOT BETWEEN 1 AND 8192 OR v_cursor IS NOT DISTINCT FROM t.cursor
  OR EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_pages_v2 WHERE task_id=t.id AND cursor_in=v_cursor)) THEN
   RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='Replacement source pagination token is invalid or repeated'; END IF;
 v_state:=CASE WHEN v_cursor IS NOT NULL THEN 'PENDING' WHEN t.records_committed+v_count=0 THEN 'NO_DATA_RETURNED' ELSE 'INGESTED' END;
 IF v_cursor IS NULL AND p_payload->>'terminal_state' IN ('IDENTITY_OR_QUALITY_UNRESOLVED','NOT_APPLICABLE','PROVIDER_LIMITATION') THEN
   IF COALESCE(jsonb_array_length(p_payload->'quality'),0)=0 THEN RAISE EXCEPTION USING ERRCODE='AI002',MESSAGE='A terminal limitation requires retained evidence'; END IF;
   v_state:=p_payload->>'terminal_state';
 END IF;
 IF v_cursor IS NULL AND jsonb_array_length(COALESCE(p_payload->'quality','[]'))>0 AND v_state='INGESTED' THEN v_state:='IDENTITY_OR_QUALITY_UNRESOLVED'; END IF;
 INSERT INTO astra_ingestion_v1.backfill_pages_v2(task_id,page_no,run_id,generation,run_fence,provider,cursor_in,cursor_out,request,http_status,request_id,fetched_at,raw_body,body_sha256,records_sha256,record_count,source_bytes,quality,headers,adapter_version)
 VALUES(t.id,t.page_no,t.run_id,t.generation,t.run_fence,t.provider,t.cursor,v_cursor,p_payload->'request',200,left(p_payload->>'request_id',256),(p_payload->>'fetched_at')::timestamptz,v_raw,v_hash,
  encode(sha256(convert_to(astra_ingestion_v1.rpc_canonical(p_payload->'records'),'UTF8')),'hex'),v_count,octet_length(v_raw),COALESCE(p_payload->'quality','[]'),COALESCE(p_payload->'headers','{}'),p_payload->>'adapter_version');
 -- Durable contract enumeration admission is independently verified and reconciled by the same controller.
 IF t.kind='alpaca_option_contracts' THEN PERFORM astra_ingestion_v1.backfill_contract_enqueue_v2(t.id,t.page_no);END IF;
 PERFORM astra_ingestion_v1.backfill_owned_v2(v_claim);
 UPDATE astra_ingestion_v1.backfill_tasks_v2 SET status=v_state,cursor=v_cursor,page_no=page_no+1,records_committed=records_committed+v_count,
  owner=NULL,lease_until=NULL,page_attempts=0,last_progress_at=v_now,next_retry_at=v_now,error_code=NULL,error_message=NULL WHERE id=t.id;
 UPDATE astra_ingestion_v1.backfill_runs_v2 SET pages_committed=pages_committed+1,records_committed=records_committed+v_count,source_bytes=source_bytes+octet_length(v_raw),last_progress_at=v_now WHERE id=t.run_id;
 IF v_state IN ('IDENTITY_OR_QUALITY_UNRESOLVED','NOT_APPLICABLE','PROVIDER_LIMITATION') THEN
  INSERT INTO astra_ingestion_v1.backfill_exceptions_v2(run_id,task_id,page_no,generation,state,code,message,evidence)
   VALUES(t.run_id,t.id,t.page_no,t.generation,v_state,v_state,'Retained source page has documented per-unit limitations',COALESCE(p_payload->'quality','[]'));
 END IF;
 RETURN jsonb_build_object('state','page_committed','task_id',t.id,'page_no',t.page_no,'task_status',v_state,'record_count',v_count,'body_sha256',v_hash,'next_cursor',v_cursor);
END $function$
$claim_replacement$;
 v_before text;v_before_metadata jsonb;v_after_metadata jsonb;
 v_pin jsonb;v_pin_source text;v_pin_metadata jsonb;
 v_catalog_before jsonb;v_catalog_after jsonb;v_run_before jsonb;v_run_after jsonb;
BEGIN
 IF current_setting('statement_timeout')<>'8s' OR current_setting('lock_timeout')<>'3s'
  OR current_setting('transaction_read_only')<>'off' OR current_setting('transaction_isolation')<>'read committed' THEN
  RAISE EXCEPTION 'Claim cursor replacement requires reviewed writable RC 8s/3s bounds';
 END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(706314020261028);
 PERFORM 1 FROM astra_ingestion_v1.backfill_runs_v2 WHERE id='fixed3000-20250901-20260731-v1-20261030' FOR SHARE;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2
 WHERE id='fixed3000-20250901-20260731-v1-20261030' AND fence=1
  AND cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec' AND cohort_manifest_sha256='4134b415e2c26fcde9fced749c0d54ef51376e23f0d2f8c6ce9ef562f9fab99f'
  AND metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
  AND isfinite((metadata->>'implementation_lease_until')::timestamptz)
  AND (metadata->>'implementation_lease_until')::timestamptz>clock_timestamp())
 OR (SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id='fixed3000-20250901-20260731-v1-20261030')<>3000 THEN
 RAISE EXCEPTION 'Claim cursor owner, finite lease, status, fence, cohort or member guard differs';
 END IF;
 SELECT to_jsonb(r) INTO STRICT v_run_before FROM astra_ingestion_v1.backfill_runs_v2 r WHERE id='fixed3000-20250901-20260731-v1-20261030';
 SELECT pg_get_functiondef(p.oid),to_jsonb(p)-'prosrc' INTO STRICT v_before,v_before_metadata
 FROM pg_proc p WHERE p.oid='astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure;
 IF encode(sha256(convert_to(v_before,'UTF8')),'hex')<>'dbe8eb5a563eaf9e8e00678045f8a28da65c8c4b83b4a3295c4eb32c05f50fbf'
  OR v_before_metadata IS DISTINCT FROM v_expected_metadata THEN
  RAISE EXCEPTION 'Claim cursor exact source or metadata differs; reconcile before replay';
 END IF;
 FOR v_pin IN SELECT value FROM jsonb_array_elements(v_pins) LOOP
 SELECT pg_get_functiondef(p.oid),to_jsonb(p)-'prosrc' INTO STRICT v_pin_source,v_pin_metadata
 FROM pg_proc p WHERE p.oid=(v_pin->>'signature')::regprocedure;
 IF encode(sha256(convert_to(v_pin_source,'UTF8')),'hex') IS DISTINCT FROM v_pin->>'sha256'
  OR (v_pin ? 'metadata' AND v_pin_metadata IS DISTINCT FROM v_pin->'metadata')
  OR (v_pin ? 'metadata_sha256' AND (v_pin_metadata->>'oid' IS DISTINCT FROM v_pin->>'oid'
   OR encode(sha256(convert_to(v_pin_metadata::text,'UTF8')),'hex') IS DISTINCT FROM v_pin->>'metadata_sha256')) THEN
  RAISE EXCEPTION 'Claim cursor immutable source or full metadata differs';
 END IF;
 END LOOP;
 IF NOT EXISTS(SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_am a ON a.oid=c.relam
  WHERE i.indexrelid='astra_ingestion_v1.backfill_tasks_provider_v2'::regclass
   AND i.indrelid='astra_ingestion_v1.backfill_tasks_v2'::regclass AND i.indisvalid AND i.indisready AND i.indislive
   AND a.amname='btree' AND pg_get_indexdef(i.indexrelid)='CREATE INDEX backfill_tasks_provider_v2 ON astra_ingestion_v1.backfill_tasks_v2 USING btree (run_id, provider, status, kind)') THEN
  RAISE EXCEPTION 'Claim cursor required existing provider index differs';
 END IF;
 IF encode(sha256(convert_to(v_replacement,'UTF8')),'hex')<>'28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44' THEN
  RAISE EXCEPTION 'Claim cursor reviewed replacement bytes differ';
 END IF;
 -- CLAIM_CURSOR_BEFORE_CATALOG_SNAPSHOT
 SELECT jsonb_build_object(
 'namespace',(SELECT to_jsonb(n) FROM pg_namespace n WHERE n.oid='astra_ingestion_v1'::regnamespace),
 'functions',(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.oid) FROM pg_proc p
  WHERE (p.pronamespace='astra_ingestion_v1'::regnamespace OR p.oid='public.astra_ingestion_rpc_v1(text,jsonb)'::regprocedure)
   AND p.oid<>'astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure),
 'relations',(SELECT jsonb_agg(jsonb_build_object('oid',c.oid::text,'name',c.relname,
  'namespace',c.relnamespace::text,'kind',c.relkind,'owner',c.relowner::text,'acl',c.relacl,
  'rls',c.relrowsecurity,'force_rls',c.relforcerowsecurity,'method',c.relam::text,'options',c.reloptions)
  ORDER BY c.oid) FROM pg_class c WHERE c.relnamespace='astra_ingestion_v1'::regnamespace),
 'indexes',(SELECT jsonb_agg(jsonb_build_object('catalog',to_jsonb(i),'definition',pg_get_indexdef(i.indexrelid))
  ORDER BY i.indexrelid) FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid
  WHERE c.relnamespace='astra_ingestion_v1'::regnamespace),
 'constraints',(SELECT jsonb_agg(to_jsonb(c) ORDER BY c.oid) FROM pg_constraint c
  WHERE c.connamespace='astra_ingestion_v1'::regnamespace),
 'triggers',(SELECT jsonb_agg(to_jsonb(t) ORDER BY t.oid) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
  WHERE c.relnamespace='astra_ingestion_v1'::regnamespace),
 'policies',(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.oid) FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid
  WHERE c.relnamespace='astra_ingestion_v1'::regnamespace),
 'roles',(SELECT jsonb_agg(to_jsonb(r) ORDER BY r.oid) FROM pg_roles r
  WHERE r.rolname IN ('astra_ingestion_rpc_owner_v1','astra_ingestion_monitor_owner_v1')),
 'role_memberships',(SELECT jsonb_agg(to_jsonb(m) ORDER BY m.roleid,m.member,m.grantor) FROM pg_auth_members m
  WHERE m.roleid IN (SELECT oid FROM pg_roles WHERE rolname IN ('astra_ingestion_rpc_owner_v1','astra_ingestion_monitor_owner_v1'))
   OR m.member IN (SELECT oid FROM pg_roles WHERE rolname IN ('astra_ingestion_rpc_owner_v1','astra_ingestion_monitor_owner_v1')))
) INTO v_catalog_before;
 EXECUTE v_replacement;
 -- CLAIM_CURSOR_AFTER_REPLACEMENT
 SELECT to_jsonb(p)-'prosrc' INTO STRICT v_after_metadata FROM pg_proc p WHERE p.oid='astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure;
 SELECT jsonb_build_object(
 'namespace',(SELECT to_jsonb(n) FROM pg_namespace n WHERE n.oid='astra_ingestion_v1'::regnamespace),
 'functions',(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.oid) FROM pg_proc p
  WHERE (p.pronamespace='astra_ingestion_v1'::regnamespace OR p.oid='public.astra_ingestion_rpc_v1(text,jsonb)'::regprocedure)
   AND p.oid<>'astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure),
 'relations',(SELECT jsonb_agg(jsonb_build_object('oid',c.oid::text,'name',c.relname,
  'namespace',c.relnamespace::text,'kind',c.relkind,'owner',c.relowner::text,'acl',c.relacl,
  'rls',c.relrowsecurity,'force_rls',c.relforcerowsecurity,'method',c.relam::text,'options',c.reloptions)
  ORDER BY c.oid) FROM pg_class c WHERE c.relnamespace='astra_ingestion_v1'::regnamespace),
 'indexes',(SELECT jsonb_agg(jsonb_build_object('catalog',to_jsonb(i),'definition',pg_get_indexdef(i.indexrelid))
  ORDER BY i.indexrelid) FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid
  WHERE c.relnamespace='astra_ingestion_v1'::regnamespace),
 'constraints',(SELECT jsonb_agg(to_jsonb(c) ORDER BY c.oid) FROM pg_constraint c
  WHERE c.connamespace='astra_ingestion_v1'::regnamespace),
 'triggers',(SELECT jsonb_agg(to_jsonb(t) ORDER BY t.oid) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
  WHERE c.relnamespace='astra_ingestion_v1'::regnamespace),
 'policies',(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.oid) FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid
  WHERE c.relnamespace='astra_ingestion_v1'::regnamespace),
 'roles',(SELECT jsonb_agg(to_jsonb(r) ORDER BY r.oid) FROM pg_roles r
  WHERE r.rolname IN ('astra_ingestion_rpc_owner_v1','astra_ingestion_monitor_owner_v1')),
 'role_memberships',(SELECT jsonb_agg(to_jsonb(m) ORDER BY m.roleid,m.member,m.grantor) FROM pg_auth_members m
  WHERE m.roleid IN (SELECT oid FROM pg_roles WHERE rolname IN ('astra_ingestion_rpc_owner_v1','astra_ingestion_monitor_owner_v1'))
   OR m.member IN (SELECT oid FROM pg_roles WHERE rolname IN ('astra_ingestion_rpc_owner_v1','astra_ingestion_monitor_owner_v1')))
) INTO v_catalog_after;
 IF v_after_metadata IS DISTINCT FROM v_before_metadata OR v_after_metadata IS DISTINCT FROM v_expected_metadata
  OR v_catalog_after IS DISTINCT FROM v_catalog_before
  OR pg_get_functiondef('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure) IS DISTINCT FROM v_replacement THEN
  RAISE EXCEPTION 'Claim cursor changed unexpected source, metadata, OID, ACL or catalog';
 END IF;
 FOR v_pin IN SELECT value FROM jsonb_array_elements(v_pins) LOOP
 SELECT pg_get_functiondef(p.oid),to_jsonb(p)-'prosrc' INTO STRICT v_pin_source,v_pin_metadata
 FROM pg_proc p WHERE p.oid=(v_pin->>'signature')::regprocedure;
 IF encode(sha256(convert_to(v_pin_source,'UTF8')),'hex') IS DISTINCT FROM v_pin->>'sha256'
  OR (v_pin ? 'metadata' AND v_pin_metadata IS DISTINCT FROM v_pin->'metadata')
  OR (v_pin ? 'metadata_sha256' AND (v_pin_metadata->>'oid' IS DISTINCT FROM v_pin->>'oid'
   OR encode(sha256(convert_to(v_pin_metadata::text,'UTF8')),'hex') IS DISTINCT FROM v_pin->>'metadata_sha256')) THEN
  RAISE EXCEPTION 'Claim cursor immutable source or full metadata differs';
 END IF;
 END LOOP;
 IF NOT EXISTS(SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_am a ON a.oid=c.relam
  WHERE i.indexrelid='astra_ingestion_v1.backfill_tasks_provider_v2'::regclass
   AND i.indrelid='astra_ingestion_v1.backfill_tasks_v2'::regclass AND i.indisvalid AND i.indisready AND i.indislive
   AND a.amname='btree' AND pg_get_indexdef(i.indexrelid)='CREATE INDEX backfill_tasks_provider_v2 ON astra_ingestion_v1.backfill_tasks_v2 USING btree (run_id, provider, status, kind)') THEN
  RAISE EXCEPTION 'Claim cursor required existing provider index differs';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2
 WHERE id='fixed3000-20250901-20260731-v1-20261030' AND fence=1
  AND cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec' AND cohort_manifest_sha256='4134b415e2c26fcde9fced749c0d54ef51376e23f0d2f8c6ce9ef562f9fab99f'
  AND metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
  AND isfinite((metadata->>'implementation_lease_until')::timestamptz)
  AND (metadata->>'implementation_lease_until')::timestamptz>clock_timestamp())
 OR (SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id='fixed3000-20250901-20260731-v1-20261030')<>3000 THEN
 RAISE EXCEPTION 'Claim cursor owner, finite lease, status, fence, cohort or member guard differs';
 END IF;
 SELECT to_jsonb(r) INTO STRICT v_run_after FROM astra_ingestion_v1.backfill_runs_v2 r WHERE id='fixed3000-20250901-20260731-v1-20261030';
 IF v_run_after IS DISTINCT FROM v_run_before THEN
  RAISE EXCEPTION 'Claim cursor replacement changed the run row';
 END IF;
END $claim_cursor_restore$;
COMMIT;
