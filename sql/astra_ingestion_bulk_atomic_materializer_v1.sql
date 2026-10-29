-- ASTRA forward-only STAGED atomic retained-source page materializer.
-- Apply only AFTER ledger, 24-family retained gate, runtime port and exact unit binding.
-- NO production installation or grants, no provider calls, no licensed records in Git.
-- A separately authorised source adapter must populate immutable source pages.
-- Restricted worker never supplies output contents, reviewer evidence or page hashes.
BEGIN;
CREATE TABLE astra_ingestion_v1.bulk_retained_source_page_v1 (
 work_key text NOT NULL REFERENCES astra_ingestion_v1.bulk_work_v1(work_key),
 page_no integer NOT NULL CHECK (page_no >= 0),
 source_receipt_sha256 text NOT NULL CHECK (source_receipt_sha256 ~ '^[0-9a-f]{64}$'),
 rows_sha256 text NOT NULL CHECK (rows_sha256 ~ '^[0-9a-f]{64}$'),
 source_rows jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY (work_key,page_no),
 CHECK (jsonb_typeof(source_rows)='array'),
 CHECK (jsonb_array_length(source_rows) BETWEEN 1 AND 128),
 CHECK (rows_sha256 = encode(sha256(convert_to(source_rows::text,'UTF8')),'hex'))
);
CREATE TABLE astra_ingestion_v1.bulk_retained_output_v1 (
 work_key text NOT NULL,
 page_no integer NOT NULL,
 ordinal integer NOT NULL CHECK(ordinal BETWEEN 1 AND 128),
 row_data jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(work_key,page_no,ordinal),
 FOREIGN KEY(work_key,page_no) REFERENCES astra_ingestion_v1.bulk_retained_source_page_v1(work_key,page_no)
);
CREATE FUNCTION astra_ingestion_v1.bulk_retained_rows_immutable_v1()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
BEGIN
 RAISE EXCEPTION 'retained source and output rows are immutable; reconcile rather than replace';
END $$;
CREATE TRIGGER bulk_retained_source_immutable_v1 BEFORE UPDATE OR DELETE OR TRUNCATE
 ON astra_ingestion_v1.bulk_retained_source_page_v1 FOR EACH STATEMENT
 EXECUTE FUNCTION astra_ingestion_v1.bulk_retained_rows_immutable_v1();
CREATE TRIGGER bulk_retained_output_immutable_v1 BEFORE UPDATE OR DELETE OR TRUNCATE
 ON astra_ingestion_v1.bulk_retained_output_v1 FOR EACH STATEMENT
 EXECUTE FUNCTION astra_ingestion_v1.bulk_retained_rows_immutable_v1();
ALTER TABLE astra_ingestion_v1.bulk_retained_source_page_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE astra_ingestion_v1.bulk_retained_output_v1 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON astra_ingestion_v1.bulk_retained_source_page_v1,
 astra_ingestion_v1.bulk_retained_output_v1 FROM PUBLIC;

