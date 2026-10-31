-- ASTRA forward-only RESTRICTED RUNTIME PORT, staged/not installed.
-- Apply only after isolated bulk ledger and 24-family review gate. This is
-- intentionally not an admission or deployment: external separate reviewer,
-- RLS/role and source-backed materializer assurance remain prerequisites.
-- No public grants, direct table rights, provider rights or verifier mutation.
BEGIN;

-- Python dispatcher requires a different shape from the stored review row.
-- Never let the worker infer approval from a row count or self-issued report.
CREATE FUNCTION astra_ingestion_v1.bulk_runtime_admission_v1(p_manifest text)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog SET timezone='UTC' AS $$
DECLARE m record; a record; n integer; source_matches integer;
BEGIN
 IF p_manifest IS NULL OR p_manifest !~ '^[0-9a-f]{64}$' THEN
  RETURN NULL;
 END IF;
 SELECT * INTO m FROM astra_ingestion_v1.bulk_manifest_v1
 WHERE manifest_sha256=p_manifest;
 IF NOT FOUND OR m.stopped OR m.capture_key IS DISTINCT FROM 'top3000-augsep2026-retained-scope-v1'
 OR m.capture_receipt_sha256 IS DISTINCT FROM 'ba13899b530288b6aae8d4af3a429efa3f4bd5ec305a7dc698f98c9d552f4496'
 THEN RETURN NULL; END IF;
 SELECT * INTO a FROM astra_ingestion_v1.bulk_manifest_review_v1
 WHERE manifest_sha256=p_manifest;
 IF NOT FOUND OR a.status IS DISTINCT FROM 'INDEPENDENTLY_REVIEWED_RETAINED_ONLY'
 OR a.family_count IS DISTINCT FROM 24
 OR a.independent_report_sha256 !~ '^[0-9a-f]{64}$'
 THEN RETURN NULL; END IF;
 SELECT count(*) INTO n FROM astra_ingestion_v1.bulk_family_review_v1
 WHERE manifest_sha256=p_manifest AND independent_report_sha256=a.independent_report_sha256
 AND expected_units=observed_units;
 IF n IS DISTINCT FROM 24 THEN RETURN NULL; END IF;
 -- Reconcile source contracts again on each admission, not only at review.
 SELECT count(*) INTO source_matches
 FROM astra_ingestion_v1.bulk_family_review_v1 r
 JOIN astra_ingestion_v1.bulk_scope_evidence_v1 e
 ON e.capture_key=m.capture_key AND e.kind='contract'
 AND e.evidence_key=r.family AND e.source_sha256=r.contract_sha256
 WHERE r.manifest_sha256=p_manifest
 AND r.independent_report_sha256=a.independent_report_sha256;
 IF source_matches IS DISTINCT FROM 24 THEN RETURN NULL; END IF;
 RETURN jsonb_build_object(
  'status',a.status, 'manifest_sha256',m.manifest_sha256,
  'capture_key',m.capture_key, 'capture_receipt_sha256',m.capture_receipt_sha256,
  'complete_family_count',n, 'independent_review_sha256',a.independent_report_sha256,
  'stopped',m.stopped);
END $$;

-- Narrow pending retained-only claim. Actual worker identity must separately
-- bind to an authenticated restricted DB principal before any EXECUTE grant.
-- Never grant generic bulk_claim_v1, bulk_verify_v1, bulk_reserve_v1 or raw DML.
CREATE FUNCTION astra_ingestion_v1.bulk_runtime_claim_v1(
 p_manifest text,p_owner text,p_lease_seconds int)
RETURNS jsonb LANGUAGE plpgsql SECURITY DEFINER
SET search_path=pg_catalog SET timezone='UTC' AS $$
BEGIN
 IF p_owner IS NULL OR p_owner !~ '^[A-Za-z0-9_.:-]{1,128}$' THEN
  RAISE EXCEPTION 'invalid non-secret restricted worker identity';
 END IF;
 IF astra_ingestion_v1.bulk_runtime_admission_v1(p_manifest) IS NULL THEN
  RETURN NULL;
 END IF;
 RETURN astra_ingestion_v1.bulk_claim_retained_v1(p_manifest,p_owner,p_lease_seconds);
END $$;

-- PostgreSQL defaults EXECUTE on functions to PUBLIC: revoke explicitly.
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_runtime_admission_v1(text) FROM PUBLIC;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_runtime_claim_v1(text,text,int) FROM PUBLIC;
COMMIT;
