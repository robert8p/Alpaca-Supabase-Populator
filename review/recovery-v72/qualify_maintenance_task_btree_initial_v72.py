"""Isolated PostgreSQL plan proof for exact maintenance task eligibility indexes.

No production calls or application changes. The full synthetic task scale uses
the retained live 15-index inventory. It does not reproduce production cache,
bloat, concurrent writers or the timed-out cron transaction.
"""
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import sys
from time import monotonic
import unittest

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
V71=HERE.parent/'recovery-v71'
STAGED=Path('/tmp/replacement-claim-capability-staged-v71')
sys.path[:0]=[str(STAGED/'tests/ingestion'),str(STAGED)]
import test_backfill_claim_capability_filter_v2 as base

INVENTORY=json.loads((V71/'live_task_index_inventory_1351.json').read_text())[0]['evidence']
SOURCE=(V71/'maintenance_selectors_readonly_v71.sql').read_text()
QUERIES={k:v for k,v in re.findall(r"\('([A-Z0-9_]+)',\$query\$(.*?)\$query\$\)",SOURCE,re.S)
         if k in ('BREADTH_PENDING','MINUTE_ACCOUNT_PENDING')}
N=712899
D03=24189
MINUTE_UPPER_BOUND=26466
BREADTH_PREDICATE="family='D03' AND lower(provider)='derived'"
MINUTE_PREDICATE="family IN('P01','P02') AND kind IN('retained_reuse','alpaca_stock_bars') AND COALESCE(scope->>'timeframe','1Min')='1Min'"
INDEXES={
    'backfill_tasks_breadth_pending_id_v2':BREADTH_PREDICATE,
    'backfill_tasks_minute_pending_id_v2':MINUTE_PREDICATE,
}
RESULT={'schema':'astra.maintenance-eligibility-index-plan-qualification/1',
    'production_calls':0,'production_ddl':False,'repair_installed':False,
    'interpretation':['Synthetic local planner proof, not live runtime recovery or install-duration proof.',
        '26466 is the live P01 family/kind group upper bound, used as a synthetic eligible count; the exact live timeframe-qualified count is unknown.',
        'Tables copy actual fixture column types, defaults, checks and existing index definitions; foreign keys and triggers are not copied into the isolated plan-only schema.',
        'Original selectors are unchanged except schema adaptation; cache is warm from fixture construction and bloat is fresh.']}


def nodes(plan):
    yield plan
    for child in plan.get('Plans',[]):yield from nodes(child)


