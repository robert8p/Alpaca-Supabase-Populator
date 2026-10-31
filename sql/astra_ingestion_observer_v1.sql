-- Additive, bounded independent useful-progress observer for ASTRA ingestion.
-- Reviewed candidate. Apply only AFTER disposable PostgreSQL qualification.
-- This migration creates NO pg_cron job; schedule separately after live DDL readback.
-- Never edit the existing ingestion dispatcher, receipts or jobs.
SET LOCAL statement_timeout = '30s';
SET LOCAL lock_timeout = '3s';
SET LOCAL search_path = pg_catalog;
SELECT pg_catalog.pg_advisory_xact_lock(706314020261028);

DO $admission$
BEGIN
  IF pg_catalog.to_regnamespace('astra_ingestion_v1') IS NULL
     OR (SELECT version FROM astra_ingestion_v1.schema_info WHERE id=1) IS DISTINCT FROM 1
     OR pg_catalog.to_regprocedure('astra_ingestion_v1.rpc_dispatch(text,jsonb)') IS NULL
     OR (SELECT COUNT(*) FROM pg_catalog.pg_class c JOIN pg_catalog.pg_namespace n ON c.relnamespace=n.oid
          WHERE n.nspname='astra_ingestion_v1' AND c.relkind='r') <> 10
     OR pg_catalog.to_regclass('astra_ingestion_v1.monitor_incidents') IS NOT NULL
     OR pg_catalog.to_regclass('astra_ingestion_v1.monitor_ticks') IS NOT NULL
     OR pg_catalog.to_regprocedure('astra_ingestion_v1.monitor_tick_v1()') IS NOT NULL
     OR EXISTS(SELECT 1 FROM pg_catalog.pg_roles WHERE rolname='astra_ingestion_monitor_owner_v1')
  THEN
    RAISE EXCEPTION 'Monitor migration refused: schema or monitor objects differ from admitted v1 baseline';
  END IF;
  CREATE ROLE astra_ingestion_monitor_owner_v1 NOLOGIN NOINHERIT NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION NOBYPASSRLS;
  EXECUTE pg_catalog.format('GRANT astra_ingestion_monitor_owner_v1 TO %I',current_user);
END $admission$;

CREATE TABLE astra_ingestion_v1.monitor_incidents (
  job_id text NOT NULL,
  partition_id text NOT NULL DEFAULT '',
  generation integer NOT NULL DEFAULT 0 CHECK (generation >= 0),
  reason text NOT NULL CHECK (reason IN ('deadline_overdue','lease_expired','eligible_unclaimed')),
  detected_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  observed_job_status text NOT NULL,
  observed_partition_status text,
  observed_progress_at double precision,
  observed_deadline_at double precision NOT NULL,
  observed_job_requests integer NOT NULL,
  observed_job_records integer NOT NULL,
  observed_partition_pages integer,
  disposition text NOT NULL DEFAULT 'FAIL_CLOSED_MANUAL_REVIEW'
    CHECK (disposition='FAIL_CLOSED_MANUAL_REVIEW'),
  PRIMARY KEY(job_id, partition_id, generation, reason)
);
CREATE TABLE astra_ingestion_v1.monitor_ticks (
  id uuid PRIMARY KEY DEFAULT pg_catalog.gen_random_uuid(),
  observed_at timestamptz NOT NULL DEFAULT pg_catalog.clock_timestamp(),
  active_jobs integer NOT NULL CHECK (active_jobs >= 0),
  new_incidents integer NOT NULL CHECK (new_incidents >= 0),
  observed_partitions integer NOT NULL CHECK (observed_partitions >= 0)
);
CREATE INDEX monitor_ticks_observed_at_idx ON astra_ingestion_v1.monitor_ticks(observed_at);
ALTER TABLE astra_ingestion_v1.monitor_incidents ENABLE ROW LEVEL SECURITY;
ALTER TABLE astra_ingestion_v1.monitor_ticks ENABLE ROW LEVEL SECURITY;

CREATE FUNCTION astra_ingestion_v1.monitor_tick_v1()
RETURNS jsonb LANGUAGE plpgsql VOLATILE SECURITY DEFINER
SET search_path = '' SET statement_timeout='8s' SET lock_timeout='2s' AS $monitor$
DECLARE
  v_now double precision := EXTRACT(EPOCH FROM pg_catalog.clock_timestamp());
  v_not_before double precision := 0;
  v_job astra_ingestion_v1.jobs%ROWTYPE;
  v_part record;
  v_reason text;
  v_new integer := 0;
  v_added integer := 0;
  v_active integer := 0;
  v_seen integer := 0;
