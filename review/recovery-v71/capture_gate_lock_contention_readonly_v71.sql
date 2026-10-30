-- Bounded passive capture of the existing authentication advisory gate.
-- No application RPC, provider request, lock acquisition or persistent object.
-- P0001/ASTRA_GATE_LOCK_CAPTURE_V71 is the intentional result transport; it
-- aborts this read-only transaction after returning the bounded JSON message.
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL transaction_read_only=on;
SET LOCAL transaction_isolation='repeatable read';
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $capture$
DECLARE
 v_started timestamptz:=clock_timestamp();
 v_sampled timestamptz;
 v_samples jsonb:='[]'::jsonb;
 v_sample jsonb;
 v_next jsonb;
 v_count integer:=0;
 v_output_limited boolean:=false;
 v_i integer;
BEGIN
 IF current_setting('transaction_read_only')<>'on'
  OR current_setting('transaction_isolation')<>'repeatable read'
  OR current_setting('statement_timeout')<>'8s'
  OR current_setting('lock_timeout')<>'3s' THEN
  RAISE EXCEPTION 'Gate capture requires the explicit bounded read-only transaction state';
 END IF;
 IF encode(sha256(convert_to(pg_get_functiondef('astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure),'UTF8')),'hex')
     <>'28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44'
  OR encode(sha256(convert_to(pg_get_functiondef('astra_ingestion_v1.rpc_dispatch(text,jsonb)'::regprocedure),'UTF8')),'hex')
     <>'a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520' THEN
  RAISE EXCEPTION 'Gate capture source changed; reconcile without replaying an installed repair';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2
  WHERE id='fixed3000-20250901-20260731-v1-20261030' AND status='ACTIVE' AND fence=1
   AND cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
   AND metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
   AND (metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()) THEN
  RAISE EXCEPTION 'Gate capture requires the same active fixed run and unexpired existing owner';
 END IF;
 FOR v_i IN 1..20 LOOP
  PERFORM pg_stat_clear_snapshot();
  v_sampled:=clock_timestamp();
  WITH gate AS MATERIALIZED (
   SELECT l.pid,l.mode,l.granted,l.waitstart
   FROM pg_locks l
   WHERE l.locktype='advisory'
    AND l.database=(SELECT oid FROM pg_database WHERE datname=current_database())
    AND l.classid::bigint=164451 AND l.objid::bigint=2353466532 AND l.objsubid=1
   ORDER BY l.granted DESC,l.pid NULLS LAST LIMIT 8
  ), links AS MATERIALIZED (
   SELECT g.*,CASE WHEN g.pid IS NULL THEN ARRAY[]::integer[] ELSE pg_blocking_pids(g.pid) END blockers
   FROM gate g
  ), related AS MATERIALIZED (
   SELECT pid FROM links WHERE pid IS NOT NULL
   UNION SELECT unnest(blockers) FROM links
  ), activity AS MATERIALIZED (
   SELECT a.pid,a.backend_start,a.xact_start,a.query_start,a.state_change,a.state,
    a.wait_event_type,a.wait_event,a.backend_type,a.query_id::text query_id,
    lower(COALESCE(a.application_name,'')) LIKE '%postgrest%' application_is_postgrest,
    a.usename='authenticator' session_is_authenticator,
    a.usename='postgres' session_is_postgres,
    CASE
     WHEN a.query ~* '^\s*(COMMIT|END)\s*;?\s*$' THEN 'COMMIT'
     WHEN a.query ~* '^\s*(ROLLBACK|ABORT)\s*;?\s*$' THEN 'ROLLBACK'
     WHEN a.query ~* '^\s*(BEGIN|START\s+TRANSACTION)\M' THEN 'TRANSACTION_START'
     WHEN a.query ~* '^\s*(CREATE|ALTER|DROP)\M' THEN 'DDL'
     WHEN position('astra_ingestion_rpc_v1' in COALESCE(a.query,''))>0 THEN 'PUBLIC_INGESTION_RPC'
     WHEN position('rpc_dispatch' in COALESCE(a.query,''))>0 THEN 'PRIVATE_RPC_DISPATCH'
     WHEN position('pg_advisory_xact_lock' in COALESCE(a.query,''))>0 THEN 'DIRECT_ADVISORY_STATEMENT'
     ELSE 'OTHER_OR_REDACTED'
    END query_shape
   FROM pg_stat_activity a JOIN related r ON r.pid=a.pid
   WHERE a.pid<>pg_backend_pid() AND a.datname=current_database()
   ORDER BY a.pid LIMIT 8
  )
  SELECT jsonb_build_object('sample',v_i,'sampled_at',v_sampled,
   'gate_locks',COALESCE((SELECT jsonb_agg(to_jsonb(g) ORDER BY g.granted DESC,g.pid) FROM links g),'[]'::jsonb),
   'related_activity',COALESCE((SELECT jsonb_agg(to_jsonb(a) ORDER BY a.pid) FROM activity a),'[]'::jsonb),
   'gate_limit_reached',(SELECT count(*)=8 FROM gate),
   'activity_limit_reached',(SELECT count(*)=8 FROM activity)) INTO v_sample;
  v_next:=v_samples||jsonb_build_array(v_sample);
  IF octet_length(v_next::text)>60000 THEN v_output_limited:=true;EXIT;END IF;
  v_samples:=v_next;v_count:=v_count+1;
  IF v_i<20 THEN PERFORM pg_sleep(0.3);END IF;
 END LOOP;
 RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='ASTRA_GATE_LOCK_CAPTURE_V71:'||jsonb_build_object(
  'schema','astra.gate-lock-readonly-capture/1','started_at',v_started,'finished_at',clock_timestamp(),
  'gate_key',706314020261028::bigint,'classid',164451,'objid',2353466532,'objsubid',1,
  'transaction_read_only',current_setting('transaction_read_only'),
  'transaction_isolation',current_setting('transaction_isolation'),
  'sample_count',v_count,'maximum_samples',20,'interval_seconds',0.3,
  'output_limited',v_output_limited,'capture_complete',v_count=20 AND NOT v_output_limited,
  'raw_query_returned',false,'raw_headers_or_payload_returned',false,'samples',v_samples)::text;
END $capture$;
ROLLBACK;
