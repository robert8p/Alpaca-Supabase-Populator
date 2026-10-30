-- v78: Align static-plan pending predicates with the existing snapshot eligibility.
-- Exactly two existing helpers and three predicates. No grants, new operation,
-- counter repair, broad plan_static exclusion, retry/deadline or worker change.
BEGIN;
SET LOCAL statement_timeout='8s';SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);
DO $v78$
DECLARE r astra_ingestion_v1.backfill_runs_v2%ROWTYPE;a astra_ingestion_v1.backfill_runs_v2%ROWTYPE;
 before_pins jsonb:='[{"metadata_sha256":"e7c2c36c0fa1db906255f0194e62ae1d1ebbdf3b11c0fb718723b6ec524a79b6","oid":"16040232","signature":"astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)","source_sha256":"dbe8eb5a563eaf9e8e00678045f8a28da65c8c4b83b4a3295c4eb32c05f50fbf"},{"signature":"astra_ingestion_v1.backfill_plan_next_v2(jsonb)","oid":"16041635","source_sha256":"54c73bd41769eb6c698a7941d0785e503c9f48f88a3ccb7afcc6448d46c5048d","metadata_sha256":"ca71e86cf6901b655a7d81b1ca15d39ee8d8db1fa0cef329e2ee92bc0b04f875"},{"signature":"astra_ingestion_v1.backfill_plan_snapshot_v2(text,integer)","oid":"16041469","source_sha256":"67c4b74348ad271d59bc21a901cbfee650ecc91c3a86713b2e29f308094f1ad2","metadata_sha256":"2298d7d2dc6af8f2360df643ed9c05067e625103fe3e09ba59b3fdc1a7ed1f69"},{"signature":"astra_ingestion_v1.backfill_seal_plan_v2(text,bigint,text,jsonb)","oid":"16041471","source_sha256":"6b1b74c618a0f555fd023f7e9980e94c11d1beb556d89815e7e16f6018c5d296","metadata_sha256":"26059708eb74c9b3f291e98da0a74b3b2c381073ec04feb947c07e5fa91a2f8c"},{"metadata_sha256":"05efbf80a36ecaf99c1ecf1c3bde8372489963c867bd98708f5fc12223b05f43","oid":"16050105","signature":"astra_ingestion_v1.backfill_shared_refresh_v2(text,jsonb)","source_sha256":"7f538bf47cb5e74050c20266e01cbe9d6521c1a65663aaf2e0fe38d62041f1a4"},{"signature":"astra_ingestion_v1.backfill_snapshot_task_v2(text)","oid":"16041466","source_sha256":"66cf1ddad758759353ac0e7ca10aa119cbc88b21bee26d1b5f8356df090518b2","metadata_sha256":"3b039c556a14a96cec82bbe9cf701f6fd45474393b255460fb14d62648087418"},{"metadata_sha256":"1f123366c142c43aadb28a9a4ea3df9e8c376a74a90c69c81b1363c10afeca7e","oid":"15986028","signature":"astra_ingestion_v1.rpc_dispatch(text,jsonb)","source_sha256":"a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520"},{"metadata_sha256":"412040bbed9e8a96e9c7231c1f1474326c0eacf7a8157043703983c68b2d1f51","oid":"15986030","signature":"public.astra_ingestion_rpc_v1(text,jsonb)","source_sha256":"566d2248b8addac92a5dc2659233fb50f12ae1c55869fc278555da6cbd1ffffb"},{"metadata_sha256":"4497ec91787767ee138d167beb19970a5289f9baec3d01c9eeda6962a8d0460d","oid":"16041463","signature":"astra_ingestion_v1.backfill_maintain_v2(integer)","source_sha256":"6c880114a645c8a9167d5260c4aeabf58a10617c4244cf0340be1d6cf4bf0ce7"}]'::jsonb;
 after_pins jsonb:='[{"metadata_sha256":"e7c2c36c0fa1db906255f0194e62ae1d1ebbdf3b11c0fb718723b6ec524a79b6","oid":"16040232","signature":"astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)","source_sha256":"dbe8eb5a563eaf9e8e00678045f8a28da65c8c4b83b4a3295c4eb32c05f50fbf"},{"signature":"astra_ingestion_v1.backfill_plan_next_v2(jsonb)","oid":"16041635","source_sha256":"54c73bd41769eb6c698a7941d0785e503c9f48f88a3ccb7afcc6448d46c5048d","metadata_sha256":"ca71e86cf6901b655a7d81b1ca15d39ee8d8db1fa0cef329e2ee92bc0b04f875"},{"signature":"astra_ingestion_v1.backfill_plan_snapshot_v2(text,integer)","oid":"16041469","source_sha256":"8b8f595bfca0e6ddf74aa12271314620b8364df26079cd86f843a4a81f92b18f","metadata_sha256":"2298d7d2dc6af8f2360df643ed9c05067e625103fe3e09ba59b3fdc1a7ed1f69"},{"signature":"astra_ingestion_v1.backfill_seal_plan_v2(text,bigint,text,jsonb)","oid":"16041471","source_sha256":"a93e5fbede881afc9e813e8eaaec1c300d636e008fe8c3423d478d55243d2ba1","metadata_sha256":"26059708eb74c9b3f291e98da0a74b3b2c381073ec04feb947c07e5fa91a2f8c"},{"metadata_sha256":"05efbf80a36ecaf99c1ecf1c3bde8372489963c867bd98708f5fc12223b05f43","oid":"16050105","signature":"astra_ingestion_v1.backfill_shared_refresh_v2(text,jsonb)","source_sha256":"7f538bf47cb5e74050c20266e01cbe9d6521c1a65663aaf2e0fe38d62041f1a4"},{"signature":"astra_ingestion_v1.backfill_snapshot_task_v2(text)","oid":"16041466","source_sha256":"66cf1ddad758759353ac0e7ca10aa119cbc88b21bee26d1b5f8356df090518b2","metadata_sha256":"3b039c556a14a96cec82bbe9cf701f6fd45474393b255460fb14d62648087418"},{"metadata_sha256":"1f123366c142c43aadb28a9a4ea3df9e8c376a74a90c69c81b1363c10afeca7e","oid":"15986028","signature":"astra_ingestion_v1.rpc_dispatch(text,jsonb)","source_sha256":"a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520"},{"metadata_sha256":"412040bbed9e8a96e9c7231c1f1474326c0eacf7a8157043703983c68b2d1f51","oid":"15986030","signature":"public.astra_ingestion_rpc_v1(text,jsonb)","source_sha256":"566d2248b8addac92a5dc2659233fb50f12ae1c55869fc278555da6cbd1ffffb"},{"metadata_sha256":"4497ec91787767ee138d167beb19970a5289f9baec3d01c9eeda6962a8d0460d","oid":"16041463","signature":"astra_ingestion_v1.backfill_maintain_v2(integer)","source_sha256":"6c880114a645c8a9167d5260c4aeabf58a10617c4244cf0340be1d6cf4bf0ce7"}]'::jsonb;
 ok boolean;