BEGIN
  IF NOT pg_catalog.pg_try_advisory_xact_lock(706314020261029) THEN
    RETURN pg_catalog.jsonb_build_object('state','already_running');
  END IF;
  SELECT COALESCE(next_request_at,0) INTO v_not_before
    FROM astra_ingestion_v1.source_limits WHERE id='alpaca';
  v_not_before := COALESCE(v_not_before,0);
  SELECT COUNT(*) INTO v_active FROM astra_ingestion_v1.jobs
    WHERE status IN ('queued','running');

  -- Expired deadlines are a genuine useful-progress failure even if all
  -- workers are offline. Do not mutate an admitted job or extend its deadline.
  FOR v_job IN SELECT * FROM astra_ingestion_v1.jobs
     WHERE status IN ('queued','running') AND deadline_at <= v_now-60
  LOOP
    INSERT INTO astra_ingestion_v1.monitor_incidents
      (job_id,partition_id,generation,reason,observed_job_status,
       observed_deadline_at,observed_progress_at,observed_job_requests,observed_job_records)
    VALUES (v_job.id,'',0,'deadline_overdue',v_job.status,
            v_job.deadline_at,v_job.last_progress_at,v_job.request_count,v_job.record_count)
    ON CONFLICT DO NOTHING;
    GET DIAGNOSTICS v_added = ROW_COUNT;
    v_new := v_new+v_added;
  END LOOP;

  FOR v_part IN
    SELECT p.id,p.job_id,p.status,p.generation,p.lease_until,p.next_attempt_at,
           p.last_progress_at,p.page_count,
           j.status AS job_status,j.deadline_at,j.created_at,
           j.last_progress_at AS job_progress_at,j.request_count,j.record_count,
           (SELECT COUNT(*) FROM astra_ingestion_v1.partitions q
             WHERE q.job_id=p.job_id
               AND q.status IN ('running','verifying')
               AND q.lease_until>v_now) AS live_claims
      FROM astra_ingestion_v1.partitions p
      JOIN astra_ingestion_v1.jobs j ON j.id=p.job_id
     WHERE j.status IN ('queued','running') AND j.deadline_at>v_now
  LOOP
    v_seen := v_seen+1;
    v_reason := NULL;
    IF v_part.status IN ('running','verifying')
       AND v_part.lease_until IS NOT NULL
       AND v_part.lease_until<=v_now-60 THEN
       v_reason := 'lease_expired';
    ELSIF v_part.status IN ('pending','loaded')
       AND v_part.live_claims=0
       AND v_part.next_attempt_at<=v_now-240
       AND COALESCE(v_part.last_progress_at,v_part.created_at)<=v_now-240
       AND COALESCE(v_part.job_progress_at,v_part.created_at)<=v_now-240
       AND (v_part.status='loaded' OR v_not_before<=v_now) THEN
       v_reason := 'eligible_unclaimed';
    END IF;
    IF v_reason IS NOT NULL THEN
      INSERT INTO astra_ingestion_v1.monitor_incidents
        (job_id,partition_id,generation,reason,observed_job_status,
         observed_partition_status,observed_progress_at,observed_deadline_at,
         observed_job_requests,observed_job_records,observed_partition_pages)
      VALUES (v_part.job_id,v_part.id,v_part.generation,v_reason,
              v_part.job_status,v_part.status,v_part.last_progress_at,v_part.deadline_at,
              v_part.request_count,v_part.record_count,v_part.page_count)
      ON CONFLICT DO NOTHING;
      GET DIAGNOSTICS v_added = ROW_COUNT;
      v_new := v_new+v_added;
    END IF;
  END LOOP;
  INSERT INTO astra_ingestion_v1.monitor_ticks(active_jobs,new_incidents,observed_partitions)
  VALUES (v_active,v_new,v_seen);
  RETURN pg_catalog.jsonb_build_object('state','observed','active_jobs',v_active,
           'observed_partitions',v_seen,'new_incidents',v_new,
           'disposition','FAIL_CLOSED_MANUAL_REVIEW');
END
$monitor$;

