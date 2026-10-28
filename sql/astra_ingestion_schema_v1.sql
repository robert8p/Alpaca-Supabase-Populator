-- PREPARED OFFLINE. Not executed. Target: oxzabweahkoimtevbbny.
-- Same tables, indexes, seeds and trigger bodies as Store.migrate; strict admission and scoped ACL cleanup added.
BEGIN;
SET LOCAL statement_timeout = '10s';
SET LOCAL lock_timeout = '3s';
SET LOCAL search_path = pg_catalog;

SELECT pg_advisory_xact_lock(706314020261028);

DO $admission$
BEGIN
  IF pg_catalog.to_regnamespace('astra_ingestion_v1') IS NOT NULL THEN
    RAISE EXCEPTION 'Admission refused: astra_ingestion_v1 already exists; reconcile before retry';
  END IF;
END
$admission$;

CREATE SCHEMA IF NOT EXISTS astra_ingestion_v1;

REVOKE ALL ON SCHEMA astra_ingestion_v1 FROM PUBLIC;

CREATE TABLE IF NOT EXISTS astra_ingestion_v1.schema_info (id INTEGER PRIMARY KEY, version INTEGER NOT NULL);

CREATE TABLE IF NOT EXISTS astra_ingestion_v1.jobs (
                id TEXT PRIMARY KEY, request_key TEXT UNIQUE NOT NULL, scope_hash TEXT NOT NULL,
                name TEXT NOT NULL, spec TEXT NOT NULL, status TEXT NOT NULL,
                verification_status TEXT NOT NULL DEFAULT 'pending',
                created_at DOUBLE PRECISION NOT NULL, updated_at DOUBLE PRECISION NOT NULL,
                last_progress_at DOUBLE PRECISION, deadline_at DOUBLE PRECISION NOT NULL,
                request_count INTEGER NOT NULL DEFAULT 0, record_count INTEGER NOT NULL DEFAULT 0,
                receipt_bytes INTEGER NOT NULL DEFAULT 0, error TEXT);

CREATE TABLE IF NOT EXISTS astra_ingestion_v1.partitions (
                id TEXT PRIMARY KEY, job_id TEXT NOT NULL REFERENCES astra_ingestion_v1.jobs(id),
                symbol TEXT NOT NULL, start_at TEXT NOT NULL, end_at TEXT NOT NULL,
                status TEXT NOT NULL, verification_status TEXT NOT NULL DEFAULT 'pending',
                owner TEXT, generation INTEGER NOT NULL DEFAULT 0, lease_until DOUBLE PRECISION,
                retry_count INTEGER NOT NULL DEFAULT 0, next_attempt_at DOUBLE PRECISION NOT NULL DEFAULT 0,
                next_page_token TEXT, page_count INTEGER NOT NULL DEFAULT 0,
                record_count INTEGER NOT NULL DEFAULT 0, request_count INTEGER NOT NULL DEFAULT 0,
                last_progress_at DOUBLE PRECISION, error TEXT,
                UNIQUE(job_id,symbol,start_at,end_at));

CREATE TABLE IF NOT EXISTS astra_ingestion_v1.receipts (
                partition_id TEXT NOT NULL REFERENCES astra_ingestion_v1.partitions(id), page_no INTEGER NOT NULL,
                token_in TEXT, token_out TEXT, request_id TEXT, raw_body TEXT NOT NULL,
                body_sha256 TEXT NOT NULL, received_at DOUBLE PRECISION NOT NULL,
                PRIMARY KEY(partition_id,page_no));

CREATE TABLE IF NOT EXISTS astra_ingestion_v1.records (
                partition_id TEXT NOT NULL REFERENCES astra_ingestion_v1.partitions(id),
                record_key TEXT NOT NULL, payload TEXT NOT NULL,
                PRIMARY KEY(partition_id,record_key));

