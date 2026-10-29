-- ASTRA isolated, forward-only durable bulk ledger. STAGED: NO automatic installation.
-- No licensed source rows, broker access, provider calls, credential provisioning,
-- public grants, existing-job mutation, legacy schema writes or campaign expiry.
-- Installation and restricted-runtime actor qualification are separate gates.
BEGIN;
CREATE TABLE astra_ingestion_v1.bulk_manifest_v1 (
 manifest_sha256 text PRIMARY KEY CHECK (manifest_sha256 ~ '^[0-9a-f]{64}$'),
 capture_key text NOT NULL REFERENCES astra_ingestion_v1.bulk_scope_capture_v1(capture_key),
 capture_receipt_sha256 text NOT NULL CHECK (capture_receipt_sha256 ~ '^[0-9a-f]{64}$'),
 max_requests bigint NOT NULL CHECK(max_requests BETWEEN 0 AND 1000000000),
 max_records bigint NOT NULL CHECK(max_records BETWEEN 1 AND 1000000000000),
 reserved_requests bigint NOT NULL DEFAULT 0 CHECK(reserved_requests>=0 AND reserved_requests<=max_requests),
 reserved_records bigint NOT NULL DEFAULT 0 CHECK(reserved_records>=0 AND reserved_records<=max_records),
 stopped boolean NOT NULL DEFAULT false,
 stop_reason text,
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 CHECK ((NOT stopped AND stop_reason IS NULL) OR (stopped AND stop_reason IS NOT NULL AND length(stop_reason) BETWEEN 1 AND 500))
);
CREATE TABLE astra_ingestion_v1.bulk_work_v1 (
 work_key text PRIMARY KEY CHECK (work_key ~ '^astra-bulk-v1-[0-9a-f]{64}$'),
 manifest_sha256 text NOT NULL REFERENCES astra_ingestion_v1.bulk_manifest_v1(manifest_sha256),
 family text NOT NULL CHECK (family IN ('REF01','P01','P02','D01','N01','N03','D02','D03','D04','F04','F05','S02','F06','CTX06','CTX14','REF03','D05','F01','F02','F03','N02','S01','CTX02','CTX07')),
 unit_key text NOT NULL CHECK (length(unit_key) BETWEEN 1 AND 512),
 mode text NOT NULL CHECK(mode IN ('retained_source_reuse','provider_acquisition')),
 source_receipt_sha256 text NOT NULL CHECK (source_receipt_sha256 ~ '^[0-9a-f]{64}$'),
 original_deadline timestamptz NOT NULL,
 max_requests int NOT NULL CHECK(max_requests BETWEEN 0 AND 200),
 max_records int NOT NULL CHECK(max_records BETWEEN 1 AND 1000000),
 predecessors text[] NOT NULL DEFAULT '{}'::text[],
 status text NOT NULL DEFAULT 'pending' CHECK(status IN ('pending','claimed','verified','blocked','cancelled')),
 claim_owner text,
 claim_fence bigint NOT NULL DEFAULT 0 CHECK(claim_fence>=0),
 claim_until timestamptz,
 attempts int NOT NULL DEFAULT 0 CHECK(attempts BETWEEN 0 AND 2),
 requests_committed int NOT NULL DEFAULT 0 CHECK(requests_committed>=0 AND requests_committed<=max_requests),
 records_committed bigint NOT NULL DEFAULT 0 CHECK(records_committed>=0 AND records_committed<=max_records),
 last_page int NOT NULL DEFAULT -1 CHECK(last_page>=-1),
 last_committed_at timestamptz,
 verified_attestation_sha256 text CHECK(verified_attestation_sha256 ~ '^[0-9a-f]{64}$'),
 created_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 UNIQUE(manifest_sha256,family,unit_key),
 CHECK ((mode='retained_source_reuse' AND max_requests=0) OR (mode='provider_acquisition' AND max_requests>0)),
 CHECK ((status='claimed' AND claim_owner IS NOT NULL AND claim_until IS NOT NULL) OR (status <> 'claimed' AND claim_owner IS NULL AND claim_until IS NULL)),
 CHECK ((status='verified' AND verified_attestation_sha256 IS NOT NULL) OR (status <> 'verified' AND verified_attestation_sha256 IS NULL))
);
CREATE TABLE astra_ingestion_v1.bulk_receipt_v1 (
 work_key text NOT NULL REFERENCES astra_ingestion_v1.bulk_work_v1(work_key),
 page_no int NOT NULL CHECK(page_no>=0),
 source_sha256 text NOT NULL CHECK (source_sha256 ~ '^[0-9a-f]{64}$'),
 output_sha256 text NOT NULL CHECK (output_sha256 ~ '^[0-9a-f]{64}$'),
 records_committed int NOT NULL CHECK(records_committed BETWEEN 0 AND 1000000),
 requests_committed int NOT NULL CHECK(requests_committed BETWEEN 0 AND 200),
 committed_at timestamptz NOT NULL DEFAULT clock_timestamp(),
 PRIMARY KEY (work_key,page_no)
);
CREATE FUNCTION astra_ingestion_v1.bulk_manifest_guard_v1() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER
SET search_path=pg_catalog AS $$ BEGIN
 IF NEW.manifest_sha256 IS DISTINCT FROM OLD.manifest_sha256 OR NEW.capture_key IS DISTINCT FROM OLD.capture_key
  OR NEW.capture_receipt_sha256 IS DISTINCT FROM OLD.capture_receipt_sha256
  OR NEW.max_requests IS DISTINCT FROM OLD.max_requests OR NEW.max_records IS DISTINCT FROM OLD.max_records
  OR NEW.created_at IS DISTINCT FROM OLD.created_at OR NEW.reserved_requests<OLD.reserved_requests
  OR NEW.reserved_records<OLD.reserved_records OR (OLD.stopped AND NOT NEW.stopped)
  OR (OLD.stopped AND NEW.stop_reason IS DISTINCT FROM OLD.stop_reason) THEN
   RAISE EXCEPTION 'bulk manifest pins, budgets and stop are irreversible';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER bulk_manifest_guard_v1 BEFORE UPDATE ON astra_ingestion_v1.bulk_manifest_v1
 FOR EACH ROW EXECUTE FUNCTION astra_ingestion_v1.bulk_manifest_guard_v1();
