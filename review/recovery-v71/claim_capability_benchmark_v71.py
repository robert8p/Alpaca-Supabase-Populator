"""Disposable-only experiment: scalar capability InitPlan versus a late semijoin.

This file is not an installable production repair. The root controller must
establish a relevant live bottleneck before proposing an operational forward.
"""
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from time import perf_counter
import unittest

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'tests/ingestion'))
sys.path.insert(0,str(ROOT))
import test_backfill_runtime_status_performance_v2 as current

OLD='q.kind IN (SELECT jsonb_array_elements_text(v_supported))'
NEW='q.kind = ANY(ARRAY(SELECT jsonb_array_elements_text(v_supported)))'
KINDS=['alpaca_reference','alpaca_stock_bars','alpaca_news','alpaca_actions',
       'alpaca_option_contracts','alpaca_option_bars','derive_daily','derive_intraday',
       'derive_breadth','retained_reuse','retained_identity','retained_massive_archive']
RESULT={}


def nodes(plan):
    yield plan
    for child in plan.get('Plans',[]):yield from nodes(child)


class Experiment(current.RuntimeStatusPerformanceTests):
    def test_null_duplicate_empty_and_mixed_json_semantics(self):
        values=[[],[None],['alpaca_news'],['alpaca_news','alpaca_news'],
                ['other',None],['alpaca_news',None],[1,True,{},[],None],
                ['1',1],['true',True],['{"a": 1}',{'a':1}],['["x"]',['x']]]
        lhs=[None,'alpaca_news','other','1','true','{"a": 1}','["x"]','é']
        checked=0
        with self.f.admin() as conn:
            for kinds in values:
                for kind in lhs:
                    row=conn.execute('''SELECT %s::text IN(SELECT jsonb_array_elements_text(%s::jsonb)) old,
                        %s::text = ANY(ARRAY(SELECT jsonb_array_elements_text(%s::jsonb))) new''',
                        (kind,json.dumps(kinds),kind,json.dumps(kinds))).fetchone()
                    self.assertIs(row['old'],row['new']);checked+=1
        RESULT['three_valued_semantics']={'cases':checked,'passed':True,'nulls_coalesced':False}

    def test_realistic_unsupported_news_prefix(self):
        unsupported=22121;supported=21922
        with self.f.admin() as conn:
            before=conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (self.f.schema+'.backfill_dispatch_v2(text,jsonb)',)).fetchone()['d']
            self.assertEqual(before.count(OLD),2)
            after=before.replace(OLD,NEW)
            self.assertEqual(after.replace(NEW,OLD),before)
            # Use the observed two news kinds, priority-separated unsupported
            # prefix and the current 12 worker kinds; invent no dependencies.
            for label,kind,provider,priority,count in [
                ('unsupported','massive_news','Massive',50,unsupported),
                ('supported','alpaca_news','Alpaca',51,supported)]:
                conn.execute(f'''INSERT INTO {self.f.schema}.backfill_tasks_v2
                    (id,run_id,family,provider,kind,scope,priority,created_at,next_retry_at)
                    SELECT %s||'-'||%s||'-'||lpad(g::text,5,'0'),%s,'N01',%s,%s,
                      jsonb_build_object('symbols',jsonb_build_array('AAPL'),'member_ids',jsonb_build_array('member-1'),
                       'start','2025-09-01T04:00:00Z','end','2026-08-01T03:59:59Z',
                       'target_start','2025-09-01','target_end','2026-07-31',
                       'identity_status','UNRESOLVED_PROVIDER_ANCHOR','market_timezone','America/New_York'),
                      %s,'2026-10-30T06:00:00Z','2026-10-30T06:00:00Z'
                    FROM generate_series(1,%s)g''',(self.run,label,self.run,provider,kind,priority,count))
            conn.execute(self.index_sql)
            for table in ('backfill_tasks_v2','backfill_members_v2'):conn.execute(f'ANALYZE {self.f.schema}.{table}')
            conn.commit()
            def candidate(definition):
                begin=definition.rindex('SELECT q.* INTO t FROM '+self.f.schema+'.backfill_tasks_v2')
                end=definition.index(' LIMIT 1 FOR UPDATE OF q;',begin)+len(' LIMIT 1 FOR UPDATE OF q;')
                query=definition[begin:end].replace(' INTO t ',' ')
                for a,b in [('v_fair_run','$1'),('v_fair_pick.family','$2'),('v_supported','$3'),('v_now','$4')]:query=query.replace(a,b)
                return query
            for label,definition in [('baseline',before),('candidate',after)]:
                conn.execute('PREPARE capability_'+label+'(text,text,jsonb,timestamptz) AS '+candidate(definition))
            conn.execute("SET statement_timeout='8s'")
            args="('"+self.run+"','N01','"+json.dumps(KINDS,separators=(',',':'))+"'::jsonb,'2026-10-30T12:00:00Z'::timestamptz)"
            plans={}
            for mode in ('force_generic_plan','force_custom_plan'):
                conn.execute('SET plan_cache_mode='+mode);plans[mode]={}
                for label in ('baseline','candidate'):
                    query='EXECUTE capability_'+label+args
                    got=conn.execute(query).fetchone()
                    self.assertEqual(got['id'],self.run+'-supported-00001')
                    plan=conn.execute('EXPLAIN(ANALYZE,BUFFERS,TIMING FALSE,SETTINGS TRUE,FORMAT JSON) '+query).fetchone()['QUERY PLAN'][0]
                    plans[mode][label]=plan
                    self.assertTrue(any(n['Node Type']=='LockRows' for n in nodes(plan['Plan'])))
            # This experiment measures behavior; do not fabricate a performance
            # threshold or label an unhelpful alternative a successful repair.
            RESULT['news_prefix']={'unsupported_tasks':unsupported,'supported_tasks':supported,
                'dependencies_invented':False,'all_expected_candidate_ids_match':True,
                'live_bottleneck_established_by_this_agent':False,'plans':plans,
                'before_normalized_definition_sha256':sha256(before.replace(self.f.schema,'astra_ingestion_v1').encode()).hexdigest(),
                'only_two_predicate_substitutions':True}


if __name__=='__main__':
    started=perf_counter()
    suite=unittest.TestSuite([Experiment('test_null_duplicate_empty_and_mixed_json_semantics'),Experiment('test_realistic_unsupported_news_prefix')])
    result=unittest.TextTestRunner(verbosity=2).run(suite)
    RESULT.update(schema='astra.claim-capability-filter.experiment/1',passed=result.wasSuccessful(),tests=result.testsRun,
        elapsed_seconds=perf_counter()-started,production_calls=0,production_repair_prepared=False,
        old_predicate=OLD,new_predicate=NEW)
    path=HERE/'claim_capability_benchmark_result_v71.json';path.write_text(json.dumps(RESULT,indent=2)+'\n')
    raise SystemExit(0 if result.wasSuccessful() else 1)
