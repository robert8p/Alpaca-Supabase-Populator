-- STAGED only. Apply AFTER the isolated bulk_ledger_v1, never on startup.
-- Restricted retained-only admission. This records the 24 independently
-- reviewed source/expected-unit witnesses and permits NO provider acquisition.
-- A source report hash alone is not independent verification: provision a
-- distinct reviewer DB principal and verify its transport/permissions BEFORE
-- any production insert. Application principals receive NO grants here.
BEGIN;

CREATE TABLE astra_ingestion_v1.bulk_family_review_v1 (
 manifest_sha256 text NOT NULL REFERENCES astra_ingestion_v1.bulk_manifest_v1(manifest_sha256),
 family text NOT NULL CHECK(family IN (
 'REF01','P01','P02','D01','N01','N03','D02','D03','D04','F04','F05','S02',
 'F06','CTX06','CTX14','REF03','D05','F01','F02','F03','N02','S01','CTX02','CTX07')),
 contract_sha256 text NOT NULL CHECK(contract_sha256 ~ '^[0-9a-f]{64}$'),
 expected_manifest_sha256 text NOT NULL CHECK(expected_manifest_sha256 ~ '^[0-9a-f]{64}$'),
 source_receipt_sha256 text NOT NULL CHECK(source_receipt_sha256 ~ '^[0-9a-f]{64}$'),
 provenance_sha256 text NOT NULL CHECK(provenance_sha256 ~ '^[0-9a-f]{64}$'),
 identity_sha256 text NOT NULL CHECK(identity_sha256 ~ '^[0-9a-f]{64}$'),
 pit_sha256 text NOT NULL CHECK(pit_sha256 ~ '^[0-9a-f]{64}$'),
 expected_units bigint NOT NULL CHECK(expected_units BETWEEN 1 AND 200000),
 observed_units bigint NOT NULL CHECK(observed_units BETWEEN 1 AND 200000 AND observed_units=expected_units),
 independent_report_sha256 text NOT NULL CHECK(independent_report_sha256 ~ '^[0-9a-f]{64}$'),
 inserted_by name NOT NULL DEFAULT current_user,
 inserted_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(manifest_sha256,family)
);
CREATE TABLE astra_ingestion_v1.bulk_manifest_review_v1 (
 manifest_sha256 text PRIMARY KEY REFERENCES astra_ingestion_v1.bulk_manifest_v1(manifest_sha256),
 independent_report_sha256 text NOT NULL CHECK(independent_report_sha256 ~ '^[0-9a-f]{64}$'),
 family_count smallint NOT NULL CHECK(family_count=24),
 reviewed_by name NOT NULL DEFAULT current_user,
 reviewed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 status text NOT NULL DEFAULT 'INDEPENDENTLY_REVIEWED_RETAINED_ONLY'
 CHECK(status='INDEPENDENTLY_REVIEWED_RETAINED_ONLY')
);
CREATE FUNCTION astra_ingestion_v1.bulk_review_immutable_v1() RETURNS trigger
LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
BEGIN
 RAISE EXCEPTION 'review evidence is immutable; conflict requires a new manifest/review';
END $$;
CREATE TRIGGER bulk_family_review_immutable_v1 BEFORE UPDATE OR DELETE OR TRUNCATE
 ON astra_ingestion_v1.bulk_family_review_v1 FOR EACH STATEMENT
 EXECUTE FUNCTION astra_ingestion_v1.bulk_review_immutable_v1();
CREATE TRIGGER bulk_manifest_review_immutable_v1 BEFORE UPDATE OR DELETE OR TRUNCATE
 ON astra_ingestion_v1.bulk_manifest_review_v1 FOR EACH STATEMENT
 EXECUTE FUNCTION astra_ingestion_v1.bulk_review_immutable_v1();

