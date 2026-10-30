-- ASTRA source-only candidate: atomic P01/P02 quarantined provider page + receipt.
-- Apply ONLY after ledger, independent 24-family + unit gates, reviewed request,
-- durable pre-call ticket and immutable response quarantine, with separate
-- authenticated HTTPS transport principal/roles independently qualified.
-- Nothing in this file verifies that an HTTP response genuinely came from Alpaca.
-- Synthetic CI source-provenance pins ARE NOT independent transport assurance.
-- NEVER install/grant as a shortcut around hosted JWT, provenance or stop gates.
-- No PUBLIC grants, no provider calls, no legacy writes, no licensed rows in Git.
BEGIN;
CREATE TABLE astra_ingestion_v1.bulk_provider_transport_proof_v1 (
 work_key text NOT NULL,
 page_no int NOT NULL CHECK(page_no BETWEEN 0 AND 199),
 request_sha256 text NOT NULL CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
 source_page_sha256 text NOT NULL CHECK(source_page_sha256 ~ '^[0-9a-f]{64}$'),
 eligible_bars_sha256 text NOT NULL CHECK(eligible_bars_sha256 ~ '^[0-9a-f]{64}$'),
 provider_https_receipt_sha256 text NOT NULL CHECK(provider_https_receipt_sha256 ~ '^[0-9a-f]{64}$'),
 origin text NOT NULL CHECK(origin='ALPACA_STOCK_BARS_1MIN_SIP_RAW'),
 recorded_by name NOT NULL DEFAULT session_user,
 attested_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(work_key,page_no),
 FOREIGN KEY(work_key,page_no)
  REFERENCES astra_ingestion_v1.bulk_provider_response_quarantine_v1(work_key,page_no)
);
-- The transport attestor is a distinct, separately authenticated principal.
-- No insertion route or grant for that principal is supplied by this migration.
CREATE TRIGGER bulk_provider_transport_proof_immutable_v1
 BEFORE UPDATE OR DELETE OR TRUNCATE
 ON astra_ingestion_v1.bulk_provider_transport_proof_v1
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.bulk_review_immutable_v1();
ALTER TABLE astra_ingestion_v1.bulk_provider_transport_proof_v1 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON astra_ingestion_v1.bulk_provider_transport_proof_v1 FROM PUBLIC;

CREATE TABLE astra_ingestion_v1.bulk_provider_output_v1 (
 work_key text NOT NULL,
 page_no int NOT NULL CHECK(page_no BETWEEN 0 AND 199),
 ordinal int NOT NULL CHECK(ordinal BETWEEN 1 AND 1000),
 row_data jsonb NOT NULL,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(work_key,page_no,ordinal),
 FOREIGN KEY(work_key,page_no)
  REFERENCES astra_ingestion_v1.bulk_provider_response_quarantine_v1(work_key,page_no)
);
CREATE TRIGGER bulk_provider_output_immutable_v1
 BEFORE UPDATE OR DELETE OR TRUNCATE
 ON astra_ingestion_v1.bulk_provider_output_v1
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.bulk_review_immutable_v1();
ALTER TABLE astra_ingestion_v1.bulk_provider_output_v1 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON astra_ingestion_v1.bulk_provider_output_v1 FROM PUBLIC;

-- The restricted worker supplies ONLY an existing work key/fenced claim/page.
-- All source records, hashes and transport evidence come from immutable tables.
-- PostgreSQL commits output, receipt and cumulative counters in ONE transaction.
-- This is source/test mechanics, not permission for synthetic transport proof in
-- production. Actual provider authentication and independent source review gate.
CREATE FUNCTION astra_ingestion_v1.bulk_atomic_provider_page_v1(
 p_work text,p_owner text,p_fence bigint,p_page int)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog SET timezone='UTC' AS $$
DECLARE v_manifest text; m record; w record; t record; q record; a record;
        proof record; v_count bigint; v_digest text; v_used bigint;
        v_receipt jsonb;