-- Strip every inherited default grant before granting the deliberately narrow
-- observer privileges. The observer owns no tables, cannot update ingestion,
-- cannot dispatch provider requests, and has no runtime capability token.
DO $acl$
DECLARE v_table text; v_grantee record; v_object record;
BEGIN
  FOREACH v_table IN ARRAY ARRAY['monitor_incidents','monitor_ticks'] LOOP
    EXECUTE pg_catalog.format('REVOKE ALL ON astra_ingestion_v1.%I FROM PUBLIC',v_table);
    FOR v_grantee IN SELECT DISTINCT r.rolname
       FROM pg_catalog.pg_class c
       CROSS JOIN LATERAL pg_catalog.aclexplode(c.relacl) a
       JOIN pg_catalog.pg_roles r ON r.oid=a.grantee
       WHERE c.oid=pg_catalog.to_regclass('astra_ingestion_v1.'||v_table)
         AND a.grantee<>c.relowner
    LOOP
      EXECUTE pg_catalog.format('REVOKE ALL ON astra_ingestion_v1.%I FROM %I',v_table,v_grantee.rolname);
    END LOOP;
  END LOOP;
  FOR v_object IN
    SELECT p.oid,n.nspname,p.proname,pg_catalog.pg_get_function_identity_arguments(p.oid) args,p.proowner,p.proacl
    FROM pg_catalog.pg_proc p JOIN pg_catalog.pg_namespace n ON n.oid=p.pronamespace
    WHERE n.nspname='astra_ingestion_v1' AND p.proname='monitor_tick_v1'
  LOOP
    EXECUTE pg_catalog.format('REVOKE ALL ON FUNCTION %I.%I(%s) FROM PUBLIC',v_object.nspname,v_object.proname,v_object.args);
    FOR v_grantee IN SELECT DISTINCT r.rolname
      FROM pg_catalog.aclexplode(v_object.proacl) a
      JOIN pg_catalog.pg_roles r ON r.oid=a.grantee
      WHERE a.grantee<>v_object.proowner
    LOOP
      EXECUTE pg_catalog.format('REVOKE ALL ON FUNCTION %I.%I(%s) FROM %I',
         v_object.nspname,v_object.proname,v_object.args,v_grantee.rolname);
    END LOOP;
  END LOOP;
END $acl$;

GRANT USAGE ON SCHEMA astra_ingestion_v1 TO astra_ingestion_monitor_owner_v1;
GRANT SELECT ON astra_ingestion_v1.jobs,astra_ingestion_v1.partitions,
                astra_ingestion_v1.source_limits TO astra_ingestion_monitor_owner_v1;
GRANT INSERT ON astra_ingestion_v1.monitor_incidents,
                astra_ingestion_v1.monitor_ticks TO astra_ingestion_monitor_owner_v1;
CREATE POLICY ingestion_monitor_read ON astra_ingestion_v1.jobs
  FOR SELECT TO astra_ingestion_monitor_owner_v1 USING (true);
CREATE POLICY ingestion_monitor_read ON astra_ingestion_v1.partitions
  FOR SELECT TO astra_ingestion_monitor_owner_v1 USING (true);
CREATE POLICY ingestion_monitor_read ON astra_ingestion_v1.source_limits
  FOR SELECT TO astra_ingestion_monitor_owner_v1 USING (true);
CREATE POLICY ingestion_monitor_incident_write ON astra_ingestion_v1.monitor_incidents
  FOR INSERT TO astra_ingestion_monitor_owner_v1 WITH CHECK (true);
CREATE POLICY ingestion_monitor_tick_write ON astra_ingestion_v1.monitor_ticks
  FOR INSERT TO astra_ingestion_monitor_owner_v1 WITH CHECK (true);
GRANT CREATE ON SCHEMA astra_ingestion_v1 TO astra_ingestion_monitor_owner_v1;
ALTER FUNCTION astra_ingestion_v1.monitor_tick_v1() OWNER TO astra_ingestion_monitor_owner_v1;
REVOKE CREATE ON SCHEMA astra_ingestion_v1 FROM astra_ingestion_monitor_owner_v1;
DO $grant$ BEGIN
  EXECUTE pg_catalog.format('GRANT EXECUTE ON FUNCTION astra_ingestion_v1.monitor_tick_v1() TO %I',current_user);
END $grant$;
-- pg_cron scheduling is a separately controlled action after qualification and
-- requires a verified existing cron extension; no service, scheduler or
-- provider worker is started by this migration.
