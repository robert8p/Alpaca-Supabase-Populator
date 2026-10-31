-- v81: Guarded inverse to the retained planner; preserve committed scan/snapshot/manifest work.
-- One existing planner branch. No new functions, grants, roles, source, settings,
-- index, retry, timeout, worker deployment or acquisition-accounting changes.
BEGIN;
SET LOCAL statement_timeout='8s';SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);
DO $v81$
DECLARE r astra_ingestion_v1.backfill_runs_v2%ROWTYPE;a astra_ingestion_v1.backfill_runs_v2%ROWTYPE;
 before_pins jsonb:='[{"metadata_sha256":"e7c2c36c0fa1db906255f0194e62ae1d1ebbdf3b11c0fb718723b6ec524a79b6","oid":"16040232","signature":"astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)","source_sha256":"dbe8eb5a563eaf9e8e00678045f8a28da65c8c4b83b4a3295c4eb32c05f50fbf"},{"metadata_sha256":"ca71e86cf6901b655a7d81b1ca15d39ee8d8db1fa0cef329e2ee92bc0b04f875","oid":"16041635","signature":"astra_ingestion_v1.backfill_plan_next_v2(jsonb)","source_sha256":"b4d89146c677d38889ddd15a7986bd03723eb2f1b986582da30e46d24b5e172d"},{"metadata_sha256":"2298d7d2dc6af8f2360df643ed9c05067e625103fe3e09ba59b3fdc1a7ed1f69","oid":"16041469","signature":"astra_ingestion_v1.backfill_plan_snapshot_v2(text,integer)","source_sha256":"8b8f595bfca0e6ddf74aa12271314620b8364df26079cd86f843a4a81f92b18f"},{"metadata_sha256":"26059708eb74c9b3f291e98da0a74b3b2c381073ec04feb947c07e5fa91a2f8c","oid":"16041471","signature":"astra_ingestion_v1.backfill_seal_plan_v2(text,bigint,text,jsonb)","source_sha256":"a93e5fbede881afc9e813e8eaaec1c300d636e008fe8c3423d478d55243d2ba1"},{"metadata_sha256":"05efbf80a36ecaf99c1ecf1c3bde8372489963c867bd98708f5fc12223b05f43","oid":"16050105","signature":"astra_ingestion_v1.backfill_shared_refresh_v2(text,jsonb)","source_sha256":"7f538bf47cb5e74050c20266e01cbe9d6521c1a65663aaf2e0fe38d62041f1a4"},{"metadata_sha256":"3b039c556a14a96cec82bbe9cf701f6fd45474393b255460fb14d62648087418","oid":"16041466","signature":"astra_ingestion_v1.backfill_snapshot_task_v2(text)","source_sha256":"66cf1ddad758759353ac0e7ca10aa119cbc88b21bee26d1b5f8356df090518b2"},{"metadata_sha256":"1f123366c142c43aadb28a9a4ea3df9e8c376a74a90c69c81b1363c10afeca7e","oid":"15986028","signature":"astra_ingestion_v1.rpc_dispatch(text,jsonb)","source_sha256":"a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520"},{"metadata_sha256":"412040bbed9e8a96e9c7231c1f1474326c0eacf7a8157043703983c68b2d1f51","oid":"15986030","signature":"public.astra_ingestion_rpc_v1(text,jsonb)","source_sha256":"566d2248b8addac92a5dc2659233fb50f12ae1c55869fc278555da6cbd1ffffb"},{"metadata_sha256":"4497ec91787767ee138d167beb19970a5289f9baec3d01c9eeda6962a8d0460d","oid":"16041463","signature":"astra_ingestion_v1.backfill_maintain_v2(integer)","source_sha256":"6c880114a645c8a9167d5260c4aeabf58a10617c4244cf0340be1d6cf4bf0ce7"},{"metadata_sha256":"f7b0c166958ff0da7fdd453d57fa0c45134cdac1d52c389a72c87ed53bb8bb63","oid":"16041470","signature":"astra_ingestion_v1.backfill_plan_coverage_check_v2(text,datemultirange,datemultirange)","source_sha256":"b2503ecd484e3fb7023a00d474cfc44410e8cf9489c037f8a69a37dfc8c0cc5e"},{"metadata_sha256":"0b1c18018c2277b8de57e12248815d1ead7f7ef7634091fe560dc5693a4557fd","oid":"15986014","signature":"astra_ingestion_v1.rpc_canonical(jsonb)","source_sha256":"a7ddedfe281d1494141830d8e89773314856ca94f4d5a4b64b76bb25b3c5e5eb"},{"metadata_sha256":"e0f12f2f1e16dc4ca3802733c39652defb8437abc8ed652a62229fde6bc2c958","oid":"16041364","signature":"astra_ingestion_v1.backfill_date_v2(text)","source_sha256":"7adc3f4ac60be32dd4348becbb325aeaf625cfd8c624b4d266fdbb7a038302f9"},{"metadata_sha256":"0b4e6822e020b5db4a45fc0c84409b2b8b3a70af1a4c76eeef58dd6bcc7f24dc","oid":"16041465","signature":"astra_ingestion_v1.backfill_task_definition_sha256_v2(astra_ingestion_v1.backfill_tasks_v2)","source_sha256":"ba6d5bfd137045abfedb61524d47e734c0489f01957b153fa913f7686db45633"},{"signature":"astra_ingestion_v1.backfill_evidence_guard_v2()","oid":"16040226","source_sha256":"b96725307395500c65f69238c138e40338a19a922c3ff235198b1ad376289dd8","metadata_sha256":"9b757fe27c7ac0713887926ac5c50da7c348f65e325d8c69e355d65af1d01278"},{"signature":"astra_ingestion_v1.backfill_run_guard_v2()","oid":"16040222","source_sha256":"6bf61021944840245e8cf66db118aff413c9f7a8809ecafe025ec4d7f2f5512c","metadata_sha256":"98615ec21c2bc752328d8ad460d2c33a61117068854d0b6b53756b61ecca287f"},{"signature":"astra_ingestion_v1.backfill_snapshot_insert_v2()","oid":"16041467","source_sha256":"dd4b49c8d3b5ec85d2c144a99464482f3b584628b516c0afcb8218e06094434e","metadata_sha256":"628354e3254f593acddd0e874f576073b388126a3a916b1c125932b2321fbee3"},{"signature":"astra_ingestion_v1.backfill_task_guard_v2()","oid":"16040224","source_sha256":"94646a710138c821c9779849edca400d6445b84bec270cc2761a019ecac4b13e","metadata_sha256":"14ea179e67155da200192fb05cd1117bc3b0aea892b94ade7956343f7cf2f4a6"}]'::jsonb;
 after_pins jsonb:='[{"metadata_sha256":"e7c2c36c0fa1db906255f0194e62ae1d1ebbdf3b11c0fb718723b6ec524a79b6","oid":"16040232","signature":"astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)","source_sha256":"dbe8eb5a563eaf9e8e00678045f8a28da65c8c4b83b4a3295c4eb32c05f50fbf"},{"metadata_sha256":"ca71e86cf6901b655a7d81b1ca15d39ee8d8db1fa0cef329e2ee92bc0b04f875","oid":"16041635","signature":"astra_ingestion_v1.backfill_plan_next_v2(jsonb)","source_sha256":"54c73bd41769eb6c698a7941d0785e503c9f48f88a3ccb7afcc6448d46c5048d"},{"metadata_sha256":"2298d7d2dc6af8f2360df643ed9c05067e625103fe3e09ba59b3fdc1a7ed1f69","oid":"16041469","signature":"astra_ingestion_v1.backfill_plan_snapshot_v2(text,integer)","source_sha256":"8b8f595bfca0e6ddf74aa12271314620b8364df26079cd86f843a4a81f92b18f"},{"metadata_sha256":"26059708eb74c9b3f291e98da0a74b3b2c381073ec04feb947c07e5fa91a2f8c","oid":"16041471","signature":"astra_ingestion_v1.backfill_seal_plan_v2(text,bigint,text,jsonb)","source_sha256":"a93e5fbede881afc9e813e8eaaec1c300d636e008fe8c3423d478d55243d2ba1"},{"metadata_sha256":"05efbf80a36ecaf99c1ecf1c3bde8372489963c867bd98708f5fc12223b05f43","oid":"16050105","signature":"astra_ingestion_v1.backfill_shared_refresh_v2(text,jsonb)","source_sha256":"7f538bf47cb5e74050c20266e01cbe9d6521c1a65663aaf2e0fe38d62041f1a4"},{"metadata_sha256":"3b039c556a14a96cec82bbe9cf701f6fd45474393b255460fb14d62648087418","oid":"16041466","signature":"astra_ingestion_v1.backfill_snapshot_task_v2(text)","source_sha256":"66cf1ddad758759353ac0e7ca10aa119cbc88b21bee26d1b5f8356df090518b2"},{"metadata_sha256":"1f123366c142c43aadb28a9a4ea3df9e8c376a74a90c69c81b1363c10afeca7e","oid":"15986028","signature":"astra_ingestion_v1.rpc_dispatch(text,jsonb)","source_sha256":"a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520"},{"metadata_sha256":"412040bbed9e8a96e9c7231c1f1474326c0eacf7a8157043703983c68b2d1f51","oid":"15986030","signature":"public.astra_ingestion_rpc_v1(text,jsonb)","source_sha256":"566d2248b8addac92a5dc2659233fb50f12ae1c55869fc278555da6cbd1ffffb"},{"metadata_sha256":"4497ec91787767ee138d167beb19970a5289f9baec3d01c9eeda6962a8d0460d","oid":"16041463","signature":"astra_ingestion_v1.backfill_maintain_v2(integer)","source_sha256":"6c880114a645c8a9167d5260c4aeabf58a10617c4244cf0340be1d6cf4bf0ce7"},{"metadata_sha256":"f7b0c166958ff0da7fdd453d57fa0c45134cdac1d52c389a72c87ed53bb8bb63","oid":"16041470","signature":"astra_ingestion_v1.backfill_plan_coverage_check_v2(text,datemultirange,datemultirange)","source_sha256":"b2503ecd484e3fb7023a00d474cfc44410e8cf9489c037f8a69a37dfc8c0cc5e"},{"metadata_sha256":"0b1c18018c2277b8de57e12248815d1ead7f7ef7634091fe560dc5693a4557fd","oid":"15986014","signature":"astra_ingestion_v1.rpc_canonical(jsonb)","source_sha256":"a7ddedfe281d1494141830d8e89773314856ca94f4d5a4b64b76bb25b3c5e5eb"},{"metadata_sha256":"e0f12f2f1e16dc4ca3802733c39652defb8437abc8ed652a62229fde6bc2c958","oid":"16041364","signature":"astra_ingestion_v1.backfill_date_v2(text)","source_sha256":"7adc3f4ac60be32dd4348becbb325aeaf625cfd8c624b4d266fdbb7a038302f9"},{"metadata_sha256":"0b4e6822e020b5db4a45fc0c84409b2b8b3a70af1a4c76eeef58dd6bcc7f24dc","oid":"16041465","signature":"astra_ingestion_v1.backfill_task_definition_sha256_v2(astra_ingestion_v1.backfill_tasks_v2)","source_sha256":"ba6d5bfd137045abfedb61524d47e734c0489f01957b153fa913f7686db45633"},{"signature":"astra_ingestion_v1.backfill_evidence_guard_v2()","oid":"16040226","source_sha256":"b96725307395500c65f69238c138e40338a19a922c3ff235198b1ad376289dd8","metadata_sha256":"9b757fe27c7ac0713887926ac5c50da7c348f65e325d8c69e355d65af1d01278"},{"signature":"astra_ingestion_v1.backfill_run_guard_v2()","oid":"16040222","source_sha256":"6bf61021944840245e8cf66db118aff413c9f7a8809ecafe025ec4d7f2f5512c","metadata_sha256":"98615ec21c2bc752328d8ad460d2c33a61117068854d0b6b53756b61ecca287f"},{"signature":"astra_ingestion_v1.backfill_snapshot_insert_v2()","oid":"16041467","source_sha256":"dd4b49c8d3b5ec85d2c144a99464482f3b584628b516c0afcb8218e06094434e","metadata_sha256":"628354e3254f593acddd0e874f576073b388126a3a916b1c125932b2321fbee3"},{"signature":"astra_ingestion_v1.backfill_task_guard_v2()","oid":"16040224","source_sha256":"94646a710138c821c9779849edca400d6445b84bec270cc2761a019ecac4b13e","metadata_sha256":"14ea179e67155da200192fb05cd1117bc3b0aea892b94ade7956343f7cf2f4a6"}]'::jsonb;
 primary_key_pins jsonb:='[{"attribute":"id","collation_oid":"100","index_definition_sha256":"b5c5e71c2fdc51167b2308a16b62c1838bf90710040a6b274e3a22ed09a37a28","index_name":"backfill_tasks_v2_pkey","index_oid":"16040151","relation_name":"backfill_tasks_v2","relation_oid":"16040120","type_oid":"25","typmod":-1},{"attribute":"task_id","collation_oid":"100","index_definition_sha256":"a2fe7dc9f8249fbb3ffdc2ec706982522272751ce28829909b5d47f91170fdbd","index_name":"backfill_plan_units_v2_pkey","index_oid":"16041321","relation_name":"backfill_plan_units_v2","relation_oid":"16041315","type_oid":"25","typmod":-1}]'::jsonb;
 pk_pin jsonb; pk_observed record; pk_results jsonb:='[]';
 trigger_pins jsonb:='[{"found":true,"tgtype":58,"tgenabled":"O","definition":"CREATE TRIGGER backfill_plan_units_immutable_v2 BEFORE DELETE OR UPDATE OR TRUNCATE ON astra_ingestion_v1.backfill_plan_units_v2 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.backfill_evidence_guard_v2()","table_name":"astra_ingestion_v1.backfill_plan_units_v2","trigger_oid":"16041361","function_oid":"16040226","relation_oid":"16041315","tgisinternal":false,"trigger_name":"backfill_plan_units_immutable_v2","full_trigger_metadata_sha256":"10a7f1b4ecfdc225e97069f8ce7f0a084f4cad96532cb64bc370e7e7176fc5f5"},{"found":true,"tgtype":19,"tgenabled":"O","definition":"CREATE TRIGGER backfill_run_immutable_v2 BEFORE UPDATE ON astra_ingestion_v1.backfill_runs_v2 FOR EACH ROW EXECUTE FUNCTION astra_ingestion_v1.backfill_run_guard_v2()","table_name":"astra_ingestion_v1.backfill_runs_v2","trigger_oid":"16040223","function_oid":"16040222","relation_oid":"16040070","tgisinternal":false,"trigger_name":"backfill_run_immutable_v2","full_trigger_metadata_sha256":"324ed022b79f8710c442e2876bd8e4c209f1084a7fb730251e649adce9e3548c"},{"found":true,"tgtype":5,"tgenabled":"O","definition":"CREATE TRIGGER backfill_static_plan_snapshot_v2 AFTER INSERT ON astra_ingestion_v1.backfill_tasks_v2 FOR EACH ROW EXECUTE FUNCTION astra_ingestion_v1.backfill_snapshot_insert_v2()","table_name":"astra_ingestion_v1.backfill_tasks_v2","trigger_oid":"16041468","function_oid":"16041467","relation_oid":"16040120","tgisinternal":false,"trigger_name":"backfill_static_plan_snapshot_v2","full_trigger_metadata_sha256":"74709c28f3db1ec351d07deaf492e29636c63b39245f5bd77e2aa19964deddf9"},{"found":true,"tgtype":23,"tgenabled":"O","definition":"CREATE TRIGGER backfill_task_scope_v2 BEFORE INSERT OR UPDATE ON astra_ingestion_v1.backfill_tasks_v2 FOR EACH ROW EXECUTE FUNCTION astra_ingestion_v1.backfill_task_guard_v2()","table_name":"astra_ingestion_v1.backfill_tasks_v2","trigger_oid":"16040225","function_oid":"16040224","relation_oid":"16040120","tgisinternal":false,"trigger_name":"backfill_task_scope_v2","full_trigger_metadata_sha256":"d1705f679536181300a1f6dea3efe94d02068127b5b6d5da908fe78ae27ae4c1"},{"tgtype":58,"tgenabled":"O","definition":"CREATE TRIGGER backfill_plan_manifest_immutable_v2 BEFORE DELETE OR UPDATE OR TRUNCATE ON astra_ingestion_v1.backfill_plan_manifests_v2 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.backfill_evidence_guard_v2()","trigger_oid":"16041362","function_oid":"16040226","relation_oid":"16041342","tgisinternal":false,"trigger_name":"backfill_plan_manifest_immutable_v2","full_trigger_metadata_sha256":"82707ad7bbf31a1fe5f6296ef81c2fe3867d277be90b06077ba08252748b1aa6","table_name":"astra_ingestion_v1.backfill_plan_manifests_v2","found":true}]'::jsonb;
 trigger_pin jsonb; trigger_observed record;
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
 THEN RAISE EXCEPTION 'v81 requires the current finite existing controller, fixed cohort and unchanged scope'; END IF;
 -- Restore preserves any already committed seal; it never resets a manifest.
 SELECT count(*)=17 AND bool_and(COALESCE(p.oid::text=e.v->>'oid'
  AND encode(sha256(convert_to(pg_get_functiondef(p.oid),'UTF8')),'hex')=e.v->>'source_sha256'
  AND encode(sha256(convert_to((to_jsonb(p)-'prosrc')::text,'UTF8')),'hex')=e.v->>'metadata_sha256',false)) INTO ok
 FROM jsonb_array_elements(before_pins) e(v) LEFT JOIN pg_proc p ON p.oid=to_regprocedure(e.v->>'signature');
 IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'v81 exact source/OID/full metadata guard failed; reconcile, do not replay'; END IF;
  IF jsonb_array_length(primary_key_pins) IS DISTINCT FROM 2 THEN
   RAISE EXCEPTION 'v81 requires exactly two pinned global primary keys; no function replaced'; END IF;
  FOR pk_pin IN SELECT value FROM jsonb_array_elements(primary_key_pins) LOOP
   SELECT c.oid::text relation_oid,c.relname,c.relkind,c.relispartition,c.relhassubclass,
    i.indexrelid::text index_oid,i.indisprimary,i.indisunique,i.indimmediate,i.indisvalid,i.indisready,i.indislive,
    i.indnkeyatts,i.indnatts,i.indpred IS NULL predicate_absent,i.indexprs IS NULL expressions_absent,
    catalog_attribute.attname,catalog_attribute.attnotnull,catalog_attribute.atttypid::text type_oid,catalog_attribute.atttypmod typmod,catalog_attribute.attcollation::text collation_oid,
    k.condeferrable,k.condeferred,k.convalidated,k.conkey=ARRAY[catalog_attribute.attnum]::smallint[] exact_constraint_key,
    encode(sha256(convert_to(pg_get_indexdef(i.indexrelid),'UTF8')),'hex') index_definition_sha256,
    EXISTS(SELECT 1 FROM pg_catalog.pg_inherits h WHERE h.inhrelid=c.oid OR h.inhparent=c.oid) inheritance_present
    INTO pk_observed FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    JOIN pg_catalog.pg_index i ON i.indrelid=c.oid JOIN pg_catalog.pg_attribute catalog_attribute ON catalog_attribute.attrelid=c.oid AND catalog_attribute.attnum=i.indkey[0]
    JOIN pg_catalog.pg_constraint k ON k.conrelid=c.oid AND k.conindid=i.indexrelid AND k.contype='p'
    WHERE c.oid=(pk_pin->>'relation_oid')::oid AND i.indexrelid=(pk_pin->>'index_oid')::oid AND n.nspname='astra_ingestion_v1';
   IF NOT FOUND OR pk_observed.relation_oid IS DISTINCT FROM pk_pin->>'relation_oid' OR pk_observed.relname IS DISTINCT FROM pk_pin->>'relation_name'
    OR pk_observed.index_oid IS DISTINCT FROM pk_pin->>'index_oid' OR pk_observed.relkind IS DISTINCT FROM 'r'::"char"
    OR pk_observed.relispartition OR pk_observed.relhassubclass OR pk_observed.inheritance_present
    OR NOT COALESCE(pk_observed.indisprimary AND pk_observed.indisunique AND pk_observed.indimmediate AND pk_observed.indisvalid
     AND pk_observed.indisready AND pk_observed.indislive AND pk_observed.predicate_absent AND pk_observed.expressions_absent
     AND pk_observed.attnotnull AND pk_observed.exact_constraint_key AND pk_observed.convalidated,false)
    OR pk_observed.indnkeyatts IS DISTINCT FROM 1 OR pk_observed.indnatts IS DISTINCT FROM 1
    OR pk_observed.condeferrable IS DISTINCT FROM false OR pk_observed.condeferred IS DISTINCT FROM false
    OR pk_observed.attname IS DISTINCT FROM pk_pin->>'attribute' OR pk_observed.type_oid IS DISTINCT FROM pk_pin->>'type_oid'
    OR pk_observed.typmod IS DISTINCT FROM (pk_pin->>'typmod')::integer OR pk_observed.collation_oid IS DISTINCT FROM pk_pin->>'collation_oid'
    OR pk_observed.index_definition_sha256 IS DISTINCT FROM pk_pin->>'index_definition_sha256' THEN
    RAISE EXCEPTION 'v81 candidate immediate global primary-key/catalog premise changed; no function replaced'; END IF;
   pk_results:=pk_results||jsonb_build_array(to_jsonb(pk_observed));
  END LOOP;
 IF current_setting('session_replication_role') IS DISTINCT FROM 'origin'
  OR jsonb_array_length(trigger_pins) IS DISTINCT FROM 5 THEN
  RAISE EXCEPTION 'v81 requires five enabled original trigger controls under origin replication role'; END IF;
 FOR trigger_pin IN SELECT value FROM jsonb_array_elements(trigger_pins) LOOP
  SELECT control.oid::text trigger_oid,control.tgrelid::text relation_oid,control.tgfoid::text function_oid,
   control.tgname trigger_name,control.tgenabled,control.tgtype,control.tgisinternal,
   pg_get_triggerdef(control.oid,true) definition,
   encode(sha256(convert_to(to_jsonb(control)::text,'UTF8')),'hex') full_trigger_metadata_sha256
   INTO trigger_observed FROM pg_catalog.pg_trigger control
   WHERE control.oid=(trigger_pin->>'trigger_oid')::oid AND control.tgrelid=to_regclass(trigger_pin->>'table_name');
  IF NOT FOUND OR trigger_observed.trigger_oid IS DISTINCT FROM trigger_pin->>'trigger_oid'
   OR trigger_observed.relation_oid IS DISTINCT FROM trigger_pin->>'relation_oid'
   OR trigger_observed.function_oid IS DISTINCT FROM trigger_pin->>'function_oid'
   OR trigger_observed.trigger_name IS DISTINCT FROM trigger_pin->>'trigger_name'
   OR trigger_observed.tgenabled IS DISTINCT FROM 'O'::"char" OR trigger_observed.tgisinternal
   OR trigger_observed.tgtype IS DISTINCT FROM (trigger_pin->>'tgtype')::smallint
   OR trigger_observed.definition IS DISTINCT FROM trigger_pin->>'definition'
   OR trigger_observed.full_trigger_metadata_sha256 IS DISTINCT FROM trigger_pin->>'full_trigger_metadata_sha256' THEN
   RAISE EXCEPTION 'v81 current trigger definition, enabled state or full metadata changed'; END IF;
 END LOOP;
 EXECUTE $definition0$CREATE OR REPLACE FUNCTION astra_ingestion_v1.backfill_plan_next_v2(p_payload jsonb)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
 SET "TimeZone" TO 'UTC'
 SET statement_timeout TO '8s'
 SET lock_timeout TO '1s'
