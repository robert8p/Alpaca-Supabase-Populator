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
STAGED=Path('/tmp/replacement-maintenance-index-staged-v72')
sys.path[:0]=[str(STAGED/'tests/ingestion'),str(STAGED)]
import test_backfill_claim_capability_filter_v2 as base

INVENTORY=json.loads((V71/'live_task_index_inventory_1351.json').read_text())[0]['evidence']
SOURCE=(V71/'maintenance_selectors_readonly_v71.sql').read_text()
QUERIES={k:v for k,v in re.findall(r"\('([A-Z0-9_]+)',\$query\$(.*?)\$query\$\)",SOURCE,re.S)
         if k in ('BREADTH_PENDING','MINUTE_ACCOUNT_PENDING')}
N=60000
D03=24189
MINUTE_UPPER_BOUND=26466
BREADTH_PREDICATE="family='D03' AND lower(provider)='derived'"
MINUTE_PREDICATE="family IN('P01','P02') AND kind IN('retained_reuse','alpaca_stock_bars') AND COALESCE(scope->>'timeframe','1Min')='1Min'"
INDEXES={
    'backfill_tasks_breadth_pending_id_v2':BREADTH_PREDICATE,
    'backfill_tasks_minute_pending_id_v2':MINUTE_PREDICATE,
}
RESULT={'schema':'astra.maintenance-hash-positive-generic-qualification/1',
    'production_calls':0,'production_ddl':False,'repair_installed':False,
    'interpretation':['Synthetic local planner proof, not live runtime recovery or install-duration proof.',
        '26466 is the live P01 family/kind group upper bound, used as a synthetic eligible count; the exact live timeframe-qualified count is unknown.',
        'Tables copy actual fixture column types, defaults, checks and existing index definitions; foreign keys and triggers are not copied into the isolated plan-only schema.',
        'Original selectors are unchanged except schema adaptation; cache is warm from fixture construction and bloat is fresh.']}


def nodes(plan):
    yield plan
    for child in plan.get('Plans',[]):yield from nodes(child)


