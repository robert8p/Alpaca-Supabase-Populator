-- One-time isolated evidence capture infrastructure. No acquisition or serving.
-- Execute transactionally after exact-revision CI. Existing v1 jobs untouched.
-- Source schema is READ ONLY. No grants to worker/provider/admin API identities.
CREATE TABLE astra_ingestion_v1.bulk_scope_capture_v1 (
 capture_key text PRIMARY KEY,
 first_run_id text NOT NULL,
 captured_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 evidence_rows integer NOT NULL CHECK(evidence_rows > 0),
 evidence_sha256 text NOT NULL CHECK(evidence_sha256 ~ '^[0-9a-f]{64}$'),
 state text NOT NULL DEFAULT 'CAPTURED_NOT_ADMITTED' CHECK(state='CAPTURED_NOT_ADMITTED'),
 provider_requests integer NOT NULL DEFAULT 0 CHECK(provider_requests=0),
 incremental_cost_microusd bigint NOT NULL DEFAULT 0 CHECK(incremental_cost_microusd=0),
 historical_coverage text NOT NULL DEFAULT 'NOT_CERTIFIED' CHECK(historical_coverage='NOT_CERTIFIED')
);
CREATE TABLE astra_ingestion_v1.bulk_scope_evidence_v1 (
 capture_key text NOT NULL REFERENCES astra_ingestion_v1.bulk_scope_capture_v1(capture_key)
   DEFERRABLE INITIALLY DEFERRED,
 kind text NOT NULL CHECK(kind IN ('scope','cohort','membership','company','contract','calendar','preservation','acceptance_event')),
 evidence_key text NOT NULL,
 source_text text NOT NULL CHECK(octet_length(source_text) BETWEEN 2 AND 16000000),
 source_sha256 text NOT NULL CHECK(source_sha256 = encode(sha256(convert_to(source_text,'UTF8')),'hex')),
 PRIMARY KEY(capture_key,kind,evidence_key)
);
ALTER TABLE astra_ingestion_v1.bulk_scope_capture_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE astra_ingestion_v1.bulk_scope_evidence_v1 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON astra_ingestion_v1.bulk_scope_capture_v1, astra_ingestion_v1.bulk_scope_evidence_v1 FROM PUBLIC;

CREATE FUNCTION astra_ingestion_v1.bulk_evidence_immutable_v1() RETURNS trigger
LANGUAGE plpgsql SET search_path=pg_catalog AS $$
BEGIN RAISE EXCEPTION 'bulk evidence is immutable; retain history and create a separately admitted revision'; END $$;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_evidence_immutable_v1() FROM PUBLIC;
CREATE TRIGGER bulk_capture_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
 ON astra_ingestion_v1.bulk_scope_capture_v1 FOR EACH STATEMENT
 EXECUTE FUNCTION astra_ingestion_v1.bulk_evidence_immutable_v1();
CREATE TRIGGER bulk_evidence_immutable BEFORE UPDATE OR DELETE OR TRUNCATE
 ON astra_ingestion_v1.bulk_scope_evidence_v1 FOR EACH STATEMENT
 EXECUTE FUNCTION astra_ingestion_v1.bulk_evidence_immutable_v1();