CREATE FUNCTION astra_ingestion_v1.bulk_work_guard_v1() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER
SET search_path=pg_catalog AS $$ BEGIN
 IF NEW.work_key IS DISTINCT FROM OLD.work_key OR NEW.manifest_sha256 IS DISTINCT FROM OLD.manifest_sha256
  OR NEW.family IS DISTINCT FROM OLD.family OR NEW.unit_key IS DISTINCT FROM OLD.unit_key
  OR NEW.mode IS DISTINCT FROM OLD.mode OR NEW.source_receipt_sha256 IS DISTINCT FROM OLD.source_receipt_sha256
  OR NEW.original_deadline IS DISTINCT FROM OLD.original_deadline OR NEW.max_requests IS DISTINCT FROM OLD.max_requests
  OR NEW.max_records IS DISTINCT FROM OLD.max_records OR NEW.predecessors IS DISTINCT FROM OLD.predecessors
  OR NEW.created_at IS DISTINCT FROM OLD.created_at OR NEW.claim_fence<OLD.claim_fence
  OR NEW.attempts<OLD.attempts OR NEW.requests_committed<OLD.requests_committed
  OR NEW.records_committed<OLD.records_committed OR NEW.last_page<OLD.last_page
  OR (OLD.status IN ('verified','cancelled') AND NEW.status IS DISTINCT FROM OLD.status) THEN
   RAISE EXCEPTION 'bulk work scope, original deadline, counters or terminal outcome may not be changed';
 END IF;
 RETURN NEW;
