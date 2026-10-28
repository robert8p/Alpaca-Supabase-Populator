-- Apply only to the new isolated schema with an authorised migration identity.
-- No passwords or LOGIN activation. This is a one-time fresh-role setup.
-- Existing same-name roles cause a full rollback, even if they appear harmless.
BEGIN;
SET LOCAL statement_timeout = '10s';
SET LOCAL lock_timeout = '3s';
SET LOCAL search_path = pg_catalog;
SELECT pg_advisory_xact_lock(706314020261028);

-- Explicit fresh-role admission: never silently adopt a colliding role.
DO $runtime_roles$
BEGIN
  IF pg_catalog.to_regnamespace('astra_ingestion_v1') IS NULL THEN
    RAISE EXCEPTION 'Admission refused: ingestion schema is missing';
  END IF;
  IF EXISTS (SELECT 1 FROM pg_catalog.pg_roles WHERE rolname IN ('astra_ingestion_api','astra_ingestion_worker')) THEN
    RAISE EXCEPTION 'Admission refused: ingestion role name already exists; inspect it before retry';
  END IF;
  CREATE ROLE astra_ingestion_api NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  CREATE ROLE astra_ingestion_worker NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
END
$runtime_roles$;

-- Strict outside-schema denial cannot be achieved when PUBLIC exposes pg_net.
-- NOINHERIT does not exclude PUBLIC. Do not alter provider-owned net grants here.
-- This check intentionally aborts the full setup on the currently observed target.
DO $pg_net_admission$
DECLARE
  runtime_role text;
  net_schema oid;
BEGIN
  SELECT oid INTO net_schema FROM pg_catalog.pg_namespace WHERE nspname='net';
  IF net_schema IS NOT NULL THEN
    FOREACH runtime_role IN ARRAY ARRAY['astra_ingestion_api','astra_ingestion_worker']
    LOOP
      IF pg_catalog.has_schema_privilege(runtime_role,net_schema,'USAGE') AND EXISTS (
        SELECT 1 FROM pg_catalog.pg_class c
        WHERE c.relnamespace=net_schema
          AND c.relkind IN ('r','p','v','m','f')
          AND c.relname IN ('_http_response','http_request_queue')
          AND pg_catalog.has_table_privilege(runtime_role,c.oid,'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')
      ) THEN
        RAISE EXCEPTION 'Runtime isolation admission refused: % inherits pg_net access; preserve the hold and change access architecture', runtime_role;
      END IF;
    END LOOP;
  END IF;
END
$pg_net_admission$;

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

GRANT USAGE ON SCHEMA astra_ingestion_v1 TO astra_ingestion_api, astra_ingestion_worker;
GRANT SELECT ON astra_ingestion_v1.schema_info TO astra_ingestion_api, astra_ingestion_worker;
GRANT SELECT, INSERT, UPDATE ON astra_ingestion_v1.jobs, astra_ingestion_v1.partitions TO astra_ingestion_api;
GRANT SELECT, INSERT ON astra_ingestion_v1.events TO astra_ingestion_api;
GRANT SELECT ON astra_ingestion_v1.verifications TO astra_ingestion_api;
GRANT SELECT, UPDATE ON astra_ingestion_v1.jobs, astra_ingestion_v1.partitions, astra_ingestion_v1.source_limits TO astra_ingestion_worker;
GRANT SELECT, INSERT ON astra_ingestion_v1.receipts, astra_ingestion_v1.records, astra_ingestion_v1.rejections, astra_ingestion_v1.events TO astra_ingestion_worker;
GRANT SELECT, INSERT, UPDATE ON astra_ingestion_v1.verifications TO astra_ingestion_worker;
DO $$
DECLARE table_name text;
BEGIN
  FOREACH table_name IN ARRAY ARRAY['schema_info','jobs','partitions','receipts','records','verifications','events','rejections','source_limits']
  LOOP
    EXECUTE format('ALTER TABLE astra_ingestion_v1.%I ENABLE ROW LEVEL SECURITY', table_name);
    EXECUTE format('DROP POLICY IF EXISTS ingestion_runtime_roles ON astra_ingestion_v1.%I', table_name);
    EXECUTE format('CREATE POLICY ingestion_runtime_roles ON astra_ingestion_v1.%I TO astra_ingestion_api,astra_ingestion_worker USING (true) WITH CHECK (true)', table_name);
  END LOOP;
END $$;
-- No privileges on legacy rd_* tables, scanner schemas or canonical research.
-- Application roles cannot update/delete retained source receipts or records.

COMMIT;
