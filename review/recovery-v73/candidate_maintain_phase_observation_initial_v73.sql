CREATE OR REPLACE FUNCTION astra_ingestion_v1.backfill_maintain_v2(p_limit integer DEFAULT 2)
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
    END IF;
   END IF;
  EXCEPTION WHEN query_canceled OR assert_failure THEN RAISE;
   WHEN OTHERS THEN NULL;
  END;
 END IF;
 -- PHASE_OBSERVATION_V73_END append_optional_observation
 RETURN jsonb_build_object('state','OBSERVED','verified_pages',v_readbacks,'readback_errors',v_errors,'runs',v_final);
END $function$