END $$;
CREATE TRIGGER bulk_work_guard_v1 BEFORE UPDATE ON astra_ingestion_v1.bulk_work_v1
 FOR EACH ROW EXECUTE FUNCTION astra_ingestion_v1.bulk_work_guard_v1();
CREATE INDEX bulk_work_claimable_v1 ON astra_ingestion_v1.bulk_work_v1(manifest_sha256,status,original_deadline,work_key);
CREATE INDEX bulk_work_predecessor_v1 ON astra_ingestion_v1.bulk_work_v1(manifest_sha256);
ALTER TABLE astra_ingestion_v1.bulk_manifest_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE astra_ingestion_v1.bulk_work_v1 ENABLE ROW LEVEL SECURITY;
ALTER TABLE astra_ingestion_v1.bulk_receipt_v1 ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON astra_ingestion_v1.bulk_manifest_v1, astra_ingestion_v1.bulk_work_v1, astra_ingestion_v1.bulk_receipt_v1 FROM PUBLIC;

CREATE FUNCTION astra_ingestion_v1.bulk_receipt_immutable_v1() RETURNS trigger LANGUAGE plpgsql
SECURITY INVOKER SET search_path=pg_catalog AS $$ BEGIN
 RAISE EXCEPTION 'bulk receipts are immutable';
END $$;
CREATE TRIGGER bulk_receipt_no_mutation_v1 BEFORE UPDATE OR DELETE OR TRUNCATE ON astra_ingestion_v1.bulk_receipt_v1
 FOR EACH STATEMENT EXECUTE FUNCTION astra_ingestion_v1.bulk_receipt_immutable_v1();

CREATE FUNCTION astra_ingestion_v1.bulk_manifest_create_v1(p_manifest text,p_capture text,p_receipt text,p_max_requests bigint,p_max_records bigint)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog SET timezone='UTC' AS $$
DECLARE result jsonb; captured record;
BEGIN
 IF p_manifest !~ '^[0-9a-f]{64}$' OR p_capture IS DISTINCT FROM 'top3000-augsep2026-retained-scope-v1'
    OR p_receipt IS DISTINCT FROM 'ba13899b530288b6aae8d4af3a429efa3f4bd5ec305a7dc698f98c9d552f4496'
    OR p_max_requests IS NULL OR p_max_requests NOT BETWEEN 0 AND 1000000000
    OR p_max_records IS NULL OR p_max_records NOT BETWEEN 1 AND 1000000000000 THEN
   RAISE EXCEPTION 'invalid pinned bulk manifest or finite resource budget';
 END IF;
 SELECT evidence_sha256,evidence_rows,state,provider_requests,incremental_cost_microusd INTO captured
 FROM astra_ingestion_v1.bulk_scope_capture_v1 WHERE capture_key=p_capture;
 IF NOT FOUND OR captured.evidence_sha256 IS DISTINCT FROM p_receipt OR captured.evidence_rows IS DISTINCT FROM 4136
    OR captured.state IS DISTINCT FROM 'CAPTURED_NOT_ADMITTED' OR captured.provider_requests IS DISTINCT FROM 0
    OR captured.incremental_cost_microusd IS DISTINCT FROM 0 THEN
   RAISE EXCEPTION 'retained scope capture missing or changed';
 END IF;
 INSERT INTO astra_ingestion_v1.bulk_manifest_v1(manifest_sha256,capture_key,capture_receipt_sha256,max_requests,max_records)
 VALUES(p_manifest,p_capture,p_receipt,p_max_requests,p_max_records) ON CONFLICT DO NOTHING;
 SELECT to_jsonb(m) INTO result FROM astra_ingestion_v1.bulk_manifest_v1 m WHERE manifest_sha256=p_manifest;
 IF result IS NULL OR result->>'capture_key' IS DISTINCT FROM p_capture
   OR result->>'capture_receipt_sha256' IS DISTINCT FROM p_receipt
   OR (result->>'max_requests')::bigint IS DISTINCT FROM p_max_requests
   OR (result->>'max_records')::bigint IS DISTINCT FROM p_max_records THEN
   RAISE EXCEPTION 'bulk manifest idempotency collision';
 END IF;
 RETURN result;
