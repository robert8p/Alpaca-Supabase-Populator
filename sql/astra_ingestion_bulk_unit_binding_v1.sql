-- ASTRA staged only. Install AFTER bulk ledger, retained review gate and runtime port.
-- Append-only independently reviewed exact-unit set, not count-only attestation.
-- No worker/reviewer grants, no production population, no provider calls.
-- Reviewer provenance, source completeness and authenticated JWT-over-HTTPS
-- must be independently proved BEFORE admitting protected production work.
BEGIN;
CREATE TABLE astra_ingestion_v1.bulk_reviewed_unit_v1 (
 manifest_sha256 text NOT NULL REFERENCES astra_ingestion_v1.bulk_manifest_v1(manifest_sha256),
 family text NOT NULL,
 unit_key text NOT NULL CHECK (length(unit_key) BETWEEN 1 AND 512),
 source_receipt_sha256 text NOT NULL CHECK (source_receipt_sha256 ~ '^[0-9a-f]{64}$'),
 provenance_sha256 text NOT NULL CHECK (provenance_sha256 ~ '^[0-9a-f]{64}$'),
 identity_sha256 text NOT NULL CHECK (identity_sha256 ~ '^[0-9a-f]{64}$'),
 pit_sha256 text NOT NULL CHECK (pit_sha256 ~ '^[0-9a-f]{64}$'),
 independent_report_sha256 text NOT NULL CHECK (independent_report_sha256 ~ '^[0-9a-f]{64}$'),
 recorded_by name NOT NULL DEFAULT current_user,
 recorded_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(manifest_sha256,family,unit_key),
 FOREIGN KEY(manifest_sha256,family)
  REFERENCES astra_ingestion_v1.bulk_family_review_v1(manifest_sha256,family)
);
CREATE TABLE astra_ingestion_v1.bulk_unit_seal_v1 (
 manifest_sha256 text NOT NULL,
 family text NOT NULL,
 expected_manifest_sha256 text NOT NULL CHECK (expected_manifest_sha256 ~ '^[0-9a-f]{64}$'),
 exact_unit_set_sha256 text NOT NULL CHECK (exact_unit_set_sha256 ~ '^[0-9a-f]{64}$'),
 unit_count bigint NOT NULL CHECK (unit_count BETWEEN 1 AND 200000),
 independent_report_sha256 text NOT NULL CHECK (independent_report_sha256 ~ '^[0-9a-f]{64}$'),
 sealed_by name NOT NULL DEFAULT current_user,
 sealed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY(manifest_sha256,family),
 FOREIGN KEY(manifest_sha256,family)
  REFERENCES astra_ingestion_v1.bulk_family_review_v1(manifest_sha256,family)
);
-- Rows, seals and all verification columns are immutable even for administrative
-- integration callers. A corrected review needs a NEW independently pinned manifest.
CREATE TRIGGER bulk_reviewed_unit_immutable_v1
 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.bulk_reviewed_unit_v1
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.bulk_review_immutable_v1();
CREATE TRIGGER bulk_unit_seal_immutable_v1
 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.bulk_unit_seal_v1
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.bulk_review_immutable_v1();

-- Serialize reviewer source rows and final seal with the manifest lock. Direct
-- INSERT access is NOT granted to any runtime application principal.
CREATE FUNCTION astra_ingestion_v1.bulk_reviewed_unit_insert_guard_v1()
RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
DECLARE m record; r record;
BEGIN
 SELECT * INTO m FROM astra_ingestion_v1.bulk_manifest_v1
 WHERE manifest_sha256=NEW.manifest_sha256 FOR UPDATE;
 IF NOT FOUND OR m.stopped THEN
  RAISE EXCEPTION 'reviewed unit manifest absent or stopped';
 END IF;
 SELECT * INTO r FROM astra_ingestion_v1.bulk_family_review_v1
 WHERE manifest_sha256=NEW.manifest_sha256 AND family=NEW.family;
 IF NOT FOUND OR r.independent_report_sha256 IS DISTINCT FROM NEW.independent_report_sha256 THEN
  RAISE EXCEPTION 'unit witness not bound to family independent report';
 END IF;
 IF EXISTS (SELECT 1 FROM astra_ingestion_v1.bulk_unit_seal_v1 s
            WHERE s.manifest_sha256=NEW.manifest_sha256 AND s.family=NEW.family) THEN
  RAISE EXCEPTION 'sealed reviewed unit set is immutable';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER bulk_reviewed_unit_insert_guard_v1
 BEFORE INSERT ON astra_ingestion_v1.bulk_reviewed_unit_v1
 FOR EACH ROW EXECUTE FUNCTION astra_ingestion_v1.bulk_reviewed_unit_insert_guard_v1();