BEGIN
 IF p_work IS NULL OR p_work !~ '^astra-bulk-v1-[0-9a-f]{64}$'
 OR p_owner IS NULL OR p_owner !~ '^[A-Za-z0-9_.:-]{1,128}$'
 OR p_fence IS NULL OR p_fence<1
 OR p_page IS NULL OR p_page NOT BETWEEN 0 AND 199
 THEN RAISE EXCEPTION 'invalid bounded provider materialization identity'; END IF;
 SELECT manifest_sha256 INTO v_manifest
 FROM astra_ingestion_v1.bulk_work_v1 WHERE work_key=p_work;
 IF NOT FOUND THEN RAISE EXCEPTION 'unknown provider work'; END IF;
 -- Serialize with explicit stop and immutable reservation before work claim.
 SELECT * INTO m FROM astra_ingestion_v1.bulk_manifest_v1
 WHERE manifest_sha256=v_manifest FOR SHARE;
 IF NOT FOUND OR m.stopped
 OR m.capture_key IS DISTINCT FROM 'top3000-augsep2026-retained-scope-v1'
 OR m.capture_receipt_sha256 IS DISTINCT FROM 'ba13899b530288b6aae8d4af3a429efa3f4bd5ec305a7dc698f98c9d552f4496'
 THEN RAISE EXCEPTION 'provider commit refused: manifest stopped or changed'; END IF;
 SELECT * INTO w FROM astra_ingestion_v1.bulk_work_v1
 WHERE work_key=p_work FOR UPDATE;
 IF NOT FOUND OR w.manifest_sha256 IS DISTINCT FROM v_manifest
 OR w.mode IS DISTINCT FROM 'provider_acquisition'
 OR w.family NOT IN ('P01','P02')
 OR w.status IS DISTINCT FROM 'claimed'
 OR w.claim_owner IS DISTINCT FROM p_owner
 OR w.claim_fence IS DISTINCT FROM p_fence
 OR w.claim_until IS NULL OR w.claim_until<=clock_timestamp()
 OR w.original_deadline<=clock_timestamp()
 OR w.attempts NOT BETWEEN 1 AND 2
 OR w.last_page+1 IS DISTINCT FROM p_page
 OR w.requests_committed+1>w.max_requests
 THEN RAISE EXCEPTION 'provider commit refused: stale claim, deadline, stop or sequence'; END IF;
 IF EXISTS (SELECT 1 FROM astra_ingestion_v1.bulk_receipt_v1
  WHERE work_key=p_work AND page_no=p_page) THEN
  RAISE EXCEPTION 'provider receipt already committed: reconcile, never replay';
 END IF;
 SELECT * INTO t FROM astra_ingestion_v1.bulk_provider_precall_v1
 WHERE work_key=p_work AND page_no=p_page FOR SHARE;
 SELECT * INTO q FROM astra_ingestion_v1.bulk_provider_response_quarantine_v1
 WHERE work_key=p_work AND page_no=p_page FOR SHARE;
 IF t.work_key IS NULL OR q.work_key IS NULL
 OR t.manifest_sha256 IS DISTINCT FROM v_manifest
 OR t.family IS DISTINCT FROM w.family
 OR t.source_receipt_sha256 IS DISTINCT FROM w.source_receipt_sha256
 OR t.owner IS DISTINCT FROM p_owner OR t.fence IS DISTINCT FROM p_fence
 OR t.original_deadline IS DISTINCT FROM w.original_deadline
 OR q.manifest_sha256 IS DISTINCT FROM v_manifest
 OR q.family IS DISTINCT FROM w.family
 OR q.request_sha256 IS DISTINCT FROM t.request_sha256
 OR q.claim_owner IS DISTINCT FROM p_owner
 OR q.claim_fence IS DISTINCT FROM p_fence
 OR q.original_deadline IS DISTINCT FROM w.original_deadline
 OR q.status IS DISTINCT FROM 'QUARANTINED_UNAUTHENTICATED_NOT_BULK_COMMITTED'
 OR t.records_reserved<q.provider_records_observed
 OR q.eligible_records+q.inclusive_end_records_excluded<>q.provider_records_observed
 OR q.eligible_bars_sha256 IS DISTINCT FROM
   encode(sha256(convert_to(q.eligible_bars::text,'UTF8')),'hex')
 THEN RAISE EXCEPTION 'provider commit missing immutable exact source/ticket/quarantine'; END IF;
 SELECT * INTO a FROM astra_ingestion_v1.bulk_manifest_review_v1
 WHERE manifest_sha256=v_manifest;
 IF NOT FOUND OR a.family_count IS DISTINCT FROM 24
 OR NOT EXISTS (
  SELECT 1 FROM astra_ingestion_v1.bulk_provider_review_v1 rv
   WHERE rv.manifest_sha256=v_manifest
     AND rv.independent_report_sha256=a.independent_report_sha256
 ) OR NOT EXISTS (
  SELECT 1 FROM astra_ingestion_v1.bulk_provider_reviewed_request_v1 rr
  WHERE rr.work_key=p_work AND rr.page_no=p_page
  AND rr.manifest_sha256=v_manifest AND rr.family=w.family
  AND rr.source_receipt_sha256=w.source_receipt_sha256
  AND rr.independent_report_sha256=a.independent_report_sha256
  AND rr.request_sha256=t.request_sha256
  AND rr.records_reserved=t.records_reserved
 ) OR NOT EXISTS (
  SELECT 1 FROM astra_ingestion_v1.bulk_reviewed_unit_v1 u
  WHERE u.manifest_sha256=v_manifest AND u.family=w.family
  AND u.unit_key=w.unit_key AND u.source_receipt_sha256=w.source_receipt_sha256
  AND u.independent_report_sha256=a.independent_report_sha256
 ) THEN RAISE EXCEPTION 'provider commit missing distinct source/unit/request review'; END IF;
 -- A transport proof is written ONLY by a separately authorized external
 -- attestor. A synthetic CI proof does NOT demonstrate genuine HTTPS/JWT.
 SELECT * INTO proof FROM astra_ingestion_v1.bulk_provider_transport_proof_v1
 WHERE work_key=p_work AND page_no=p_page FOR SHARE;
 IF NOT FOUND
 OR proof.request_sha256 IS DISTINCT FROM t.request_sha256
 OR proof.source_page_sha256 IS DISTINCT FROM q.source_page_sha256
 OR proof.eligible_bars_sha256 IS DISTINCT FROM q.eligible_bars_sha256
 OR proof.attested_at<t.reserved_at
 OR proof.attested_at>clock_timestamp()
 OR proof.attested_at>w.original_deadline
 THEN RAISE EXCEPTION 'separate provider transport proof missing or inconsistent'; END IF;
 -- Budget counts ALL observed provider records, including a valid excluded
 -- inclusive-end boundary. Eligible output is not the provider debit.
 SELECT COALESCE(sum(previous.provider_records_observed),0) INTO v_used
 FROM astra_ingestion_v1.bulk_provider_response_quarantine_v1 previous
 JOIN astra_ingestion_v1.bulk_receipt_v1 rr
  ON rr.work_key=previous.work_key AND rr.page_no=previous.page_no
 WHERE previous.work_key=p_work AND previous.page_no<p_page;
 IF GREATEST(w.records_committed,v_used)+q.provider_records_observed > w.max_records
 OR w.records_committed+q.eligible_records > w.max_records
 THEN RAISE EXCEPTION 'cumulative actual provider record budget exceeded'; END IF;
 IF p_page>0 AND NOT EXISTS (
  SELECT 1 FROM astra_ingestion_v1.bulk_provider_response_quarantine_v1 prev
  JOIN astra_ingestion_v1.bulk_receipt_v1 rr
   ON rr.work_key=prev.work_key AND rr.page_no=prev.page_no
  WHERE prev.work_key=p_work AND prev.page_no=p_page-1
  AND prev.next_page_required AND rr.requests_committed=1
  AND prev.continuation_token_sha256=q.previous_continuation_token_sha256
 ) THEN RAISE EXCEPTION 'provider continuation has no committed predecessor'; END IF;
 INSERT INTO astra_ingestion_v1.bulk_provider_output_v1(work_key,page_no,ordinal,row_data)
 SELECT p_work,p_page,ordinal::int,item
 FROM jsonb_array_elements(q.eligible_bars) WITH ORDINALITY AS x(item,ordinal);
 SELECT count(*),encode(sha256(convert_to(
   COALESCE(jsonb_agg(row_data ORDER BY ordinal)::text,'[]'),'UTF8')),'hex')
 INTO v_count,v_digest
 FROM astra_ingestion_v1.bulk_provider_output_v1
 WHERE work_key=p_work AND page_no=p_page;
 IF v_count IS DISTINCT FROM q.eligible_records
 OR v_digest IS DISTINCT FROM q.eligible_bars_sha256
 THEN RAISE EXCEPTION 'provider output changed from immutable quarantine'; END IF;
 v_receipt:=astra_ingestion_v1.bulk_commit_page_v1(
  p_work,p_owner,p_fence,p_page,q.source_page_sha256,v_digest,v_count::int,1);
 IF v_receipt->>'source_sha256' IS DISTINCT FROM q.source_page_sha256
 OR v_receipt->>'output_sha256' IS DISTINCT FROM v_digest
 OR (v_receipt->>'records_committed')::int IS DISTINCT FROM v_count
 OR (v_receipt->>'requests_committed')::int IS DISTINCT FROM 1
 THEN RAISE EXCEPTION 'atomic provider receipt mismatch'; END IF;
 RETURN jsonb_build_object(
  'status','ATOMICALLY_COMMITTED_PENDING_INDEPENDENT_TRANSPORT_AND_SOURCE_ACCEPTANCE',
  'work_key',p_work,'page_no',p_page,'request_sha256',t.request_sha256,
  'receipt_sha256',q.source_page_sha256,
  'output_sha256',v_digest,'eligible_records_committed',v_count,
  'provider_records_consumed',q.provider_records_observed,
  'requests_committed',1,'coverage_certified',false,
  'source_authenticity_independently_certified',false);