END $$;

CREATE FUNCTION astra_ingestion_v1.bulk_reserve_v1(p_manifest text,p_family text,p_unit text,p_mode text,p_source text,
  p_deadline timestamptz,p_max_requests int,p_max_records int,p_predecessors text[] DEFAULT '{}'::text[])
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog SET timezone='UTC' AS $$
DECLARE m record; k text; existing record; distinct_predecessors int;
BEGIN
 IF p_family IS NULL OR p_family NOT IN ('REF01','P01','P02','D01','N01','N03','D02','D03','D04','F04','F05','S02','F06','CTX06','CTX14','REF03','D05','F01','F02','F03','N02','S01','CTX02','CTX07')
 OR p_unit IS NULL OR length(p_unit) NOT BETWEEN 1 AND 512 OR p_mode NOT IN ('retained_source_reuse','provider_acquisition')
 OR p_source !~ '^[0-9a-f]{64}$' OR p_deadline IS NULL OR p_deadline <= clock_timestamp()
 OR p_max_requests IS NULL OR p_max_requests NOT BETWEEN 0 AND 200
 OR p_max_records IS NULL OR p_max_records NOT BETWEEN 1 AND 1000000
 OR NOT ((p_mode='retained_source_reuse' AND p_max_requests=0) OR (p_mode='provider_acquisition' AND p_max_requests>0))
 OR p_predecessors IS NULL OR array_position(p_predecessors,NULL) IS NOT NULL THEN
  RAISE EXCEPTION 'invalid bounded bulk partition';
 END IF;
 -- This key is manifest, contract/source, original deadline and accounting bound.
 k := 'astra-bulk-v1-'||encode(sha256(convert_to(jsonb_build_array(p_manifest,p_family,p_unit,p_mode,p_source,
         p_deadline,p_max_requests,p_max_records,p_predecessors)::text,'UTF8')),'hex');
 SELECT * INTO m FROM astra_ingestion_v1.bulk_manifest_v1 WHERE manifest_sha256=p_manifest FOR UPDATE;
 IF NOT FOUND OR m.stopped THEN RAISE EXCEPTION 'manifest missing or stopped'; END IF;
 SELECT * INTO existing FROM astra_ingestion_v1.bulk_work_v1 WHERE work_key=k;
 IF FOUND THEN
   RETURN to_jsonb(existing);
 END IF;
 IF (SELECT count(*) FROM unnest(p_predecessors) AS d(k)) IS DISTINCT FROM
    (SELECT count(DISTINCT d.k) FROM unnest(p_predecessors) AS d(k)) THEN
   RAISE EXCEPTION 'duplicate dependency';
 END IF;
 IF p_predecessors IS DISTINCT FROM COALESCE((SELECT array_agg(d.k ORDER BY d.k)
   FROM unnest(p_predecessors) AS d(k)),ARRAY[]::text[]) THEN
   RAISE EXCEPTION 'dependency keys must be deterministically sorted';
 END IF;
 IF EXISTS(SELECT 1 FROM unnest(p_predecessors) AS d(k)
   LEFT JOIN astra_ingestion_v1.bulk_work_v1 w ON w.work_key=d.k AND w.manifest_sha256=p_manifest
   WHERE w.work_key IS NULL) THEN RAISE EXCEPTION 'missing dependency in manifest'; END IF;
 -- Only predecessors already registered may be referenced, preventing graph cycles.
 IF m.reserved_requests+p_max_requests > m.max_requests OR m.reserved_records+p_max_records > m.max_records THEN
   RAISE EXCEPTION 'cumulative immutable budget exhausted';
 END IF;
 INSERT INTO astra_ingestion_v1.bulk_work_v1(work_key,manifest_sha256,family,unit_key,mode,source_receipt_sha256,original_deadline,max_requests,max_records,predecessors)
 VALUES(k,p_manifest,p_family,p_unit,p_mode,p_source,p_deadline,p_max_requests,p_max_records,p_predecessors);
 UPDATE astra_ingestion_v1.bulk_manifest_v1 SET reserved_requests=reserved_requests+p_max_requests,
   reserved_records=reserved_records+p_max_records WHERE manifest_sha256=p_manifest;
 RETURN (SELECT to_jsonb(w) FROM astra_ingestion_v1.bulk_work_v1 w WHERE work_key=k);