class IndexPlanQualification(base.CapabilityFilterPostgreSQLTests):
    def test_full_scale_original_selectors_and_exact_predicate_edges(self):
        bench=self.f.schema+'_plans'
        ddl_timings={}
        progress=lambda label:print(json.dumps({'phase':label}),flush=True)
        tables=('backfill_tasks_v2','backfill_pages_v2','backfill_readbacks_v2',
            'backfill_breadth_projected_pages_v2','backfill_minute_projection_v2','backfill_audit_v2')
        def cleanup():
            with self.f.admin() as conn:conn.execute('DROP SCHEMA IF EXISTS '+bench+' CASCADE')
        self.addCleanup(cleanup)
        progress('create isolated plan fixture')
        with self.f.admin() as conn:
            conn.execute('CREATE SCHEMA '+bench)
            for table in tables:
                options='INCLUDING DEFAULTS INCLUDING CONSTRAINTS INCLUDING IDENTITY INCLUDING STORAGE' if table=='backfill_tasks_v2' else 'INCLUDING ALL'
                conn.execute(f'CREATE TABLE {bench}.{table} (LIKE {self.f.schema}.{table} {options})')
            conn.execute("SET LOCAL statement_timeout='0'")
            started=monotonic()
            conn.execute(f'''INSERT INTO {bench}.backfill_tasks_v2
              (id,run_id,family,provider,kind,scope,status,next_retry_at,created_at)
              SELECT 'backfill-plan-'||encode(sha256(convert_to('maintenance-plan:'||g::text,'UTF8')),'hex'),
               %s,CASE WHEN g<=%s THEN 'D03' WHEN g<=%s THEN 'P01' ELSE 'D01' END,
               CASE WHEN g>%s AND g<=%s THEN 'REUSE' WHEN g>%s AND g<=%s THEN 'Alpaca' ELSE 'DERIVED' END,
               CASE WHEN g<=%s THEN 'derive_daily' WHEN g<=%s THEN 'retained_reuse' WHEN g<=%s THEN 'alpaca_stock_bars' ELSE 'derive_intraday' END,
               jsonb_build_object('symbols',jsonb_build_array('AAPL'),'member_ids',jsonb_build_array('member-1'),
                 'source_month','2025-09-01','fixture_ordinal',g,'fixture_padding',repeat('x',650),'timeframe','1Min'),
               'PENDING','2026-10-30T13:00:00Z'::timestamptz,'2026-10-30T05:00:00Z'::timestamptz
              FROM generate_series(1,%s) g''',
                (base.LIVE_RUN,D03,D03+MINUTE_UPPER_BOUND,D03,D03+26376,D03+26376,D03+MINUTE_UPPER_BOUND,
                 D03,D03+26376,D03+MINUTE_UPPER_BOUND,N))
            ddl_timings['task_population_seconds']=monotonic()-started
        progress('build all 15 retained task indexes')
        with self.f.admin() as conn:
            conn.execute("SET LOCAL statement_timeout='0'")
            for item in INVENTORY['indexes']:
                started=monotonic()
                conn.execute(item['definition'].replace('astra_ingestion_v1',bench))
                ddl_timings['baseline_index_'+item['name']]=monotonic()-started
            conn.execute(f'''INSERT INTO {bench}.backfill_pages_v2
             (task_id,page_no,run_id,generation,run_fence,provider,request,http_status,fetched_at,committed_at,
              raw_body,body_sha256,records_sha256,record_count,source_bytes,adapter_version)
             SELECT t.id,0,t.run_id,1,1,t.provider,'{{}}'::jsonb,200,'2026-10-30T06:00:00Z',
              '2026-10-30T06:00:01Z'::timestamptz + ((t.scope->>'fixture_ordinal')::integer * interval '1 millisecond'),
              '{{"rows":[{{"fixture":"'||repeat('x',1000)||'"}}]}}',repeat('a',64),repeat('b',64),1,1025,'plan-only-fixture'
             FROM {bench}.backfill_tasks_v2 t WHERE (t.scope->>'fixture_ordinal')::integer<=438
              OR (t.scope->>'fixture_ordinal')::integer BETWEEN %s AND %s
              OR (t.scope->>'fixture_ordinal')::integer BETWEEN %s AND %s''',
                (D03+1,D03+508,D03+MINUTE_UPPER_BOUND+1,D03+MINUTE_UPPER_BOUND+3732))
            conn.execute(f'''INSERT INTO {bench}.backfill_readbacks_v2
             (task_id,page_no,run_id,body_sha256,readback_sha256,expected_records,actual_records,target_records,
              support_records,unknown_date_records,rth_records,pre_records,post_records,unclassified_session_records)
             SELECT task_id,page_no,run_id,body_sha256,body_sha256,1,1,0,0,1,0,0,0,0 FROM {bench}.backfill_pages_v2''')
            conn.execute(f'''INSERT INTO {bench}.backfill_breadth_projected_pages_v2
             (task_id,page_no,run_id,source_month,body_sha256,projected_records)
             SELECT p.task_id,p.page_no,p.run_id,'2025-09-01',p.body_sha256,1
             FROM {bench}.backfill_pages_v2 p JOIN {bench}.backfill_tasks_v2 t ON t.id=p.task_id WHERE t.family='D03' ''')
            conn.execute(f'''INSERT INTO {bench}.backfill_minute_projection_v2(task_id,last_verified_page)
             SELECT p.task_id,0 FROM {bench}.backfill_pages_v2 p JOIN {bench}.backfill_tasks_v2 t ON t.id=p.task_id WHERE t.family='P01' ''')
            for table in tables:conn.execute('ANALYZE '+bench+'.'+table)
            sizes=conn.execute(f'''SELECT count(*) task_count,pg_relation_size('{bench}.backfill_tasks_v2') heap_bytes,
             pg_total_relation_size('{bench}.backfill_tasks_v2') total_bytes,
             (SELECT count(*) FROM {bench}.backfill_pages_v2) page_count,
             (SELECT count(*) FROM {bench}.backfill_readbacks_v2) readback_count
             FROM {bench}.backfill_tasks_v2''').fetchone()
            self.assertEqual((sizes['task_count'],sizes['page_count'],sizes['readback_count']),(N,4678,4678))
        progress('measure unchanged selectors before candidate indexes')
        def measure():
            out={}
            with self.f.admin() as conn:
                conn.execute("SET LOCAL jit=off")
                conn.execute("SET LOCAL random_page_cost=1.1")
                conn.execute("SET LOCAL work_mem='5MB'")
                conn.execute("SET LOCAL effective_cache_size='1536MB'")
                conn.execute("SET LOCAL max_parallel_workers_per_gather=0")
                conn.execute("SET LOCAL statement_timeout='8s'")
                for label,query in QUERIES.items():
                    sql=query.replace('astra_ingestion_v1',bench)
                    plan=conn.execute('EXPLAIN (ANALYZE TRUE,BUFFERS TRUE,TIMING FALSE,SETTINGS TRUE,FORMAT JSON) '+sql).fetchone()['QUERY PLAN'][0]
                    result=conn.execute(sql).fetchall()
                    self.assertEqual(result,[])
                    out[label]={'plan':plan,'selected_rows':0,'task_nodes':[{k:n.get(k) for k in (
                        'Node Type','Index Name','Actual Rows','Actual Loops','Rows Removed by Filter','Heap Fetches','Shared Hit Blocks','Shared Read Blocks')}
                        for n in nodes(plan['Plan']) if n.get('Relation Name')=='backfill_tasks_v2']}
            return out
        before=measure()
        progress('build two exact-predicate candidate indexes locally only')
        with self.f.admin() as conn:
            conn.execute("SET LOCAL statement_timeout='8s'")
            for name,predicate in INDEXES.items():
                started=monotonic()
                conn.execute(f'CREATE INDEX {name} ON {bench}.backfill_tasks_v2(id) WHERE {predicate}')
                ddl_timings['candidate_'+name]=monotonic()-started
        after=measure()
        for label in QUERIES:
            self.assertTrue(any(x['Index Name'] in INDEXES for x in after[label]['task_nodes']),after[label]['task_nodes'])
            self.assertFalse(any(x['Index Name']=='backfill_tasks_v2_pkey' for x in after[label]['task_nodes']))
            self.assertEqual(before[label]['selected_rows'],after[label]['selected_rows'])
        with self.f.admin() as conn:
            new_indexes=conn.execute('''SELECT c.relname,pg_relation_size(c.oid) bytes,i.indisvalid valid,i.indisready ready,
             pg_get_indexdef(c.oid) definition,pg_get_expr(i.indpred,i.indrelid) predicate FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
             WHERE i.indrelid=%s::regclass AND c.relname=ANY(%s) ORDER BY c.relname''',
                (bench+'.backfill_tasks_v2',list(INDEXES))).fetchall()
            self.assertTrue(all(x['ready'] and x['valid'] for x in new_indexes))
            # The exact predicates are also checked against a complete small
            # SQL/JSON edge matrix, independently of the scale workload.
            frames=[('missing',{}),('json_null',{'timeframe':None}),('exact',{'timeframe':'1Min'}),
                    ('lowercase',{'timeframe':'1min'}),('daily',{'timeframe':'1Day'}),('empty',{'timeframe':''}),
                    ('number',{'timeframe':1}),('array',{'timeframe':[]}),('object',{'timeframe':{}}),('boolean',{'timeframe':True})]
            matrix=[]
            for family in ('P01','P02','D01','D03'):
                for kind in ('retained_reuse','alpaca_stock_bars','derive_daily'):
                    for label,scope in frames:
                        expected=family in ('P01','P02') and kind in ('retained_reuse','alpaca_stock_bars') and label in ('missing','json_null','exact')
                        got=conn.execute('SELECT '+MINUTE_PREDICATE+' AS eligible FROM (SELECT %s::text family,%s::text kind,%s::jsonb scope) q',
                            (family,kind,json.dumps(scope))).fetchone()['eligible']
                        self.assertEqual(got,expected)
                        matrix.append({'family':family,'kind':kind,'timeframe_case':label,'eligible':got})
            breadth_matrix=[]
            for family in ('D03','D04',None):
                for provider in ('DERIVED','derived','DeRiVeD','Alpaca',None):
                    got=conn.execute('SELECT '+BREADTH_PREDICATE+' AS eligible FROM (SELECT %s::text family,%s::text provider) q',(family,provider)).fetchone()['eligible']
                    expected=(family=='D03' and provider is not None and provider.lower()=='derived')
                    self.assertEqual(got is True,expected)
                    breadth_matrix.append({'family':family,'provider':provider,'sql_value':got})
            preserved=conn.execute('SELECT c.relname,pg_get_indexdef(c.oid) definition FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid WHERE i.indrelid=%s::regclass',
                (bench+'.backfill_tasks_v2',)).fetchall()
            actual={x['relname']:x['definition'] for x in preserved}
            for original in INVENTORY['indexes']:
                self.assertEqual(actual[original['name']],original['definition'].replace('astra_ingestion_v1',bench))
        RESULT.update(fixture=dict(sizes),live_inventory={'observed_at':INVENTORY['observed_at'],**INVENTORY['table']},
            synthetic_d03_eligible=D03,synthetic_minute_eligible_upper_bound=MINUTE_UPPER_BOUND,
            before=before,after=after,new_indexes=[dict(x) for x in new_indexes],ddl_timings=ddl_timings,
            minute_predicate_cases=matrix,breadth_predicate_cases=breadth_matrix,
            all15_original_indexes_preserved=True,original_selector_text_preserved=True,
            production_build_duration_not_inferred=True,planner_parallel_workers_per_gather=0)
        progress('qualification completed; remove isolated plan fixture')


if __name__=='__main__':
    if os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL')!='postgresql://postgres@127.0.0.1:55432/astra_ingestion_qualification':
        raise SystemExit('Only the known disposable loopback PostgreSQL fixture is permitted')
    started=monotonic()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([
        IndexPlanQualification('test_full_scale_original_selectors_and_exact_predicate_edges')]))
    RESULT.update(passed=result.wasSuccessful(),tests=result.testsRun,errors=len(result.errors),failures=len(result.failures),
        skipped=len(result.skipped),elapsed_seconds=monotonic()-started,test_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    path=HERE/'maintenance_task_index_plan_qualification_v72.json'
    path.write_text(json.dumps(RESULT,indent=2,default=str)+'\n')
    print(json.dumps({'passed':result.wasSuccessful(),'receipt':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}),flush=True)
    raise SystemExit(0 if result.wasSuccessful() else 1)