AS $function$
DECLARE
 r astra_ingestion_v1.backfill_runs_v2;
 m astra_ingestion_v1.backfill_members_v2;
 v_run text:=COALESCE(p_payload->>'run_id','fixed3000-20250901-20260731-v1-20261030');
 v_limit int:=GREATEST(1,LEAST(COALESCE((p_payload->>'member_limit')::int,1),5));
 v_next int; v_breadth int; v_phase text; v_added int:=0; v_members int:=0; v_expected bigint;
 v_calendar jsonb; v_month_calendar jsonb; v_target_dates jsonb; v_map jsonb; v_workflow jsonb; v_snapshot jsonb;
 v_scope jsonb; v_base jsonb; v_key text; v_source_id text; v_raw_id text; v_split_id text;
 v_anchor_count int; v_instrument int; v_asset text; v_month date; v_first date; v_last date;
 v_input date; v_entry jsonb; v_day date; v_family text; v_adjustment text; v_status text;
 v_count bigint; v_hash text; v_calendar_hash text; v_fallback boolean;
 v_after int; v_result jsonb; v_supported jsonb:=COALESCE(p_payload->'supported_kinds','[]'::jsonb);
BEGIN
 -- Same transaction lock as the authenticated existing RPC; no lease can be
 -- advanced by a competing planner between its insertions and checkpoint.
 PERFORM pg_advisory_xact_lock(706314020261028);
 SELECT * INTO STRICT r FROM astra_ingestion_v1.backfill_runs_v2 WHERE id=v_run FOR UPDATE;
 IF r.status<>'ACTIVE' THEN RETURN jsonb_build_object('state','PLANNING_PAUSED','run_id',r.id,'run_status',r.status,'plan_complete',false); END IF;
 IF r.metadata->'planning_complete'='true'::jsonb THEN
  RETURN jsonb_build_object('state','FULL_PLAN_SEALED','run_id',r.id,'plan_complete',true,
   'expected_task_count',r.metadata->'expected_static_task_count','expected_plan_sha256',r.metadata->'expected_plan_sha256');
 END IF;
 IF r.cohort_sha256<>'2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
 OR r.cohort_manifest_sha256<>'4134b415e2c26fcde9fced749c0d54ef51376e23f0d2f8c6ce9ef562f9fab99f'
 OR r.target_start<>'2025-09-01'::date OR r.target_end<>'2026-07-31'::date THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Planner accepts only the frozen replacement cohort and dates';
 END IF;
 SELECT count(*),encode(sha256(convert_to(string_agg(member_id,E'\n' ORDER BY selection_order,member_id),'UTF8')),'hex')
 INTO v_count,v_hash FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id=r.id;
 IF v_count<>3000 OR v_hash<>'a83310df6a6465ce8d37ffd5352095f6e38d91a3204afd8807fff39092cfd85e' THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Frozen actual 3000-member list differs; selection cannot be reopened';
 END IF;
 SELECT jsonb_agg(jsonb_build_object('date',e->>'date','open',e->>'open','close',e->>'close') ORDER BY e->>'date')
 INTO v_calendar FROM jsonb_array_elements(r.scope#>'{calendar,sessions}') e;
 v_calendar_hash:=encode(sha256(convert_to(astra_ingestion_v1.rpc_canonical(v_calendar),'UTF8')),'hex');
 IF v_calendar IS NULL OR jsonb_array_length(v_calendar)<>290 OR v_calendar_hash<>'8483822a5553f0d270d87d1ff69c9a30d512d9ea8f660036664aebbf70053d49'
 OR r.scope->>'daily_support_start' IS DISTINCT FROM '2025-06-05'
 OR r.scope->>'intraday_support_start' IS DISTINCT FROM '2025-08-04' THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Exact retained 290-session calendar and support history required';
 END IF;
 SELECT jsonb_agg(e->>'date' ORDER BY e->>'date') INTO v_target_dates FROM jsonb_array_elements(v_calendar) e
 WHERE e->>'date' BETWEEN '2025-09-01' AND '2026-07-31';
 v_workflow:=jsonb_build_object('version','fixed3000-plan-v2.1','target_start','2025-09-01','target_end','2026-07-31',
  'market_timezone','America/New_York','session_dates',v_target_dates,'cohort_classification','RETROSPECTIVE_FIXED_COHORT',
  'representative_policy','ONE_FROZEN_COMPANY_ONE_EXPLICIT_ANCHOR_SECURITY; ELIGIBILITY_UNKNOWN_UNTIL_EVIDENCED',
  'daily_support_start','2025-06-05','intraday_support_start','2025-08-04','calendar_sha256',v_calendar_hash,
  'formula_manifest_sha256','e0b0835ad53ef7b71d072184bbb1576b3cd8f514c523361fa31865f71a0c8a65',
  'families',jsonb_build_array('REF01','REF03','P01','P02','D01','D02','D03','D04','D05','N01','N02','N03','S01','S02','CTX02','CTX06'),
  'REF03',jsonb_build_object('mode','CONTINUOUS_AUDIT','scope','All replacement tasks/pages/exceptions/readbacks/recovery',
   'destination','astra_ingestion_v1.backfill_family_ref03_v2'),
  'P02',jsonb_build_object('mode','SHARED_P01_SOURCE_RETRIEVAL','sessions',jsonb_build_array('PRE','POST')),
  'event_policy','Retain all supplied action dates and boundary events; no ex-date-only archive restriction',
  'news_policy','All calendar dates, prefer Massive; separately retained Alpaca alternative if Massive worker configuration unavailable',
  'short_interest_policy','Settlement-date selection; actual publication/retrieval availability retained separately',
  'options_policy','Active and inactive underlying contracts; expiry Sep2025 through2099; dynamic individual-contract daily pages',
  'programme_expires_at',NULL);
 IF r.metadata->>'planner_version' IS NULL THEN
  v_snapshot:=astra_ingestion_v1.backfill_plan_snapshot_v2(r.id,500);
  IF v_snapshot->'more'='true'::jsonb THEN
   RETURN jsonb_build_object('state','SNAPSHOTTING_EXISTING_TASKS','plan_complete',false,'snapshot',v_snapshot);
  END IF;
  SELECT count(*) INTO v_expected FROM astra_ingestion_v1.backfill_plan_units_v2 WHERE run_id=r.id;
  r.metadata:=r.metadata||jsonb_build_object('planner_version','fixed3000-plan-v2.1','planner_phase','MEMBERS',
   'planner_next_selection_order',1,'planner_next_breadth_index',0,'planner_expected_static_count',v_expected,
   'planner_preexisting_static_count',v_expected,'workflow_plan',v_workflow);
 ELSIF r.metadata->>'planner_version'<>'fixed3000-plan-v2.1' THEN
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Existing planner version differs; retain and explicitly reconcile its checkpoint';
 END IF;
 v_next:=(r.metadata->>'planner_next_selection_order')::int;
 v_breadth:=(r.metadata->>'planner_next_breadth_index')::int;
 v_phase:=r.metadata->>'planner_phase';
 v_expected:=(r.metadata->>'planner_expected_static_count')::bigint;
 IF jsonb_typeof(v_supported)<>'array' THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Worker supported kinds must be an explicit array'; END IF;
 v_fallback:=v_supported ? 'alpaca_news' AND NOT (v_supported ? 'massive_news');

 IF v_phase='MEMBERS' THEN
  -- backfill_planner_one_member_v2: commit one complete member before the next existing worker call.
  FOR m IN SELECT * FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id=r.id AND selection_order>=v_next
   ORDER BY selection_order LIMIT LEAST(v_limit,1)
  LOOP
   v_base:=jsonb_build_object('member_ids',jsonb_build_array(m.member_id),'symbols',jsonb_build_array(m.anchor_ticker),
    'symbol',m.anchor_ticker,'market_timezone','America/New_York','target_start','2025-09-01','target_end','2026-07-31',
    'identity_status','UNRESOLVED_PROVIDER_ANCHOR','asof','2026-08-03','cohort_classification','RETROSPECTIVE_FIXED_COHORT');
   v_key:=m.member_id||':';
   -- Daily raw/split series are fetched once per member for all required support.
   FOREACH v_adjustment IN ARRAY ARRAY['raw','split'] LOOP
    v_scope:=v_base||jsonb_build_object('timeframe','1Day','feed','sip','adjustment',v_adjustment,
     'start','2025-06-05T04:00:00Z','end','2026-08-01T03:59:59.999999Z','input_start','2025-06-05',
     'calendar',v_calendar,'daily_basis','ALPACA_PROVIDER_DAILY_NOT_ASSERTED_RTH','governing_date','MARKET_DATE',
     'support_history_policy','Observations before2025-09-01 retained as support history');
    v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'daily-source:'||v_adjustment,'D02','Alpaca','alpaca_stock_bars',v_scope,'{}',20);
   END LOOP;
   v_raw_id:=astra_ingestion_v1.backfill_plan_task_id_v2(r.id,v_key||'daily-source:raw');
   v_split_id:=astra_ingestion_v1.backfill_plan_task_id_v2(r.id,v_key||'daily-source:split');
   v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'reference:alpaca','REF01','Alpaca','alpaca_reference',
    v_base||jsonb_build_object('reference_policy','CURRENT_PROVIDER_IDENTIFIERS_NOT_HISTORICAL_PROOF'),'{}',10);
   SELECT count(*),min(instrument_key),min(alpaca_asset_id::text) INTO v_anchor_count,v_instrument,v_asset
    FROM reference.alpaca_fixed_window_instruments_v1 WHERE symbol=m.anchor_ticker AND alpaca_asset_id IS NOT NULL;
   -- Twelve monthly minute-source units cover Aug support plus all11 targetmonths.
   FOR v_month IN SELECT d::date FROM generate_series('2025-08-01'::date,'2026-07-01'::date,interval '1 month') d LOOP
    v_first:=GREATEST(v_month,'2025-08-04'::date);v_last:=(v_month+interval '1 month')::date-1;
    SELECT jsonb_agg(e ORDER BY e->>'date') INTO v_month_calendar FROM jsonb_array_elements(v_calendar) e
     WHERE (e->>'date')::date BETWEEN v_first AND v_last;
    v_scope:=v_base||jsonb_build_object('source_month',v_month::text,'target_start',v_first::text,'target_end',v_last::text,
     'input_start',v_first::text,'calendar',COALESCE(v_month_calendar,'[]'::jsonb),'feed','sip','timeframe','1Min','adjustment','raw',
     'start',to_char(v_first::timestamp AT TIME ZONE 'America/New_York' AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"'),
     'end_exclusive',to_char((v_last+1)::timestamp AT TIME ZONE 'America/New_York' AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"'),
     'support_history',v_last<'2025-09-01'::date,'governing_date','MARKET_SESSION',
     'shared_families',jsonb_build_array('P01','P02'),'identity_mapping_basis','POST_WINDOW_PROVIDER_ANCHOR_ONLY');
    IF v_anchor_count=1 THEN
     v_scope:=v_scope||jsonb_build_object('instrument_key',v_instrument,'alpaca_asset_id',v_asset,
      'reuse_policy','VERIFY_RETAINED_SOURCE_AND_ADMIT_ONLY_MISSING_OR_UNQUALIFIED_RANGES');
     v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'minutes:'||v_month::text,'P01','REUSE','retained_reuse',v_scope,'{}',30);
    ELSE
     v_scope:=v_scope||jsonb_build_object('end',to_char(((v_last+1)::timestamp AT TIME ZONE 'America/New_York')-interval '1 microsecond','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
      'retained_reference_state',CASE WHEN v_anchor_count=0 THEN 'NO_MATCHING_RETAINED_PROVIDER_ANCHOR' ELSE 'AMBIGUOUS_RETAINED_PROVIDER_ANCHOR' END);
     v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'minutes:'||v_month::text,'P01','Alpaca','alpaca_stock_bars',v_scope,'{}',30);
    END IF;
    IF v_month<'2025-09-01'::date THEN CONTINUE; END IF;
    v_source_id:=astra_ingestion_v1.backfill_plan_task_id_v2(r.id,v_key||'minutes:'||v_month::text);
    FOR v_entry IN SELECT e FROM jsonb_array_elements(v_month_calendar) e LOOP
     v_day:=(v_entry->>'date')::date;
     v_scope:=v_base||jsonb_build_object('target_start',v_day::text,'target_end',v_day::text,'input_start',v_day::text,
      'source_month',v_month::text,'calendar',jsonb_build_array(v_entry),'governing_date','MARKET_SESSION',
      'formula_version','fixed3000-derived-v2.1','prefer_retained_formula_cache',true,
      'retained_formula_policy','Preserve original qualifying formula version and lineage when equivalent cache is available');
     v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'D01:'||v_day::text,'D01','DERIVED','derive_intraday',v_scope,ARRAY[v_source_id],160);
    END LOOP;
    -- The last60 actual preceding sessions, plus current month, are sufficient
    -- for all recovered daily horizons. Missing observations are never filled.
    SELECT min((x.e->>'date')::date) INTO v_input FROM (SELECT e FROM jsonb_array_elements(v_calendar) e
     WHERE (e->>'date')::date<v_month ORDER BY e->>'date' DESC LIMIT 60) x;
    SELECT jsonb_agg(e ORDER BY e->>'date') INTO v_month_calendar FROM jsonb_array_elements(v_calendar) e
     WHERE (e->>'date')::date BETWEEN v_input AND v_last;
    FOREACH v_family IN ARRAY ARRAY['D02','D03','D04','D05'] LOOP
     v_scope:=v_base||jsonb_build_object('target_start',v_month::text,'target_end',v_last::text,'input_start',v_input::text,
      'source_month',v_month::text,'calendar',v_month_calendar,'governing_date','MARKET_SESSION',
      'formula_version','fixed3000-derived-v2.1','prefer_retained_formula_cache',true);
     v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||v_family||':'||v_month::text,v_family,'DERIVED','derive_daily',v_scope,ARRAY[v_raw_id,v_split_id],100);
    END LOOP;
    v_scope:=v_base||jsonb_build_object('target_start',v_month::text,'target_end',v_last::text,'asof',v_month::text,
     'governing_date','REFERENCE_AS_OF','reference_policy','DATED_PROVIDER_SNAPSHOT_ATTRIBUTION_REMAINS_EXPLICIT');
    v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'reference:massive:'||v_month::text,'REF01','Massive','massive_reference',v_scope,'{}',40);
    v_scope:=v_base||jsonb_build_object('target_start',v_month::text,'target_end',v_last::text,
     'start',to_char(v_month::timestamp AT TIME ZONE 'America/New_York' AT TIME ZONE 'UTC','YYYY-MM-DD"T"HH24:MI:SS"Z"'),
     'end',to_char(((v_last+1)::timestamp AT TIME ZONE 'America/New_York')-interval '1 microsecond','YYYY-MM-DD"T"HH24:MI:SS.US"Z"'),
     'governing_date','PUBLICATION_TIMESTAMP','include_weekends_holidays',true,'archive_scope','MASSIVE_ENTITLED_ARCHIVE',
     'permitted_alternative','alpaca_news');
    v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'news:massive:'||v_month::text,'N01','Massive','massive_news',v_scope,'{}',50);
    IF v_fallback THEN
     v_scope:=v_scope||jsonb_build_object('archive_scope','ALPACA_ENTITLED_ARCHIVE',
      'alternative_reason','MASSIVE_WORKER_CONFIGURATION_UNAVAILABLE','does_not_complete_primary_archive',true,
      'primary_task_id',astra_ingestion_v1.backfill_plan_task_id_v2(r.id,v_key||'news:massive:'||v_month::text));
     v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'news:alpaca:'||v_month::text,'N01','Alpaca','alpaca_news',v_scope,'{}',51);
    END IF;
   END LOOP;
   v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'reference:massive:2026-07-31','REF01','Massive','massive_reference',
    v_base||jsonb_build_object('asof','2026-07-31','governing_date','REFERENCE_AS_OF'),'{}',40);
   v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'dividends:massive','N02','Massive','massive_dividends',
    v_base||jsonb_build_object('governing_date','DECLARATION_EX_RECORD_PAYMENT_EFFECTIVE_SEPARATE','archive_date_filter','UNBOUNDED_PROVIDER_EVENT_HISTORY','retain_boundary_crossing_events',true),'{}',45);
   v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'splits:massive','N03','Massive','massive_splits',
    v_base||jsonb_build_object('governing_date','EXECUTION_EFFECTIVE_DATE','archive_date_filter','UNBOUNDED_PROVIDER_EVENT_HISTORY','retain_boundary_crossing_events',true),'{}',45);
   v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'actions:alpaca','N02','Alpaca','alpaca_actions',
    v_base||jsonb_build_object('start','2025-06-05','end',(r.created_at AT TIME ZONE 'America/New_York')::date::text,
     'governing_date','PROVIDER_PROCESS_DATE_WITH_SUPPLIED_ACTION_DATES_RETAINED','retain_boundary_crossing_events',true,
     'shared_families',jsonb_build_array('N02','N03')),'{}',45);
   v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'short-volume','S01','Massive','massive_short_volume',
    v_base||jsonb_build_object('start','2025-09-01','end','2026-07-31','governing_date','REPORTING_DATE',
     'reporting_scope','PROVIDER_FINRA_OFF_EXCHANGE_NOT_TOTAL_MARKET'),'{}',60);
   v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'short-interest','S02','Massive','massive_short_interest',
    v_base||jsonb_build_object('start','2025-09-01','end','2026-07-31','governing_date','SETTLEMENT_DATE',
     'publication_date_filter','NONE','retain_later_publications',true,'availability_policy','ACTUAL_PUBLICATION_WHEN_SUPPLIED_ELSE_RETRIEVAL_UPPER_BOUND'),'{}',60);
   FOREACH v_status IN ARRAY ARRAY['active','inactive'] LOOP
    v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,v_key||'options:'||v_status,'CTX02','Alpaca','alpaca_option_contracts',
     v_base||jsonb_build_object('status',v_status,'expiration_start','2025-09-01','expiration_end','2099-12-31',
      'governing_date','CONTRACT_EXPIRY_REFERENCE_AND_DAILY_MARKET_DATE','include_adjusted_contracts',true,
      'historical_enumeration_completeness','UNKNOWN_UNTIL_PROVIDER_REFERENCE_EXHAUSTED'),'{}',70);
   END LOOP;
   v_next:=m.selection_order+1;v_members:=v_members+1;
  END LOOP;
  IF v_next>3000 THEN v_phase:='BREADTH'; END IF;
 ELSIF v_phase='BREADTH' THEN
  SELECT jsonb_object_agg(member_id,jsonb_build_object('symbol',anchor_ticker,'eligible',NULL) ORDER BY selection_order)
   INTO v_map FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id=r.id;
  v_after:=v_breadth;
  FOR v_entry IN SELECT e FROM jsonb_array_elements(v_calendar) e WHERE e->>'date' BETWEEN '2025-09-01' AND '2026-07-31'
   ORDER BY e->>'date' OFFSET v_after LIMIT v_limit
  LOOP
   v_day:=(v_entry->>'date')::date;
   v_scope:=jsonb_build_object('target_start',v_day::text,'target_end',v_day::text,'input_start',v_day::text,
    'market_timezone','America/New_York','calendar',jsonb_build_array(v_entry),'source_family','D03',
    'source_month',date_trunc('month',v_day)::date::text,'representative_security',v_map,
    'representative_policy',v_workflow->'representative_policy','governing_date','MARKET_SESSION',
    'formula_version','fixed3000-derived-v2.1','cohort_classification','RETROSPECTIVE_FIXED_COHORT');
   v_added:=v_added+astra_ingestion_v1.backfill_plan_insert_v2(r.id,r.fence,'CTX06:'||v_day::text,'CTX06','DERIVED','derive_breadth',v_scope,'{}',250);
   v_breadth:=v_breadth+1;
  END LOOP;
  IF v_breadth=230 THEN v_phase:='SEAL'; END IF;
 ELSIF v_phase='SEAL' THEN
  v_snapshot:=astra_ingestion_v1.backfill_plan_snapshot_v2(r.id,500);
  IF v_snapshot->'more'='true'::jsonb THEN RETURN jsonb_build_object('state','SNAPSHOTTING_EXISTING_TASKS','plan_complete',false,'snapshot',v_snapshot); END IF;
  SELECT count(*),encode(sha256(convert_to(COALESCE(string_agg(task_id||':'||definition_sha256,E'\n' ORDER BY task_id COLLATE "C"),''),'UTF8')),'hex')
   INTO v_count,v_hash FROM astra_ingestion_v1.backfill_plan_units_v2 WHERE run_id=r.id;
  IF v_count<>v_expected THEN RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Actual static plan count differs from transactionally admitted expected count'; END IF;
  v_result:=astra_ingestion_v1.backfill_seal_plan_v2(r.id,v_expected,v_hash,v_workflow);
  RETURN v_result||jsonb_build_object('run_id',r.id,'plan_complete',v_result->>'state'='FULL_PLAN_SEALED',
   'planned_members',3000,'next_selection_order',3001,'breadth_sessions',230);
 ELSE
  RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='Unknown persisted planner phase';
 END IF;
 v_expected:=v_expected+v_added;
 UPDATE astra_ingestion_v1.backfill_runs_v2 SET metadata=r.metadata||jsonb_build_object(
  'planner_phase',v_phase,'planner_next_selection_order',v_next,'planner_next_breadth_index',v_breadth,
  'planner_expected_static_count',v_expected,'workflow_plan',v_workflow,'planner_last_progress_at',clock_timestamp()),
  last_progress_at=CASE WHEN v_added>0 THEN clock_timestamp() ELSE last_progress_at END WHERE id=r.id;
 RETURN jsonb_build_object('state','PLAN_ADVANCED','run_id',r.id,'phase',v_phase,'plan_complete',false,
  'members_admitted_this_call',v_members,'planned_members',v_next-1,'next_selection_order',v_next,
  'breadth_sessions',v_breadth,'inserted_tasks',v_added,'expected_static_task_count',v_expected);