CREATE FUNCTION astra_ingestion_v1.capture_retained_top3000_scope_v1(p_run_id text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog SET timezone='UTC' AS $$
DECLARE
 k constant text := 'top3000-augsep2026-retained-scope-v1';
 s constant text := 'corrected_company_scope_8e6ca1178f03822c';
 cohort constant text := '2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec';
 acceptance constant text := '20b9dac759857e9b510ccaeca33e4a94d8c748d588fb0cc27740cc66c389b5f9';
 rows_json jsonb; row_count integer; manifest_hash text; actual_hash text; actual_count integer;
 ok boolean; contract_set text; receipt jsonb;
BEGIN
 IF current_setting('transaction_isolation') NOT IN ('repeatable read','serializable') THEN
   RAISE EXCEPTION 'capture requires a consistent repeatable-read transaction';
 END IF;
 IF clock_timestamp() >= '2026-11-05T02:00:00Z'::timestamptz THEN
   RAISE EXCEPTION 'completion campaign deadline reached';
 END IF;
 IF p_run_id IS NULL OR p_run_id !~ '^[a-zA-Z0-9][a-zA-Z0-9_.:-]{7,127}$' THEN
   RAISE EXCEPTION 'invalid finite capture run identifier';
 END IF;
 -- Nonblocking: a second caller must reconcile rather than wait and compete.
 IF NOT pg_try_advisory_xact_lock(21471926, 300024) THEN
   RAISE EXCEPTION 'retained scope capture already owned';
 END IF;
 SELECT count(*)=1 AND bool_and(payload_sha256='969bab3ac1a4348958e6c2cc501462f4ec1bb35cc500779b4327bab17a46835e'
   AND (encode(sha256(convert_to(payload_text,'UTF8')),'hex')=payload_sha256) IS TRUE) INTO ok
 FROM population_top3000_202608_202609_v1.catalog_scope WHERE scope_id=s;
 IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'scope source drift'; END IF;
 SELECT count(*)=1 AND bool_and((encode(sha256(convert_to(content::text,'UTF8')),'hex')=cohort) IS TRUE) INTO ok
 FROM population_top3000_202608_202609_v1.ref01_practical_snapshot_v1 WHERE snapshot_sha256=cohort;
 IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'cohort source drift'; END IF;
 SELECT count(*)=1 AND bool_and(encode(sha256(convert_to(content::text,'UTF8')),'hex')=acceptance
   AND content->>'membership_accepted'='true' AND content->>'company_count'='3000') IS TRUE INTO ok
 FROM population_top3000_202608_202609_v1.ref01_practical_membership_v1
 WHERE snapshot_sha256=cohort AND acceptance_sha256=acceptance;
 IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'membership source drift'; END IF;
 SELECT count(*)=1 INTO ok
 FROM population_top3000_202608_202609_v1.ref01_practical_membership_v1 m
 JOIN population_top3000_202608_202609_v1.pipeline_event e ON e.event_id=m.root_acceptance_event_id
 WHERE m.snapshot_sha256=cohort AND m.acceptance_sha256=acceptance
   AND e.event='ROOT_PRACTICAL_COHORT_MEMBERSHIP_ACCEPTANCE_V1'
   AND e.details->>'snapshot_sha256'=cohort AND e.details->>'membership_only'='true';
 IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'root acceptance evidence drift'; END IF;
 SELECT count(*)=3000 AND count(DISTINCT company_id)=3000
   AND count(DISTINCT selection_order)=3000 AND min(selection_order)=1 AND max(selection_order)=3000
   AND bool_and((cohort_sha256=cohort AND membership_acceptance_sha256=acceptance
     AND membership_accepted IS TRUE AND exact_global_rank_certified IS FALSE
     AND financial_capitalization_qualified IS FALSE AND full_period_instrument_coverage_accepted IS FALSE) IS TRUE)
 INTO ok FROM population_top3000_202608_202609_v1.working_accepted_companies_v1;
 IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'accepted membership count, identity, rank or hold drift'; END IF;
 SELECT count(*)=24 AND count(DISTINCT family_id)=24 AND bool_and(
   (encode(sha256(convert_to(contract_text,'UTF8')),'hex')=contract_sha256) IS TRUE),
   encode(sha256(convert_to(string_agg(family_id||':'||contract_sha256,E'\n' ORDER BY family_id),'UTF8')),'hex')
 INTO ok,contract_set FROM population_top3000_202608_202609_v1.catalog_family_contract WHERE scope_id=s;
 IF ok IS DISTINCT FROM true OR contract_set IS DISTINCT FROM
 'e47a1e4152768418bd8e6187310b34cfc7b096edbc1e1de11fe243275e046dc0' THEN
   RAISE EXCEPTION '24-family contract set drift';
 END IF;
 SELECT count(*)=42 AND count(DISTINCT session_date)=42 AND sum(regular_scheduled_minutes)=16380
   AND min(session_date)='2026-08-03'::date AND max(session_date)='2026-09-30'::date
   AND bool_and((encode(sha256(convert_to(source_record_text,'UTF8')),'hex')=source_record_sha256
     AND encode(sha256(convert_to(source_receipt_text,'UTF8')),'hex')=source_receipt_sha256) IS TRUE)
 INTO ok FROM population_top3000_202608_202609_v1.catalog_calendar WHERE scope_id=s;
 IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'calendar count or retained-source drift'; END IF;
 SELECT count(*)=3 AND count(DISTINCT relation_name)=3 AND bool_and(
   (encode(sha256(convert_to(metadata_text,'UTF8')),'hex')=metadata_sha256) IS TRUE)
 INTO ok FROM population_top3000_202608_202609_v1.catalog_d06_preservation WHERE scope_id=s;
 IF ok IS DISTINCT FROM true THEN RAISE EXCEPTION 'D06 preservation catalogue drift'; END IF;

 WITH source_rows(kind,evidence_key,source_text) AS (
  SELECT 'scope',scope_id,payload_text FROM population_top3000_202608_202609_v1.catalog_scope WHERE scope_id=s
  UNION ALL SELECT 'cohort',snapshot_sha256,content::text FROM population_top3000_202608_202609_v1.ref01_practical_snapshot_v1 WHERE snapshot_sha256=cohort
  UNION ALL SELECT 'membership',acceptance_sha256,content::text FROM population_top3000_202608_202609_v1.ref01_practical_membership_v1 WHERE snapshot_sha256=cohort AND acceptance_sha256=acceptance
  UNION ALL SELECT 'company',company_id,to_jsonb(c)::text FROM population_top3000_202608_202609_v1.working_accepted_companies_v1 c
  UNION ALL SELECT 'contract',family_id,contract_text FROM population_top3000_202608_202609_v1.catalog_family_contract WHERE scope_id=s
  UNION ALL SELECT 'calendar',session_date::text,to_jsonb(c)::text FROM population_top3000_202608_202609_v1.catalog_calendar c WHERE scope_id=s
  UNION ALL SELECT 'preservation',relation_name,to_jsonb(d)::text FROM population_top3000_202608_202609_v1.catalog_d06_preservation d WHERE scope_id=s
  UNION ALL SELECT 'acceptance_event',e.event_id::text,to_jsonb(e)::text
   FROM population_top3000_202608_202609_v1.pipeline_event e
   WHERE e.event_id IN (SELECT root_acceptance_event_id FROM population_top3000_202608_202609_v1.ref01_practical_membership_v1 WHERE snapshot_sha256=cohort AND acceptance_sha256=acceptance
     UNION SELECT independent_review_event_id FROM population_top3000_202608_202609_v1.ref01_practical_membership_v1 WHERE snapshot_sha256=cohort AND acceptance_sha256=acceptance)
 ) SELECT jsonb_agg(to_jsonb(r) ORDER BY kind,evidence_key),count(*),
   encode(sha256(convert_to(jsonb_agg(jsonb_build_array(kind,evidence_key,
     encode(sha256(convert_to(source_text,'UTF8')),'hex')) ORDER BY kind,evidence_key)::text,'UTF8')),'hex')
 INTO rows_json,row_count,manifest_hash FROM source_rows r;
 IF row_count != 3074 OR octet_length(rows_json::text)>16000000 THEN
   RAISE EXCEPTION 'capture boundary failed; expected 3074 bounded evidence records';
 END IF;
 INSERT INTO astra_ingestion_v1.bulk_scope_evidence_v1(capture_key,kind,evidence_key,source_text,source_sha256)
 SELECT k,r.kind,r.evidence_key,r.source_text,encode(sha256(convert_to(r.source_text,'UTF8')),'hex') FROM jsonb_to_recordset(rows_json)
   AS r(kind text,evidence_key text,source_text text)
 ON CONFLICT DO NOTHING;
 SELECT count(*),encode(sha256(convert_to(jsonb_agg(jsonb_build_array(kind,evidence_key,source_sha256)
   ORDER BY kind,evidence_key)::text,'UTF8')),'hex') INTO actual_count,actual_hash
 FROM astra_ingestion_v1.bulk_scope_evidence_v1 WHERE capture_key=k;
 IF actual_count IS DISTINCT FROM row_count OR actual_hash IS DISTINCT FROM manifest_hash THEN
   RAISE EXCEPTION 'existing capture conflicts; never overwrite or blindly replay';
 END IF;
 INSERT INTO astra_ingestion_v1.bulk_scope_capture_v1(capture_key,first_run_id,evidence_rows,evidence_sha256)
 VALUES(k,p_run_id,row_count,manifest_hash) ON CONFLICT DO NOTHING;
 SELECT to_jsonb(c) INTO receipt FROM astra_ingestion_v1.bulk_scope_capture_v1 c WHERE capture_key=k;
 IF receipt->>'evidence_sha256' IS DISTINCT FROM manifest_hash
   OR (receipt->>'evidence_rows')::integer IS DISTINCT FROM row_count THEN
   RAISE EXCEPTION 'existing capture receipt conflicts';
 END IF;
 RETURN receipt;
END $$;
REVOKE ALL ON FUNCTION astra_ingestion_v1.capture_retained_top3000_scope_v1(text) FROM PUBLIC;
-- Explicitly undo possible default grants. No new runtime privileges are implied.
DO $$ DECLARE r text; BEGIN
 FOREACH r IN ARRAY ARRAY['anon','authenticated','service_role',
   'astra_ingestion_monitor_owner_v1','astra_ingestion_rpc_owner_v1','astra_ingestion_verifier_owner_v1'] LOOP
  IF EXISTS(SELECT 1 FROM pg_roles WHERE rolname=r) THEN
   EXECUTE format('REVOKE ALL ON astra_ingestion_v1.bulk_scope_capture_v1, astra_ingestion_v1.bulk_scope_evidence_v1 FROM %I',r);
   EXECUTE format('REVOKE ALL ON FUNCTION astra_ingestion_v1.capture_retained_top3000_scope_v1(text), astra_ingestion_v1.bulk_evidence_immutable_v1() FROM %I',r);
  END IF;
 END LOOP;
END $$;
