"""Prepare source-pinned read-only probes; never execute a production operation.

Each SQL file executes one full SELECT projection under one 8s read-only bound.
The caller chooses the next evidence-supported component; the files are not a
batch instruction. Current projected after-state cannot reconstruct old_summary.
"""
from hashlib import sha256
import json
from pathlib import Path
import re

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
NESTED=ROOT/'review/recovery-v73/live_shared_nested_definitions_after_restore_v73.json'
PURE=ROOT/'review/recovery-v73/live_shared_pure_dependencies_after_restore_v73.json'
HISTORICAL=ROOT/'review/recovery-v73/live_shared_historical_page_receipts_v73.json'
HISTORICAL_SQL=ROOT/'review/recovery-v73/shared_historical_page_receipts_readonly_v73.sql'
functions={x['name']:x for x in json.loads(NESTED.read_text())[0]['functions']+json.loads(PURE.read_text())[0]['functions']}
for f in functions.values():
    assert sha256(f['definition'].encode()).hexdigest()==f['source_sha256']
source=functions['backfill_shared_project_v2']['definition']
meta=source[source.index('SELECT x.record_ordinal,'):source.index('),\n versions AS')]
assert meta.startswith('SELECT x.record_ordinal,') and meta.endswith(' x')
meta=meta.replace('t.provider','$3').replace('t.kind','$4').replace('p_task','$1').replace('p_page','$2')
meta='WITH rows AS MATERIALIZED('+meta+') SELECT record_ordinal,m FROM rows'
summary=functions['backfill_shared_summary_v2']['definition'].split('AS $function$\n',1)[1].rsplit('$function$',1)[0].strip()
refresh=functions['backfill_shared_refresh_v2']['definition']
first=refresh[refresh.index(' WITH keys AS'):refresh.index('\n DELETE FROM')]
first=first.replace(' INSERT INTO astra_ingestion_v1.backfill_shared_records_v2\n','\n',1)
first=first[:first.index('\n ON CONFLICT(')].strip()
second=refresh[refresh.index(' WITH keys AS',refresh.index('\n DELETE FROM')):refresh.rindex('\nEND $function$')]
second=second.replace(' INSERT INTO astra_ingestion_v1.backfill_shared_links_v2\n','\n',1).strip().removesuffix(';')
def bind(query):
    return re.sub(r'\bp_keys\b','$6',re.sub(r'\bp_run\b','$5',query))
queries={
 'PARSE_FULL_PAGE':'SELECT * FROM astra_ingestion_v1.backfill_page_rows_v2($1,$2)',
 'PROJECT_FULL_METADATA':meta,
 'CURRENT_SUMMARY':bind(summary),
 'REFRESH_RECORD_SELECT_INPUT':bind(first),
 'REFRESH_LINK_SELECT_INPUT':bind(second),
}
for query in queries.values():
    assert not re.search(r'\b(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|PERFORM)\b',query,re.I)
    assert 'backfill_shared_refresh_v2(' not in query and 'backfill_shared_apply_delta_v2(' not in query
    assert query.startswith(('SELECT','WITH'))
old_pins=json.loads(re.search(r'\$source_pins\$(.*?)\$source_pins\$',HISTORICAL_SQL.read_text(),re.S).group(1))
pins={x['signature']:{**x,'metadata_kind':'compact'} for x in old_pins}
for f in functions.values():
    pins[f['signature']]={'signature':f['signature'],'sha256':f['source_sha256'],'metadata_kind':'full','metadata':f['metadata']}
