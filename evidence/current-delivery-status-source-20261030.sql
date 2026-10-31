
 SELECT jsonb_build_object('runs',COALESCE(jsonb_agg(x),'[]'),'observed_at',clock_timestamp()) FROM (
  SELECT r.id run_id,r.status run_status,r.cohort_policy,r.cohort_sha256,r.target_start,r.target_end,
   r.metadata->'planning_complete'='true'::jsonb planning_complete,r.last_progress_at,
   jsonb_build_object('requests_reserved',r.requests_reserved,'physical_pages',r.pages_committed,'physical_source_and_derived_records',r.records_committed,'source_bytes',r.source_bytes) physical_totals,
   (SELECT count(*) FROM astra_ingestion_v1.backfill_pages_v2 p WHERE p.run_id=r.id AND NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_readbacks_v2 v WHERE v.task_id=p.task_id AND v.page_no=p.page_no)) required_readbacks_remaining,
   (SELECT jsonb_agg(to_jsonb(f) ORDER BY f.family) FROM astra_ingestion_v1.backfill_family_status_v2 f WHERE f.run_id=r.id) families,
   (SELECT COALESCE(jsonb_agg(to_jsonb(d)),'[]') FROM astra_ingestion_v1.backfill_provider_dependencies_v2 d WHERE d.run_id=r.id) provider_dependencies,
   (SELECT COALESCE(jsonb_agg(z),'[]') FROM (SELECT t.id,t.family,t.kind,t.status,t.error_code,t.error_message,t.generation,t.page_attempts,t.next_retry_at,t.source_revision,
     CASE WHEN t.status='RETRY_WAIT' THEN 'Persisted retry; worker may claim after next_retry_at'
      WHEN t.error_code='MISSING_PROVIDER_CREDENTIAL' THEN 'Restore provider configuration and advertise changed capability_revision'
      WHEN t.status IN ('OPERATIONAL_ERROR','BLOCKED_EXTERNAL') THEN 'Repair and deploy; call backfill_recover with exact task generation, repair revision and verification evidence'
      WHEN t.status='RUNNING' THEN 'Current finite lease, or automatic stale-lease takeover'
      ELSE 'Configured worker claim or dependency completion' END executable_next_action
     FROM astra_ingestion_v1.backfill_tasks_v2 t WHERE t.run_id=r.id AND t.status IN ('OPERATIONAL_ERROR','BLOCKED_EXTERNAL','RETRY_WAIT') ORDER BY t.created_at,t.id LIMIT 100) z) outstanding_actions
  FROM astra_ingestion_v1.backfill_runs_v2 r WHERE p_run_id IS NULL OR r.id=p_run_id ORDER BY r.created_at DESC LIMIT 20
 ) x
