-- Isolated, independently privileged readback verifier.
-- Applies after astra_ingestion_observer_v1.sql; no scheduler is created here.
-- No data-provider credentials, runtime API tokens, service roles or job controls.
SET LOCAL statement_timeout='30s';
SET LOCAL lock_timeout='3s';
SET LOCAL search_path=pg_catalog;
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);

DO $admission$
BEGIN
  IF pg_catalog.to_regnamespace('astra_ingestion_v1') IS NULL
     OR (SELECT version FROM astra_ingestion_v1.schema_info WHERE id=1) IS DISTINCT FROM 1
     OR (SELECT count(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
         WHERE n.nspname='astra_ingestion_v1' AND c.relkind='r')<>12
     OR pg_catalog.to_regclass('astra_ingestion_v1.monitor_incidents') IS NULL
     OR pg_catalog.to_regprocedure('astra_ingestion_v1.monitor_tick_v1()') IS NULL
     OR pg_catalog.to_regclass('astra_ingestion_v1.independent_verifications') IS NOT NULL
     OR pg_catalog.to_regprocedure('astra_ingestion_v1.independent_verify_tick_v1()') IS NOT NULL
     OR EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='astra_ingestion_verifier_owner_v1')
  THEN RAISE EXCEPTION 'Independent verification migration refused: installed ingestion/monitor baseline differs'; END IF;
  CREATE ROLE astra_ingestion_verifier_owner_v1 NOLOGIN NOINHERIT NOSUPERUSER
    NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  EXECUTE pg_catalog.format('GRANT astra_ingestion_verifier_owner_v1 TO %I',current_user);
END $admission$;

CREATE TABLE astra_ingestion_v1.independent_verifications(
  partition_id text NOT NULL REFERENCES astra_ingestion_v1.partitions(id),
  verifier_version text NOT NULL DEFAULT 'sql_v1' CHECK(verifier_version='sql_v1'),
  job_id text NOT NULL REFERENCES astra_ingestion_v1.jobs(id),
  scope_hash text NOT NULL CHECK(scope_hash ~ '^[0-9a-f]{64}$'),
  checked_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  result text NOT NULL CHECK(result IN ('passed','failed')),
  failure_code text,
  receipt_count integer NOT NULL CHECK(receipt_count>=0),
  source_count integer NOT NULL CHECK(source_count>=0),
  stored_count integer NOT NULL CHECK(stored_count>=0),
  expected_sha256 text NOT NULL CHECK(expected_sha256 ~ '^[0-9a-f]{64}$'),
  stored_sha256 text NOT NULL CHECK(stored_sha256 ~ '^[0-9a-f]{64}$'),
  coverage_certification text NOT NULL DEFAULT 'NOT_CERTIFIED' CHECK(coverage_certification='NOT_CERTIFIED'),
  PRIMARY KEY(partition_id,verifier_version)
);
ALTER TABLE astra_ingestion_v1.independent_verifications ENABLE ROW LEVEL SECURITY;

CREATE FUNCTION astra_ingestion_v1.independent_verify_tick_v1()
RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path='' SET statement_timeout='8s' SET lock_timeout='2s' AS $fn$
DECLARE
 v_p astra_ingestion_v1.partitions%ROWTYPE;
 v_j astra_ingestion_v1.jobs%ROWTYPE;
 v_receipt astra_ingestion_v1.receipts%ROWTYPE;
 v_row astra_ingestion_v1.records%ROWTYPE;
 v_parsed jsonb;
 v_payload jsonb;
 v_expected jsonb:='{}'::jsonb;
 v_actual jsonb:='{}'::jsonb;
 v_expected_hash text;
 v_actual_hash text;
 v_expected_count integer:=0;
 v_actual_count integer:=0;
 v_pages integer:=0;
 v_token text:=NULL;
 v_key text;
 v_state text:='passed';
 v_failure text:=NULL;
 v_receipt_bytes bigint:=0;
 v_scope_hash text;