pins=list(pins.values())
receipt=json.loads(HISTORICAL.read_text())
page=next(x for w in receipt['windows'] if w['audit_id']==41 for x in w['receipts'] if x['kind']=='alpaca_option_contracts')
assert page['record_count']==1000 and page['source_bytes']==711481 and page['stored_metadata_consistent']
pin_json=json.dumps(pins,separators=(',',':'))
assert '$source_pins$' not in pin_json
TEMPLATE=r'''-- One component only. No mutating helper, provider request, advisory gate or write.
-- The page is an immutable temporal candidate, not a proved individual cause.
-- Summary and refresh inputs use current projected after-state, not historical old_summary.
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL transaction_read_only='on';
SET LOCAL transaction_isolation='repeatable read';
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $shared_read_profile$
DECLARE
 v_pins constant jsonb := $source_pins$__PINS__$source_pins$::jsonb;
 v_component constant text := '__COMPONENT__';
 v_sql constant text := $read_select$__QUERY__$read_select$;
 v_task astra_ingestion_v1.backfill_tasks_v2;
 v_run jsonb; v_member_count bigint; v_definition text; v_metadata jsonb; v_pin jsonb;
 v_keys jsonb; v_occurrences bigint; v_key_count integer; v_keys_ms numeric;
 v_plan jsonb; v_nodes jsonb; v_node_count integer; v_result jsonb; v_started timestamptz;
 v_role_matches_project_owner boolean; v_body_digest text; v_raw_bytes integer;
BEGIN
 IF current_setting('transaction_read_only')<>'on'
  OR current_setting('transaction_isolation')<>'repeatable read'
  OR current_setting('statement_timeout')<>'8s' OR current_setting('lock_timeout')<>'3s' THEN
  RAISE EXCEPTION 'Shared read profile requires enforced read-only repeatable-read 8s/3s bounds';
 END IF;
 IF v_component NOT IN ('PARSE_FULL_PAGE','PROJECT_FULL_METADATA','CURRENT_SUMMARY',
  'REFRESH_RECORD_SELECT_INPUT','REFRESH_LINK_SELECT_INPUT') THEN
  RAISE EXCEPTION 'Shared read profile component is not admitted';
 END IF;
 FOR v_pin IN SELECT value FROM jsonb_array_elements(v_pins) LOOP
  SELECT pg_get_functiondef(f.oid),CASE WHEN v_pin->>'metadata_kind'='full'
   THEN to_jsonb(f)-'prosrc' ELSE jsonb_build_object('acl',f.proacl,'owner',f.proowner::text,
    'config',f.proconfig,'security_definer',f.prosecdef) END
   INTO STRICT v_definition,v_metadata FROM pg_proc f WHERE f.oid=(v_pin->>'signature')::regprocedure;
  IF encode(sha256(convert_to(v_definition,'UTF8')),'hex') IS DISTINCT FROM v_pin->>'sha256'
   OR v_metadata IS DISTINCT FROM v_pin->'metadata' THEN
   RAISE EXCEPTION 'Shared read profile source or metadata changed';
  END IF;
 END LOOP;
 SELECT current_user=pg_get_userbyid(proowner) INTO STRICT v_role_matches_project_owner
 FROM pg_proc WHERE oid='astra_ingestion_v1.backfill_shared_project_v2(text,integer)'::regprocedure;
 SELECT jsonb_build_object('id',id,'status',status,'fence',fence,'cohort_sha256',cohort_sha256,
  'owner',metadata->>'implementation_owner','lease_until',metadata->>'implementation_lease_until')
 INTO STRICT v_run FROM astra_ingestion_v1.backfill_runs_v2
 WHERE id='fixed3000-20250901-20260731-v1-20261030';
 SELECT count(*) INTO v_member_count FROM astra_ingestion_v1.backfill_members_v2
 WHERE run_id=v_run->>'id';
 IF v_run->>'owner' IS DISTINCT FROM 'root-replacement-20261030T042603Z'
  OR COALESCE((v_run->>'lease_until')::timestamptz>clock_timestamp(),false) IS NOT TRUE
  OR (v_run->>'fence')::bigint IS DISTINCT FROM 1
  OR v_run->>'cohort_sha256' IS DISTINCT FROM '2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
  OR v_member_count<>3000 THEN
  RAISE EXCEPTION 'Shared read profile owner, lease, fence, cohort or members changed';
 END IF;
 SELECT * INTO STRICT v_task FROM astra_ingestion_v1.backfill_tasks_v2
 WHERE id='__TASK__' AND run_id=v_run->>'id' AND run_fence=1
  AND family='CTX02' AND kind='alpaca_option_contracts' AND provider='Alpaca';
 SELECT encode(sha256(convert_to(p.raw_body,'UTF8')),'hex'),octet_length(p.raw_body)
 INTO STRICT v_body_digest,v_raw_bytes
 FROM astra_ingestion_v1.backfill_pages_v2 p
 JOIN astra_ingestion_v1.backfill_readbacks_v2 b USING(task_id,page_no)
 JOIN astra_ingestion_v1.backfill_shared_pages_v2 s USING(task_id,page_no)
 WHERE p.task_id=v_task.id AND p.page_no=0 AND p.run_id=v_run->>'id'
  AND b.run_id=p.run_id AND s.run_id=p.run_id
  AND p.record_count=1000 AND p.source_bytes=711481 AND s.source_records=1000
  AND p.body_sha256='__BODY_SHA__' AND p.records_sha256='__RECORDS_SHA__'
  AND p.committed_at='__COMMITTED_AT__'::timestamptz
  AND b.actual_records=1000 AND b.expected_records=b.actual_records
  AND b.body_sha256=p.body_sha256 AND b.readback_sha256=b.body_sha256
  AND b.verified_at='__VERIFIED_AT__'::timestamptz
  AND s.projected_at='__PROJECTED_AT__'::timestamptz;
 IF v_body_digest IS DISTINCT FROM '__BODY_SHA__' OR v_raw_bytes IS DISTINCT FROM 711481 THEN
  RAISE EXCEPTION 'Shared read profile retained body integrity changed';
 END IF;
 IF v_component IN ('CURRENT_SUMMARY','REFRESH_RECORD_SELECT_INPUT','REFRESH_LINK_SELECT_INPUT') THEN
  v_started:=clock_timestamp();
  SELECT count(*),COALESCE(jsonb_agg(DISTINCT record_key),'[]') INTO v_occurrences,v_keys
  FROM astra_ingestion_v1.backfill_shared_occurrences_v2
  WHERE task_id=v_task.id AND page_no=0 AND run_id=v_run->>'id';
  v_keys_ms:=extract(epoch FROM clock_timestamp()-v_started)*1000;
  v_key_count:=jsonb_array_length(v_keys);
  IF v_occurrences<>1000 OR v_key_count<1 OR v_key_count>1000 THEN
   RAISE EXCEPTION 'Shared read profile retained occurrence/key bounds changed';
  END IF;
 END IF;
 EXECUTE 'EXPLAIN (ANALYZE TRUE,BUFFERS TRUE,TIMING FALSE,SETTINGS FALSE,FORMAT JSON) '||v_sql
 INTO v_plan USING v_task.id,0,v_task.provider,v_task.kind,v_task.run_id,v_keys;
 WITH RECURSIVE nodes(path,node) AS(
  SELECT ARRAY[0::bigint],v_plan->0->'Plan'
  UNION ALL SELECT n.path||c.ordinality,c.value FROM nodes n
   CROSS JOIN LATERAL jsonb_array_elements(COALESCE(n.node->'Plans','[]')) WITH ORDINALITY c(value,ordinality)
 )
 SELECT count(*),jsonb_agg(jsonb_build_object('path',path,'node_type',node->'Node Type',
  'parent_relationship',node->'Parent Relationship','join_type',node->'Join Type',
  'relation',CASE WHEN node->>'Relation Name'=ANY(ARRAY[
   'backfill_shared_versions_v2','backfill_shared_records_v2','backfill_shared_occurrences_v2',
   'backfill_shared_version_links_v2','backfill_shared_links_v2','backfill_members_v2'])
   THEN node->'Relation Name' ELSE NULL END,
  'actual_rows',node->'Actual Rows','actual_loops',node->'Actual Loops',
  'rows_removed_filter',node->'Rows Removed by Filter','rows_removed_join_filter',node->'Rows Removed by Join Filter',
  'shared_hits',node->'Shared Hit Blocks','shared_reads',node->'Shared Read Blocks',
  'temp_reads',node->'Temp Read Blocks','temp_writes',node->'Temp Written Blocks') ORDER BY path)
 INTO v_node_count,v_nodes FROM nodes;
 IF v_node_count>300 THEN RAISE EXCEPTION 'Shared read profile plan exceeded bounded node count';END IF;
 IF COALESCE((v_run->>'lease_until')::timestamptz>clock_timestamp(),false) IS NOT TRUE THEN
  RAISE EXCEPTION 'Shared read profile lease expired during read';
 END IF;
 v_result:=jsonb_build_object('schema','astra.shared-pure-read-profile/1','complete',true,
  'observed_at',clock_timestamp(),'component',v_component,'run',v_run,'member_count',v_member_count,
  'task_id',v_task.id,'page_no',0,'body_sha256',v_body_digest,'raw_bytes',v_raw_bytes,
  'retained_page_records',1000,'source_and_readback_integrity_verified',true,
  'temporal_origin_audit_id',41,'page_backend_identity_proven',false,
  'key_source',CASE WHEN v_keys IS NOT NULL THEN 'CURRENT_IMMUTABLE_PAGE_OCCURRENCES' ELSE 'NOT_USED' END,
  'current_occurrences',v_occurrences,'current_distinct_keys',v_key_count,'key_derivation_ms',v_keys_ms,
  'keys_sha256',CASE WHEN v_keys IS NOT NULL THEN encode(sha256(convert_to(v_keys::text,'UTF8')),'hex') ELSE NULL END,
  'planning_ms',v_plan->0->'Planning Time','execution_ms',v_plan->0->'Execution Time','nodes',v_nodes,
  'source_pin_count',jsonb_array_length(v_pins),'source_and_metadata_pins_verified',true,
  'execution_role_matches_shared_project_owner',v_role_matches_project_owner,
  'transaction_read_only',current_setting('transaction_read_only'),
  'transaction_isolation',current_setting('transaction_isolation'),
  'statement_timeout',current_setting('statement_timeout'),'lock_timeout',current_setting('lock_timeout'),
  'raw_source_metadata_values_keys_or_plan_expressions_returned',false,
  'mutating_helpers_or_provider_calls',false,'advisory_lock_acquired',false,
  'interpretation',jsonb_build_array(
   'A full SELECT projection is evaluated; no COUNT wrapper can prune its output expressions.',
   'This already-projected immutable page is a temporal candidate, not a proved individual cause of audit41 shared time.',
   'Summary and refresh inputs read current persisted after-state; they do not reconstruct historical old_summary or initial insert work.',
   'These independently bounded calls have separate snapshots and cache conditions; no uncontrolled latency ratio is justified.',
   'A dynamic direct-role SELECT plan does not establish the original cached function plan, write/trigger cost, lock wait or whole-phase recovery.'));
 IF octet_length(v_result::text)>60000 THEN RAISE EXCEPTION 'Shared read profile output exceeded bound';END IF;
 RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='SHARED_READ_PROFILE_V74 '||v_result::text;
END $shared_read_profile$;
ROLLBACK;
'''
replacements={'__PINS__':pin_json,'__TASK__':page['task_id'],'__BODY_SHA__':page['body_sha256'],
 '__RECORDS_SHA__':page['records_sha256'],'__COMMITTED_AT__':page['committed_at'],
 '__VERIFIED_AT__':page['verified_at'],'__PROJECTED_AT__':page['projected_at']}