END $function$
$definition0$;
 SELECT count(*)=17 AND bool_and(COALESCE(p.oid::text=e.v->>'oid'
  AND encode(sha256(convert_to(pg_get_functiondef(p.oid),'UTF8')),'hex')=e.v->>'source_sha256'
  AND encode(sha256(convert_to((to_jsonb(p)-'prosrc')::text,'UTF8')),'hex')=e.v->>'metadata_sha256',false)) INTO ok
 FROM jsonb_array_elements(after_pins) e(v) LEFT JOIN pg_proc p ON p.oid=to_regprocedure(e.v->>'signature');
 IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'v81 post-replacement source/OID/full metadata differs'; END IF;
 IF current_setting('session_replication_role') IS DISTINCT FROM 'origin'
  OR jsonb_array_length(trigger_pins) IS DISTINCT FROM 5 THEN
  RAISE EXCEPTION 'v81 requires five enabled original trigger controls under origin replication role'; END IF;
 FOR trigger_pin IN SELECT value FROM jsonb_array_elements(trigger_pins) LOOP
  SELECT control.oid::text trigger_oid,control.tgrelid::text relation_oid,control.tgfoid::text function_oid,
   control.tgname trigger_name,control.tgenabled,control.tgtype,control.tgisinternal,
   pg_get_triggerdef(control.oid,true) definition,
   encode(sha256(convert_to(to_jsonb(control)::text,'UTF8')),'hex') full_trigger_metadata_sha256
   INTO trigger_observed FROM pg_catalog.pg_trigger control
   WHERE control.oid=(trigger_pin->>'trigger_oid')::oid AND control.tgrelid=to_regclass(trigger_pin->>'table_name');
  IF NOT FOUND OR trigger_observed.trigger_oid IS DISTINCT FROM trigger_pin->>'trigger_oid'
   OR trigger_observed.relation_oid IS DISTINCT FROM trigger_pin->>'relation_oid'
   OR trigger_observed.function_oid IS DISTINCT FROM trigger_pin->>'function_oid'
   OR trigger_observed.trigger_name IS DISTINCT FROM trigger_pin->>'trigger_name'
   OR trigger_observed.tgenabled IS DISTINCT FROM 'O'::"char" OR trigger_observed.tgisinternal
   OR trigger_observed.tgtype IS DISTINCT FROM (trigger_pin->>'tgtype')::smallint
   OR trigger_observed.definition IS DISTINCT FROM trigger_pin->>'definition'
   OR trigger_observed.full_trigger_metadata_sha256 IS DISTINCT FROM trigger_pin->>'full_trigger_metadata_sha256' THEN
   RAISE EXCEPTION 'v81 current trigger definition, enabled state or full metadata changed'; END IF;
 END LOOP;

 SELECT * INTO STRICT a FROM astra_ingestion_v1.backfill_runs_v2 WHERE id=r.id;
 IF to_jsonb(a) IS DISTINCT FROM to_jsonb(r) THEN RAISE EXCEPTION 'v81 altered run state or accounting'; END IF;
END $v81$;
COMMIT;
