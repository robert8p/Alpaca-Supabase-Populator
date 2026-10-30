-- READ-ONLY COMBINED-STATUS DATABASE TIMING; NOT AUTHENTICATED RPC PROOF.
-- Calls the same inner-status + delivery branch with the dashboard's empty
-- payload, but bypasses rpc_dispatch authentication and its advisory lock.
-- No token is read, exported, synthesized, or submitted by this probe.
BEGIN;
SET TRANSACTION READ ONLY;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $guard$
DECLARE s text;n text;b text;a integer;z integer;
BEGIN
 SELECT p.prosrc,ns.nspname INTO STRICT s,n FROM pg_proc p JOIN pg_namespace ns ON ns.oid=p.pronamespace
 WHERE p.oid='astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure;
 a:=strpos(s,$start$ IF p_operation='backfill_status' THEN$start$);
 z:=strpos(s,$end$ ELSIF p_operation='backfill_claim' THEN$end$);
 IF a=0 OR z<=a THEN RAISE EXCEPTION 'Runtime status boundaries changed';END IF;
 b:=substring(s FROM a FOR z-a);
 IF encode(sha256(convert_to(replace(b,n,'astra'||'_ingestion_v1'),'UTF8')),'hex')
  <>'cee8f62d034a88e3fb5166fce2b4b4903cdd1aee802e2efebfc3f08cf6c0a5de' THEN
  RAISE EXCEPTION 'Expected installed report-as-of branch differs';
 END IF;
 SELECT p.prosrc,ns.nspname INTO STRICT s,n FROM pg_proc p JOIN pg_namespace ns ON ns.oid=p.pronamespace
 WHERE p.oid='astra_ingestion_v1.backfill_delivery_dispatch_v2(text,jsonb)'::regprocedure;
 a:=strpos(s,$start$ ELSIF p_operation='backfill_status' THEN$start$);
 z:=strpos(s,$end$ ELSIF p_operation='backfill_finalize' THEN$end$);
 IF a=0 OR z<=a THEN RAISE EXCEPTION 'Combined status route changed';END IF;
 b:=substring(s FROM a FOR z-a);
 IF encode(sha256(convert_to(replace(b,n,'astra'||'_ingestion_v1'),'UTF8')),'hex')<>'e77cc64058262565c43c5475a10d9da572433398d569aaee9b3b7d8b681d2456' THEN
  RAISE EXCEPTION 'Combined status route differs from the qualified source';
 END IF;
END $guard$;
WITH started AS MATERIALIZED (
 SELECT clock_timestamp() started_at
), measured AS MATERIALIZED (
 SELECT started_at,astra_ingestion_v1.backfill_delivery_dispatch_v2('backfill_status','{}'::jsonb) body
 FROM started
), finished AS MATERIALIZED (
 SELECT started_at,body,clock_timestamp() finished_at FROM measured
)
SELECT started_at,finished_at,
 round((1000*extract(epoch FROM finished_at-started_at))::numeric,3) combined_database_ms,
 false authenticated_rpc_proof,false outer_advisory_lock_measured,
 body->>'observed_at' runtime_observed_at,body#>>'{delivery,observed_at}' delivery_observed_at,
 jsonb_array_length(body->'runs') runtime_runs,jsonb_array_length(body#>'{delivery,runs}') delivery_runs,
 octet_length(body::text) combined_json_bytes,
 encode(sha256(convert_to(body::text,'UTF8')),'hex') combined_json_sha256
FROM finished;
ROLLBACK;