END $$;

CREATE FUNCTION astra_ingestion_v1.bulk_claim_v1(p_manifest text,p_owner text,p_lease_seconds int)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog SET timezone='UTC' AS $$
DECLARE w record;
BEGIN
 IF p_owner IS NULL OR length(p_owner) NOT BETWEEN 1 AND 128 OR p_lease_seconds IS NULL OR p_lease_seconds NOT BETWEEN 10 AND 180 THEN
  RAISE EXCEPTION 'invalid finite claim identity or lease';
 END IF;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.bulk_manifest_v1 WHERE manifest_sha256=p_manifest AND NOT stopped) THEN
  RETURN NULL;
 END IF;
 SELECT * INTO w FROM astra_ingestion_v1.bulk_work_v1 w1
 WHERE w1.manifest_sha256=p_manifest AND w1.status='pending' AND w1.attempts<2
   AND w1.original_deadline>clock_timestamp()
   AND NOT EXISTS(SELECT 1 FROM unnest(w1.predecessors) AS d(k)
       JOIN astra_ingestion_v1.bulk_work_v1 parent ON parent.work_key=d.k
       WHERE parent.status <> 'verified')
 ORDER BY w1.created_at,w1.work_key LIMIT 1 FOR UPDATE OF w1 SKIP LOCKED;
 IF NOT FOUND THEN RETURN NULL; END IF;
 UPDATE astra_ingestion_v1.bulk_work_v1 SET status='claimed',claim_owner=p_owner,
   claim_fence=claim_fence+1,claim_until=LEAST(original_deadline,clock_timestamp()+(p_lease_seconds||' seconds')::interval),
   attempts=attempts+1 WHERE work_key=w.work_key;
 RETURN (SELECT to_jsonb(x) FROM astra_ingestion_v1.bulk_work_v1 x WHERE work_key=w.work_key);
END $$;

CREATE FUNCTION astra_ingestion_v1.bulk_commit_page_v1(p_work text,p_owner text,p_fence bigint,p_page int,p_source text,p_output text,p_records int,p_requests int)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog SET timezone='UTC' AS $$
DECLARE w record; r record;
BEGIN
 SELECT * INTO w FROM astra_ingestion_v1.bulk_work_v1 WHERE work_key=p_work FOR UPDATE;
 IF NOT FOUND THEN RAISE EXCEPTION 'unknown bulk work'; END IF;
 SELECT * INTO r FROM astra_ingestion_v1.bulk_receipt_v1 WHERE work_key=p_work AND page_no=p_page;
 IF FOUND THEN
   IF r.source_sha256 IS DISTINCT FROM p_source OR r.output_sha256 IS DISTINCT FROM p_output
     OR r.records_committed IS DISTINCT FROM p_records OR r.requests_committed IS DISTINCT FROM p_requests THEN
      RAISE EXCEPTION 'uncertain receipt conflict, no replay';
   END IF;
   RETURN to_jsonb(r); -- Previously committed exact effects; never double increment.
 END IF;
 IF w.status <> 'claimed' OR w.claim_owner IS DISTINCT FROM p_owner OR w.claim_fence IS DISTINCT FROM p_fence
   OR w.claim_until <= clock_timestamp() OR w.original_deadline <= clock_timestamp()
   OR EXISTS(SELECT 1 FROM astra_ingestion_v1.bulk_manifest_v1 m WHERE m.manifest_sha256=w.manifest_sha256 AND m.stopped)
   OR p_page IS NULL OR p_page <> w.last_page+1 OR p_source !~ '^[0-9a-f]{64}$' OR p_output !~ '^[0-9a-f]{64}$'
   OR p_records IS NULL OR p_records NOT BETWEEN 0 AND 1000000 OR p_requests IS NULL OR p_requests NOT BETWEEN 0 AND 200
   OR w.records_committed+p_records > w.max_records OR w.requests_committed+p_requests > w.max_requests THEN
   RAISE EXCEPTION 'stale owner, stop, deadline, sequence or bounded receipt violation';
 END IF;
 INSERT INTO astra_ingestion_v1.bulk_receipt_v1(work_key,page_no,source_sha256,output_sha256,records_committed,requests_committed)
 VALUES(p_work,p_page,p_source,p_output,p_records,p_requests);
 UPDATE astra_ingestion_v1.bulk_work_v1 SET records_committed=records_committed+p_records,
 requests_committed=requests_committed+p_requests,last_page=p_page,last_committed_at=clock_timestamp() WHERE work_key=p_work;
 RETURN (SELECT to_jsonb(x) FROM astra_ingestion_v1.bulk_receipt_v1 x WHERE x.work_key=p_work AND x.page_no=p_page);
