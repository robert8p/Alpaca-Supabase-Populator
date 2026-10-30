-- LOCAL PREPARATION ONLY: independent review, publication and exact-head CI precede activation.
-- install only backfill_maintain_v2; no helper/provider invocation or grant/configuration change.
-- Source, full maintenance metadata, 13 unchanged function pins, audit permissions,
-- the installed hash pair and all other schema catalogs are checked before/after.
BEGIN;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $phase_observation_install$
DECLARE
 v_before text; v_before_metadata jsonb; v_after_metadata jsonb;
 v_catalog_before jsonb; v_catalog_after jsonb;
 v_audit_before jsonb; v_audit_after jsonb; v_indexes_before jsonb; v_indexes_after jsonb;
 v_pin_source text; v_pin_metadata jsonb; v_pin_partial jsonb; g record;
 v_expected_metadata constant jsonb := $maintain_metadata${"oid":"16041463","proacl":["astra_ingestion_rpc_owner_v1=X/astra_ingestion_rpc_owner_v1","astra_ingestion_monitor_owner_v1=X/astra_ingestion_rpc_owner_v1"],"proallargtypes":null,"proargdefaults":"({CONST :consttype 23 :consttypmod -1 :constcollid 0 :constlen 4 :constbyval true :constisnull false :location -1 :constvalue 4 [ 2 0 0 0 0 0 0 0 ]})","proargmodes":null,"proargnames":["p_limit"],"proargtypes":["23"],"probin":null,"proconfig":["search_path=\"\"","statement_timeout=8s","lock_timeout=2s"],"procost":100,"proisstrict":false,"prokind":"f","prolang":"13619","proleakproof":false,"proname":"backfill_maintain_v2","pronamespace":"15984556","pronargdefaults":1,"pronargs":1,"proowner":"15985999","proparallel":"u","proretset":false,"prorettype":"3802","prorows":0,"prosecdef":true,"prosqlbody":null,"prosupport":"-","protrftypes":null,"provariadic":"0","provolatile":"v"}$maintain_metadata$::jsonb;
 v_expected_audit constant jsonb := $audit_metadata${"audit_sequence":{"acl":["postgres=rwU/postgres","astra_ingestion_rpc_owner_v1=U/postgres"],"name":"astra_ingestion_v1.backfill_audit_v2_id_seq","oid":"16041300","owner":"16388"},"audit_table":{"acl":["postgres=arwdDxtm/postgres","astra_ingestion_rpc_owner_v1=ar/postgres"],"force_rls":false,"oid":"16041301","owner":"16388","rls":true},"constraints":[{"definition":"PRIMARY KEY (id)","name":"backfill_audit_v2_pkey","type":"p"},{"definition":"FOREIGN KEY (run_id) REFERENCES astra_ingestion_v1.backfill_runs_v2(id)","name":"backfill_audit_v2_run_id_fkey","type":"f"}],"existing_maintain_owner_privileges":{"audit_delete":false,"audit_insert":true,"audit_select":true,"audit_update":false,"run_select":true,"run_update":true,"sequence_update":false,"sequence_usage":true},"policies":[{"oid":"16041480","polcmd":"a","polname":"backfill_delivery_insert","polpermissive":true,"polqual":null,"polrelid":"16041301","polroles":["15985999"],"polwithcheck":"{CONST :consttype 16 :consttypmod -1 :constcollid 0 :constlen 1 :constbyval true :constisnull false :location -1 :constvalue 1 [ 1 0 0 0 0 0 0 0 ]}"},{"oid":"16041475","polcmd":"r","polname":"backfill_delivery_read","polpermissive":true,"polqual":"{CONST :consttype 16 :consttypmod -1 :constcollid 0 :constlen 1 :constbyval true :constisnull false :location -1 :constvalue 1 [ 1 0 0 0 0 0 0 0 ]}","polrelid":"16041301","polroles":["15985999"],"polwithcheck":null}],"standard_roles":{"anon":{"audit_insert":false,"audit_select":false,"maintain_execute":false,"monitor_execute":false},"authenticated":{"audit_insert":false,"audit_select":false,"maintain_execute":false,"monitor_execute":false},"service_role":{"audit_insert":false,"audit_select":false,"maintain_execute":false,"monitor_execute":false}},"triggers":[{"definition":"CREATE CONSTRAINT TRIGGER \"RI_ConstraintTrigger_c_16041312\" AFTER INSERT ON astra_ingestion_v1.backfill_audit_v2 FROM astra_ingestion_v1.backfill_runs_v2 NOT DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION \"RI_FKey_check_ins\"()","enabled":"O","function":"\"RI_FKey_check_ins\"()","internal":true,"name":"RI_ConstraintTrigger_c_16041312"},{"definition":"CREATE CONSTRAINT TRIGGER \"RI_ConstraintTrigger_c_16041313\" AFTER UPDATE ON astra_ingestion_v1.backfill_audit_v2 FROM astra_ingestion_v1.backfill_runs_v2 NOT DEFERRABLE INITIALLY IMMEDIATE FOR EACH ROW EXECUTE FUNCTION \"RI_FKey_check_upd\"()","enabled":"O","function":"\"RI_FKey_check_upd\"()","internal":true,"name":"RI_ConstraintTrigger_c_16041313"},{"definition":"CREATE TRIGGER backfill_audit_immutable_v2 BEFORE DELETE OR UPDATE OR TRUNCATE ON astra_ingestion_v1.backfill_audit_v2 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.backfill_evidence_guard_v2()","enabled":"O","function":"astra_ingestion_v1.backfill_evidence_guard_v2()","internal":false,"name":"backfill_audit_immutable_v2"}]}$audit_metadata$::jsonb;
 v_expected_indexes constant jsonb := $index_metadata$[{"acl":null,"definition":"CREATE INDEX backfill_tasks_breadth_pending_id_v2 ON astra_ingestion_v1.backfill_tasks_v2 USING hash (id) WHERE ((family = 'D03'::text) AND (lower(provider) = 'derived'::text))","live":true,"method":"hash","name":"backfill_tasks_breadth_pending_id_v2","oid":"16638529","owner":"16388","ready":true,"valid":true},{"acl":null,"definition":"CREATE INDEX backfill_tasks_minute_pending_id_v2 ON astra_ingestion_v1.backfill_tasks_v2 USING hash (id) WHERE ((family = ANY (ARRAY['P01'::text, 'P02'::text])) AND (kind = ANY (ARRAY['retained_reuse'::text, 'alpaca_stock_bars'::text])) AND (COALESCE((scope ->> 'timeframe'::text), '1Min'::text) = '1Min'::text))","live":true,"method":"hash","name":"backfill_tasks_minute_pending_id_v2","oid":"16638569","owner":"16388","ready":true,"valid":true}]$index_metadata$::jsonb;
 v_expected_role constant jsonb := $owner_metadata${"oid":"15985999","rolbypassrls":false,"rolcanlogin":false,"rolname":"astra_ingestion_rpc_owner_v1","rolsuper":false}$owner_metadata$::jsonb;
 v_replacement constant text := $phase_replacement$CREATE OR REPLACE FUNCTION astra_ingestion_v1.backfill_maintain_v2(p_limit integer DEFAULT 2)
 RETURNS jsonb
 LANGUAGE plpgsql
 SECURITY DEFINER
 SET search_path TO ''
 SET statement_timeout TO '8s'
 SET lock_timeout TO '2s'
