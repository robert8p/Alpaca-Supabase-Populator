-- ASTRA bounded P01/P02 provider-response QUARANTINE. Staged source ONLY.
-- Prerequisites: ledger, independent 24-family/unit review, provider pre-call v1.
-- This is deliberately NOT a market-data ingestion/output or provider transport grant.
-- No PUBLIC privileges, no production install, no licensed rows in repository.
-- All provider records, including excluded eligible-window boundary observations,
-- consume the finite record cap across pages. No terminal-page continuation.
-- The one durable pre-call ticket is permanently consumed for this page even
-- if the remote response was lost. A missing/uncertain response must NOT refetch.
BEGIN;
CREATE TABLE astra_ingestion_v1.bulk_provider_response_quarantine_v1 (
 work_key text NOT NULL,
 page_no int NOT NULL CHECK(page_no BETWEEN 0 AND 199),
 manifest_sha256 text NOT NULL CHECK(manifest_sha256 ~ '^[0-9a-f]{64}$'),
 family text NOT NULL CHECK(family IN ('P01','P02')),
 original_deadline timestamptz NOT NULL,
 request_sha256 text NOT NULL CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
 source_page_sha256 text NOT NULL CHECK(source_page_sha256 ~ '^[0-9a-f]{64}$'),
 stage_candidate_sha256 text NOT NULL CHECK(stage_candidate_sha256 ~ '^[0-9a-f]{64}$'),
 claim_owner text NOT NULL,
 claim_fence bigint NOT NULL CHECK(claim_fence>=1),
 provider_records_observed int NOT NULL CHECK(provider_records_observed BETWEEN 0 AND 1000),
 eligible_records int NOT NULL CHECK(eligible_records BETWEEN 0 AND 1000),
 inclusive_end_records_excluded int NOT NULL CHECK(inclusive_end_records_excluded BETWEEN 0 AND 1),
 eligible_bars jsonb NOT NULL,
 eligible_bars_sha256 text NOT NULL CHECK(eligible_bars_sha256 ~ '^[0-9a-f]{64}$'),
 next_page_required boolean NOT NULL,
 continuation_token_sha256 text CHECK(continuation_token_sha256 ~ '^[0-9a-f]{64}$'),
 previous_continuation_token_sha256 text CHECK(previous_continuation_token_sha256 ~ '^[0-9a-f]{64}$'),
 received_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 status text NOT NULL DEFAULT 'QUARANTINED_UNAUTHENTICATED_NOT_BULK_COMMITTED'
 CHECK(status='QUARANTINED_UNAUTHENTICATED_NOT_BULK_COMMITTED'),
 PRIMARY KEY(work_key,page_no),
 FOREIGN KEY(work_key,page_no)
  REFERENCES astra_ingestion_v1.bulk_provider_precall_v1(work_key,page_no),
 CHECK(jsonb_typeof(eligible_bars)='array'),
 CHECK(jsonb_array_length(eligible_bars)=eligible_records),
 CHECK(provider_records_observed=eligible_records+inclusive_end_records_excluded),
 CHECK(eligible_bars_sha256=encode(sha256(convert_to(eligible_bars::text,'UTF8')),'hex')),
 CHECK((next_page_required AND continuation_token_sha256 IS NOT NULL
         AND eligible_records>0)
   OR (NOT next_page_required AND continuation_token_sha256 IS NULL)),
 CHECK((page_no=0 AND previous_continuation_token_sha256 IS NULL)
    OR (page_no>0 AND previous_continuation_token_sha256 IS NOT NULL))
);
CREATE UNIQUE INDEX bulk_provider_response_continuation_nonreplay_v1
 ON astra_ingestion_v1.bulk_provider_response_quarantine_v1(work_key,continuation_token_sha256)
 WHERE continuation_token_sha256 IS NOT NULL;
CREATE TRIGGER bulk_provider_response_quarantine_immutable_v1
 BEFORE UPDATE OR DELETE OR TRUNCATE
 ON astra_ingestion_v1.bulk_provider_response_quarantine_v1
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.bulk_review_immutable_v1();
ALTER TABLE astra_ingestion_v1.bulk_provider_response_quarantine_v1 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON astra_ingestion_v1.bulk_provider_response_quarantine_v1 FROM PUBLIC;

-- Direct use requires a separate qualified DB principal with minimal grants.
-- An administrator fixture in CI is NOT a separate live authenticated actor.
-- The function can only *quarantine* a validated candidate, never authorize
-- transport, bind external provider provenance, or increment committed output.
CREATE FUNCTION astra_ingestion_v1.bulk_provider_quarantine_response_v1(
 p_work text,p_owner text,p_fence bigint,p_page int,p_request_sha256 text,p_stage jsonb)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