END $$;

CREATE FUNCTION astra_ingestion_v1.bulk_verify_v1(p_work text,p_owner text,p_fence bigint,p_attestation text)
RETURNS jsonb LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog SET timezone='UTC' AS $$
DECLARE w record;
BEGIN
 SELECT * INTO w FROM astra_ingestion_v1.bulk_work_v1 WHERE work_key=p_work FOR UPDATE;
 IF NOT FOUND OR w.status <> 'claimed' OR w.claim_owner IS DISTINCT FROM p_owner OR w.claim_fence IS DISTINCT FROM p_fence
   OR w.claim_until <= clock_timestamp() OR w.original_deadline <= clock_timestamp()
   OR p_attestation !~ '^[0-9a-f]{64}$' OR w.last_page<0 OR w.records_committed=0
   OR EXISTS(SELECT 1 FROM astra_ingestion_v1.bulk_manifest_v1 m WHERE m.manifest_sha256=w.manifest_sha256 AND m.stopped) THEN
   RAISE EXCEPTION 'verification requires active exact owner, receipts and independent attestation';
 END IF;
 UPDATE astra_ingestion_v1.bulk_work_v1 SET status='verified',claim_owner=NULL,claim_until=NULL,
 verified_attestation_sha256=p_attestation WHERE work_key=p_work;
 RETURN (SELECT to_jsonb(x) FROM astra_ingestion_v1.bulk_work_v1 x WHERE work_key=p_work);
END $$;

CREATE FUNCTION astra_ingestion_v1.bulk_stop_v1(p_manifest text,p_reason text)
RETURNS boolean LANGUAGE plpgsql SECURITY INVOKER SET search_path=pg_catalog AS $$
BEGIN
 IF p_reason IS NULL OR length(p_reason) NOT BETWEEN 1 AND 500 THEN
  RAISE EXCEPTION 'bounded explicit stop reason required';
 END IF;
 UPDATE astra_ingestion_v1.bulk_manifest_v1 SET stopped=true,
   stop_reason=COALESCE(stop_reason,p_reason) WHERE manifest_sha256=p_manifest;
 RETURN FOUND;
END $$;

REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_manifest_guard_v1() FROM PUBLIC;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_work_guard_v1() FROM PUBLIC;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_receipt_immutable_v1() FROM PUBLIC;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_manifest_create_v1(text,text,text,bigint,bigint) FROM PUBLIC;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_reserve_v1(text,text,text,text,text,timestamptz,int,int,text[]) FROM PUBLIC;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_claim_v1(text,text,int) FROM PUBLIC;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_commit_page_v1(text,text,bigint,int,text,text,int,int) FROM PUBLIC;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_verify_v1(text,text,bigint,text) FROM PUBLIC;
REVOKE ALL ON FUNCTION astra_ingestion_v1.bulk_stop_v1(text,text) FROM PUBLIC;
COMMIT;