AS $function$
DECLARE p record; r record; v_readbacks integer:=0; v_errors integer:=0; v_final jsonb:='[]'; v_result jsonb;
 -- PHASE_OBSERVATION_V73_BEGIN declarations
 v_obs_enabled boolean:=false; v_obs_started timestamptz; v_obs_gate timestamptz;
 v_obs_admitted timestamptz; v_obs_phases jsonb;
 v_obs_breadth timestamptz;
 v_obs_minute timestamptz;
 v_obs_identity_discover timestamptz;
 v_obs_identity_refresh timestamptz;
 v_obs_nonminute timestamptz;
 v_obs_s02 timestamptz;
 v_obs_shared timestamptz;
 v_obs_contract timestamptz;
 v_obs_readback timestamptz;
 v_obs_finalize timestamptz;
 -- PHASE_OBSERVATION_V73_END declarations
BEGIN
 -- PHASE_OBSERVATION_V73_BEGIN entry
 v_obs_started:=clock_timestamp();
 -- PHASE_OBSERVATION_V73_END entry
 -- backfill_bounded_maintenance_wait_v2: existing two-second lock timeout.
 BEGIN
  PERFORM pg_advisory_xact_lock(706314020261028);
 EXCEPTION WHEN lock_not_available THEN
  RETURN jsonb_build_object('state','BUSY','reason','BOUNDED_WORKER_LOCK_WAIT_EXHAUSTED');
 END;
 -- PHASE_OBSERVATION_V73_BEGIN admission_after_existing_gate
 v_obs_gate:=clock_timestamp();
 -- The original VOLATILE function and existing gate serialize RC observations.
 -- Stronger isolation skips only telemetry: no new snapshot or timeout policy.
 IF current_setting('transaction_isolation')='read committed'
  AND v_obs_gate<'2026-10-30 15:45:00+00'::timestamptz THEN
  BEGIN
   SELECT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2 rr
    WHERE rr.id='fixed3000-20250901-20260731-v1-20261030' AND rr.fence=1
     AND rr.status IN ('ACTIVE','PARTIAL_OPERATIONAL_FAILURE','BLOCKED_EXTERNAL')
     AND rr.cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
     AND rr.metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
     AND (rr.metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()
     AND clock_timestamp()<'2026-10-30 15:45:00+00'::timestamptz) AND (SELECT count(*) FROM astra_ingestion_v1.backfill_audit_v2 a
      WHERE a.run_id='fixed3000-20250901-20260731-v1-20261030' AND a.action='MAINTENANCE_PHASE_OBSERVATION_V73'
       AND a.source_revision='maintenance-global-phase-observation-v73-20261030T1545Z' AND a.evidence->>'probe_id'='maintenance-global-phase-observation-v73-20261030T1545Z')<4 INTO v_obs_enabled;
  EXCEPTION WHEN query_canceled OR assert_failure THEN RAISE;
   WHEN OTHERS THEN v_obs_enabled:=false;
  END;
 END IF;
 IF v_obs_enabled THEN v_obs_admitted:=clock_timestamp(); END IF;
 -- PHASE_OBSERVATION_V73_END admission_after_existing_gate
 PERFORM astra_ingestion_v1.backfill_breadth_project_pending_v2(2);
 -- PHASE_OBSERVATION_V73_BEGIN breadth_finished
 IF v_obs_enabled THEN v_obs_breadth:=clock_timestamp(); END IF;
 -- PHASE_OBSERVATION_V73_END breadth_finished
 PERFORM astra_ingestion_v1.backfill_minute_account_pending_v2(2);
 -- PHASE_OBSERVATION_V73_BEGIN minute_finished
 IF v_obs_enabled THEN v_obs_minute:=clock_timestamp(); END IF;
 -- PHASE_OBSERVATION_V73_END minute_finished
 PERFORM astra_ingestion_v1.backfill_identity_discover_pending_v2();
 -- PHASE_OBSERVATION_V73_BEGIN identity_discover_finished
 IF v_obs_enabled THEN v_obs_identity_discover:=clock_timestamp(); END IF;
 -- PHASE_OBSERVATION_V73_END identity_discover_finished
 PERFORM astra_ingestion_v1.backfill_identity_refresh_pending_v2(2);
 -- PHASE_OBSERVATION_V73_BEGIN identity_refresh_finished
 IF v_obs_enabled THEN v_obs_identity_refresh:=clock_timestamp(); END IF;
 -- PHASE_OBSERVATION_V73_END identity_refresh_finished
 PERFORM astra_ingestion_v1.backfill_nonminute_project_pending_v2(2);
 -- PHASE_OBSERVATION_V73_BEGIN nonminute_finished
 IF v_obs_enabled THEN v_obs_nonminute:=clock_timestamp(); END IF;
 -- PHASE_OBSERVATION_V73_END nonminute_finished
 PERFORM astra_ingestion_v1.backfill_s02_maintain_v2();
 -- PHASE_OBSERVATION_V73_BEGIN s02_finished
 IF v_obs_enabled THEN v_obs_s02:=clock_timestamp(); END IF;
 -- PHASE_OBSERVATION_V73_END s02_finished
 PERFORM astra_ingestion_v1.backfill_shared_maintain_v2(4);
 -- PHASE_OBSERVATION_V73_BEGIN shared_finished
 IF v_obs_enabled THEN v_obs_shared:=clock_timestamp(); END IF;
 -- PHASE_OBSERVATION_V73_END shared_finished
 PERFORM astra_ingestion_v1.backfill_contract_maintain_v2();
 -- PHASE_OBSERVATION_V73_BEGIN contract_finished
 IF v_obs_enabled THEN v_obs_contract:=clock_timestamp(); END IF;
 -- PHASE_OBSERVATION_V73_END contract_finished
 FOR p IN SELECT pg.task_id,pg.page_no,pg.run_id FROM astra_ingestion_v1.backfill_pages_v2 pg
  JOIN astra_ingestion_v1.backfill_runs_v2 rr ON rr.id=pg.run_id
  WHERE rr.status IN ('ACTIVE','PARTIAL_OPERATIONAL_FAILURE','BLOCKED_EXTERNAL') AND pg.committed_at<transaction_timestamp() AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_readbacks_v2 v WHERE v.task_id=pg.task_id AND v.page_no=pg.page_no)
   AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_audit_v2 a WHERE a.task_id=pg.task_id AND a.action='READBACK_FAILURE' AND a.evidence->>'page_no'=pg.page_no::text)
  ORDER BY pg.committed_at,pg.task_id,pg.page_no LIMIT GREATEST(1,LEAST(p_limit,8))
 LOOP
  BEGIN
   PERFORM astra_ingestion_v1.backfill_recheck_page_v2(p.task_id,p.page_no);v_readbacks:=v_readbacks+1;
  EXCEPTION WHEN OTHERS THEN
   v_errors:=v_errors+1;
   IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_audit_v2 a WHERE a.task_id=p.task_id AND a.action='READBACK_FAILURE' AND a.evidence->>'page_no'=p.page_no::text) THEN
    INSERT INTO astra_ingestion_v1.backfill_audit_v2(run_id,task_id,action,evidence) VALUES(p.run_id,p.task_id,'READBACK_FAILURE',jsonb_build_object('page_no',p.page_no,'sqlstate',SQLSTATE,'reason',left(SQLERRM,500)));
   END IF;
  END;
 END LOOP;
 -- PHASE_OBSERVATION_V73_BEGIN readback_finished
 IF v_obs_enabled THEN v_obs_readback:=clock_timestamp(); END IF;
 -- PHASE_OBSERVATION_V73_END readback_finished
 FOR r IN SELECT id FROM astra_ingestion_v1.backfill_runs_v2 WHERE status IN ('ACTIVE','PARTIAL_OPERATIONAL_FAILURE','BLOCKED_EXTERNAL') LOOP
  v_result:=astra_ingestion_v1.backfill_try_finalize_v2(r.id);v_final:=v_final||jsonb_build_array(jsonb_build_object('run_id',r.id,'result',v_result));
 END LOOP;
 -- PHASE_OBSERVATION_V73_BEGIN append_optional_observation
 IF v_obs_enabled THEN
  v_obs_finalize:=clock_timestamp();
  BEGIN
   v_obs_phases:=jsonb_build_object('gate_admission_ms',round(extract(epoch FROM v_obs_gate-v_obs_started)*1000,3),
    'breadth_ms',round(extract(epoch FROM v_obs_breadth-v_obs_admitted)*1000,3),
    'minute_ms',round(extract(epoch FROM v_obs_minute-v_obs_breadth)*1000,3),
    'identity_discover_ms',round(extract(epoch FROM v_obs_identity_discover-v_obs_minute)*1000,3),
    'identity_refresh_ms',round(extract(epoch FROM v_obs_identity_refresh-v_obs_identity_discover)*1000,3),
    'nonminute_ms',round(extract(epoch FROM v_obs_nonminute-v_obs_identity_refresh)*1000,3),
    's02_ms',round(extract(epoch FROM v_obs_s02-v_obs_nonminute)*1000,3),
    'shared_ms',round(extract(epoch FROM v_obs_shared-v_obs_s02)*1000,3),
    'contract_ms',round(extract(epoch FROM v_obs_contract-v_obs_shared)*1000,3),
    'readback_ms',round(extract(epoch FROM v_obs_readback-v_obs_contract)*1000,3),
    'finalize_ms',round(extract(epoch FROM v_obs_finalize-v_obs_readback)*1000,3));
   -- Wall-clock reversal omits a sample instead of exporting misleading durations.
   IF v_obs_admitted>=v_obs_gate
    AND NOT EXISTS(SELECT 1 FROM jsonb_each_text(v_obs_phases) x WHERE x.value::numeric<0) THEN
    -- These are existing INSERT/row-lock privileges, not new grants. NOWAIT only
    -- avoids relation/row lock waiting; it cannot bound buffer, IO or commit cost.
    LOCK TABLE astra_ingestion_v1.backfill_audit_v2 IN ROW EXCLUSIVE MODE NOWAIT;
    PERFORM rr.id FROM astra_ingestion_v1.backfill_runs_v2 rr
     WHERE rr.id='fixed3000-20250901-20260731-v1-20261030' AND rr.fence=1
     AND rr.status IN ('ACTIVE','PARTIAL_OPERATIONAL_FAILURE','BLOCKED_EXTERNAL')
     AND rr.cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
     AND rr.metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
     AND (rr.metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()
     AND clock_timestamp()<'2026-10-30 15:45:00+00'::timestamptz FOR SHARE NOWAIT;
    IF FOUND AND (SELECT count(*) FROM astra_ingestion_v1.backfill_audit_v2 a
      WHERE a.run_id='fixed3000-20250901-20260731-v1-20261030' AND a.action='MAINTENANCE_PHASE_OBSERVATION_V73'
       AND a.source_revision='maintenance-global-phase-observation-v73-20261030T1545Z' AND a.evidence->>'probe_id'='maintenance-global-phase-observation-v73-20261030T1545Z')<4 THEN
     INSERT INTO astra_ingestion_v1.backfill_audit_v2(run_id,action,source_revision,evidence)
     SELECT 'fixed3000-20250901-20260731-v1-20261030','MAINTENANCE_PHASE_OBSERVATION_V73','maintenance-global-phase-observation-v73-20261030T1545Z',jsonb_build_object(
      'probe_id','maintenance-global-phase-observation-v73-20261030T1545Z','timing_scope','GLOBAL_MAINTENANCE_BEFORE_TELEMETRY',
      'backend_pid',pg_backend_pid(),'total_ms',round(extract(epoch FROM v_obs_finalize-v_obs_started)*1000,3),
      'telemetry_admission_ms',round(extract(epoch FROM v_obs_admitted-v_obs_gate)*1000,3),'phases_ms',v_obs_phases)
     WHERE clock_timestamp()<'2026-10-30 15:45:00+00'::timestamptz
      AND EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2 rr WHERE rr.id='fixed3000-20250901-20260731-v1-20261030' AND rr.fence=1
     AND rr.status IN ('ACTIVE','PARTIAL_OPERATIONAL_FAILURE','BLOCKED_EXTERNAL')
     AND rr.cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
     AND rr.metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
     AND (rr.metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()
     AND clock_timestamp()<'2026-10-30 15:45:00+00'::timestamptz);
     -- If the optional INSERT itself crossed expiry, roll back only its
     -- diagnostic subtransaction. The caller's later COMMIT is unmeasured.
     IF clock_timestamp()>='2026-10-30 15:45:00+00'::timestamptz
      OR NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2 rr WHERE rr.id='fixed3000-20250901-20260731-v1-20261030' AND rr.fence=1
     AND rr.status IN ('ACTIVE','PARTIAL_OPERATIONAL_FAILURE','BLOCKED_EXTERNAL')
     AND rr.cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
     AND rr.metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
     AND (rr.metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()
     AND clock_timestamp()<'2026-10-30 15:45:00+00'::timestamptz) THEN
      RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='PHASE_OBSERVATION_WINDOW_EXPIRED';
     END IF;
    END IF;
   END IF;
  EXCEPTION WHEN query_canceled OR assert_failure THEN RAISE;
   WHEN OTHERS THEN NULL;
  END;
 END IF;
 -- PHASE_OBSERVATION_V73_END append_optional_observation
 RETURN jsonb_build_object('state','OBSERVED','verified_pages',v_readbacks,'readback_errors',v_errors,'runs',v_final);
END $function$
$phase_replacement$;
BEGIN
 IF current_setting('statement_timeout')<>'8s' OR current_setting('lock_timeout')<>'3s'
  OR current_setting('transaction_read_only')<>'off' OR current_setting('transaction_isolation')<>'read committed' THEN
  RAISE EXCEPTION 'Phase observation replacement requires reviewed writable RC 8s/3s transaction bounds';
 END IF;
 IF clock_timestamp()>='2026-10-30 15:45:00+00'::timestamptz THEN
  RAISE EXCEPTION 'Phase observation fixed installation window expired';
 END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(706314020261028);
 PERFORM 1 FROM astra_ingestion_v1.backfill_runs_v2 WHERE id='fixed3000-20250901-20260731-v1-20261030' AND status='ACTIVE' AND fence=1
  AND cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
  AND metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
  AND (metadata->>'implementation_lease_until')::timestamptz>clock_timestamp() FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Phase observation owner, lease, status, fence or cohort differs'; END IF;
 IF (SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id='fixed3000-20250901-20260731-v1-20261030')<>3000 THEN
  RAISE EXCEPTION 'Phase observation requires the exact 3000-member cohort';
 END IF;
 SELECT pg_get_functiondef(p.oid),to_jsonb(p)-'prosrc' INTO STRICT v_before,v_before_metadata
  FROM pg_proc p WHERE p.oid='astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure;
 IF encode(sha256(convert_to(v_before,'UTF8')),'hex')<>'6c880114a645c8a9167d5260c4aeabf58a10617c4244cf0340be1d6cf4bf0ce7'
  OR v_before_metadata IS DISTINCT FROM v_expected_metadata THEN
  RAISE EXCEPTION 'Phase observation exact maintenance source/metadata differs; reconcile before replay';
 END IF;
 IF (SELECT jsonb_build_object('oid',r.oid::text,'rolname',r.rolname,'rolsuper',r.rolsuper,
  'rolcanlogin',r.rolcanlogin,'rolbypassrls',r.rolbypassrls) FROM pg_roles r
  WHERE r.oid=(v_expected_metadata->>'proowner')::oid) IS DISTINCT FROM v_expected_role THEN
  RAISE EXCEPTION 'Phase observation maintenance owner role differs';
 END IF;
 FOR g IN SELECT * FROM (VALUES
  ('astra_ingestion_v1.backfill_breadth_project_pending_v2(integer)','65c981bd15a70f01d35eefc06a3807c7e6cfa1120a4b149ba3829951a63cc0d0',false,$pin_metadata${"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"config":["search_path=\"\""],"owner":"16388","security_definer":false}$pin_metadata$::jsonb),
  ('astra_ingestion_v1.backfill_contract_maintain_v2()','52007f177dca38faf48fab8773936173519dcbfa54af896b5ef6f902ad64c748',false,$pin_metadata${"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"config":["search_path=\"\"","statement_timeout=20s"],"owner":"16388","security_definer":true}$pin_metadata$::jsonb),
  ('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)','28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44',true,$pin_metadata${"oid":"16040232","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"proallargtypes":null,"proargdefaults":null,"proargmodes":null,"proargnames":["p_operation","p_payload"],"proargtypes":["25","3802"],"probin":null,"proconfig":["search_path=\"\""],"procost":100,"proisstrict":false,"prokind":"f","prolang":"13619","proleakproof":false,"proname":"backfill_dispatch_v2","pronamespace":"15984556","pronargdefaults":0,"pronargs":2,"proowner":"16388","proparallel":"u","proretset":false,"prorettype":"3802","prorows":0,"prosecdef":false,"prosqlbody":null,"prosupport":"-","protrftypes":null,"provariadic":"0","provolatile":"v"}$pin_metadata$::jsonb),
  ('astra_ingestion_v1.backfill_identity_discover_pending_v2()','faf5e83a8f7baf717cfd9054948ed62a8fbda7aa432a1f671d895fe77db37618',false,$pin_metadata${"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"config":["search_path=\"\""],"owner":"16388","security_definer":false}$pin_metadata$::jsonb),
  ('astra_ingestion_v1.backfill_identity_refresh_pending_v2(integer)','87ebac87ea08bea09b98f01ae123ed698e8252bcd6ff6abeb1cec3abf6ba5e25',false,$pin_metadata${"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"config":["search_path=\"\"","statement_timeout=8s"],"owner":"16388","security_definer":false}$pin_metadata$::jsonb),
  ('astra_ingestion_v1.backfill_minute_account_pending_v2(integer)','49cc9131c989de8f2da0926a2d1312bee7262f2e7f63c7a800219257af1632f2',false,$pin_metadata${"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"config":["search_path=\"\"","statement_timeout=8s"],"owner":"16388","security_definer":true}$pin_metadata$::jsonb),
  ('astra_ingestion_v1.backfill_nonminute_project_pending_v2(integer)','ceb1889732da767e8815741a792347ccb91c33c53acd38eeff36f9176d063cec',false,$pin_metadata${"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"config":["search_path=\"\"","statement_timeout=8s"],"owner":"16388","security_definer":true}$pin_metadata$::jsonb),
  ('astra_ingestion_v1.backfill_recheck_page_v2(text,integer)','0ccd4018d16e3ed3932176d2886fe78c2c1b442d70473d71e137d86e7b6dfb37',true,$pin_metadata${"oid":"16041451","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"proallargtypes":null,"proargdefaults":null,"proargmodes":null,"proargnames":["p_task_id","p_page_no"],"proargtypes":["25","23"],"probin":null,"proconfig":["search_path=\"\""],"procost":100,"proisstrict":false,"prokind":"f","prolang":"13619","proleakproof":false,"proname":"backfill_recheck_page_v2","pronamespace":"15984556","pronargdefaults":0,"pronargs":2,"proowner":"16388","proparallel":"u","proretset":false,"prorettype":"3802","prorows":0,"prosecdef":false,"prosqlbody":null,"prosupport":"-","protrftypes":null,"provariadic":"0","provolatile":"v"}$pin_metadata$::jsonb),
  ('astra_ingestion_v1.backfill_s02_maintain_v2()','40827de08ca59d1470a02aceff6ccc249e6b43bb8ef13ff39eddffa673e78939',false,$pin_metadata${"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"config":["search_path=\"\"","statement_timeout=8s"],"owner":"16388","security_definer":true}$pin_metadata$::jsonb),
  ('astra_ingestion_v1.backfill_shared_maintain_v2(integer)','5da488f3e44e2521b64f58230b2bc6db3c34800ae4ac259166f4dc223c8ad2be',false,$pin_metadata${"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"config":["search_path=\"\"","statement_timeout=15s"],"owner":"16388","security_definer":true}$pin_metadata$::jsonb),
  ('astra_ingestion_v1.backfill_try_finalize_v2(text)','f8f9ef6d8d9ada232b132170bde9922397a2b247dbc7e4b391cbca57b67b7063',false,$pin_metadata${"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"config":["search_path=\"\""],"owner":"16388","security_definer":false}$pin_metadata$::jsonb),
  ('astra_ingestion_v1.monitor_tick_v1()','875c017ecf73df15163d15d3f9129b4507235dc893ccb4233d0a435154389057',true,$pin_metadata${"oid":"15990404","proacl":["astra_ingestion_monitor_owner_v1=X/astra_ingestion_monitor_owner_v1","postgres=X/astra_ingestion_monitor_owner_v1"],"proallargtypes":null,"proargdefaults":null,"proargmodes":null,"proargnames":null,"proargtypes":[],"probin":null,"proconfig":["search_path=\"\"","statement_timeout=8s","lock_timeout=2s"],"procost":100,"proisstrict":false,"prokind":"f","prolang":"13619","proleakproof":false,"proname":"monitor_tick_v1","pronamespace":"15984556","pronargdefaults":0,"pronargs":0,"proowner":"15990376","proparallel":"u","proretset":false,"prorettype":"3802","prorows":0,"prosecdef":true,"prosqlbody":null,"prosupport":"-","protrftypes":null,"provariadic":"0","provolatile":"v"}$pin_metadata$::jsonb),
  ('astra_ingestion_v1.rpc_dispatch(text,jsonb)','a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520',true,$pin_metadata${"oid":"15986028","proacl":["astra_ingestion_rpc_owner_v1=X/astra_ingestion_rpc_owner_v1","anon=X/astra_ingestion_rpc_owner_v1"],"proallargtypes":null,"proargdefaults":null,"proargmodes":null,"proargnames":["p_operation","p_payload"],"proargtypes":["25","3802"],"probin":null,"proconfig":["search_path=\"\"","statement_timeout=10s","lock_timeout=3s"],"procost":100,"proisstrict":false,"prokind":"f","prolang":"13619","proleakproof":false,"proname":"rpc_dispatch","pronamespace":"15984556","pronargdefaults":0,"pronargs":2,"proowner":"15985999","proparallel":"u","proretset":false,"prorettype":"3802","prorows":0,"prosecdef":true,"prosqlbody":null,"prosupport":"-","protrftypes":null,"provariadic":"0","provolatile":"v"}$pin_metadata$::jsonb)
 ) pinned(signature,expected_sha256,full_metadata,metadata) LOOP
  SELECT pg_get_functiondef(p.oid),to_jsonb(p)-'prosrc',
   jsonb_build_object('acl',p.proacl,'owner',p.proowner::text,'config',p.proconfig,'security_definer',p.prosecdef)
   INTO STRICT v_pin_source,v_pin_metadata,v_pin_partial FROM pg_proc p WHERE p.oid=g.signature::regprocedure;
  IF encode(sha256(convert_to(v_pin_source,'UTF8')),'hex')<>g.expected_sha256
   OR (CASE WHEN g.full_metadata THEN v_pin_metadata ELSE v_pin_partial END) IS DISTINCT FROM g.metadata THEN
   RAISE EXCEPTION 'Phase observation pinned helper, verifier, dispatch or monitor source/metadata differs';
  END IF;
 END LOOP;
 SELECT jsonb_build_object(
 'audit_table',(SELECT jsonb_build_object('acl',c.relacl,'oid',c.oid::text,'rls',c.relrowsecurity,
  'owner',c.relowner::text,'force_rls',c.relforcerowsecurity) FROM pg_class c
  WHERE c.oid='astra_ingestion_v1.backfill_audit_v2'::regclass),
 'audit_sequence',(SELECT jsonb_build_object('acl',c.relacl,'oid',c.oid::text,
  'name','astra_ingestion_v1.backfill_audit_v2_id_seq','owner',c.relowner::text) FROM pg_class c
  WHERE c.oid='astra_ingestion_v1.backfill_audit_v2_id_seq'::regclass),
 'existing_maintain_owner_privileges',jsonb_build_object(
  'run_select',has_table_privilege('astra_ingestion_rpc_owner_v1','astra_ingestion_v1.backfill_runs_v2','SELECT'),
  'run_update',has_table_privilege('astra_ingestion_rpc_owner_v1','astra_ingestion_v1.backfill_runs_v2','UPDATE'),
  'audit_delete',has_table_privilege('astra_ingestion_rpc_owner_v1','astra_ingestion_v1.backfill_audit_v2','DELETE'),
  'audit_insert',has_table_privilege('astra_ingestion_rpc_owner_v1','astra_ingestion_v1.backfill_audit_v2','INSERT'),
  'audit_select',has_table_privilege('astra_ingestion_rpc_owner_v1','astra_ingestion_v1.backfill_audit_v2','SELECT'),
  'audit_update',has_table_privilege('astra_ingestion_rpc_owner_v1','astra_ingestion_v1.backfill_audit_v2','UPDATE'),
  'sequence_usage',has_sequence_privilege('astra_ingestion_rpc_owner_v1','astra_ingestion_v1.backfill_audit_v2_id_seq','USAGE'),
  'sequence_update',has_sequence_privilege('astra_ingestion_rpc_owner_v1','astra_ingestion_v1.backfill_audit_v2_id_seq','UPDATE')),
 'constraints',(SELECT jsonb_agg(jsonb_build_object('name',c.conname,'type',c.contype,'definition',pg_get_constraintdef(c.oid))
  ORDER BY c.conname) FROM pg_constraint c WHERE c.conrelid='astra_ingestion_v1.backfill_audit_v2'::regclass),
 'triggers',(SELECT jsonb_agg(jsonb_build_object('name',t.tgname,'enabled',t.tgenabled,
  'function',t.tgfoid::regprocedure::text,'internal',t.tgisinternal,'definition',pg_get_triggerdef(t.oid))
  ORDER BY t.tgname) FROM pg_trigger t WHERE t.tgrelid='astra_ingestion_v1.backfill_audit_v2'::regclass),
 'policies',(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.polname) FROM pg_policy p
  WHERE p.polrelid='astra_ingestion_v1.backfill_audit_v2'::regclass),
 'standard_roles',(SELECT jsonb_object_agg(r,jsonb_build_object(
  'audit_insert',has_table_privilege(r,'astra_ingestion_v1.backfill_audit_v2','INSERT'),
  'audit_select',has_table_privilege(r,'astra_ingestion_v1.backfill_audit_v2','SELECT'),
  'monitor_execute',has_function_privilege(r,'astra_ingestion_v1.monitor_tick_v1()','EXECUTE'),
  'maintain_execute',has_function_privilege(r,'astra_ingestion_v1.backfill_maintain_v2(integer)','EXECUTE')))
  FROM unnest(ARRAY['anon','authenticated','service_role']::text[]) AS r)
) INTO v_audit_before;
 SELECT jsonb_agg(jsonb_build_object('acl',c.relacl,'oid',c.oid::text,
 'live',i.indislive,'name',c.relname,'owner',c.relowner::text,'ready',i.indisready,'valid',i.indisvalid,
 'method',a.amname,'definition',pg_get_indexdef(i.indexrelid)) ORDER BY c.relname)
 INTO v_indexes_before FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_am a ON a.oid=c.relam
 WHERE i.indrelid='astra_ingestion_v1.backfill_tasks_v2'::regclass
  AND c.relname IN ('backfill_tasks_breadth_pending_id_v2','backfill_tasks_minute_pending_id_v2');
 IF v_audit_before IS DISTINCT FROM v_expected_audit OR v_indexes_before IS DISTINCT FROM v_expected_indexes THEN
  RAISE EXCEPTION 'Phase observation audit privileges/catalog or exact installed hash pair differs';
 END IF;
 IF encode(sha256(convert_to(v_replacement,'UTF8')),'hex')<>'12e05b1fa5a6e59f1f626a33aaec4e30248d0cfc858917be171fd812b41c229d' THEN
  RAISE EXCEPTION 'Phase observation replacement bytes do not match reviewed source';
 END IF;
 SELECT jsonb_build_object(
 'namespace',(SELECT to_jsonb(n) FROM pg_namespace n WHERE n.oid='astra_ingestion_v1'::regnamespace),
 'functions',(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.oid) FROM pg_proc p
  WHERE p.pronamespace='astra_ingestion_v1'::regnamespace
   AND p.oid<>'astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure),
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
 -- INSTALLATION_TEST_BOUNDARY: all mutations below remain inside this atomic DO.
 EXECUTE v_replacement;
 SELECT to_jsonb(p)-'prosrc' INTO STRICT v_after_metadata FROM pg_proc p
  WHERE p.oid='astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure;
 SELECT jsonb_build_object(
 'namespace',(SELECT to_jsonb(n) FROM pg_namespace n WHERE n.oid='astra_ingestion_v1'::regnamespace),
 'functions',(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.oid) FROM pg_proc p
  WHERE p.pronamespace='astra_ingestion_v1'::regnamespace
   AND p.oid<>'astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure),
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
 SELECT jsonb_build_object(
 'audit_table',(SELECT jsonb_build_object('acl',c.relacl,'oid',c.oid::text,'rls',c.relrowsecurity,
  'owner',c.relowner::text,'force_rls',c.relforcerowsecurity) FROM pg_class c
  WHERE c.oid='astra_ingestion_v1.backfill_audit_v2'::regclass),
 'audit_sequence',(SELECT jsonb_build_object('acl',c.relacl,'oid',c.oid::text,
  'name','astra_ingestion_v1.backfill_audit_v2_id_seq','owner',c.relowner::text) FROM pg_class c
  WHERE c.oid='astra_ingestion_v1.backfill_audit_v2_id_seq'::regclass),
 'existing_maintain_owner_privileges',jsonb_build_object(
  'run_select',has_table_privilege('astra_ingestion_rpc_owner_v1','astra_ingestion_v1.backfill_runs_v2','SELECT'),
  'run_update',has_table_privilege('astra_ingestion_rpc_owner_v1','astra_ingestion_v1.backfill_runs_v2','UPDATE'),
  'audit_delete',has_table_privilege('astra_ingestion_rpc_owner_v1','astra_ingestion_v1.backfill_audit_v2','DELETE'),
  'audit_insert',has_table_privilege('astra_ingestion_rpc_owner_v1','astra_ingestion_v1.backfill_audit_v2','INSERT'),
  'audit_select',has_table_privilege('astra_ingestion_rpc_owner_v1','astra_ingestion_v1.backfill_audit_v2','SELECT'),
  'audit_update',has_table_privilege('astra_ingestion_rpc_owner_v1','astra_ingestion_v1.backfill_audit_v2','UPDATE'),
  'sequence_usage',has_sequence_privilege('astra_ingestion_rpc_owner_v1','astra_ingestion_v1.backfill_audit_v2_id_seq','USAGE'),
  'sequence_update',has_sequence_privilege('astra_ingestion_rpc_owner_v1','astra_ingestion_v1.backfill_audit_v2_id_seq','UPDATE')),
 'constraints',(SELECT jsonb_agg(jsonb_build_object('name',c.conname,'type',c.contype,'definition',pg_get_constraintdef(c.oid))
  ORDER BY c.conname) FROM pg_constraint c WHERE c.conrelid='astra_ingestion_v1.backfill_audit_v2'::regclass),
 'triggers',(SELECT jsonb_agg(jsonb_build_object('name',t.tgname,'enabled',t.tgenabled,
  'function',t.tgfoid::regprocedure::text,'internal',t.tgisinternal,'definition',pg_get_triggerdef(t.oid))
  ORDER BY t.tgname) FROM pg_trigger t WHERE t.tgrelid='astra_ingestion_v1.backfill_audit_v2'::regclass),
 'policies',(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.polname) FROM pg_policy p
  WHERE p.polrelid='astra_ingestion_v1.backfill_audit_v2'::regclass),
 'standard_roles',(SELECT jsonb_object_agg(r,jsonb_build_object(
  'audit_insert',has_table_privilege(r,'astra_ingestion_v1.backfill_audit_v2','INSERT'),
  'audit_select',has_table_privilege(r,'astra_ingestion_v1.backfill_audit_v2','SELECT'),
  'monitor_execute',has_function_privilege(r,'astra_ingestion_v1.monitor_tick_v1()','EXECUTE'),
  'maintain_execute',has_function_privilege(r,'astra_ingestion_v1.backfill_maintain_v2(integer)','EXECUTE')))
  FROM unnest(ARRAY['anon','authenticated','service_role']::text[]) AS r)
) INTO v_audit_after;
 SELECT jsonb_agg(jsonb_build_object('acl',c.relacl,'oid',c.oid::text,
 'live',i.indislive,'name',c.relname,'owner',c.relowner::text,'ready',i.indisready,'valid',i.indisvalid,
 'method',a.amname,'definition',pg_get_indexdef(i.indexrelid)) ORDER BY c.relname)
 INTO v_indexes_after FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_am a ON a.oid=c.relam
 WHERE i.indrelid='astra_ingestion_v1.backfill_tasks_v2'::regclass
  AND c.relname IN ('backfill_tasks_breadth_pending_id_v2','backfill_tasks_minute_pending_id_v2');
 IF v_after_metadata IS DISTINCT FROM v_before_metadata OR v_after_metadata IS DISTINCT FROM v_expected_metadata
  OR v_catalog_after IS DISTINCT FROM v_catalog_before OR v_audit_after IS DISTINCT FROM v_expected_audit
  OR v_indexes_after IS DISTINCT FROM v_expected_indexes
  OR pg_get_functiondef('astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure) IS DISTINCT FROM v_replacement THEN
  RAISE EXCEPTION 'Phase observation changed unexpected source, OID, metadata, permissions or schema catalog';
 END IF;
 -- Fixed pins are repeated after the preservation snapshot and replacement.
 FOR g IN SELECT * FROM (VALUES
  ('astra_ingestion_v1.backfill_breadth_project_pending_v2(integer)','65c981bd15a70f01d35eefc06a3807c7e6cfa1120a4b149ba3829951a63cc0d0',false,$pin_metadata${"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"config":["search_path=\"\""],"owner":"16388","security_definer":false}$pin_metadata$::jsonb),
  ('astra_ingestion_v1.backfill_contract_maintain_v2()','52007f177dca38faf48fab8773936173519dcbfa54af896b5ef6f902ad64c748',false,$pin_metadata${"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"config":["search_path=\"\"","statement_timeout=20s"],"owner":"16388","security_definer":true}$pin_metadata$::jsonb),
  ('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)','28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44',true,$pin_metadata${"oid":"16040232","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"proallargtypes":null,"proargdefaults":null,"proargmodes":null,"proargnames":["p_operation","p_payload"],"proargtypes":["25","3802"],"probin":null,"proconfig":["search_path=\"\""],"procost":100,"proisstrict":false,"prokind":"f","prolang":"13619","proleakproof":false,"proname":"backfill_dispatch_v2","pronamespace":"15984556","pronargdefaults":0,"pronargs":2,"proowner":"16388","proparallel":"u","proretset":false,"prorettype":"3802","prorows":0,"prosecdef":false,"prosqlbody":null,"prosupport":"-","protrftypes":null,"provariadic":"0","provolatile":"v"}$pin_metadata$::jsonb),
  ('astra_ingestion_v1.backfill_identity_discover_pending_v2()','faf5e83a8f7baf717cfd9054948ed62a8fbda7aa432a1f671d895fe77db37618',false,$pin_metadata${"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"config":["search_path=\"\""],"owner":"16388","security_definer":false}$pin_metadata$::jsonb),
  ('astra_ingestion_v1.backfill_identity_refresh_pending_v2(integer)','87ebac87ea08bea09b98f01ae123ed698e8252bcd6ff6abeb1cec3abf6ba5e25',false,$pin_metadata${"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"config":["search_path=\"\"","statement_timeout=8s"],"owner":"16388","security_definer":false}$pin_metadata$::jsonb),
  ('astra_ingestion_v1.backfill_minute_account_pending_v2(integer)','49cc9131c989de8f2da0926a2d1312bee7262f2e7f63c7a800219257af1632f2',false,$pin_metadata${"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"config":["search_path=\"\"","statement_timeout=8s"],"owner":"16388","security_definer":true}$pin_metadata$::jsonb),
  ('astra_ingestion_v1.backfill_nonminute_project_pending_v2(integer)','ceb1889732da767e8815741a792347ccb91c33c53acd38eeff36f9176d063cec',false,$pin_metadata${"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"config":["search_path=\"\"","statement_timeout=8s"],"owner":"16388","security_definer":true}$pin_metadata$::jsonb),
  ('astra_ingestion_v1.backfill_recheck_page_v2(text,integer)','0ccd4018d16e3ed3932176d2886fe78c2c1b442d70473d71e137d86e7b6dfb37',true,$pin_metadata${"oid":"16041451","proacl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"proallargtypes":null,"proargdefaults":null,"proargmodes":null,"proargnames":["p_task_id","p_page_no"],"proargtypes":["25","23"],"probin":null,"proconfig":["search_path=\"\""],"procost":100,"proisstrict":false,"prokind":"f","prolang":"13619","proleakproof":false,"proname":"backfill_recheck_page_v2","pronamespace":"15984556","pronargdefaults":0,"pronargs":2,"proowner":"16388","proparallel":"u","proretset":false,"prorettype":"3802","prorows":0,"prosecdef":false,"prosqlbody":null,"prosupport":"-","protrftypes":null,"provariadic":"0","provolatile":"v"}$pin_metadata$::jsonb),
  ('astra_ingestion_v1.backfill_s02_maintain_v2()','40827de08ca59d1470a02aceff6ccc249e6b43bb8ef13ff39eddffa673e78939',false,$pin_metadata${"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"config":["search_path=\"\"","statement_timeout=8s"],"owner":"16388","security_definer":true}$pin_metadata$::jsonb),
  ('astra_ingestion_v1.backfill_shared_maintain_v2(integer)','5da488f3e44e2521b64f58230b2bc6db3c34800ae4ac259166f4dc223c8ad2be',false,$pin_metadata${"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"config":["search_path=\"\"","statement_timeout=15s"],"owner":"16388","security_definer":true}$pin_metadata$::jsonb),
  ('astra_ingestion_v1.backfill_try_finalize_v2(text)','f8f9ef6d8d9ada232b132170bde9922397a2b247dbc7e4b391cbca57b67b7063',false,$pin_metadata${"acl":["postgres=X/postgres","astra_ingestion_rpc_owner_v1=X/postgres"],"config":["search_path=\"\""],"owner":"16388","security_definer":false}$pin_metadata$::jsonb),
  ('astra_ingestion_v1.monitor_tick_v1()','875c017ecf73df15163d15d3f9129b4507235dc893ccb4233d0a435154389057',true,$pin_metadata${"oid":"15990404","proacl":["astra_ingestion_monitor_owner_v1=X/astra_ingestion_monitor_owner_v1","postgres=X/astra_ingestion_monitor_owner_v1"],"proallargtypes":null,"proargdefaults":null,"proargmodes":null,"proargnames":null,"proargtypes":[],"probin":null,"proconfig":["search_path=\"\"","statement_timeout=8s","lock_timeout=2s"],"procost":100,"proisstrict":false,"prokind":"f","prolang":"13619","proleakproof":false,"proname":"monitor_tick_v1","pronamespace":"15984556","pronargdefaults":0,"pronargs":0,"proowner":"15990376","proparallel":"u","proretset":false,"prorettype":"3802","prorows":0,"prosecdef":true,"prosqlbody":null,"prosupport":"-","protrftypes":null,"provariadic":"0","provolatile":"v"}$pin_metadata$::jsonb),
  ('astra_ingestion_v1.rpc_dispatch(text,jsonb)','a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520',true,$pin_metadata${"oid":"15986028","proacl":["astra_ingestion_rpc_owner_v1=X/astra_ingestion_rpc_owner_v1","anon=X/astra_ingestion_rpc_owner_v1"],"proallargtypes":null,"proargdefaults":null,"proargmodes":null,"proargnames":["p_operation","p_payload"],"proargtypes":["25","3802"],"probin":null,"proconfig":["search_path=\"\"","statement_timeout=10s","lock_timeout=3s"],"procost":100,"proisstrict":false,"prokind":"f","prolang":"13619","proleakproof":false,"proname":"rpc_dispatch","pronamespace":"15984556","pronargdefaults":0,"pronargs":2,"proowner":"15985999","proparallel":"u","proretset":false,"prorettype":"3802","prorows":0,"prosecdef":true,"prosqlbody":null,"prosupport":"-","protrftypes":null,"provariadic":"0","provolatile":"v"}$pin_metadata$::jsonb)
 ) pinned(signature,expected_sha256,full_metadata,metadata) LOOP
  SELECT pg_get_functiondef(p.oid),to_jsonb(p)-'prosrc',
   jsonb_build_object('acl',p.proacl,'owner',p.proowner::text,'config',p.proconfig,'security_definer',p.prosecdef)
   INTO STRICT v_pin_source,v_pin_metadata,v_pin_partial FROM pg_proc p WHERE p.oid=g.signature::regprocedure;
  IF encode(sha256(convert_to(v_pin_source,'UTF8')),'hex')<>g.expected_sha256
   OR (CASE WHEN g.full_metadata THEN v_pin_metadata ELSE v_pin_partial END) IS DISTINCT FROM g.metadata THEN
   RAISE EXCEPTION 'Phase observation pinned helper, verifier, dispatch or monitor source/metadata differs';
  END IF;
 END LOOP;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2 WHERE id='fixed3000-20250901-20260731-v1-20261030' AND status='ACTIVE' AND fence=1
  AND cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
  AND metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
  AND (metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()) THEN
  RAISE EXCEPTION 'Phase observation owner, lease, status, fence or cohort changed before completion';
 END IF;
 IF (SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id='fixed3000-20250901-20260731-v1-20261030')<>3000 THEN
  RAISE EXCEPTION 'Phase observation requires the exact 3000-member cohort';
 END IF;
 IF clock_timestamp()>='2026-10-30 15:45:00+00'::timestamptz THEN
  RAISE EXCEPTION 'Phase observation fixed installation window expired';
 END IF;
END $phase_observation_install$;
COMMIT;
