-- ASTRA P01/P02 finite pre-call durable reservation; STAGED SOURCE ONLY.
-- Prerequisites: ledger, complete 24-family review and exact-unit binding.
-- No production migration, public grants, provider transport or authorization
-- to issue requests. Genuine external reviewer/HTTPS identity and hosted
-- recovery gates must be separately proved before any production installation.
-- Each reservation permanently burns its page key: uncertain provider effects
-- are NOT retried with a new idempotency key or a replacement owner.
BEGIN;
CREATE TABLE astra_ingestion_v1.bulk_provider_review_v1 (
 manifest_sha256 text PRIMARY KEY REFERENCES astra_ingestion_v1.bulk_manifest_v1(manifest_sha256),
 independent_report_sha256 text NOT NULL CHECK (independent_report_sha256 ~ '^[0-9a-f]{64}$'),
 identity_assurance_sha256 text NOT NULL CHECK (identity_assurance_sha256 ~ '^[0-9a-f]{64}$'),
 entitlement_assurance_sha256 text NOT NULL CHECK (entitlement_assurance_sha256 ~ '^[0-9a-f]{64}$'),
 recorded_by name NOT NULL DEFAULT current_user,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 status text NOT NULL DEFAULT 'PROVIDER_SOURCE_REVIEW_REQUIRES_AUTHENTICATED_TRANSPORT'
 CHECK(status='PROVIDER_SOURCE_REVIEW_REQUIRES_AUTHENTICATED_TRANSPORT')
);
-- Exact provider request shape must itself be externally reviewed; a
-- caller-chosen 64-hex hash is not proof of an allowable symbol/session.
-- Continuation requests need a NEW independently bound row derived from the
-- prior immutable page receipt, not a modified original reservation.
CREATE TABLE astra_ingestion_v1.bulk_provider_reviewed_request_v1 (
 work_key text NOT NULL REFERENCES astra_ingestion_v1.bulk_work_v1(work_key),
 page_no integer NOT NULL CHECK(page_no BETWEEN 0 AND 199),
 manifest_sha256 text NOT NULL,
 family text NOT NULL CHECK(family IN ('P01','P02')),
 source_receipt_sha256 text NOT NULL CHECK(source_receipt_sha256 ~ '^[0-9a-f]{64}$'),
 independent_report_sha256 text NOT NULL CHECK(independent_report_sha256 ~ '^[0-9a-f]{64}$'),
 request_sha256 text NOT NULL CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
 records_reserved integer NOT NULL CHECK(records_reserved BETWEEN 1 AND 1000),
 recorded_by name NOT NULL DEFAULT current_user,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(work_key,page_no)
);
CREATE TABLE astra_ingestion_v1.bulk_provider_precall_v1 (
 work_key text NOT NULL REFERENCES astra_ingestion_v1.bulk_work_v1(work_key),
 page_no integer NOT NULL CHECK(page_no BETWEEN 0 AND 199),
 manifest_sha256 text NOT NULL,
 family text NOT NULL CHECK(family IN ('P01','P02')),
 source_receipt_sha256 text NOT NULL CHECK(source_receipt_sha256 ~ '^[0-9a-f]{64}$'),
 request_sha256 text NOT NULL CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
 owner text NOT NULL CHECK(owner ~ '^[A-Za-z0-9_.:-]{1,128}$'),
 fence bigint NOT NULL CHECK(fence>=1),
 records_reserved integer NOT NULL CHECK(records_reserved BETWEEN 1 AND 1000),
 original_deadline timestamptz NOT NULL,
 reserved_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(work_key,page_no),
 CHECK(original_deadline > reserved_at)
);
CREATE TRIGGER bulk_provider_review_immutable_v1
 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.bulk_provider_review_v1
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.bulk_review_immutable_v1();
CREATE TRIGGER bulk_provider_request_immutable_v1
 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.bulk_provider_reviewed_request_v1
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.bulk_review_immutable_v1();
CREATE TRIGGER bulk_provider_precall_immutable_v1
 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.bulk_provider_precall_v1
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.bulk_review_immutable_v1();
ALTER TABLE astra_ingestion_v1.bulk_provider_review_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE astra_ingestion_v1.bulk_provider_precall_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE astra_ingestion_v1.bulk_provider_reviewed_request_v1 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON astra_ingestion_v1.bulk_provider_review_v1,
 astra_ingestion_v1.bulk_provider_reviewed_request_v1,
 astra_ingestion_v1.bulk_provider_precall_v1 FROM PUBLIC;

