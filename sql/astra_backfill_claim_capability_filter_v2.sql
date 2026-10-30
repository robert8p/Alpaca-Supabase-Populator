-- Evaluate the unchanged supported-kind membership as a scalar array InitPlan.
-- Exactly two predicate substitutions: recovery and normal claim candidates.
-- No grants, authentication, scope, fairness, ordering, row locks or data writes.
-- Apply only after current ownership and uncertain-write reconciliation.
BEGIN;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);

DO $repair$
DECLARE
 before_definition text;
 after_definition text;
 actual_definition text;
 before_metadata jsonb;
 after_metadata jsonb;
 auth_definition text;
 auth_metadata jsonb;
 current_auth_metadata jsonb;
 status_branch text;
 status_start integer;
 status_end integer;
 old_predicate constant text:='q.kind IN (SELECT jsonb_array_elements_text(v_supported))';
 new_predicate constant text:='q.kind = ANY(ARRAY(SELECT jsonb_array_elements_text(v_supported)))';
 expected_before constant text:='136871b8ca305ae69c661541d9c2684e71b1d5e6fe84a6ec9b8b594b1da56d02';
 expected_after constant text:='28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44';
 expected_auth constant text:='a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520';
 expected_status constant text:='cee8f62d034a88e3fb5166fce2b4b4903cdd1aee802e2efebfc3f08cf6c0a5de';
BEGIN
 -- Lock the existing run for this bounded transaction so a concurrent owner,
 -- stop or fence change cannot race the installation. Do not renew its lease.
 PERFORM 1 FROM astra_ingestion_v1.backfill_runs_v2
 WHERE id='fixed3000-20250901-20260731-v1-20261030'
  AND status='ACTIVE' AND fence=1
  AND cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
  AND cohort_manifest_sha256='4134b415e2c26fcde9fced749c0d54ef51376e23f0d2f8c6ce9ef562f9fab99f'
  AND target_start='2025-09-01'::date AND target_end='2026-07-31'::date
  AND metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
  AND (metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()
 FOR SHARE;
 IF NOT FOUND THEN
  RAISE EXCEPTION 'Capability filter repair requires the same active fixed-cohort owner, fence and unexpired lease';
 END IF;
 IF (SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2
     WHERE run_id='fixed3000-20250901-20260731-v1-20261030')<>3000 THEN
  RAISE EXCEPTION 'Capability filter repair requires the intact 3000-member cohort';
 END IF;
 SELECT pg_get_functiondef(p.oid),to_jsonb(p)-'prosrc'
  INTO STRICT before_definition,before_metadata
 FROM pg_proc p WHERE p.oid='astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure;
 SELECT pg_get_functiondef(p.oid),to_jsonb(p)-'prosrc'
  INTO STRICT auth_definition,auth_metadata
 FROM pg_proc p WHERE p.oid='astra_ingestion_v1.rpc_dispatch(text,jsonb)'::regprocedure;
 IF encode(sha256(convert_to(before_definition,'UTF8')),'hex')<>expected_before
  OR encode(sha256(convert_to(auth_definition,'UTF8')),'hex')<>expected_auth THEN
  RAISE EXCEPTION 'Capability filter repair source or authentication drift; reconcile before applying';
 END IF;
 IF (length(before_definition)-length(replace(before_definition,old_predicate,'')))/length(old_predicate)<>2
  OR strpos(before_definition,new_predicate)>0 THEN
  RAISE EXCEPTION 'Capability filter repair requires exactly the original recovery and normal predicates';
 END IF;
 status_start:=strpos(before_definition,$start$ IF p_operation='backfill_status' THEN$start$);
 status_end:=strpos(before_definition,$end$ ELSIF p_operation='backfill_claim' THEN$end$);
 IF status_start=0 OR status_end<=status_start THEN
  RAISE EXCEPTION 'Capability filter repair status boundary drift';
 END IF;
 status_branch:=substring(before_definition FROM status_start FOR status_end-status_start);
 IF encode(sha256(convert_to(status_branch,'UTF8')),'hex')<>expected_status THEN
  RAISE EXCEPTION 'Capability filter repair status source drift';
 END IF;
 after_definition:=replace(before_definition,old_predicate,new_predicate);
 IF replace(after_definition,new_predicate,old_predicate)<>before_definition
  OR encode(sha256(convert_to(after_definition,'UTF8')),'hex')<>expected_after THEN
  RAISE EXCEPTION 'Capability filter repair must change only two exact predicates';
 END IF;
 EXECUTE after_definition;
 SELECT pg_get_functiondef(p.oid),to_jsonb(p)-'prosrc'
  INTO STRICT actual_definition,after_metadata
 FROM pg_proc p WHERE p.oid='astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure;
 SELECT to_jsonb(p)-'prosrc' INTO STRICT current_auth_metadata
 FROM pg_proc p WHERE p.oid='astra_ingestion_v1.rpc_dispatch(text,jsonb)'::regprocedure;
 IF actual_definition<>after_definition OR after_metadata IS DISTINCT FROM before_metadata
  OR current_auth_metadata IS DISTINCT FROM auth_metadata
  OR pg_get_functiondef('astra_ingestion_v1.rpc_dispatch(text,jsonb)'::regprocedure)<>auth_definition THEN
  RAISE EXCEPTION 'Capability filter repair failed exact source, OID, owner, ACL, configuration or authentication preservation';
 END IF;
 IF substring(actual_definition FROM status_start FOR status_end-status_start)<>status_branch THEN
  RAISE EXCEPTION 'Capability filter repair changed the status branch';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2
   WHERE id='fixed3000-20250901-20260731-v1-20261030'
    AND (metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()) THEN
  RAISE EXCEPTION 'Capability filter repair owner lease expired before commit';
 END IF;
END $repair$;
COMMIT;
