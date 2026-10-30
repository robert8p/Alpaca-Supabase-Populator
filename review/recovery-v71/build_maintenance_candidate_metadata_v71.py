"""Build compact metadata for exactly the retained ten selector shapes."""
from hashlib import sha256
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
profile=(HERE/'maintenance_selectors_readonly_v71.sql').read_text()
queries=dict(re.findall(r"\('([A-Z0-9_]+)',\$query\$(.*?)\$query\$\)",profile,re.S))
assert len(queries)==10
start=profile.index('BEGIN ISOLATION LEVEL')
end=profile.index(" FOR x IN SELECT * FROM (VALUES\n  ('BREADTH_PENDING'")
prefix=profile[start:end]
prefix=re.sub(r'\bx\b','source_guard_record',prefix)
prefix=prefix.replace('p jsonb;','candidate_result jsonb;')
ctes=[]
unions=[]
for i,(label,sql) in enumerate(queries.items()):
    ctes.append('q'+str(i)+' AS MATERIALIZED('+sql+')')
    if label in ('IDENTITY_DISCOVERY_PENDING','IDENTITY_REFRESH_QUEUE'):
        continue
    page='NULL::integer' if label=='MINUTE_ACCOUNT_PENDING' else 'page_no'
    unions.append("SELECT '"+label+"'::text component,task_id,"+page+' page_no FROM q'+str(i))
identity_idx={label:list(queries).index(label) for label in ('IDENTITY_DISCOVERY_PENDING','IDENTITY_REFRESH_QUEUE')}
body="""
 WITH
__CTES__,
 candidates AS MATERIALIZED(__UNIONS__),
 page_metadata AS (
  SELECT c.component,c.task_id,c.page_no,t.run_id,t.family,t.provider,t.kind,t.status,
   COALESCE(t.scope->>'timeframe','') timeframe,
   a.archived_pages,a.verified_pages,a.source_records,a.raw_bytes,a.max_page_no,a.max_verified_page,
   a.earliest_committed_at,a.latest_committed_at,
   mp.last_verified_page minute_projection_last_page,
   CASE WHEN c.page_no IS NOT NULL THEN EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_shared_pages_v2 s
    WHERE s.task_id=c.task_id AND s.page_no=c.page_no) ELSE NULL END shared_page_already_projected
  FROM candidates c JOIN astra_ingestion_v1.backfill_tasks_v2 t ON t.id=c.task_id
  LEFT JOIN astra_ingestion_v1.backfill_minute_projection_v2 mp ON mp.task_id=c.task_id
  CROSS JOIN LATERAL (
   SELECT count(*) archived_pages,count(b.task_id) verified_pages,COALESCE(sum(pg.record_count),0) source_records,
    COALESCE(sum(octet_length(pg.raw_body)),0) raw_bytes,max(pg.page_no) max_page_no,max(b.page_no) max_verified_page,
    min(pg.committed_at) earliest_committed_at,max(pg.committed_at) latest_committed_at
   FROM astra_ingestion_v1.backfill_pages_v2 pg
   LEFT JOIN astra_ingestion_v1.backfill_readbacks_v2 b ON b.task_id=pg.task_id AND b.page_no=pg.page_no
   WHERE pg.task_id=c.task_id AND (c.page_no IS NULL OR pg.page_no=c.page_no)
    AND (c.component<>'MINUTE_ACCOUNT_PENDING' OR b.task_id IS NOT NULL)
  ) a
 )
 SELECT jsonb_build_object('schema','astra.maintenance-candidate-metadata/1','observed_at',clock_timestamp(),
  'complete',true,'selector_count',10,'maintenance_functions_invoked',false,'advisory_lock_acquired',false,
  'raw_page_bodies_returned',false,'transaction_read_only',current_setting('transaction_read_only'),
  'transaction_isolation',current_setting('transaction_isolation'),
  'page_candidates',COALESCE((SELECT jsonb_agg(to_jsonb(m) ORDER BY component,task_id,page_no) FROM page_metadata m),'[]'::jsonb),
  'identity_discovery_candidates',COALESCE((SELECT jsonb_agg(jsonb_build_object('run_id',run_id,'member_id',member_id)) FROM q__DISCOVERY__),'[]'::jsonb),
  'identity_refresh_candidates',COALESCE((SELECT jsonb_agg(jsonb_build_object('run_id',run_id,'member_id',member_id,
    'ready_after',ready_after,'after_task_id',after_task_id,'earliest_date',earliest_date,'latest_date',latest_date)) FROM q__REFRESH__),'[]'::jsonb),
  'current_run_finalizer_gates',(SELECT jsonb_build_object('status',r.status,'planning_complete',r.metadata->'planning_complete',
    'identity_discovery_pending',EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_identity_discovered_members_v2 d WHERE d.run_id=r.id AND NOT d.complete),
    'identity_refresh_pending',EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_identity_refresh_v2 f WHERE f.run_id=r.id),
    'plan_manifest_exists',EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_plan_manifests_v2 f WHERE f.run_id=r.id),
    'runnable_work_exists',EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_tasks_v2 t WHERE t.run_id=r.id AND t.status IN('PENDING','RUNNING','RETRY_WAIT')))
   FROM astra_ingestion_v1.backfill_runs_v2 r WHERE r.id='fixed3000-20250901-20260731-v1-20261030')
 ) INTO candidate_result;
 IF octet_length(candidate_result::text)>60000 THEN RAISE EXCEPTION 'Maintenance candidate metadata exceeds bounded result size';END IF;
 RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='ASTRA_MAINTENANCE_CANDIDATES_V71:'||candidate_result::text;
END $profile$;
ROLLBACK;
""".replace('__CTES__',',\n'.join(ctes)).replace('__UNIONS__',' UNION ALL '.join(unions)).replace('__DISCOVERY__',str(identity_idx['IDENTITY_DISCOVERY_PENDING'])).replace('__REFRESH__',str(identity_idx['IDENTITY_REFRESH_QUEUE']))
path=HERE/'maintenance_candidate_metadata_readonly_v71.sql'
path.write_text('-- Same ten original selectors, compact source counts only, no helper invocation.\n-- Separate snapshot from the selector profile; candidate identities may advance.\n'+prefix+body)
print(json.dumps({'path':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}))