-- Reviewer-authored records require separate principal qualification.
-- This is an engineering admission predicate, NOT evidence of genuine
-- independent review merely because a synthetic row exists.
CREATE FUNCTION astra_ingestion_v1.bulk_provider_precall_reserve_v1(
 p_work text,p_owner text,p_fence bigint,p_page integer,
 p_request_sha256 text,p_records_reserved integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
SET search_path=pg_catalog SET timezone='UTC' AS $$
DECLARE v_manifest text; m record; w record; a record; r record; u record;
        n integer; v_inflight integer; v_receipt jsonb;
BEGIN
 IF p_work IS NULL OR p_work !~ '^astra-bulk-v1-[0-9a-f]{64}$'
 OR p_owner IS NULL OR p_owner !~ '^[A-Za-z0-9_.:-]{1,128}$'
 OR p_fence IS NULL OR p_fence < 1
 OR p_page IS NULL OR p_page NOT BETWEEN 0 AND 199
 OR p_request_sha256 IS NULL OR p_request_sha256 !~ '^[0-9a-f]{64}$'
 OR p_records_reserved IS NULL OR p_records_reserved NOT BETWEEN 1 AND 1000
 THEN RAISE EXCEPTION 'invalid immutable provider pre-call reservation'; END IF;
 SELECT manifest_sha256 INTO v_manifest
 FROM astra_ingestion_v1.bulk_work_v1 WHERE work_key=p_work;
 IF NOT FOUND THEN RAISE EXCEPTION 'unknown provider work'; END IF;
 -- Lock order is manifest -> work. Serialize stops, new work and claims.
 SELECT * INTO m FROM astra_ingestion_v1.bulk_manifest_v1
 WHERE manifest_sha256=v_manifest FOR SHARE;
 IF NOT FOUND OR m.stopped
 OR m.capture_key IS DISTINCT FROM 'top3000-augsep2026-retained-scope-v1'
 OR m.capture_receipt_sha256 IS DISTINCT FROM 'ba13899b530288b6aae8d4af3a429efa3f4bd5ec305a7dc698f98c9d552f4496'
 THEN RAISE EXCEPTION 'provider manifest absent, stopped or wrong capture'; END IF;
 SELECT * INTO w FROM astra_ingestion_v1.bulk_work_v1
 WHERE work_key=p_work FOR UPDATE;
 IF NOT FOUND OR w.manifest_sha256 IS DISTINCT FROM v_manifest
 OR w.family NOT IN ('P01','P02') OR w.mode <> 'provider_acquisition'
 OR w.status <> 'claimed' OR w.claim_owner IS DISTINCT FROM p_owner
 OR w.claim_fence IS DISTINCT FROM p_fence OR w.claim_until IS NULL
 OR w.claim_until <= clock_timestamp() OR w.original_deadline <= clock_timestamp()
 OR w.attempts NOT BETWEEN 1 AND 2 OR w.last_page+1 IS DISTINCT FROM p_page
 OR w.requests_committed+1 > w.max_requests
 OR w.records_committed+p_records_reserved > w.max_records
 OR w.source_receipt_sha256 !~ '^[0-9a-f]{64}$'
 THEN RAISE EXCEPTION 'provider request denied by claim, stop, deadline, budget or sequence'; END IF;
 -- Entire reviewed family population and exact security unit MUST be sealed.
 SELECT * INTO a FROM astra_ingestion_v1.bulk_manifest_review_v1
 WHERE manifest_sha256=v_manifest;
 SELECT * INTO r FROM astra_ingestion_v1.bulk_provider_review_v1
 WHERE manifest_sha256=v_manifest;
 IF a.manifest_sha256 IS NULL OR r.manifest_sha256 IS NULL
 OR a.family_count IS DISTINCT FROM 24
 OR r.independent_report_sha256 IS DISTINCT FROM a.independent_report_sha256
 THEN RAISE EXCEPTION 'distinct provider acquisition review absent'; END IF;
 SELECT count(*) INTO n
 FROM astra_ingestion_v1.bulk_family_review_v1 f
 JOIN astra_ingestion_v1.bulk_unit_seal_v1 s
 ON s.manifest_sha256=f.manifest_sha256 AND s.family=f.family
 AND s.expected_manifest_sha256=f.expected_manifest_sha256
 AND s.unit_count=f.expected_units
 AND s.independent_report_sha256=f.independent_report_sha256
 JOIN astra_ingestion_v1.bulk_scope_evidence_v1 e
 ON e.capture_key=m.capture_key AND e.kind='contract'
 AND e.evidence_key=f.family AND e.source_sha256=f.contract_sha256
 WHERE f.manifest_sha256=v_manifest
 AND f.independent_report_sha256=a.independent_report_sha256
 AND f.expected_units=f.observed_units;
 IF n<>24 THEN RAISE EXCEPTION 'complete 24-family source-backed review absent'; END IF;
 -- One unreviewed reserved unit invalidates admission for the ENTIRE manifest.
 IF EXISTS (
  SELECT 1 FROM astra_ingestion_v1.bulk_work_v1 x
  LEFT JOIN astra_ingestion_v1.bulk_reviewed_unit_v1 y
  ON y.manifest_sha256=x.manifest_sha256 AND y.family=x.family
  AND y.unit_key=x.unit_key AND y.source_receipt_sha256=x.source_receipt_sha256
  AND y.independent_report_sha256=a.independent_report_sha256
  WHERE x.manifest_sha256=v_manifest AND y.unit_key IS NULL
 ) THEN RAISE EXCEPTION 'manifest contains unreviewed source work'; END IF;
 IF NOT EXISTS (
  SELECT 1 FROM astra_ingestion_v1.bulk_provider_reviewed_request_v1 q
  WHERE q.work_key=p_work AND q.page_no=p_page
  AND q.manifest_sha256=v_manifest AND q.family=w.family
  AND q.source_receipt_sha256=w.source_receipt_sha256
  AND q.independent_report_sha256=a.independent_report_sha256
  AND q.request_sha256=p_request_sha256 AND q.records_reserved=p_records_reserved
 ) THEN RAISE EXCEPTION 'independently pinned exact provider request missing or mismatched'; END IF;
 SELECT * INTO u FROM astra_ingestion_v1.bulk_reviewed_unit_v1
 WHERE manifest_sha256=v_manifest AND family=w.family
 AND unit_key=w.unit_key AND source_receipt_sha256=w.source_receipt_sha256
 AND independent_report_sha256=a.independent_report_sha256;
 IF NOT FOUND THEN RAISE EXCEPTION 'unreviewed exact provider work unit'; END IF;
 -- Never issue two concurrent or replacement calls for an uncertain page.
 -- A request may have reached the provider even when no receipt exists.
 SELECT count(*) INTO v_inflight FROM astra_ingestion_v1.bulk_provider_precall_v1
 WHERE work_key=p_work AND page_no>=p_page;
 IF v_inflight<>0 OR EXISTS(
   SELECT 1 FROM astra_ingestion_v1.bulk_receipt_v1
   WHERE work_key=p_work AND page_no=p_page
 ) THEN RAISE EXCEPTION 'provider page already reserved or committed: reconcile, do not refetch'; END IF;
 IF p_page>0 AND NOT EXISTS (
   SELECT 1 FROM astra_ingestion_v1.bulk_receipt_v1
   WHERE work_key=p_work AND page_no=p_page-1 AND requests_committed=1
 ) THEN RAISE EXCEPTION 'provider continuation lacks previous committed receipt'; END IF;
 INSERT INTO astra_ingestion_v1.bulk_provider_precall_v1(
   work_key,page_no,manifest_sha256,family,source_receipt_sha256,
   request_sha256,owner,fence,records_reserved,original_deadline)
 VALUES(p_work,p_page,v_manifest,w.family,w.source_receipt_sha256,
        p_request_sha256,p_owner,p_fence,p_records_reserved,w.original_deadline);
 -- This is a durable accounting marker, NOT permission to transmit.
 SELECT jsonb_build_object(
   'status','RESERVED_NO_PROVIDER_TRANSPORT_GRANT',
   'work_key',p_work,'page_no',p_page,'manifest_sha256',v_manifest,
   'family',w.family,'claim_fence',p_fence,
   'request_sha256',p_request_sha256,
   'records_reserved',p_records_reserved,
   'original_deadline',w.original_deadline,
   'provider_submission_authorized',false)
 INTO v_receipt;
 RETURN v_receipt;
END $$;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_provider_precall_reserve_v1(text,text,bigint,int,text,int)
 FROM PUBLIC;
COMMIT;
),
 independent_report_sha256 text NOT NULL CHECK(independent_report_sha256 ~ '^[0-9a-f]{64}
 work_key text NOT NULL REFERENCES astra_ingestion_v1.bulk_work_v1(work_key),
 page_no integer NOT NULL CHECK (page_no BETWEEN 0 AND 199),
 manifest_sha256 text NOT NULL,
 family text NOT NULL CHECK(family IN ('P01','P02')),
 source_receipt_sha256 text NOT NULL CHECK(source_receipt_sha256 ~ '^[0-9a-f]{64}$'),
 request_sha256 text NOT NULL CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
 owner text NOT NULL CHECK(owner ~ '^[A-Za-z0-9_.:-]{1,128}$'),
 fence bigint NOT NULL CHECK(fence>=1),
 records_reserved integer NOT NULL CHECK(records_reserved BETWEEN 1 AND 1000),
 original_deadline timestamptz NOT NULL,
 reserved_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(work_key,page_no),
 CHECK(original_deadline > reserved_at)
);
CREATE TRIGGER bulk_provider_review_immutable_v1
 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.bulk_provider_review_v1
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.bulk_review_immutable_v1();
CREATE TRIGGER bulk_provider_precall_immutable_v1
 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.bulk_provider_precall_v1
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.bulk_review_immutable_v1();
ALTER TABLE astra_ingestion_v1.bulk_provider_review_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE astra_ingestion_v1.bulk_provider_precall_v1 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON astra_ingestion_v1.bulk_provider_review_v1,
 astra_ingestion_v1.bulk_provider_precall_v1 FROM PUBLIC;