-- The independent reviewer supplies an expected exact SET hash obtained from
-- an external source-backed verification. PostgreSQL recomputes it from every
-- ordered, fully evidenced row. A fabricated external digest is NOT proof of
-- actual source coverage; source-backed reviewer role qualification is required.
CREATE FUNCTION astra_ingestion_v1.bulk_seal_unit_set_v1(
 p_manifest text,p_family text,p_report text,p_external_unit_sha256 text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog SET timezone='UTC' AS $$
DECLARE m record; r record; a record; n bigint; calculated text; existing record;
BEGIN
 IF p_manifest IS NULL OR p_manifest !~ '^[0-9a-f]{64}$'
    OR p_report IS NULL OR p_report !~ '^[0-9a-f]{64}$'
    OR p_external_unit_sha256 IS NULL OR p_external_unit_sha256 !~ '^[0-9a-f]{64}$'
    OR p_family IS NULL THEN RAISE EXCEPTION 'invalid pinned unit seal'; END IF;
 SELECT * INTO m FROM astra_ingestion_v1.bulk_manifest_v1
 WHERE manifest_sha256=p_manifest FOR UPDATE;
 IF NOT FOUND OR m.stopped THEN RAISE EXCEPTION 'manifest absent or stopped'; END IF;
 SELECT * INTO a FROM astra_ingestion_v1.bulk_manifest_review_v1
 WHERE manifest_sha256=p_manifest;
 SELECT * INTO r FROM astra_ingestion_v1.bulk_family_review_v1
 WHERE manifest_sha256=p_manifest AND family=p_family;
 IF NOT FOUND OR a.independent_report_sha256 IS DISTINCT FROM p_report
   OR a.status IS DISTINCT FROM 'INDEPENDENTLY_REVIEWED_RETAINED_ONLY'
   OR r.independent_report_sha256 IS DISTINCT FROM p_report
   OR r.expected_units IS DISTINCT FROM r.observed_units THEN
  RAISE EXCEPTION 'unit seal requires original complete independent family review';
 END IF;
 SELECT * INTO existing FROM astra_ingestion_v1.bulk_unit_seal_v1
 WHERE manifest_sha256=p_manifest AND family=p_family;
 IF FOUND THEN
  IF existing.exact_unit_set_sha256 IS DISTINCT FROM p_external_unit_sha256
    OR existing.independent_report_sha256 IS DISTINCT FROM p_report
  THEN RAISE EXCEPTION 'immutable unit seal collision'; END IF;
  RETURN to_jsonb(existing);
 END IF;
 SELECT count(*), encode(sha256(convert_to(
   COALESCE(jsonb_agg(jsonb_build_array(u.unit_key,u.source_receipt_sha256,
     u.provenance_sha256,u.identity_sha256,u.pit_sha256) ORDER BY u.unit_key)::text,'[]'),
   'UTF8')),'hex')
 INTO n,calculated FROM astra_ingestion_v1.bulk_reviewed_unit_v1 u
 WHERE u.manifest_sha256=p_manifest AND u.family=p_family;
 IF n IS DISTINCT FROM r.expected_units OR calculated IS DISTINCT FROM p_external_unit_sha256 THEN
  RAISE EXCEPTION 'exact reviewed unit population missing, extra or source hash mismatch';
 END IF;
 INSERT INTO astra_ingestion_v1.bulk_unit_seal_v1 (
   manifest_sha256,family,expected_manifest_sha256,exact_unit_set_sha256,
   unit_count,independent_report_sha256)
 VALUES (p_manifest,p_family,r.expected_manifest_sha256,p_external_unit_sha256,n,p_report);
 RETURN (SELECT to_jsonb(x) FROM astra_ingestion_v1.bulk_unit_seal_v1 x
         WHERE x.manifest_sha256=p_manifest AND x.family=p_family);
END $$;

-- OVERRIDE previously staged count-only port. Only this sealed port is a
-- potential future restricted runtime interface; neither grants nor roles
-- are included. Check *all* reserved work units, not just the chosen candidate.
CREATE OR REPLACE FUNCTION astra_ingestion_v1.bulk_runtime_admission_v1(p_manifest text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog SET timezone='UTC' AS $$
DECLARE m record; a record; n int; contracts int; seals int;
BEGIN
 IF p_manifest IS NULL OR p_manifest !~ '^[0-9a-f]{64}$' THEN RETURN NULL; END IF;
 SELECT * INTO m FROM astra_ingestion_v1.bulk_manifest_v1
 WHERE manifest_sha256=p_manifest;
 IF NOT FOUND OR m.stopped
    OR m.capture_key IS DISTINCT FROM 'top3000-augsep2026-retained-scope-v1'
    OR m.capture_receipt_sha256 IS DISTINCT FROM 'ba13899b530288b6aae8d4af3a429efa3f4bd5ec305a7dc698f98c9d552f4496'
 THEN RETURN NULL; END IF;
 SELECT * INTO a FROM astra_ingestion_v1.bulk_manifest_review_v1
 WHERE manifest_sha256=p_manifest;
 IF NOT FOUND OR a.status IS DISTINCT FROM 'INDEPENDENTLY_REVIEWED_RETAINED_ONLY'
  OR a.family_count IS DISTINCT FROM 24 OR a.independent_report_sha256 !~ '^[0-9a-f]{64}$'
 THEN RETURN NULL; END IF;
 SELECT count(*) INTO n FROM astra_ingestion_v1.bulk_family_review_v1 r
 WHERE r.manifest_sha256=p_manifest AND r.independent_report_sha256=a.independent_report_sha256
 AND r.expected_units=r.observed_units;
 IF n IS DISTINCT FROM 24 THEN RETURN NULL; END IF;
 SELECT count(*) INTO contracts FROM astra_ingestion_v1.bulk_family_review_v1 r
 JOIN astra_ingestion_v1.bulk_scope_evidence_v1 e
 ON e.capture_key=m.capture_key AND e.kind='contract'
 AND e.evidence_key=r.family AND e.source_sha256=r.contract_sha256
 WHERE r.manifest_sha256=p_manifest AND r.independent_report_sha256=a.independent_report_sha256;
 IF contracts IS DISTINCT FROM 24 THEN RETURN NULL; END IF;
 SELECT count(*) INTO seals
 FROM astra_ingestion_v1.bulk_family_review_v1 r
 JOIN astra_ingestion_v1.bulk_unit_seal_v1 s
 ON s.manifest_sha256=r.manifest_sha256 AND s.family=r.family
 AND s.expected_manifest_sha256=r.expected_manifest_sha256
 AND s.independent_report_sha256=r.independent_report_sha256
 AND s.unit_count=r.expected_units
 WHERE r.manifest_sha256=p_manifest AND r.independent_report_sha256=a.independent_report_sha256;
 IF seals IS DISTINCT FROM 24 THEN RETURN NULL; END IF;
 -- Fail all admission when ANY reserved work lacks its unique independently
 -- reviewed source, including an arbitrary unit inserted after sealing.
 IF EXISTS(
  SELECT 1 FROM astra_ingestion_v1.bulk_work_v1 w
  LEFT JOIN astra_ingestion_v1.bulk_reviewed_unit_v1 u
   ON u.manifest_sha256=w.manifest_sha256 AND u.family=w.family
   AND u.unit_key=w.unit_key AND u.source_receipt_sha256=w.source_receipt_sha256
   AND u.independent_report_sha256=a.independent_report_sha256
  WHERE w.manifest_sha256=p_manifest
    AND (w.mode<>'retained_source_reuse' OR w.max_requests<>0 OR
         w.requests_committed<>0 OR u.unit_key IS NULL)
 ) THEN RETURN NULL; END IF;
 RETURN jsonb_build_object(
  'status',a.status,'manifest_sha256',m.manifest_sha256,
  'capture_key',m.capture_key,'capture_receipt_sha256',m.capture_receipt_sha256,
  'complete_family_count',n,'independent_review_sha256',a.independent_report_sha256,
  'stopped',m.stopped);
END $$;

-- Holding the manifest SHARE lock serializes this entire review+claim with
-- bulk_reserve_v1's manifest UPDATE lock and explicit stop updates.
CREATE OR REPLACE FUNCTION astra_ingestion_v1.bulk_runtime_claim_v1(
 p_manifest text,p_owner text,p_lease_seconds int)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog SET timezone='UTC' AS $$
DECLARE m record;
BEGIN
 IF p_owner IS NULL OR p_owner !~ '^[A-Za-z0-9_.:-]{1,128}$'
 OR p_lease_seconds IS NULL OR p_lease_seconds NOT BETWEEN 10 AND 180
 THEN RAISE EXCEPTION 'invalid finite restricted worker identity or lease'; END IF;
 SELECT * INTO m FROM astra_ingestion_v1.bulk_manifest_v1
 WHERE manifest_sha256=p_manifest FOR SHARE;
 IF NOT FOUND OR m.stopped OR astra_ingestion_v1.bulk_runtime_admission_v1(p_manifest) IS NULL
 THEN RETURN NULL; END IF;
 RETURN astra_ingestion_v1.bulk_claim_retained_v1(p_manifest,p_owner,p_lease_seconds);
END $$;
ALTER TABLE astra_ingestion_v1.bulk_reviewed_unit_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE astra_ingestion_v1.bulk_unit_seal_v1 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON astra_ingestion_v1.bulk_reviewed_unit_v1,
 astra_ingestion_v1.bulk_unit_seal_v1 FROM PUBLIC;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_reviewed_unit_insert_guard_v1() FROM PUBLIC;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_seal_unit_set_v1(text,text,text,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_runtime_admission_v1(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_runtime_claim_v1(text,text,int) FROM PUBLIC;
COMMIT;