END $$;

-- Post-crash readback NEVER returns licensed prices; it is not a retry path.
-- The source-page hash, output digest, request and provider observed record
-- counts remain auditable even for empty eligible pages.
CREATE FUNCTION astra_ingestion_v1.bulk_provider_atomic_readback_v1(
 p_work text,p_page int)
RETURNS jsonb LANGUAGE sql SECURITY DEFINER
SET search_path=pg_catalog SET timezone='UTC' AS $$
 SELECT jsonb_build_object(
  'work_key',r.work_key,'page_no',r.page_no,
  'source_sha256',r.source_sha256,'output_sha256',r.output_sha256,
  'records_committed',r.records_committed,
  'requests_committed',r.requests_committed,
  'provider_records_observed',q.provider_records_observed,
  'provider_https_receipt_sha256',p.provider_https_receipt_sha256,
  'actual_output_records',x.actual_count,
  'actual_output_sha256',x.actual_digest,
  'consistent',r.requests_committed=1
   AND r.records_committed=x.actual_count
   AND r.output_sha256=x.actual_digest
   AND r.output_sha256=q.eligible_bars_sha256
   AND r.source_sha256=q.source_page_sha256
   AND q.source_page_sha256=p.source_page_sha256,
  'coverage_certified',false,'source_authenticity_independently_certified',false)
 FROM astra_ingestion_v1.bulk_receipt_v1 r
 JOIN astra_ingestion_v1.bulk_provider_response_quarantine_v1 q
  ON q.work_key=r.work_key AND q.page_no=r.page_no
 JOIN astra_ingestion_v1.bulk_provider_transport_proof_v1 p
  ON p.work_key=r.work_key AND p.page_no=r.page_no
 CROSS JOIN LATERAL (
   SELECT count(*) actual_count,
    encode(sha256(convert_to(
      COALESCE(jsonb_agg(row_data ORDER BY ordinal)::text,'[]'),'UTF8')),'hex') actual_digest
   FROM astra_ingestion_v1.bulk_provider_output_v1 o
   WHERE o.work_key=r.work_key AND o.page_no=r.page_no
 ) x
 WHERE r.work_key=p_work AND r.page_no=p_page
$$;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_atomic_provider_page_v1(text,text,bigint,int) FROM PUBLIC;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_provider_atomic_readback_v1(text,int) FROM PUBLIC;
COMMIT;