-- Reviewer-authored records require separate principal qualification.
-- This is an engineering admission predicate, NOT evidence of genuine
-- independent review merely because a synthetic row exists.
CREATE FUNCTION astra_ingestion_v1.bulk_provider_precall_reserve_v1(
 p_work text,p_owner text,p_fence bigint,p_page integer,
 p_request_sha256 text,p_records_reserved integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
SET search_path=pg_catalog SET timezone='UTC' AS $$
DECLARE v_manifest text; m record; w record; a record; r record; u record;
        n integer; v_inflight integer; v_receipt jsonb;
BEGIN
 IF p_work IS NULL OR p_work !~ '^astra-bulk-v1-[0-9a-f]{64}$'
 OR p_owner IS NULL OR p_owner !~ '^[A-Za-z0-9_.:-]{1,128}$'
 OR p_fence IS NULL OR p_fence < 1
 OR p_page IS NULL OR p_page NOT BETWEEN 0 AND 199
 OR p_request_sha256 IS NULL OR p_request_sha256 !~ '^[0-9a-f]{64}$'
 OR p_records_reserved IS NULL OR p_records_reserved NOT BETWEEN 1 AND 1000
 THEN RAISE EXCEPTION 'invalid immutable provider pre-call reservation'; END IF;
 SELECT manifest_sha256 INTO v_manifest
 FROM astra_ingestion_v1.bulk_work_v1 WHERE work_key=p_work;
 IF NOT FOUND THEN RAISE EXCEPTION 'unknown provider work'; END IF;
 -- Lock order is manifest -> work. Serialize stops, new work and claims.
 SELECT * INTO m FROM astra_ingestion_v1.bulk_manifest_v1
 WHERE manifest_sha256=v_manifest FOR SHARE;
 IF NOT FOUND OR m.stopped
 OR m.capture_key IS DISTINCT FROM 'top3000-augsep2026-retained-scope-v1'
 OR m.capture_receipt_sha256 IS DISTINCT FROM 'ba13899b530288b6aae8d4af3a429efa3f4bd5ec305a7dc698f98c9d552f4496'
 THEN RAISE EXCEPTION 'provider manifest absent, stopped or wrong capture'; END IF;
 SELECT * INTO w FROM astra_ingestion_v1.bulk_work_v1
 WHERE work_key=p_work FOR UPDATE;
 IF NOT FOUND OR w.manifest_sha256 IS DISTINCT FROM v_manifest
 OR w.family NOT IN ('P01','P02') OR w.mode <> 'provider_acquisition'
 OR w.status <> 'claimed' OR w.claim_owner IS DISTINCT FROM p_owner
 OR w.claim_fence IS DISTINCT FROM p_fence OR w.claim_until IS NULL
 OR w.claim_until <= clock_timestamp() OR w.original_deadline <= clock_timestamp()
 OR w.attempts NOT BETWEEN 1 AND 2 OR w.last_page+1 IS DISTINCT FROM p_page
 OR w.requests_committed+1 > w.max_requests
 OR w.records_committed+p_records_reserved > w.max_records
 OR w.source_receipt_sha256 !~ '^[0-9a-f]{64}$'
 THEN RAISE EXCEPTION 'provider request denied by claim, stop, deadline, budget or sequence'; END IF;
 -- Entire reviewed family population and exact security unit MUST be sealed.
 SELECT * INTO a FROM astra_ingestion_v1.bulk_manifest_review_v1
 WHERE manifest_sha256=v_manifest;
 SELECT * INTO r FROM astra_ingestion_v1.bulk_provider_review_v1
 WHERE manifest_sha256=v_manifest;
 IF a.manifest_sha256 IS NULL OR r.manifest_sha256 IS NULL
 OR a.family_count IS DISTINCT FROM 24
 OR r.independent_report_sha256 IS DISTINCT FROM a.independent_report_sha256
 THEN RAISE EXCEPTION 'distinct provider acquisition review absent'; END IF;
 SELECT count(*) INTO n
 FROM astra_ingestion_v1.bulk_family_review_v1 f
 JOIN astra_ingestion_v1.bulk_unit_seal_v1 s
 ON s.manifest_sha256=f.manifest_sha256 AND s.family=f.family
 AND s.expected_manifest_sha256=f.expected_manifest_sha256
 AND s.unit_count=f.expected_units
 AND s.independent_report_sha256=f.independent_report_sha256
 JOIN astra_ingestion_v1.bulk_scope_evidence_v1 e
 ON e.capture_key=m.capture_key AND e.kind='contract'
 AND e.evidence_key=f.family AND e.source_sha256=f.contract_sha256
 WHERE f.manifest_sha256=v_manifest
 AND f.independent_report_sha256=a.independent_report_sha256
 AND f.expected_units=f.observed_units;
 IF n<>24 THEN RAISE EXCEPTION 'complete 24-family source-backed review absent'; END IF;
 -- One unreviewed reserved unit invalidates admission for the ENTIRE manifest.
 IF EXISTS (
  SELECT 1 FROM astra_ingestion_v1.bulk_work_v1 x
  LEFT JOIN astra_ingestion_v1.bulk_reviewed_unit_v1 y
  ON y.manifest_sha256=x.manifest_sha256 AND y.family=x.family
  AND y.unit_key=x.unit_key AND y.source_receipt_sha256=x.source_receipt_sha256
  AND y.independent_report_sha256=a.independent_report_sha256
  WHERE x.manifest_sha256=v_manifest AND y.unit_key IS NULL
 ) THEN RAISE EXCEPTION 'manifest contains unreviewed source work'; END IF;
 SELECT * INTO u FROM astra_ingestion_v1.bulk_reviewed_unit_v1
 WHERE manifest_sha256=v_manifest AND family=w.family
 AND unit_key=w.unit_key AND source_receipt_sha256=w.source_receipt_sha256
 AND independent_report_sha256=a.independent_report_sha256;
 IF NOT FOUND THEN RAISE EXCEPTION 'unreviewed exact provider work unit'; END IF;
 -- Never issue two concurrent or replacement calls for an uncertain page.
 -- A request may have reached the provider even when no receipt exists.
 SELECT count(*) INTO v_inflight FROM astra_ingestion_v1.bulk_provider_precall_v1
 WHERE work_key=p_work AND page_no>=p_page;
 IF v_inflight<>0 OR EXISTS(
   SELECT 1 FROM astra_ingestion_v1.bulk_receipt_v1
   WHERE work_key=p_work AND page_no=p_page
 ) THEN RAISE EXCEPTION 'provider page already reserved or committed: reconcile, do not refetch'; END IF;
 IF p_page>0 AND NOT EXISTS (
   SELECT 1 FROM astra_ingestion_v1.bulk_receipt_v1
   WHERE work_key=p_work AND page_no=p_page-1 AND requests_committed=1
 ) THEN RAISE EXCEPTION 'provider continuation lacks previous committed receipt'; END IF;
 INSERT INTO astra_ingestion_v1.bulk_provider_precall_v1(
   work_key,page_no,manifest_sha256,family,source_receipt_sha256,
   request_sha256,owner,fence,records_reserved,original_deadline)
 VALUES(p_work,p_page,v_manifest,w.family,w.source_receipt_sha256,
        p_request_sha256,p_owner,p_fence,p_records_reserved,w.original_deadline);
 -- This is a durable accounting marker, NOT permission to transmit.
 SELECT jsonb_build_object(
   'status','RESERVED_NO_PROVIDER_TRANSPORT_GRANT',
   'work_key',p_work,'page_no',p_page,'manifest_sha256',v_manifest,
   'family',w.family,'claim_fence',p_fence,
   'request_sha256',p_request_sha256,
   'records_reserved',p_records_reserved,
   'original_deadline',w.original_deadline,
   'provider_submission_authorized',false)
 INTO v_receipt;
 RETURN v_receipt;
END $$;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_provider_precall_reserve_v1(text,text,bigint,int,text,int)
 FROM PUBLIC;
COMMIT;
),
 request_sha256 text NOT NULL CHECK(request_sha256 ~ '^[0-9a-f]{64}
 work_key text NOT NULL REFERENCES astra_ingestion_v1.bulk_work_v1(work_key),
 page_no integer NOT NULL CHECK (page_no BETWEEN 0 AND 199),
 manifest_sha256 text NOT NULL,
 family text NOT NULL CHECK(family IN ('P01','P02')),
 source_receipt_sha256 text NOT NULL CHECK(source_receipt_sha256 ~ '^[0-9a-f]{64}$'),
 request_sha256 text NOT NULL CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
 owner text NOT NULL CHECK(owner ~ '^[A-Za-z0-9_.:-]{1,128}$'),
 fence bigint NOT NULL CHECK(fence>=1),
 records_reserved integer NOT NULL CHECK(records_reserved BETWEEN 1 AND 1000),
 original_deadline timestamptz NOT NULL,
 reserved_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(work_key,page_no),
 CHECK(original_deadline > reserved_at)
);
CREATE TRIGGER bulk_provider_review_immutable_v1
 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.bulk_provider_review_v1
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.bulk_review_immutable_v1();
CREATE TRIGGER bulk_provider_precall_immutable_v1
 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.bulk_provider_precall_v1
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.bulk_review_immutable_v1();
ALTER TABLE astra_ingestion_v1.bulk_provider_review_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE astra_ingestion_v1.bulk_provider_precall_v1 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON astra_ingestion_v1.bulk_provider_review_v1,
 astra_ingestion_v1.bulk_provider_precall_v1 FROM PUBLIC;