SET search_path=pg_catalog SET timezone='UTC' AS $$
DECLARE v_manifest text; m record; w record; t record; prev record; a record;
 v_observed int; v_eligible int; v_excluded int; v_next boolean;
 v_bars jsonb; v_digest text; v_token text; v_prev_token text;
 v_source text; v_candidate text; v_receipt jsonb;
BEGIN
 IF p_work IS NULL OR p_work !~ '^astra-bulk-v1-[0-9a-f]{64}$'
 OR p_owner IS NULL OR p_owner !~ '^[A-Za-z0-9_.:-]{1,128}$'
 OR p_fence IS NULL OR p_fence<1
 OR p_page IS NULL OR p_page NOT BETWEEN 0 AND 199
 OR p_request_sha256 IS NULL OR p_request_sha256 !~ '^[0-9a-f]{64}$'
 OR p_stage IS NULL OR jsonb_typeof(p_stage) IS DISTINCT FROM 'object'
 THEN RAISE EXCEPTION 'invalid bounded provider response quarantine identity'; END IF;
 IF NOT (p_stage ?& ARRAY[
  'source_page_sha256','stage_candidate_sha256',
  'provider_records_observed','eligible_records',
  'inclusive_end_records_excluded','eligible_bars',
  'next_page_required','continuation_token_sha256',
  'previous_continuation_token_sha256'
 ]) OR (SELECT count(*) FROM jsonb_object_keys(p_stage))<>9
 THEN RAISE EXCEPTION 'provider response candidate schema mismatch'; END IF;
 IF jsonb_typeof(p_stage->'provider_records_observed')<>'number'
 OR jsonb_typeof(p_stage->'eligible_records')<>'number'
 OR jsonb_typeof(p_stage->'inclusive_end_records_excluded')<>'number'
 OR (p_stage->>'provider_records_observed') !~ '^(0|[1-9][0-9]{0,3})$'
 OR (p_stage->>'eligible_records') !~ '^(0|[1-9][0-9]{0,3})$'
 OR (p_stage->>'inclusive_end_records_excluded') !~ '^[01]$'
 OR jsonb_typeof(p_stage->'next_page_required')<>'boolean'
 OR jsonb_typeof(p_stage->'eligible_bars')<>'array'
 THEN RAISE EXCEPTION 'provider response counts or types invalid'; END IF;
 v_observed:=(p_stage->>'provider_records_observed')::int;
 v_eligible:=(p_stage->>'eligible_records')::int;
 v_excluded:=(p_stage->>'inclusive_end_records_excluded')::int;
 v_bars:=p_stage->'eligible_bars';
 v_next:=(p_stage->>'next_page_required')::boolean;
 v_token:=p_stage->>'continuation_token_sha256';
 v_prev_token:=p_stage->>'previous_continuation_token_sha256';
 v_source:=p_stage->>'source_page_sha256';
 v_candidate:=p_stage->>'stage_candidate_sha256';
 IF v_observed>1000 OR v_eligible>1000
 OR v_eligible+v_excluded<>v_observed
 OR jsonb_array_length(v_bars)<>v_eligible
 OR v_source IS NULL OR v_source !~ '^[0-9a-f]{64}$'
 OR v_candidate IS NULL OR v_candidate !~ '^[0-9a-f]{64}$'
 OR (v_token IS NOT NULL AND v_token !~ '^[0-9a-f]{64}$')
 OR (v_prev_token IS NOT NULL AND v_prev_token !~ '^[0-9a-f]{64}$')
 OR (v_next AND (v_token IS NULL OR v_eligible=0))
 OR (NOT v_next AND v_token IS NOT NULL)
 OR (p_page=0 AND v_prev_token IS NOT NULL)
 OR (p_page>0 AND v_prev_token IS NULL)
 THEN RAISE EXCEPTION 'invalid, unbounded or unchained provider page'; END IF;
 -- Even quarantine rows must be exactly-shaped, monotone minute witnesses.
 -- This does not by itself certify source values, security identity or PIT.
 IF EXISTS (
  SELECT 1 FROM jsonb_array_elements(v_bars) WITH ORDINALITY AS b(x,ord)
  WHERE jsonb_typeof(x)<>'object'
   OR (SELECT count(*) FROM jsonb_object_keys(x))<>9
   OR NOT (x ?& ARRAY['timestamp_utc','open','high','low','close',
                         'volume','trade_count','vwap','record_sha256'])
   OR (x->>'timestamp_utc') !~ '^2026-09-(0[1-9]|[12][0-9]|30)T([01][0-9]|2[0-3]):[0-5][0-9]:00Z$'
   OR (x->>'record_sha256') !~ '^[0-9a-f]{64}$'
   OR jsonb_typeof(x->'volume')<>'number'
   OR jsonb_typeof(x->'trade_count')<>'number'
   OR (x->>'volume') !~ '^(0|[1-9][0-9]{0,18})$'
   OR (x->>'trade_count') !~ '^(0|[1-9][0-9]{0,18})$'
   OR (x->>'open') !~ '^[0-9]{1,13}(\.[0-9]{1,18})?$'
   OR (x->>'high') !~ '^[0-9]{1,13}(\.[0-9]{1,18})?$'
   OR (x->>'low') !~ '^[0-9]{1,13}(\.[0-9]{1,18})?$'
   OR (x->>'close') !~ '^[0-9]{1,13}(\.[0-9]{1,18})?$'
   OR (x->>'vwap') !~ '^[0-9]{1,13}(\.[0-9]{1,18})?$'
 ) OR EXISTS (
  SELECT 1 FROM (
   SELECT x->>'timestamp_utc' AS stamp,
          lag(x->>'timestamp_utc') OVER(ORDER BY ord) AS prior
   FROM jsonb_array_elements(v_bars) WITH ORDINALITY AS b(x,ord)
  ) seq WHERE prior IS NOT NULL AND stamp<=prior
 ) THEN RAISE EXCEPTION 'provider quarantined bar shape or minute sequence invalid'; END IF;

 -- Lock ordering must match stop/claim paths: manifest then work.
 SELECT manifest_sha256 INTO v_manifest
 FROM astra_ingestion_v1.bulk_work_v1 WHERE work_key=p_work;
 IF NOT FOUND THEN RAISE EXCEPTION 'unknown provider response work'; END IF;
 SELECT * INTO m FROM astra_ingestion_v1.bulk_manifest_v1
 WHERE manifest_sha256=v_manifest FOR SHARE;
 IF NOT FOUND OR m.stopped
 OR m.capture_key IS DISTINCT FROM 'top3000-augsep2026-retained-scope-v1'
 OR m.capture_receipt_sha256 IS DISTINCT FROM 'ba13899b530288b6aae8d4af3a429efa3f4bd5ec305a7dc698f98c9d552f4496'
 THEN RAISE EXCEPTION 'provider response manifest stopped or changed'; END IF;
 SELECT * INTO w FROM astra_ingestion_v1.bulk_work_v1
 WHERE work_key=p_work FOR UPDATE;
 IF NOT FOUND OR w.manifest_sha256 IS DISTINCT FROM v_manifest
 OR w.mode IS DISTINCT FROM 'provider_acquisition'
 OR w.family NOT IN ('P01','P02')
 OR w.status IS DISTINCT FROM 'claimed'
 OR w.claim_owner IS DISTINCT FROM p_owner OR w.claim_fence IS DISTINCT FROM p_fence
 OR w.claim_until IS NULL OR w.claim_until<=clock_timestamp()
 OR w.original_deadline<=clock_timestamp()
 OR w.attempts NOT BETWEEN 1 AND 2
 OR w.last_page+1 IS DISTINCT FROM p_page
 OR w.requests_committed+1>w.max_requests
 OR GREATEST(w.records_committed,COALESCE((
    SELECT sum(q.provider_records_observed)
    FROM astra_ingestion_v1.bulk_provider_response_quarantine_v1 q
    JOIN astra_ingestion_v1.bulk_receipt_v1 br
      ON br.work_key=q.work_key AND br.page_no=q.page_no
    WHERE q.work_key=p_work AND q.page_no<p_page
   ),0)) + v_observed > w.max_records
 THEN RAISE EXCEPTION 'provider stage refused: stale claim, deadline, stop or cumulative budget'; END IF;
 SELECT * INTO t FROM astra_ingestion_v1.bulk_provider_precall_v1
 WHERE work_key=p_work AND page_no=p_page FOR SHARE;
 IF NOT FOUND OR t.manifest_sha256 IS DISTINCT FROM v_manifest
 OR t.family IS DISTINCT FROM w.family
 OR t.source_receipt_sha256 IS DISTINCT FROM w.source_receipt_sha256
 OR t.request_sha256 IS DISTINCT FROM p_request_sha256
 OR t.owner IS DISTINCT FROM p_owner OR t.fence IS DISTINCT FROM p_fence
 OR t.original_deadline IS DISTINCT FROM w.original_deadline
 OR t.records_reserved < v_observed OR t.reserved_at>clock_timestamp()
 THEN RAISE EXCEPTION 'original immutable provider pre-call ticket not matched'; END IF;
 -- Both distinct real review and pinned exact request must still exist.
 SELECT * INTO a FROM astra_ingestion_v1.bulk_manifest_review_v1
 WHERE manifest_sha256=v_manifest;
 IF NOT FOUND OR a.family_count IS DISTINCT FROM 24
 OR NOT EXISTS (
  SELECT 1 FROM astra_ingestion_v1.bulk_provider_review_v1 r
  WHERE r.manifest_sha256=v_manifest
  AND r.independent_report_sha256=a.independent_report_sha256
 ) OR NOT EXISTS (
  SELECT 1 FROM astra_ingestion_v1.bulk_provider_reviewed_request_v1 q
  WHERE q.work_key=p_work AND q.page_no=p_page
  AND q.manifest_sha256=v_manifest
  AND q.independent_report_sha256=a.independent_report_sha256
  AND q.request_sha256=p_request_sha256
  AND q.source_receipt_sha256=w.source_receipt_sha256
  AND q.records_reserved=t.records_reserved
 ) THEN RAISE EXCEPTION 'independent request/manifest review drifted'; END IF;
 IF EXISTS (
  SELECT 1 FROM astra_ingestion_v1.bulk_receipt_v1
  WHERE work_key=p_work AND page_no=p_page
 ) THEN RAISE EXCEPTION 'already committed provider receipt; reconcile, no replay'; END IF;
 IF p_page>0 THEN
  SELECT * INTO prev FROM astra_ingestion_v1.bulk_provider_response_quarantine_v1
  WHERE work_key=p_work AND page_no=p_page-1;
  IF NOT FOUND OR prev.next_page_required IS DISTINCT FROM true
  OR prev.continuation_token_sha256 IS DISTINCT FROM v_prev_token
  OR NOT EXISTS (
   SELECT 1 FROM astra_ingestion_v1.bulk_receipt_v1
   WHERE work_key=p_work AND page_no=p_page-1 AND requests_committed=1
  ) THEN RAISE EXCEPTION 'provider continuation has no committed predecessor chain'; END IF;
 END IF;
 v_digest:=encode(sha256(convert_to(v_bars::text,'UTF8')),'hex');
 INSERT INTO astra_ingestion_v1.bulk_provider_response_quarantine_v1(
  work_key,page_no,manifest_sha256,family,original_deadline,request_sha256,
  source_page_sha256,stage_candidate_sha256,claim_owner,claim_fence,
  provider_records_observed,eligible_records,inclusive_end_records_excluded,
  eligible_bars,eligible_bars_sha256,next_page_required,
  continuation_token_sha256,previous_continuation_token_sha256)
 VALUES(p_work,p_page,v_manifest,w.family,w.original_deadline,p_request_sha256,
        v_source,v_candidate,p_owner,p_fence,
        v_observed,v_eligible,v_excluded,v_bars,v_digest,v_next,v_token,v_prev_token);
 -- Stage and hash are atomic and immutable, while all bulk output/counters
 -- remain uncommitted. The pre-call ticket and uncertainty ban are preserved.
 SELECT jsonb_build_object(
  'status','QUARANTINED_UNAUTHENTICATED_NOT_BULK_COMMITTED',
  'work_key',p_work,'page_no',p_page,'manifest_sha256',v_manifest,
  'request_sha256',p_request_sha256,
  'source_page_sha256',v_source,'stage_candidate_sha256',v_candidate,
  'eligible_bars_sha256',v_digest,
  'provider_records_observed',v_observed,'eligible_records',v_eligible,
  'original_deadline',w.original_deadline,
  'provider_submission_authorized',false,
  'bulk_output_committed',false,
  'coverage_certified',false) INTO v_receipt;
 RETURN v_receipt;
