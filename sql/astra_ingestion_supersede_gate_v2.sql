-- Replacement instruction 62dd1a15c5c6cf46a42340917701816c6c3b86c49e4b4fb462f8b111bcaadc45.
-- Preserve the original capability boundary and completed evidence.
BEGIN;
SET LOCAL statement_timeout='10s';
SET LOCAL lock_timeout='3s';
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);
DO $gate$
DECLARE v_def text;
BEGIN
 IF EXISTS(SELECT 1 FROM astra_ingestion_v1.partitions
           WHERE owner IS NOT NULL AND lease_until>EXTRACT(EPOCH FROM pg_catalog.clock_timestamp())) THEN
   RAISE EXCEPTION 'Active original-scope writer must reach a safe checkpoint before supersession';
 END IF;
 SELECT pg_catalog.pg_get_functiondef('astra_ingestion_v1.rpc_dispatch(text,jsonb)'::regprocedure) INTO STRICT v_def;
 IF pg_catalog.strpos(v_def,'replacement_scope_admission_gate_v2')=0 THEN
   IF pg_catalog.strpos(v_def,'    CASE p_operation')=0 THEN
     RAISE EXCEPTION 'Unexpected original dispatch structure; reconcile before changing';
   END IF;
   v_def:=pg_catalog.replace(v_def,'    CASE p_operation',$insert$
    -- replacement_scope_admission_gate_v2: authenticated, serialized, immutable old scope.
    IF p_operation='submit_job' THEN
      RETURN pg_catalog.jsonb_build_object('ok',false,'error',pg_catalog.jsonb_build_object(
        'code','conflict','message','SUPERSEDED_BY_SCOPE_CHANGE: replacement fixed-cohort run owns new admission'));
    ELSIF p_operation='claim_next' THEN
      RETURN pg_catalog.jsonb_build_object('ok',true,'result',NULL);
    END IF;
    CASE p_operation$insert$);
   EXECUTE v_def;
 END IF;
 UPDATE astra_ingestion_v1.partitions
 SET status='SUPERSEDED_BY_SCOPE_CHANGE',owner=NULL,lease_until=NULL,generation=generation+1,
     error='Superseded by the fixed 3000-equity replacement mission; prior source evidence and counters preserved'
 WHERE status IN ('pending','running','loaded','verifying')
   AND job_id IN (SELECT id FROM astra_ingestion_v1.jobs WHERE status IN ('queued','running','paused'));
 UPDATE astra_ingestion_v1.jobs
 SET status='SUPERSEDED_BY_SCOPE_CHANGE',updated_at=EXTRACT(EPOCH FROM pg_catalog.clock_timestamp()),
     error='Superseded by the fixed 3000-equity replacement mission; prior source evidence and counters preserved'
 WHERE status IN ('queued','running','paused');
END $gate$;
COMMIT;