-- Reviewer-authored records require separate principal qualification.
-- This is an engineering admission predicate, NOT evidence of genuine
-- independent review merely because a synthetic row exists.
CREATE FUNCTION astra_ingestion_v1.bulk_provider_precall_reserve_v1(
 p_work text,p_owner text,p_fence bigint,p_page integer,
 p_request_sha256 text,p_records_reserved integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
SET search_path=pg_catalog SET timezone='UTC' AS $$
DECLARE v_manifest text; m record; w record; a record; r record; u record;
        n integer; v_inflight integer; v_receipt jsonb;
BEGIN
 IF p_work IS NULL OR p_work !~ '^astra-bulk-v1-[0-9a-f]{64}$'
 OR p_owner IS NULL OR p_owner !~ '^[A-Za-z0-9_.:-]{1,128}$'
 OR p_fence IS NULL OR p_fence < 1
 OR p_page IS NULL OR p_page NOT BETWEEN 0 AND 199
 OR p_request_sha256 IS NULL OR p_request_sha256 !~ '^[0-9a-f]{64}$'
 OR p_records_reserved IS NULL OR p_records_reserved NOT BETWEEN 1 AND 1000
 THEN RAISE EXCEPTION 'invalid immutable provider pre-call reservation'; END IF;
 SELECT manifest_sha256 INTO v_manifest
 FROM astra_ingestion_v1.bulk_work_v1 WHERE work_key=p_work;
 IF NOT FOUND THEN RAISE EXCEPTION 'unknown provider work'; END IF;
 -- Lock order is manifest -> work. Serialize stops, new work and claims.
 SELECT * INTO m FROM astra_ingestion_v1.bulk_manifest_v1
 WHERE manifest_sha256=v_manifest FOR SHARE;
 IF NOT FOUND OR m.stopped
 OR m.capture_key IS DISTINCT FROM 'top3000-augsep2026-retained-scope-v1'
 OR m.capture_receipt_sha256 IS DISTINCT FROM 'ba13899b530288b6aae8d4af3a429efa3f4bd5ec305a7dc698f98c9d552f4496'
 THEN RAISE EXCEPTION 'provider manifest absent, stopped or wrong capture'; END IF;
 SELECT * INTO w FROM astra_ingestion_v1.bulk_work_v1
 WHERE work_key=p_work FOR UPDATE;
 IF NOT FOUND OR w.manifest_sha256 IS DISTINCT FROM v_manifest
 OR w.family NOT IN ('P01','P02') OR w.mode <> 'provider_acquisition'
 OR w.status <> 'claimed' OR w.claim_owner IS DISTINCT FROM p_owner
 OR w.claim_fence IS DISTINCT FROM p_fence OR w.claim_until IS NULL
 OR w.claim_until <= clock_timestamp() OR w.original_deadline <= clock_timestamp()
 OR w.attempts NOT BETWEEN 1 AND 2 OR w.last_page+1 IS DISTINCT FROM p_page
 OR w.requests_committed+1 > w.max_requests
 OR w.records_committed+p_records_reserved > w.max_records
 OR w.source_receipt_sha256 !~ '^[0-9a-f]{64}$'
 THEN RAISE EXCEPTION 'provider request denied by claim, stop, deadline, budget or sequence'; END IF;
 -- Entire reviewed family population and exact security unit MUST be sealed.
 SELECT * INTO a FROM astra_ingestion_v1.bulk_manifest_review_v1
 WHERE manifest_sha256=v_manifest;
 SELECT * INTO r FROM astra_ingestion_v1.bulk_provider_review_v1
 WHERE manifest_sha256=v_manifest;
 IF a.manifest_sha256 IS NULL OR r.manifest_sha256 IS NULL
 OR a.family_count IS DISTINCT FROM 24
 OR r.independent_report_sha256 IS DISTINCT FROM a.independent_report_sha256
 THEN RAISE EXCEPTION 'distinct provider acquisition review absent'; END IF;
 SELECT count(*) INTO n
 FROM astra_ingestion_v1.bulk_family_review_v1 f
 JOIN astra_ingestion_v1.bulk_unit_seal_v1 s
 ON s.manifest_sha256=f.manifest_sha256 AND s.family=f.family
 AND s.expected_manifest_sha256=f.expected_manifest_sha256
 AND s.unit_count=f.expected_units
 AND s.independent_report_sha256=f.independent_report_sha256
 JOIN astra_ingestion_v1.bulk_scope_evidence_v1 e
 ON e.capture_key=m.capture_key AND e.kind='contract'
 AND e.evidence_key=f.family AND e.source_sha256=f.contract_sha256
 WHERE f.manifest_sha256=v_manifest
 AND f.independent_report_sha256=a.independent_report_sha256
 AND f.expected_units=f.observed_units;
 IF n<>24 THEN RAISE EXCEPTION 'complete 24-family source-backed review absent'; END IF;
 -- One unreviewed reserved unit invalidates admission for the ENTIRE manifest.
 IF EXISTS (
  SELECT 1 FROM astra_ingestion_v1.bulk_work_v1 x
  LEFT JOIN astra_ingestion_v1.bulk_reviewed_unit_v1 y
  ON y.manifest_sha256=x.manifest_sha256 AND y.family=x.family
  AND y.unit_key=x.unit_key AND y.source_receipt_sha256=x.source_receipt_sha256
  AND y.independent_report_sha256=a.independent_report_sha256
  WHERE x.manifest_sha256=v_manifest AND y.unit_key IS NULL
 ) THEN RAISE EXCEPTION 'manifest contains unreviewed source work'; END IF;
 SELECT * INTO u FROM astra_ingestion_v1.bulk_reviewed_unit_v1
 WHERE manifest_sha256=v_manifest AND family=w.family
 AND unit_key=w.unit_key AND source_receipt_sha256=w.source_receipt_sha256
 AND independent_report_sha256=a.independent_report_sha256;
 IF NOT FOUND THEN RAISE EXCEPTION 'unreviewed exact provider work unit'; END IF;
 -- Never issue two concurrent or replacement calls for an uncertain page.
 -- A request may have reached the provider even when no receipt exists.
 SELECT count(*) INTO v_inflight FROM astra_ingestion_v1.bulk_provider_precall_v1
 WHERE work_key=p_work AND page_no>=p_page;
 IF v_inflight<>0 OR EXISTS(
   SELECT 1 FROM astra_ingestion_v1.bulk_receipt_v1
   WHERE work_key=p_work AND page_no=p_page
 ) THEN RAISE EXCEPTION 'provider page already reserved or committed: reconcile, do not refetch'; END IF;
 IF p_page>0 AND NOT EXISTS (
   SELECT 1 FROM astra_ingestion_v1.bulk_receipt_v1
   WHERE work_key=p_work AND page_no=p_page-1 AND requests_committed=1
 ) THEN RAISE EXCEPTION 'provider continuation lacks previous committed receipt'; END IF;
 INSERT INTO astra_ingestion_v1.bulk_provider_precall_v1(
   work_key,page_no,manifest_sha256,family,source_receipt_sha256,
   request_sha256,owner,fence,records_reserved,original_deadline)
 VALUES(p_work,p_page,v_manifest,w.family,w.source_receipt_sha256,
        p_request_sha256,p_owner,p_fence,p_records_reserved,w.original_deadline);
 -- This is a durable accounting marker, NOT permission to transmit.
 SELECT jsonb_build_object(
   'status','RESERVED_NO_PROVIDER_TRANSPORT_GRANT',
   'work_key',p_work,'page_no',p_page,'manifest_sha256',v_manifest,
   'family',w.family,'claim_fence',p_fence,
   'request_sha256',p_request_sha256,
   'records_reserved',p_records_reserved,
   'original_deadline',w.original_deadline,
   'provider_submission_authorized',false)
 INTO v_receipt;
 RETURN v_receipt;
END $$;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_provider_precall_reserve_v1(text,text,bigint,int,text,int)
 FROM PUBLIC;
COMMIT;
),
 records_reserved integer NOT NULL CHECK(records_reserved BETWEEN 1 AND 1000),
 recorded_by name NOT NULL DEFAULT current_user,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(work_key,page_no)
);
CREATE TABLE astra_ingestion_v1.bulk_provider_precall_v1 (
 work_key text NOT NULL REFERENCES astra_ingestion_v1.bulk_work_v1(work_key),
 page_no integer NOT NULL CHECK (page_no BETWEEN 0 AND 199),
 manifest_sha256 text NOT NULL,
 family text NOT NULL CHECK(family IN ('P01','P02')),
 source_receipt_sha256 text NOT NULL CHECK(source_receipt_sha256 ~ '^[0-9a-f]{64}$'),
 request_sha256 text NOT NULL CHECK(request_sha256 ~ '^[0-9a-f]{64}$'),
 owner text NOT NULL CHECK(owner ~ '^[A-Za-z0-9_.:-]{1,128}$'),
 fence bigint NOT NULL CHECK(fence>=1),
 records_reserved integer NOT NULL CHECK(records_reserved BETWEEN 1 AND 1000),
 original_deadline timestamptz NOT NULL,
 reserved_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(work_key,page_no),
 CHECK(original_deadline > reserved_at)
);
CREATE TRIGGER bulk_provider_review_immutable_v1
 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.bulk_provider_review_v1
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.bulk_review_immutable_v1();
CREATE TRIGGER bulk_provider_precall_immutable_v1
 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.bulk_provider_precall_v1
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.bulk_review_immutable_v1();
ALTER TABLE astra_ingestion_v1.bulk_provider_review_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE astra_ingestion_v1.bulk_provider_precall_v1 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON astra_ingestion_v1.bulk_provider_review_v1,
 astra_ingestion_v1.bulk_provider_precall_v1 FROM PUBLIC;