END $$;

-- Reconcile an uncertain DB stage without returning any licensed row contents.
-- No write, no resubmission and no authentication claim.
CREATE FUNCTION astra_ingestion_v1.bulk_provider_quarantine_readback_v1(
 p_work text,p_page int)
RETURNS jsonb LANGUAGE sql SECURITY INVOKER
SET search_path=pg_catalog SET timezone='UTC' AS $$
 SELECT jsonb_build_object(
  'status',s.status,'work_key',s.work_key,'page_no',s.page_no,
  'request_sha256',s.request_sha256,
  'source_page_sha256',s.source_page_sha256,
  'stage_candidate_sha256',s.stage_candidate_sha256,
  'eligible_bars_sha256',s.eligible_bars_sha256,
  'eligible_records',s.eligible_records,
  'provider_records_observed',s.provider_records_observed,
  'consistent',(s.eligible_bars_sha256=
    encode(sha256(convert_to(s.eligible_bars::text,'UTF8')),'hex')),
  'bulk_output_committed',false)
 FROM astra_ingestion_v1.bulk_provider_response_quarantine_v1 s
 WHERE s.work_key=p_work AND s.page_no=p_page
$$;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_provider_quarantine_response_v1(text,text,bigint,int,text,jsonb) FROM PUBLIC;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_provider_quarantine_readback_v1(text,int) FROM PUBLIC;
COMMIT;