CREATE FUNCTION astra_ingestion_v1.bulk_finalize_retained_review_v1(p_manifest text,p_report text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog SET timezone='UTC' AS $$
DECLARE m record; existing record; n int; family_set text[]; source_matches int;
BEGIN
 IF p_manifest !~ '^[0-9a-f]{64}$' OR p_report !~ '^[0-9a-f]{64}$' THEN
  RAISE EXCEPTION 'invalid reviewed manifest or report digest';
 END IF;
 SELECT * INTO m FROM astra_ingestion_v1.bulk_manifest_v1
 WHERE manifest_sha256=p_manifest FOR SHARE;
 IF NOT FOUND OR m.stopped OR m.capture_key IS DISTINCT FROM 'top3000-augsep2026-retained-scope-v1'
 OR m.capture_receipt_sha256 IS DISTINCT FROM 'ba13899b530288b6aae8d4af3a429efa3f4bd5ec305a7dc698f98c9d552f4496'
 THEN RAISE EXCEPTION 'reviewed manifest absent, stopped or unpinned'; END IF;
 SELECT count(*),array_agg(family ORDER BY family) INTO n,family_set
 FROM astra_ingestion_v1.bulk_family_review_v1
 WHERE manifest_sha256=p_manifest AND independent_report_sha256=p_report
 AND expected_units=observed_units;
 IF n IS DISTINCT FROM 24 OR family_set IS DISTINCT FROM ARRAY[
 'CTX02','CTX06','CTX07','CTX14','D01','D02','D03','D04','D05',
 'F01','F02','F03','F04','F05','F06','N01','N02','N03','P01','P02','REF01','REF03','S01','S02'
 ]::text[] THEN
   RAISE EXCEPTION 'all 24 independently reviewed family unit populations required';
 END IF;
 -- Every family contract SHA must point to an actual retained original
 -- source document, never merely a newly supplied metadata assertion.
 SELECT count(*) INTO source_matches
 FROM astra_ingestion_v1.bulk_family_review_v1 r
 JOIN astra_ingestion_v1.bulk_scope_evidence_v1 e
  ON e.capture_key=m.capture_key AND e.kind='contract'
  AND e.evidence_key=r.family AND e.source_sha256=r.contract_sha256
 WHERE r.manifest_sha256=p_manifest AND r.independent_report_sha256=p_report;
 IF source_matches IS DISTINCT FROM 24 THEN
  RAISE EXCEPTION 'source contract evidence does not match original 24 retained receipts';
 END IF;
 SELECT * INTO existing FROM astra_ingestion_v1.bulk_manifest_review_v1
 WHERE manifest_sha256=p_manifest FOR UPDATE;
 IF FOUND THEN
   IF existing.independent_report_sha256 IS DISTINCT FROM p_report THEN
      RAISE EXCEPTION 'immutable independent review collision';
   END IF;
   RETURN to_jsonb(existing);
 END IF;
 INSERT INTO astra_ingestion_v1.bulk_manifest_review_v1
   (manifest_sha256,independent_report_sha256,family_count)
 VALUES(p_manifest,p_report,24);
 RETURN (SELECT to_jsonb(x) FROM astra_ingestion_v1.bulk_manifest_review_v1 x
         WHERE x.manifest_sha256=p_manifest);
END $$;

-- The only staged bulk claim path intended for an eventual restricted
-- retained-source worker. The previous unrestricted bulk_claim_v1 and the
-- reviewer functions MUST NOT be granted to this worker's DB role.
CREATE FUNCTION astra_ingestion_v1.bulk_claim_retained_v1(p_manifest text,p_owner text,p_lease_seconds int)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog SET timezone='UTC' AS $$
DECLARE m record; a record; w record;
BEGIN
 IF p_manifest !~ '^[0-9a-f]{64}$'
 OR p_owner IS NULL OR length(p_owner) NOT BETWEEN 1 AND 128
 OR p_lease_seconds IS NULL OR p_lease_seconds NOT BETWEEN 10 AND 180
 THEN RAISE EXCEPTION 'invalid bounded retained claim'; END IF;
 SELECT * INTO m FROM astra_ingestion_v1.bulk_manifest_v1
 WHERE manifest_sha256=p_manifest FOR SHARE;
 IF NOT FOUND OR m.stopped THEN RETURN NULL; END IF;
 SELECT * INTO a FROM astra_ingestion_v1.bulk_manifest_review_v1
 WHERE manifest_sha256=p_manifest;
 IF NOT FOUND OR a.status IS DISTINCT FROM 'INDEPENDENTLY_REVIEWED_RETAINED_ONLY'
 OR a.family_count IS DISTINCT FROM 24 THEN RETURN NULL; END IF;
 SELECT * INTO w FROM astra_ingestion_v1.bulk_work_v1 w1
 WHERE w1.manifest_sha256=p_manifest
   AND w1.mode='retained_source_reuse' AND w1.max_requests=0
   AND w1.requests_committed=0 AND w1.status='pending' AND w1.attempts<2
   AND w1.original_deadline>clock_timestamp()
   AND NOT EXISTS(
     SELECT 1 FROM unnest(w1.predecessors) AS d(k)
     JOIN astra_ingestion_v1.bulk_work_v1 p ON p.work_key=d.k
     WHERE p.status<>'verified')
 ORDER BY w1.created_at,w1.work_key LIMIT 1 FOR UPDATE OF w1 SKIP LOCKED;
 IF NOT FOUND THEN RETURN NULL; END IF;
 UPDATE astra_ingestion_v1.bulk_work_v1
 SET status='claimed',claim_owner=p_owner,claim_fence=claim_fence+1,
 claim_until=LEAST(original_deadline,clock_timestamp()+
                  (p_lease_seconds||' seconds')::interval),
 attempts=attempts+1 WHERE work_key=w.work_key;
 RETURN (SELECT to_jsonb(x) FROM astra_ingestion_v1.bulk_work_v1 x
         WHERE x.work_key=w.work_key);
END $$;

ALTER TABLE astra_ingestion_v1.bulk_family_review_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE astra_ingestion_v1.bulk_manifest_review_v1 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON astra_ingestion_v1.bulk_family_review_v1,
 astra_ingestion_v1.bulk_manifest_review_v1 FROM PUBLIC;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_finalize_retained_review_v1(text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_claim_retained_v1(text,text,int) FROM PUBLIC;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_review_immutable_v1() FROM PUBLIC;
COMMIT;