-- Reviewer-authored records require separate principal qualification.
-- This is an engineering admission predicate, NOT evidence of genuine
-- independent review merely because a synthetic row exists.
CREATE FUNCTION astra_ingestion_v1.bulk_provider_precall_reserve_v1(
 p_work text,p_owner text,p_fence bigint,p_page integer,
 p_request_sha256 text,p_records_reserved integer)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER
SET search_path=pg_catalog SET timezone='UTC' AS $$
DECLARE v_manifest text; m record; w record; a record; r record; u record;
        n integer; v_inflight integer; v_receipt jsonb;
BEGIN
 IF p_work IS NULL OR p_work !~ '^astra-bulk-v1-[0-9a-f]{64}$'
 OR p_owner IS NULL OR p_owner !~ '^[A-Za-z0-9_.:-]{1,128}$'
 OR p_fence IS NULL OR p_fence < 1
 OR p_page IS NULL OR p_page NOT BETWEEN 0 AND 199
 OR p_request_sha256 IS NULL OR p_request_sha256 !~ '^[0-9a-f]{64}$'
 OR p_records_reserved IS NULL OR p_records_reserved NOT BETWEEN 1 AND 1000
 THEN RAISE EXCEPTION 'invalid immutable provider pre-call reservation'; END IF;
 SELECT manifest_sha256 INTO v_manifest
 FROM astra_ingestion_v1.bulk_work_v1 WHERE work_key=p_work;
 IF NOT FOUND THEN RAISE EXCEPTION 'unknown provider work'; END IF;
 -- Lock order is manifest -> work. Serialize stops, new work and claims.
 SELECT * INTO m FROM astra_ingestion_v1.bulk_manifest_v1
 WHERE manifest_sha256=v_manifest FOR SHARE;
 IF NOT FOUND OR m.stopped
 OR m.capture_key IS DISTINCT FROM 'top3000-augsep2026-retained-scope-v1'
 OR m.capture_receipt_sha256 IS DISTINCT FROM 'ba13899b530288b6aae8d4af3a429efa3f4bd5ec305a7dc698f98c9d552f4496'
 THEN RAISE EXCEPTION 'provider manifest absent, stopped or wrong capture'; END IF;
 SELECT * INTO w FROM astra_ingestion_v1.bulk_work_v1
 WHERE work_key=p_work FOR UPDATE;
 IF NOT FOUND OR w.manifest_sha256 IS DISTINCT FROM v_manifest
 OR w.family NOT IN ('P01','P02') OR w.mode <> 'provider_acquisition'
 OR w.status <> 'claimed' OR w.claim_owner IS DISTINCT FROM p_owner
 OR w.claim_fence IS DISTINCT FROM p_fence OR w.claim_until IS NULL
 OR w.claim_until <= clock_timestamp() OR w.original_deadline <= clock_timestamp()
 OR w.attempts NOT BETWEEN 1 AND 2 OR w.last_page+1 IS DISTINCT FROM p_page
 OR w.requests_committed+1 > w.max_requests
 OR w.records_committed+p_records_reserved > w.max_records
 OR w.source_receipt_sha256 !~ '^[0-9a-f]{64}$'
 THEN RAISE EXCEPTION 'provider request denied by claim, stop, deadline, budget or sequence'; END IF;
 -- Entire reviewed family population and exact security unit MUST be sealed.
 SELECT * INTO a FROM astra_ingestion_v1.bulk_manifest_review_v1
 WHERE manifest_sha256=v_manifest;
 SELECT * INTO r FROM astra_ingestion_v1.bulk_provider_review_v1
 WHERE manifest_sha256=v_manifest;
 IF a.manifest_sha256 IS NULL OR r.manifest_sha256 IS NULL
 OR a.family_count IS DISTINCT FROM 24
 OR r.independent_report_sha256 IS DISTINCT FROM a.independent_report_sha256
 THEN RAISE EXCEPTION 'distinct provider acquisition review absent'; END IF;
 SELECT count(*) INTO n
 FROM astra_ingestion_v1.bulk_family_review_v1 f
 JOIN astra_ingestion_v1.bulk_unit_seal_v1 s
 ON s.manifest_sha256=f.manifest_sha256 AND s.family=f.family
 AND s.expected_manifest_sha256=f.expected_manifest_sha256
 AND s.unit_count=f.expected_units
 AND s.independent_report_sha256=f.independent_report_sha256
 JOIN astra_ingestion_v1.bulk_scope_evidence_v1 e
 ON e.capture_key=m.capture_key AND e.kind='contract'
 AND e.evidence_key=f.family AND e.source_sha256=f.contract_sha256
 WHERE f.manifest_sha256=v_manifest
 AND f.independent_report_sha256=a.independent_report_sha256
 AND f.expected_units=f.observed_units;
 IF n<>24 THEN RAISE EXCEPTION 'complete 24-family source-backed review absent'; END IF;
 -- One unreviewed reserved unit invalidates admission for the ENTIRE manifest.
 IF EXISTS (
  SELECT 1 FROM astra_ingestion_v1.bulk_work_v1 x
  LEFT JOIN astra_ingestion_v1.bulk_reviewed_unit_v1 y
  ON y.manifest_sha256=x.manifest_sha256 AND y.family=x.family
  AND y.unit_key=x.unit_key AND y.source_receipt_sha256=x.source_receipt_sha256
  AND y.independent_report_sha256=a.independent_report_sha256
  WHERE x.manifest_sha256=v_manifest AND y.unit_key IS NULL
 ) THEN RAISE EXCEPTION 'manifest contains unreviewed source work'; END IF;
 SELECT * INTO u FROM astra_ingestion_v1.bulk_reviewed_unit_v1
 WHERE manifest_sha256=v_manifest AND family=w.family
 AND unit_key=w.unit_key AND source_receipt_sha256=w.source_receipt_sha256
 AND independent_report_sha256=a.independent_report_sha256;
 IF NOT FOUND THEN RAISE EXCEPTION 'unreviewed exact provider work unit'; END IF;
 -- Never issue two concurrent or replacement calls for an uncertain page.
 -- A request may have reached the provider even when no receipt exists.
 SELECT count(*) INTO v_inflight FROM astra_ingestion_v1.bulk_provider_precall_v1
 WHERE work_key=p_work AND page_no>=p_page;
 IF v_inflight<>0 OR EXISTS(
   SELECT 1 FROM astra_ingestion_v1.bulk_receipt_v1
   WHERE work_key=p_work AND page_no=p_page
 ) THEN RAISE EXCEPTION 'provider page already reserved or committed: reconcile, do not refetch'; END IF;
 IF p_page>0 AND NOT EXISTS (
   SELECT 1 FROM astra_ingestion_v1.bulk_receipt_v1
   WHERE work_key=p_work AND page_no=p_page-1 AND requests_committed=1
 ) THEN RAISE EXCEPTION 'provider continuation lacks previous committed receipt'; END IF;
 INSERT INTO astra_ingestion_v1.bulk_provider_precall_v1(
   work_key,page_no,manifest_sha256,family,source_receipt_sha256,
   request_sha256,owner,fence,records_reserved,original_deadline)
 VALUES(p_work,p_page,v_manifest,w.family,w.source_receipt_sha256,
        p_request_sha256,p_owner,p_fence,p_records_reserved,w.original_deadline);
 -- This is a durable accounting marker, NOT permission to transmit.
 SELECT jsonb_build_object(
   'status','RESERVED_NO_PROVIDER_TRANSPORT_GRANT',
   'work_key',p_work,'page_no',p_page,'manifest_sha256',v_manifest,
   'family',w.family,'claim_fence',p_fence,
   'request_sha256',p_request_sha256,
   'records_reserved',p_records_reserved,
   'original_deadline',w.original_deadline,
   'provider_submission_authorized',false)
 INTO v_receipt;
 RETURN v_receipt;
END $$;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_provider_precall_reserve_v1(text,text,bigint,int,text,int)
 FROM PUBLIC;
COMMIT;