files=[]
for component,query in queries.items():
    sql=TEMPLATE.replace('__COMPONENT__',component).replace('__QUERY__',query)
    for old,new in replacements.items():sql=sql.replace(old,new)
    assert not re.search(r'__[A-Z_]+__',sql)
    path=HERE/('shared_'+component.lower()+'_readonly_v74.sql');path.write_text(sql)
    files.append({'component':component,'path':path.relative_to(ROOT).as_posix(),'sha256':sha256(path.read_bytes()).hexdigest(),
                  'bytes':path.stat().st_size,'query_sha256':sha256(query.encode()).hexdigest()})
derivation={'schema':'astra.shared-read-profile-derivation/1','state':'PREPARED_NOT_EXECUTED_OR_QUALIFIED',
 'production_calls':0,'recommended_first_component':'PROJECT_FULL_METADATA','retained_temporal_candidate':page,
 'input_pins':[{ 'path':x.relative_to(ROOT).as_posix(),'sha256':sha256(x.read_bytes()).hexdigest()} for x in [NESTED,PURE,HISTORICAL,HISTORICAL_SQL]],
 'source_pin_count':len(pins),'source_pins':pins,'files':files,
 'query_extraction':{'parse':'Full existing STABLE page_rows output, no pruning wrapper',
 'metadata':'Literal project rows SELECT, bound task/page/provider/kind, full record_ordinal/m projection',
 'summary':'Complete unchanged SQL function body with p_run/p_keys bound',
 'refresh_records':'Complete unchanged first INSERT source SELECT; remove only INSERT target and ON CONFLICT suffix',
 'refresh_links':'Complete unchanged second INSERT source SELECT; remove only INSERT target'},
 'bindings':{'$1':'fixed task id','$2':'page0','$3':'fixed provider','$4':'fixed kind','$5':'fixed run','$6':'current immutable occurrence key array'},
 'limits':{'each_statement_ms':8000,'each_lock_ms':3000,'source_records':1000,'result_bytes':60000,'plan_nodes':300},
 'not_a_batch_instruction':True,'caller_selects_next_component_from_evidence':True,'mutations_or_new_permissions':False}
(HERE/'shared_read_profile_derivation_v74.json').write_text(json.dumps(derivation,indent=2)+'\n')
print(json.dumps({'source_pin_count':len(pins),'files':files,'production_calls':0}))