BEGIN
 SELECT * INTO STRICT r FROM astra_ingestion_v1.backfill_runs_v2 WHERE id='fixed3000-20250901-20260731-v1-20261030' FOR UPDATE;
 IF r.status<>'ACTIVE' OR r.fence<>1 OR r.metadata->>'implementation_owner' IS DISTINCT FROM 'root-replacement-20261030T042603Z'
  OR NOT COALESCE(isfinite((r.metadata->>'implementation_lease_until')::timestamptz) AND (r.metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()+interval '1 minute',false)
  OR r.cohort_sha256<>'2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
  OR r.cohort_manifest_sha256<>'4134b415e2c26fcde9fced749c0d54ef51376e23f0d2f8c6ce9ef562f9fab99f'
  OR r.target_start<>'2025-09-01'::date OR r.target_end<>'2026-07-31'::date
  OR r.metadata#>>'{implementation_reporting_policy,mode}' IS DISTINCT FROM 'DOT_CONSOLIDATED_CHECKPOINTS_ONLY'
  OR NOT COALESCE((SELECT count(*)=3000 AND encode(sha256(convert_to(string_agg(member_id,E'\n' ORDER BY selection_order,member_id),'UTF8')),'hex')='a83310df6a6465ce8d37ffd5352095f6e38d91a3204afd8807fff39092cfd85e' FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id=r.id),false)
 THEN RAISE EXCEPTION 'v78 requires the current finite existing controller, fixed cohort and unchanged scope'; END IF;
 IF r.metadata->>'planner_phase' IS DISTINCT FROM 'SEAL' OR r.metadata->'planning_complete' IS DISTINCT FROM 'false'::jsonb OR r.metadata->>'planner_next_selection_order' IS DISTINCT FROM '3001' OR r.metadata->>'planner_next_breadth_index' IS DISTINCT FROM '230' THEN RAISE EXCEPTION 'v78 only repairs the reconciled unsealed final planner phase'; END IF;
 SELECT count(*)=9 AND bool_and(COALESCE(p.oid::text=e.v->>'oid'
  AND encode(sha256(convert_to(pg_get_functiondef(p.oid),'UTF8')),'hex')=e.v->>'source_sha256'
  AND encode(sha256(convert_to((to_jsonb(p)-'prosrc')::text,'UTF8')),'hex')=e.v->>'metadata_sha256',false)) INTO ok
 FROM jsonb_array_elements(before_pins) e(v) LEFT JOIN pg_proc p ON p.oid=to_regprocedure(e.v->>'signature');
 IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'v78 exact source/OID/full metadata guard failed; reconcile, do not replay'; END IF;
 EXECUTE $definition0$CREATE OR REPLACE FUNCTION astra_ingestion_v1.backfill_plan_snapshot_v2(p_run_id text, p_limit integer DEFAULT 500)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
DECLARE t record; v_count integer:=0;
BEGIN
 FOR t IN SELECT q.id FROM astra_ingestion_v1.backfill_tasks_v2 q WHERE q.run_id=p_run_id
  AND NOT ((q.kind='alpaca_option_bars' AND q.scope ? 'enumeration_parent') OR q.scope ? 'reuse_parent' OR q.scope ? 'identity_refresh_of' OR q.kind IN('retained_identity','retained_massive_archive'))
  AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_plan_units_v2 p WHERE p.task_id=q.id)
  ORDER BY q.id LIMIT GREATEST(1,LEAST(p_limit,500))
 LOOP IF astra_ingestion_v1.backfill_snapshot_task_v2(t.id) THEN v_count:=v_count+1;END IF;END LOOP;
 RETURN jsonb_build_object('snapshotted',v_count,'more',EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 q WHERE q.run_id=p_run_id
  AND NOT ((q.kind='alpaca_option_bars' AND q.scope ? 'enumeration_parent') OR q.scope ? 'reuse_parent' OR q.scope ? 'identity_refresh_of' OR q.kind IN('retained_identity','retained_massive_archive'))
  AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_plan_units_v2 p WHERE p.task_id=q.id)));