CREATE TABLE IF NOT EXISTS astra_ingestion_v1.verifications (
                partition_id TEXT PRIMARY KEY REFERENCES astra_ingestion_v1.partitions(id),
                checked_at DOUBLE PRECISION NOT NULL, result TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS astra_ingestion_v1.events (
                id TEXT PRIMARY KEY, job_id TEXT REFERENCES astra_ingestion_v1.jobs(id),
                timestamp DOUBLE PRECISION NOT NULL, event TEXT NOT NULL, detail TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS astra_ingestion_v1.rejections (
                id TEXT PRIMARY KEY, partition_id TEXT NOT NULL REFERENCES astra_ingestion_v1.partitions(id),
                received_at DOUBLE PRECISION NOT NULL, reason TEXT NOT NULL,
                raw_body TEXT NOT NULL, body_sha256 TEXT NOT NULL);

CREATE TABLE IF NOT EXISTS astra_ingestion_v1.source_limits (id TEXT PRIMARY KEY, next_request_at DOUBLE PRECISION NOT NULL);

CREATE INDEX IF NOT EXISTS ingestion_partition_ready ON astra_ingestion_v1.partitions(status,next_attempt_at);

CREATE INDEX IF NOT EXISTS ingestion_event_job ON astra_ingestion_v1.events(job_id,timestamp);

INSERT INTO astra_ingestion_v1.schema_info(id,version) VALUES(1,1) ON CONFLICT(id) DO NOTHING;

INSERT INTO astra_ingestion_v1.source_limits(id,next_request_at) VALUES('alpaca',0) ON CONFLICT(id) DO NOTHING;

DO $schema_version$
BEGIN
  IF (SELECT version FROM astra_ingestion_v1.schema_info WHERE id=1) IS DISTINCT FROM 1 THEN
    RAISE EXCEPTION 'Unsupported existing schema version';
  END IF;
END
$schema_version$;

REVOKE ALL ON ALL TABLES IN SCHEMA astra_ingestion_v1 FROM PUBLIC;

CREATE OR REPLACE FUNCTION astra_ingestion_v1.guard_job_scope() RETURNS trigger
                    LANGUAGE plpgsql SET search_path = '' AS $$
                    BEGIN
                    IF NEW.spec IS DISTINCT FROM OLD.spec OR NEW.scope_hash IS DISTINCT FROM OLD.scope_hash
                       OR NEW.request_key IS DISTINCT FROM OLD.request_key THEN
                      RAISE EXCEPTION 'Job scope is immutable';
                    END IF; RETURN NEW; END $$;

DROP TRIGGER IF EXISTS immutable_job_scope ON astra_ingestion_v1.jobs;

CREATE TRIGGER immutable_job_scope BEFORE UPDATE ON astra_ingestion_v1.jobs
                    FOR EACH ROW EXECUTE FUNCTION astra_ingestion_v1.guard_job_scope();

REVOKE ALL ON FUNCTION astra_ingestion_v1.guard_job_scope() FROM PUBLIC;

CREATE OR REPLACE FUNCTION astra_ingestion_v1.guard_partition_scope() RETURNS trigger
                    LANGUAGE plpgsql SET search_path = '' AS $$
                    BEGIN
                    IF NEW.job_id IS DISTINCT FROM OLD.job_id OR NEW.symbol IS DISTINCT FROM OLD.symbol
                       OR NEW.start_at IS DISTINCT FROM OLD.start_at OR NEW.end_at IS DISTINCT FROM OLD.end_at THEN
                      RAISE EXCEPTION 'Partition scope is immutable';
                    END IF; RETURN NEW; END $$;

DROP TRIGGER IF EXISTS immutable_partition_scope ON astra_ingestion_v1.partitions;

CREATE TRIGGER immutable_partition_scope BEFORE UPDATE ON astra_ingestion_v1.partitions
                    FOR EACH ROW EXECUTE FUNCTION astra_ingestion_v1.guard_partition_scope();

REVOKE ALL ON FUNCTION astra_ingestion_v1.guard_partition_scope() FROM PUBLIC;

-- Privacy boundary: remove PUBLIC and all non-owner object grants.
-- This also clears grants that were copied from the migration owner's default ACL.
-- Re-run this block inside every later schema migration that creates new objects.
REVOKE ALL ON SCHEMA astra_ingestion_v1 FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA astra_ingestion_v1 FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA astra_ingestion_v1 FROM PUBLIC;
REVOKE ALL ON ALL SEQUENCES IN SCHEMA astra_ingestion_v1 FROM PUBLIC;
DO $private_objects$
DECLARE
  schema_owner oid;
  role_to_revoke record;
BEGIN
  SELECT nspowner INTO STRICT schema_owner
  FROM pg_catalog.pg_namespace WHERE nspname='astra_ingestion_v1';
  IF EXISTS (
    SELECT 1 FROM pg_catalog.pg_class c
    JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
    WHERE n.nspname='astra_ingestion_v1' AND c.relowner<>schema_owner
  ) OR EXISTS (
    SELECT 1 FROM pg_catalog.pg_proc p
    JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname='astra_ingestion_v1' AND p.proowner<>schema_owner
  ) THEN
    RAISE EXCEPTION 'Admission refused: ingestion objects have unexpected mixed owners';
  END IF;
  FOR role_to_revoke IN
    WITH explicit_grantees AS (
      SELECT a.grantee
      FROM pg_catalog.pg_namespace n
      CROSS JOIN LATERAL pg_catalog.aclexplode(n.nspacl) a
      WHERE n.nspname='astra_ingestion_v1'
      UNION
      SELECT a.grantee
      FROM pg_catalog.pg_class c
      JOIN pg_catalog.pg_namespace n ON n.oid=c.relnamespace
      CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) a
      WHERE n.nspname='astra_ingestion_v1'
      UNION
      SELECT a.grantee
      FROM pg_catalog.pg_proc p
      JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
      CROSS JOIN LATERAL pg_catalog.aclexplode(p.proacl) a
      WHERE n.nspname='astra_ingestion_v1'
    )
    SELECT DISTINCT r.rolname
    FROM explicit_grantees g
    JOIN pg_catalog.pg_roles r ON r.oid=g.grantee
    WHERE g.grantee<>schema_owner
  LOOP
    EXECUTE pg_catalog.format('REVOKE ALL ON SCHEMA astra_ingestion_v1 FROM %I', role_to_revoke.rolname);
    EXECUTE pg_catalog.format('REVOKE ALL ON ALL TABLES IN SCHEMA astra_ingestion_v1 FROM %I', role_to_revoke.rolname);
    EXECUTE pg_catalog.format('REVOKE ALL ON ALL FUNCTIONS IN SCHEMA astra_ingestion_v1 FROM %I', role_to_revoke.rolname);
    EXECUTE pg_catalog.format('REVOKE ALL ON ALL SEQUENCES IN SCHEMA astra_ingestion_v1 FROM %I', role_to_revoke.rolname);
  END LOOP;
END
$private_objects$;

-- Defense in depth: no runtime policies exist at schema-only completion.
ALTER TABLE astra_ingestion_v1.schema_info ENABLE ROW LEVEL SECURITY;
ALTER TABLE astra_ingestion_v1.jobs ENABLE ROW LEVEL SECURITY;
ALTER TABLE astra_ingestion_v1.partitions ENABLE ROW LEVEL SECURITY;
ALTER TABLE astra_ingestion_v1.receipts ENABLE ROW LEVEL SECURITY;
ALTER TABLE astra_ingestion_v1.records ENABLE ROW LEVEL SECURITY;
ALTER TABLE astra_ingestion_v1.verifications ENABLE ROW LEVEL SECURITY;
ALTER TABLE astra_ingestion_v1.events ENABLE ROW LEVEL SECURITY;
ALTER TABLE astra_ingestion_v1.rejections ENABLE ROW LEVEL SECURITY;
ALTER TABLE astra_ingestion_v1.source_limits ENABLE ROW LEVEL SECURITY;

COMMIT;
