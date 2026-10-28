-- Apply with an authorised migration identity AFTER explicit Store.migrate().
-- No passwords are included. Activate LOGIN through the approved secret flow.
DO $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='astra_ingestion_api') THEN
    CREATE ROLE astra_ingestion_api NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
  IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname='astra_ingestion_worker') THEN
    CREATE ROLE astra_ingestion_worker NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  END IF;
END $$;
REVOKE ALL ON SCHEMA astra_ingestion_v1 FROM PUBLIC;
REVOKE ALL ON ALL TABLES IN SCHEMA astra_ingestion_v1 FROM PUBLIC;
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