END $function$
$definition0$;
 EXECUTE $definition1$CREATE OR REPLACE FUNCTION astra_ingestion_v1.backfill_seal_plan_v2(p_run_id text, p_expected_count bigint, p_expected_sha256 text, p_workflow_plan jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SET search_path TO ''
AS $function$
DECLARE r astra_ingestion_v1.backfill_runs_v2; v_count bigint; v_hash text; v_trading datemultirange; v_calendar datemultirange; v_missing jsonb;
BEGIN
 SELECT * INTO STRICT r FROM astra_ingestion_v1.backfill_runs_v2 WHERE id=p_run_id FOR UPDATE;
 IF r.status<>'ACTIVE' OR EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_plan_manifests_v2 WHERE run_id=r.id) THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Only an active unsealed replacement plan may be sealed'; END IF;
 IF jsonb_typeof(p_workflow_plan) IS DISTINCT FROM 'object' OR length(COALESCE(p_workflow_plan->>'version',''))=0
  OR p_workflow_plan->>'target_start' IS DISTINCT FROM '2025-09-01' OR p_workflow_plan->>'target_end' IS DISTINCT FROM '2026-07-31'
  OR p_workflow_plan->>'market_timezone' IS DISTINCT FROM 'America/New_York' OR length(COALESCE(p_workflow_plan->>'representative_policy',''))=0
  OR jsonb_typeof(p_workflow_plan->'session_dates') IS DISTINCT FROM 'array' THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Plan sealing requires explicit fixed-window, calendar and representative policy evidence'; END IF;
 SELECT range_agg(daterange(d,d+1,'[)')) INTO v_trading FROM (SELECT DISTINCT value::date d FROM jsonb_array_elements_text(p_workflow_plan->'session_dates')) x;
 IF (SELECT count(DISTINCT value) FROM jsonb_array_elements_text(p_workflow_plan->'session_dates'))<>230
  OR (SELECT encode(sha256(convert_to(string_agg(value,E'\n' ORDER BY value),'UTF8')),'hex') FROM (SELECT DISTINCT value FROM jsonb_array_elements_text(p_workflow_plan->'session_dates')) s)
     <>'acb2972a35b3458a6a41dfeaca34abea14cd0c228183b9dca602cb59deb0d9d6'
  OR EXISTS(SELECT 1 FROM jsonb_array_elements_text(p_workflow_plan->'session_dates') d WHERE d::date<r.target_start OR d::date>r.target_end) THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Frozen target exchange calendar must contain the retained 230 sessions'; END IF;
 v_calendar:=datemultirange(daterange(r.target_start,r.target_end+1,'[)'));
 IF EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 q WHERE q.run_id=r.id
  AND NOT ((q.kind='alpaca_option_bars' AND q.scope ? 'enumeration_parent') OR q.scope ? 'reuse_parent' OR q.scope ? 'identity_refresh_of' OR q.kind IN('retained_identity','retained_massive_archive'))
  AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_plan_units_v2 p WHERE p.task_id=q.id)) THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Static task snapshots are incomplete; continue bounded backfill_plan_snapshot'; END IF;
 SELECT count(*),encode(sha256(convert_to(COALESCE(string_agg(task_id||':'||definition_sha256,E'\n' ORDER BY task_id COLLATE "C"),''),'UTF8')),'hex')
 INTO v_count,v_hash FROM astra_ingestion_v1.backfill_plan_units_v2 WHERE run_id=r.id;
 IF v_count IS DISTINCT FROM p_expected_count OR v_hash IS DISTINCT FROM p_expected_sha256 THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Stored task count/hash differs from the expected complete workflow manifest'; END IF;
 v_missing:=astra_ingestion_v1.backfill_plan_coverage_check_v2(r.id,v_trading,v_calendar);
 IF jsonb_array_length(v_missing->'missing_member_date_workflows')>0 THEN
  RETURN jsonb_build_object('state','INCOMPLETE_MEMBER_DATE_WORKFLOWS','evidence',v_missing); END IF;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_plan_units_v2 WHERE run_id=r.id AND family='CTX06')
  OR EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_plan_units_v2 WHERE run_id=r.id AND family='CTX06' AND representative_map_valid IS DISTINCT FROM true) THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Every breadth unit needs an explicit representative map for the exact 3000 frozen companies'; END IF;
 INSERT INTO astra_ingestion_v1.backfill_plan_manifests_v2(run_id,expected_task_count,expected_plan_sha256,workflow_plan,required_trading_dates,required_calendar_dates)
 VALUES(r.id,v_count,v_hash,p_workflow_plan,v_trading,v_calendar);
 UPDATE astra_ingestion_v1.backfill_runs_v2 SET metadata=metadata||jsonb_build_object('planning_complete',true,'expected_static_task_count',v_count,'expected_plan_sha256',v_hash,'workflow_plan',p_workflow_plan) WHERE id=r.id;
 INSERT INTO astra_ingestion_v1.backfill_audit_v2(run_id,action,evidence) VALUES(r.id,'FULL_PLAN_SEALED',jsonb_build_object('expected_task_count',v_count,'expected_plan_sha256',v_hash,'cohort_sha256',r.cohort_sha256));
 RETURN jsonb_build_object('state','FULL_PLAN_SEALED','expected_task_count',v_count,'expected_plan_sha256',v_hash);
END $function$
$definition1$;
 SELECT count(*)=9 AND bool_and(COALESCE(p.oid::text=e.v->>'oid'
  AND encode(sha256(convert_to(pg_get_functiondef(p.oid),'UTF8')),'hex')=e.v->>'source_sha256'
  AND encode(sha256(convert_to((to_jsonb(p)-'prosrc')::text,'UTF8')),'hex')=e.v->>'metadata_sha256',false)) INTO ok
 FROM jsonb_array_elements(after_pins) e(v) LEFT JOIN pg_proc p ON p.oid=to_regprocedure(e.v->>'signature');
 IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'v78 post-replacement source/OID/full metadata differs'; END IF;
 SELECT * INTO STRICT a FROM astra_ingestion_v1.backfill_runs_v2 WHERE id=r.id;
 IF to_jsonb(a) IS DISTINCT FROM to_jsonb(r) THEN RAISE EXCEPTION 'v78 altered run state or accounting'; END IF;
END $v78$;
COMMIT;