BEGIN
 IF NOT pg_catalog.pg_try_advisory_xact_lock(706314020261030) THEN
    RETURN pg_catalog.jsonb_build_object('state','already_running'); END IF;
 SELECT p.* INTO v_p
   FROM astra_ingestion_v1.partitions p
   JOIN astra_ingestion_v1.jobs j ON j.id=p.job_id
   WHERE p.status='verified' AND j.status='completed'
     AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.independent_verifications v
        WHERE v.partition_id=p.id AND v.verifier_version='sql_v1')
   ORDER BY j.created_at,p.symbol,p.start_at LIMIT 1;
 IF NOT FOUND THEN RETURN pg_catalog.jsonb_build_object('state','idle'); END IF;
 SELECT * INTO STRICT v_j FROM astra_ingestion_v1.jobs WHERE id=v_p.job_id;

 BEGIN
   v_scope_hash:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
     astra_ingestion_v1.rpc_canonical(v_j.spec::jsonb),'UTF8')),'hex');
   IF v_scope_hash IS DISTINCT FROM v_j.scope_hash THEN
      RAISE EXCEPTION 'Immutable job scope hash is inconsistent'; END IF;
   -- All raw bytes remain private. Only hashes and counts reach the attestation.
   SELECT COALESCE(SUM(pg_catalog.octet_length(raw_body)),0) INTO v_receipt_bytes
     FROM astra_ingestion_v1.receipts WHERE partition_id=v_p.id;
   IF v_receipt_bytes>8388608 THEN
      RAISE EXCEPTION 'Verifier bounded source payload is exceeded'; END IF;
   FOR v_receipt IN SELECT * FROM astra_ingestion_v1.receipts
     WHERE partition_id=v_p.id ORDER BY page_no
   LOOP
     IF v_receipt.page_no<>v_pages OR v_receipt.token_in IS DISTINCT FROM v_token THEN
        RAISE EXCEPTION 'Retained source pagination chain is incomplete'; END IF;
     IF pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
        v_receipt.raw_body,'UTF8')),'hex')<>v_receipt.body_sha256 THEN
        RAISE EXCEPTION 'Retained receipt SHA-256 mismatch'; END IF;
     v_parsed:=astra_ingestion_v1.rpc_parse_source(
       v_receipt.raw_body,v_p.symbol,v_p.start_at,v_p.end_at);
     IF (v_parsed->>'next_page_token') IS DISTINCT FROM v_receipt.token_out THEN
        RAISE EXCEPTION 'Stored continuation token differs from source page'; END IF;
     FOR v_payload IN SELECT value FROM pg_catalog.jsonb_array_elements(v_parsed->'records')
     LOOP
       v_key:=v_payload->>'symbol'||'|'||v_payload->>'timestamp';
       IF v_expected ? v_key THEN RAISE EXCEPTION 'Duplicate source bar across retained pages'; END IF;
       v_expected:=v_expected || pg_catalog.jsonb_build_object(v_key,v_payload);
     END LOOP;
     v_token:=v_receipt.token_out;
     v_pages:=v_pages+1;
   END LOOP;
   IF v_pages=0 OR v_token IS NOT NULL THEN RAISE EXCEPTION 'Original source receipt chain is incomplete'; END IF;
   FOR v_row IN SELECT * FROM astra_ingestion_v1.records
      WHERE partition_id=v_p.id ORDER BY record_key
   LOOP
     v_payload:=v_row.payload::jsonb;
     v_key:=v_payload->>'symbol'||'|'||v_payload->>'timestamp';
     IF v_key IS NULL OR v_row.record_key<>v_key OR v_actual ? v_key THEN
        RAISE EXCEPTION 'Stored payload key or cardinality mismatch'; END IF;
     v_actual:=v_actual || pg_catalog.jsonb_build_object(v_key,v_payload);
   END LOOP;
   SELECT count(*) INTO v_expected_count FROM pg_catalog.jsonb_object_keys(v_expected);
   SELECT count(*) INTO v_actual_count FROM pg_catalog.jsonb_object_keys(v_actual);
   IF v_expected_count=0 OR v_expected_count<>v_actual_count
      OR v_expected_count<>v_p.record_count OR v_expected<>v_actual THEN
     RAISE EXCEPTION 'Source-to-target readback is not identical'; END IF;
 EXCEPTION WHEN OTHERS THEN
   -- Do not disclose raw licensed responses or SQL exceptions in persistent data.
   v_state:='failed'; v_failure:=SQLSTATE;
 END;
 -- Hashes are computed from retained in-transaction readback data only.
 v_expected_hash:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
   astra_ingestion_v1.rpc_canonical(v_expected),'UTF8')),'hex');
 v_actual_hash:=pg_catalog.encode(pg_catalog.sha256(pg_catalog.convert_to(
   astra_ingestion_v1.rpc_canonical(v_actual),'UTF8')),'hex');
 INSERT INTO astra_ingestion_v1.independent_verifications(
   partition_id,verifier_version,job_id,scope_hash,result,failure_code,
   receipt_count,source_count,stored_count,expected_sha256,stored_sha256)
 VALUES(v_p.id,'sql_v1',v_j.id,v_j.scope_hash,v_state,v_failure,
        v_pages,v_expected_count,v_actual_count,v_expected_hash,v_actual_hash);
 RETURN pg_catalog.jsonb_build_object('state','attested','partition_id',v_p.id,
            'result',v_state,'source_count',v_expected_count,
            'stored_count',v_actual_count,'receipt_count',v_pages,
            'coverage_certification','NOT_CERTIFIED');