class IndexPlanQualification(base.CapabilityFilterPostgreSQLTests):
    def test_reduced_fixture_positive_identities_and_generic_plans(self):
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
        progress('build candidate hash indexes for focused positive/generic proof')
        with self.f.admin() as conn:
            conn.execute("SET LOCAL statement_timeout='8s'")
            for name,predicate in INDEXES.items():
                conn.execute(f'CREATE INDEX {name} ON {bench}.backfill_tasks_v2 USING hash(id) WHERE {predicate}')

        with self.f.admin() as conn:
            conn.execute("SET LOCAL random_page_cost=1.1")
            conn.execute("SET LOCAL max_parallel_workers_per_gather=0")
            conn.execute("SET LOCAL jit=off")
            conn.execute("SET LOCAL statement_timeout='8s'")
            conn.execute("SET LOCAL plan_cache_mode='force_generic_plan'")
            generic={}
            for i,(label,query) in enumerate(QUERIES.items()):
                sql=query.replace('astra_ingestion_v1',bench).replace('LIMIT GREATEST(1,LEAST(2,8))','LIMIT GREATEST(1,LEAST($1,8))')
                conn.execute(f'PREPARE maintenance_generic_{i}(integer) AS '+sql)
                plan=conn.execute(f'EXPLAIN (ANALYZE TRUE,BUFFERS TRUE,TIMING FALSE,FORMAT JSON) EXECUTE maintenance_generic_{i}(2)').fetchone()['QUERY PLAN'][0]
                used={n.get('Index Name') for n in nodes(plan['Plan'])}
                self.assertTrue(used & set(INDEXES),used)
                self.assertEqual(plan['Plan']['Actual Rows'],0)
                generic[label]=plan
                conn.execute(f'DEALLOCATE maintenance_generic_{i}')
            # Select one unprojected eligible task per family and give it a page.
            # These stay local synthetic receipts; no application helper runs.
            eligible=conn.execute(f'''SELECT DISTINCT ON(family) id,family FROM {bench}.backfill_tasks_v2
             WHERE (scope->>'fixture_ordinal')::integer IN (439,24698) ORDER BY family,id''').fetchall()
            self.assertEqual({r['family'] for r in eligible},{'D03','P01'})
            for row in eligible:
                conn.execute(f'''INSERT INTO {bench}.backfill_pages_v2
                 (task_id,page_no,run_id,generation,run_fence,provider,request,http_status,fetched_at,committed_at,
                  raw_body,body_sha256,records_sha256,record_count,source_bytes,adapter_version)
                 SELECT id,0,run_id,1,1,provider,'{{}}',200,clock_timestamp(),clock_timestamp(),
                  '{{"rows":[{{"fixture":true}}]}}',repeat('a',64),repeat('b',64),1,27,'positive-plan-fixture'
                 FROM {bench}.backfill_tasks_v2 WHERE id=%s''',(row['id'],))
                conn.execute(f'''INSERT INTO {bench}.backfill_readbacks_v2
                 (task_id,page_no,run_id,body_sha256,readback_sha256,expected_records,actual_records,target_records,
                  support_records,unknown_date_records,rth_records,pre_records,post_records,unclassified_session_records)
                 SELECT task_id,page_no,run_id,body_sha256,body_sha256,1,1,0,0,1,0,0,0,0 FROM {bench}.backfill_pages_v2 WHERE task_id=%s''',(row['id'],))
            expected={row['family']:row['id'] for row in eligible}
            positive_before={label:conn.execute(query.replace('astra_ingestion_v1',bench)).fetchall() for label,query in QUERIES.items()}
            self.assertEqual(positive_before['BREADTH_PENDING'][0]['task_id'],expected['D03'])
            self.assertEqual(positive_before['MINUTE_ACCOUNT_PENDING'][0]['task_id'],expected['P01'])
            # Compare exact real selector identities with the candidate indexes
            # absent in the same transaction and snapshot.
            for name in INDEXES:conn.execute('DROP INDEX '+bench+'.'+name)
            positive_without={label:conn.execute(query.replace('astra_ingestion_v1',bench)).fetchall() for label,query in QUERIES.items()}
            self.assertEqual(positive_before,positive_without)
            for name,predicate in INDEXES.items():conn.execute(f'CREATE INDEX {name} ON {bench}.backfill_tasks_v2 USING hash(id) WHERE {predicate}')
            positive_evidence={'same_real_selector_task_page_identities_with_and_without_indexes':True,
                'exact_selected_rows_with_indexes':positive_before,'exact_selected_rows_without_indexes':positive_without,
                'breadth_candidates':len(positive_before['BREADTH_PENDING']),
                'minute_candidates':len(positive_before['MINUTE_ACCOUNT_PENDING']),
                'generic_plans':generic,'one_positive_per_family':True,
                'minute_selector_has_no_total_order':True}
        RESULT.update(fixture=dict(sizes),positive_and_generic=positive_evidence,
            original_selector_text_preserved=True,planner_parallel_workers_per_gather=0,
            forced_index_or_join_settings=False,all15_retained_index_definitions_used=True,
            reduced_fixture_is_not_the_full_scale_benchmark=True)

if __name__=='__main__':
    if os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL')!='postgresql://postgres@127.0.0.1:55432/astra_ingestion_qualification':
        raise SystemExit('Only the known disposable loopback PostgreSQL fixture is permitted')
    started=monotonic()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([
        IndexPlanQualification('test_reduced_fixture_positive_identities_and_generic_plans')]))
    RESULT.update(passed=result.wasSuccessful(),tests=result.testsRun,errors=len(result.errors),failures=len(result.failures),
        skipped=len(result.skipped),elapsed_seconds=monotonic()-started,test_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    path=HERE/'maintenance_hash_positive_generic_qualification_v72.json'
    path.write_text(json.dumps(RESULT,indent=2,default=str)+'\n')
    print(json.dumps({'passed':result.wasSuccessful(),'receipt':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}),flush=True)
    raise SystemExit(0 if result.wasSuccessful() else 1)