-- One PostgreSQL transaction either writes all output records AND the durable
-- receipt/counters, or none. The caller supplies no record data or digest.
-- The record source must be separately qualified, pinned and made immutable.
-- This function intentionally cannot verify completeness of outside sources.
CREATE FUNCTION astra_ingestion_v1.bulk_atomic_retained_page_v1(
 p_work text,p_owner text,p_fence bigint,p_page integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog SET timezone='UTC' AS $$
DECLARE v_manifest text; m record; w record; u record; s record;
        v_count integer; v_output_sha text; v_receipt jsonb;
BEGIN
 IF p_work IS NULL OR p_work !~ '^astra-bulk-v1-[0-9a-f]{64}$'
    OR p_owner IS NULL OR p_owner !~ '^[A-Za-z0-9_.:-]{1,128}$'
    OR p_fence IS NULL OR p_fence < 1 OR p_page IS NULL OR p_page < 0
 THEN RAISE EXCEPTION 'invalid bounded atomic materialization request'; END IF;
 SELECT manifest_sha256 INTO v_manifest
 FROM astra_ingestion_v1.bulk_work_v1 WHERE work_key=p_work;
 IF NOT FOUND THEN RAISE EXCEPTION 'unknown retained unit'; END IF;
 -- Manifest lock serialises a concurrent stop/reservation with admission.
 SELECT * INTO m FROM astra_ingestion_v1.bulk_manifest_v1
 WHERE manifest_sha256=v_manifest FOR SHARE;
 IF NOT FOUND OR m.stopped OR astra_ingestion_v1.bulk_runtime_admission_v1(v_manifest) IS NULL
 THEN RAISE EXCEPTION 'manifest unadmitted, stopped or changed'; END IF;
 SELECT * INTO w FROM astra_ingestion_v1.bulk_work_v1
 WHERE work_key=p_work FOR UPDATE;
 IF NOT FOUND OR w.manifest_sha256 IS DISTINCT FROM v_manifest
   OR w.mode IS DISTINCT FROM 'retained_source_reuse'
   OR w.max_requests IS DISTINCT FROM 0 OR w.requests_committed IS DISTINCT FROM 0
   OR w.status IS DISTINCT FROM 'claimed'
   OR w.claim_owner IS DISTINCT FROM p_owner OR w.claim_fence IS DISTINCT FROM p_fence
   OR w.claim_until IS NULL OR w.claim_until <= clock_timestamp()
   OR w.original_deadline <= clock_timestamp()
   OR w.attempts NOT BETWEEN 1 AND 2
   OR p_page IS DISTINCT FROM w.last_page+1
 THEN RAISE EXCEPTION 'stale owner, original deadline, stop, mode or page fence'; END IF;
 -- Existing receipt is an *outcome to reconcile*, not permission to replay.
 IF EXISTS (SELECT 1 FROM astra_ingestion_v1.bulk_receipt_v1
            WHERE work_key=p_work AND page_no=p_page) THEN
   RAISE EXCEPTION 'page already committed: read immutable receipt, never replay';
 END IF;
 SELECT * INTO u FROM astra_ingestion_v1.bulk_reviewed_unit_v1
 WHERE manifest_sha256=v_manifest AND family=w.family AND unit_key=w.unit_key
 AND source_receipt_sha256=w.source_receipt_sha256;
 IF NOT FOUND THEN RAISE EXCEPTION 'reviewed exact source unit missing'; END IF;
 SELECT * INTO s FROM astra_ingestion_v1.bulk_retained_source_page_v1
 WHERE work_key=p_work AND page_no=p_page FOR SHARE;
 IF NOT FOUND OR s.source_receipt_sha256 IS DISTINCT FROM w.source_receipt_sha256
    OR s.rows_sha256 IS DISTINCT FROM
       encode(sha256(convert_to(s.source_rows::text,'UTF8')),'hex')
 THEN RAISE EXCEPTION 'immutable staged source page missing or drifted'; END IF;
 v_count := jsonb_array_length(s.source_rows);
 IF v_count < 1 OR v_count > 128 OR w.records_committed+v_count > w.max_records
 THEN RAISE EXCEPTION 'materialization exceeds finite original record reservation'; END IF;
 INSERT INTO astra_ingestion_v1.bulk_retained_output_v1(work_key,page_no,ordinal,row_data)
 SELECT p_work,p_page,ordinal::integer,item
 FROM jsonb_array_elements(s.source_rows) WITH ORDINALITY AS x(item,ordinal);
 SELECT count(*),encode(sha256(convert_to(
   COALESCE(jsonb_agg(row_data ORDER BY ordinal)::text,'[]'),'UTF8')),'hex')
 INTO v_count,v_output_sha
 FROM astra_ingestion_v1.bulk_retained_output_v1
 WHERE work_key=p_work AND page_no=p_page;
 IF v_count IS DISTINCT FROM jsonb_array_length(s.source_rows)
    OR v_output_sha IS DISTINCT FROM s.rows_sha256
 THEN RAISE EXCEPTION 'materialized output differs from immutable source page'; END IF;
 v_receipt := astra_ingestion_v1.bulk_commit_page_v1(
   p_work,p_owner,p_fence,p_page,s.rows_sha256,v_output_sha,v_count,0);
 IF v_receipt->>'output_sha256' IS DISTINCT FROM v_output_sha
    OR (v_receipt->>'records_committed')::integer IS DISTINCT FROM v_count
 THEN RAISE EXCEPTION 'atomic materialization receipt mismatch'; END IF;
 RETURN v_receipt;
END $$;

-- Read-only post-crash reconciliation: no mutation, no resume, no replay.
-- Privilege must be scoped to an authenticated restricted actor before grant.
CREATE FUNCTION astra_ingestion_v1.bulk_retained_receipt_readback_v1(
 p_work text,p_page integer)
RETURNS jsonb LANGUAGE sql SECURITY DEFINER
SET search_path=pg_catalog SET timezone='UTC' AS $$
 SELECT CASE WHEN r.work_key IS NULL THEN NULL
 ELSE jsonb_build_object(
   'work_key',r.work_key,'page_no',r.page_no,
   'source_sha256',r.source_sha256,'output_sha256',r.output_sha256,
   'records_committed',r.records_committed,'requests_committed',r.requests_committed,
   'actual_records',x.cnt,'actual_output_sha256',x.digest,
   'consistent', x.cnt=r.records_committed AND x.digest=r.output_sha256)
 END
 FROM astra_ingestion_v1.bulk_receipt_v1 r
 CROSS JOIN LATERAL (
  SELECT count(*) AS cnt,encode(sha256(convert_to(
     COALESCE(jsonb_agg(row_data ORDER BY ordinal)::text,'[]'),'UTF8')),'hex') AS digest
  FROM astra_ingestion_v1.bulk_retained_output_v1 o
  WHERE o.work_key=r.work_key AND o.page_no=r.page_no
 ) x
 WHERE r.work_key=p_work AND r.page_no=p_page
$$;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_retained_rows_immutable_v1() FROM PUBLIC;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_atomic_retained_page_v1(text,text,bigint,int) FROM PUBLIC;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_retained_receipt_readback_v1(text,int) FROM PUBLIC;
COMMIT;