END $fn$;

DO $private_acl$
DECLARE v_grantee record; v_fn record;
BEGIN
 REVOKE ALL ON astra_ingestion_v1.independent_verifications FROM PUBLIC;
 FOR v_grantee IN SELECT DISTINCT r.rolname
   FROM pg_catalog.pg_class c CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) a
   JOIN pg_catalog.pg_roles r ON r.oid=a.grantee
   WHERE c.oid='astra_ingestion_v1.independent_verifications'::regclass AND a.grantee<>c.relowner
 LOOP EXECUTE pg_catalog.format('REVOKE ALL ON astra_ingestion_v1.independent_verifications FROM %I',v_grantee.rolname); END LOOP;
 FOR v_fn IN SELECT p.oid,p.proowner,p.proacl,n.nspname,p.proname,
             pg_catalog.pg_get_function_identity_arguments(p.oid) args
           FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
           WHERE n.nspname='astra_ingestion_v1' AND p.proname='independent_verify_tick_v1'
 LOOP
   EXECUTE pg_catalog.format('REVOKE ALL ON FUNCTION %I.%I(%s) FROM PUBLIC',
      v_fn.nspname,v_fn.proname,v_fn.args);
   FOR v_grantee IN SELECT DISTINCT r.rolname FROM pg_catalog.aclexplode(v_fn.proacl) a
      JOIN pg_catalog.pg_roles r ON r.oid=a.grantee WHERE a.grantee<>v_fn.proowner
   LOOP
      EXECUTE pg_catalog.format('REVOKE ALL ON FUNCTION %I.%I(%s) FROM %I',
        v_fn.nspname,v_fn.proname,v_fn.args,v_grantee.rolname);
   END LOOP;
 END LOOP;
END $private_acl$;

GRANT USAGE ON SCHEMA astra_ingestion_v1 TO astra_ingestion_verifier_owner_v1;
GRANT SELECT ON astra_ingestion_v1.jobs,astra_ingestion_v1.partitions,
   astra_ingestion_v1.receipts,astra_ingestion_v1.records,
   astra_ingestion_v1.verifications TO astra_ingestion_verifier_owner_v1;
GRANT INSERT ON astra_ingestion_v1.independent_verifications TO astra_ingestion_verifier_owner_v1;
CREATE POLICY ingestion_verifier_read ON astra_ingestion_v1.jobs
 FOR SELECT TO astra_ingestion_verifier_owner_v1 USING(true);
CREATE POLICY ingestion_verifier_read ON astra_ingestion_v1.partitions
 FOR SELECT TO astra_ingestion_verifier_owner_v1 USING(true);
CREATE POLICY ingestion_verifier_read ON astra_ingestion_v1.receipts
 FOR SELECT TO astra_ingestion_verifier_owner_v1 USING(true);
CREATE POLICY ingestion_verifier_read ON astra_ingestion_v1.records
 FOR SELECT TO astra_ingestion_verifier_owner_v1 USING(true);
CREATE POLICY ingestion_verifier_read ON astra_ingestion_v1.verifications
 FOR SELECT TO astra_ingestion_verifier_owner_v1 USING(true);
CREATE POLICY ingestion_verifier_attest ON astra_ingestion_v1.independent_verifications
 FOR INSERT TO astra_ingestion_verifier_owner_v1 WITH CHECK(true);
GRANT EXECUTE ON FUNCTION astra_ingestion_v1.rpc_ascii_string(text),
  astra_ingestion_v1.rpc_canonical(jsonb),
  astra_ingestion_v1.rpc_json_unique(json),
  astra_ingestion_v1.rpc_time(timestamptz),
  astra_ingestion_v1.rpc_timestamp(text),
  astra_ingestion_v1.rpc_source_timestamp(text),
  astra_ingestion_v1.rpc_number(jsonb,boolean,boolean),
  astra_ingestion_v1.rpc_parse_source(text,text,text,text)
TO astra_ingestion_verifier_owner_v1;
GRANT CREATE ON SCHEMA astra_ingestion_v1 TO astra_ingestion_verifier_owner_v1;
ALTER FUNCTION astra_ingestion_v1.independent_verify_tick_v1()
 OWNER TO astra_ingestion_verifier_owner_v1;
REVOKE CREATE ON SCHEMA astra_ingestion_v1 FROM astra_ingestion_verifier_owner_v1;
DO $grant$
BEGIN
 EXECUTE pg_catalog.format('GRANT EXECUTE ON FUNCTION astra_ingestion_v1.independent_verify_tick_v1() TO %I',current_user);
END $grant$;
-- Schedule separately only after exact-source CI, role ACL readback and a
-- bounded live dry-run. This verifier can never submit or alter ingestion jobs.
