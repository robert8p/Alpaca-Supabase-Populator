"""Real RPC status, coherent freshness boundaries, and bounded summary plans."""
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from time import perf_counter
import unittest

import test_backfill_status_index_counts_v2 as current
import test_backfill_runtime_v2 as runtime

ROOT=Path(__file__).resolve().parents[2]
INDEX='backfill_tasks_runtime_summary_v2'
PERFORMANCE={}


def branch(source):
    start=source.index(" IF p_operation='backfill_status' THEN")
    end=source.index(" ELSIF p_operation='backfill_claim' THEN",start)
    return source[start:end]


def report_select(source):
    text=branch(source)
    start=text.index('  WITH fresh_workers') if 'WITH fresh_workers' in text else text.index('  SELECT ')
    text=text[start:text.index('  RETURN jsonb_build_object(')].strip().removesuffix(';')
    return text.replace(' INTO v_result ',' ').replace('v_now','%(asof)s::timestamptz').replace(
        'p_payload',"jsonb_build_object('run_id',%(run)s::text)")


def normalized(value):
    value=deepcopy(value)
    value.pop('observed_at',None)
    for run in value.get('runs',[]):
        run['tasks'].sort(key=lambda x:tuple(x[k] for k in ('family','kind','provider','status')))
    if 'delivery' in value:
        value['delivery'].pop('observed_at',None)
    return value


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'),'Explicit disposable PostgreSQL required')
class RuntimeStatusPerformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        current.StatusIndexCountsTests.setUpClass.__func__(cls)
        cls.rewrite_sql=cls.rewrite((ROOT/'sql/astra_backfill_runtime_status_performance_v2.sql').read_text())
        cls.index_sql=cls.rewrite((ROOT/'sql/astra_backfill_runtime_summary_index_v2.sql').read_text())
        f=cls.fixture('runTest')
        with f.admin() as conn:
            conn.execute(cls.rewrite((ROOT/'sql/astra_backfill_minute_alias_index_v2.sql').read_text()))
            cls.original_definition=conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (f.schema+'.backfill_dispatch_v2(text,jsonb)',)).fetchone()['d']
            cls.original_source=conn.execute('SELECT prosrc FROM pg_proc WHERE oid=%s::regprocedure',
                (f.schema+'.backfill_dispatch_v2(text,jsonb)',)).fetchone()['prosrc']
            cls.original_metadata=conn.execute("SELECT to_jsonb(p)-'prosrc' m FROM pg_proc p WHERE oid=%s::regprocedure",
                (f.schema+'.backfill_dispatch_v2(text,jsonb)',)).fetchone()['m']
            conn.execute(cls.rewrite_sql)
            cls.candidate_definition=conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (f.schema+'.backfill_dispatch_v2(text,jsonb)',)).fetchone()['d']
            cls.candidate_source=conn.execute('SELECT prosrc FROM pg_proc WHERE oid=%s::regprocedure',
                (f.schema+'.backfill_dispatch_v2(text,jsonb)',)).fetchone()['prosrc']
        cls.baseline_query=cls.full_query(report_select(cls.original_source),f.schema)
        cls.candidate_query=cls.full_query(report_select(cls.candidate_source),f.schema)

    @staticmethod
    def full_query(select,schema):
        return "SELECT jsonb_build_object('runs',("+select+"),'observed_at',%(asof)s::timestamptz,'delivery',"+schema+".backfill_delivery_status_v2(%(run)s::text)) result"

    rewrite=classmethod(current.StatusIndexCountsTests.rewrite.__func__)
    task=runtime.BackfillRuntimeTests.task
    call=runtime.BackfillRuntimeTests.call
    claim=runtime.BackfillRuntimeTests.claim
    page=runtime.BackfillRuntimeTests.page
    fence=staticmethod(runtime.BackfillRuntimeTests.fence)

    def setUp(self):
        f=self.fixture('runTest')
        with f.admin() as conn:
            conn.execute(f'DROP INDEX IF EXISTS {f.schema}.{INDEX}')
        runtime.BackfillRuntimeTests.setUp(self)

    def report(self,query=None,*,asof=None,run='current'):
        with self.f.admin() as conn:
            return conn.execute(query or self.candidate_query,{'run':self.run if run=='current' else run,
                'asof':asof or datetime.now(timezone.utc)}).fetchone()['result']

    def worker(self,key,kinds,observed):
        with self.f.admin() as conn:
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_workers_v2
                (worker_id,source_revision,supported_kinds,capability_revision,observed_at)
                VALUES(%s,'status-fixture',%s,'status-fixture',%s)''',
                (self.run+'-'+key,json.dumps(kinds),observed))

    def test_full_json_rpc_counts_nulls_global_capabilities_and_normal_commit(self):
        states=['PENDING','RUNNING','RETRY_WAIT','INGESTED','NO_DATA_RETURNED','NOT_APPLICABLE',
                'PROVIDER_LIMITATION','IDENTITY_OR_QUALITY_UNRESOLVED','OPERATIONAL_ERROR',
                'BLOCKED_EXTERNAL','SUPERSEDED_BY_SCOPE_CHANGE']
        definitions=[('P01','alpaca_stock_bars','Alpaca'),('D01','derive_intraday','DERIVED'),
                     ('N01','massive_news','Massive'),('N01','alpaca_news','Alpaca')]
        with self.f.admin() as conn:
            for group,(family,kind,provider) in enumerate(definitions):
                for n,state in enumerate(states):
                    conn.execute(f'''INSERT INTO {self.f.schema}.backfill_tasks_v2
                        (id,run_id,family,provider,kind,scope,status,owner,lease_until,next_retry_at,records_committed,last_progress_at)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                        (self.run+f'-summary-{group}-{n}',self.run,family,provider,kind,
                         json.dumps({'symbols':['AAPL'],'member_ids':['member-1']}),state,
                         'fixture-owner' if state=='RUNNING' else None,'2100-01-01' if state=='RUNNING' else None,
                         '2100-01-01',0 if group==0 else n,None if group==0 else '2026-10-30T04:00Z'))
        self.worker('fresh-array',['derive_intraday'],'2100-01-01')
        self.worker('fresh-object',{'alpaca_news':False},'2100-01-01')
        self.worker('fresh-scalar','alpaca_stock_bars','2100-01-01')
        self.worker('expired',['massive_news'],'2000-01-01')
        self.worker('numeric',123,'2100-01-01')
        old=self.report(self.baseline_query);new=self.report()
        self.assertEqual(normalized(old),normalized(new))
        self.assertEqual(new['runs'][0]['unsupported_pending_kinds'],['massive_news'])
        zero=[x for x in new['runs'][0]['tasks'] if x['family']=='P01']
        self.assertTrue(all(x['records']==0 and x['last_progress_at'] is None for x in zero))
        self.assertTrue(new['runs'][0]['next_retry_at'].startswith('2100-01-01'))
        with self.f.admin() as conn:conn.execute(self.index_sql)
        actual=self.call('backfill_status',{'run_id':self.run},actor='api')
        self.assertEqual(normalized(new),normalized(actual))
        # The index must follow the real fenced source commit path as well.
        # Non-array JSON is a status-compatibility fixture; real worker claims
        # advertise arrays, as required by the unchanged admission path.
        with self.f.admin() as conn:
            conn.execute(f'DELETE FROM {self.f.schema}.backfill_workers_v2 WHERE worker_id=ANY(%s)',
                ([self.run+'-'+k for k in ('fresh-object','fresh-scalar','numeric')],))
        source=self.task(priority=-100)
        claimed=self.claim(['alpaca_reference'])
        self.assertEqual(claimed['id'],source)
        self.call('backfill_reserve',{'claim':self.fence(claimed)})
        self.call('backfill_commit',self.page(claimed))
        after=self.call('backfill_status',{'run_id':self.run},actor='api')
        group=next(x for x in after['runs'][0]['tasks'] if x['kind']=='alpaca_reference')
        self.assertEqual((group['tasks'],group['records'],group['status']),(1,1,'INGESTED'))
        self.assertIsNotNone(group['last_progress_at'])
        self.assertEqual(normalized(self.report(self.baseline_query)),normalized(after))

    def test_freshness_cutoff_microseconds_future_and_documented_crossing_delta(self):
        asof=datetime(2026,10,30,12,tzinfo=timezone.utc)
        cutoff=asof-timedelta(minutes=10)
        with self.f.admin() as conn:
            conn.execute(f'UPDATE {self.f.schema}.backfill_workers_v2 SET observed_at=%s',(cutoff-timedelta(days=1),))
        definitions=[('alpaca_reference','REF01','Alpaca'),('massive_news','N01','Massive'),
                     ('alpaca_news','N01','Alpaca'),('retained_reuse','P01','REUSE'),
                     ('derive_daily','D02','DERIVED'),('massive_short_volume','S01','Massive')]
        for kind,family,provider in definitions:self.task(kind=kind,family=family,provider=provider)
        self.worker('above',['alpaca_reference'],cutoff+timedelta(microseconds=1))
        self.worker('exact',['massive_news'],cutoff)
        self.worker('below',['alpaca_news'],cutoff-timedelta(microseconds=1))
        self.worker('future',['retained_reuse'],asof+timedelta(days=1))
        self.worker('mixed-old',['derive_daily'],cutoff-timedelta(days=1))
        self.worker('mixed-new',['derive_daily'],asof)
        expected=['alpaca_news','massive_news','massive_short_volume']
        self.assertEqual(self.report(asof=asof)['runs'][0]['unsupported_pending_kinds'],expected)
        later=self.report(asof=asof+timedelta(microseconds=2))
        self.assertEqual(later['runs'][0]['unsupported_pending_kinds'],['alpaca_news','alpaca_reference','massive_news','massive_short_volume'])
        # Deterministically emulate a report sampled before expiry but evaluated
        # later. No sleeps and no replacement of the production clock function.
        sampled=datetime.now(timezone.utc)-timedelta(seconds=2)
        with self.f.admin() as conn:
            conn.execute(f'UPDATE {self.f.schema}.backfill_workers_v2 SET observed_at=%s WHERE worker_id=%s',
                (sampled-timedelta(minutes=10)+timedelta(seconds=1),self.run+'-above'))
        old=self.report(self.baseline_query,asof=sampled)
        new=self.report(asof=sampled)
        self.assertIn('alpaca_reference',old['runs'][0]['unsupported_pending_kinds'])
        self.assertNotIn('alpaca_reference',new['runs'][0]['unsupported_pending_kinds'])
        self.assertEqual(datetime.fromisoformat(new['observed_at']),sampled)
        PERFORMANCE['freshness_contract']={'strict_cutoff':'greater-than; equality is stale','future_worker_still_fresh':True,
            'report_asof':'existing advertised observed_at/v_now','boundary_delta_demonstrated':True,
            'claim_admission_unchanged':True}

    def test_empty_missing_and_newest_twenty_runs_keep_existing_shape(self):
        empty=self.report()['runs'][0]
        self.assertEqual(empty['tasks'],[]);self.assertEqual(empty['unsupported_pending_kinds'],[])
        self.assertEqual(empty['provider_dependencies'],[]);self.assertIsNone(empty['next_retry_at'])
        self.assertEqual(self.report(run='missing-run')['runs'],[])
        with self.f.admin() as conn:
            for n in range(22):
                conn.execute(f'''INSERT INTO {self.f.schema}.backfill_runs_v2
                    (id,instruction_sha256,cohort_sha256,cohort_manifest_sha256,cohort_ref,scope,status,created_at)
                    SELECT %s,instruction_sha256,cohort_sha256,cohort_manifest_sha256,cohort_ref,scope,'PAUSED',
                      '2099-01-01'::timestamptz+make_interval(secs=>%s)
                    FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s''',(self.run+'-extra-'+str(n),n,self.run))
        current_report=self.report(run=None)
        self.assertEqual(len(current_report['runs']),20)
        self.assertEqual([r['id'] for r in current_report['runs']],[self.run+'-extra-'+str(n) for n in range(21,1,-1)])
        self.assertEqual(normalized(current_report),normalized(self.report(self.baseline_query,run=None)))

    def test_metadata_all_other_dispatch_paths_acl_guards_and_bounded_index_rollback(self):
        self.assertEqual(self.original_source,self.candidate_source.replace(branch(self.candidate_source),branch(self.original_source)))
        with self.f.admin() as conn:
            self.assertEqual(conn.execute("SELECT to_jsonb(p)-'prosrc' m FROM pg_proc p WHERE oid=%s::regprocedure",
                (self.f.schema+'.backfill_dispatch_v2(text,jsonb)',)).fetchone()['m'],self.original_metadata)
            self.assertEqual(conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (self.f.schema+'.rpc_dispatch(text,jsonb)',)).fetchone()['d'],self.outer_rpc)
            for role in (self.f.gateway,self.f.outsider):
                self.assertFalse(conn.execute("SELECT has_function_privilege(%s,%s,'EXECUTE') allowed",
                    (role,self.f.schema+'.backfill_dispatch_v2(text,jsonb)')).fetchone()['allowed'])
        with self.assertRaises(self.f.psycopg.Error),self.f.admin() as conn:conn.execute(self.rewrite_sql)
        drifted=self.original_definition.replace(" IF p_operation='backfill_status' THEN",
            " IF p_operation='backfill_status' THEN\n  -- fixture source drift")
        with self.f.admin() as conn:conn.execute(drifted)
        try:
            with self.assertRaises(self.f.psycopg.Error) as drift,self.f.admin() as conn:conn.execute(self.rewrite_sql)
            self.assertIn('baseline',str(drift.exception))
        finally:
            with self.f.admin() as conn:conn.execute(self.candidate_definition)
        with self.f.admin() as conn:
            conn.execute(f'ALTER TABLE {self.f.schema}.backfill_tasks_v2 ALTER COLUMN records_committed DROP NOT NULL')
        try:
            with self.assertRaises(self.f.psycopg.Error) as drift,self.f.admin() as conn:conn.execute(self.index_sql)
            self.assertIn('column types',str(drift.exception))
        finally:
            with self.f.admin() as conn:
                conn.execute(f'ALTER TABLE {self.f.schema}.backfill_tasks_v2 ALTER COLUMN records_committed SET NOT NULL')
        key=self.task()
        started=perf_counter()
        with self.f.admin() as holder:
            holder.execute(f'LOCK TABLE {self.f.schema}.backfill_tasks_v2 IN ROW EXCLUSIVE MODE')
            with self.assertRaises(self.f.psycopg.errors.LockNotAvailable),self.f.admin() as conn:conn.execute(self.index_sql)
        lock_seconds=perf_counter()-started
        self.assertTrue(2.5<lock_seconds<5.5)
        with self.f.admin() as conn:
            self.assertIsNone(conn.execute('SELECT to_regclass(%s) i',(self.f.schema+'.'+INDEX,)).fetchone()['i'])
        delayed=self.index_sql.rsplit('COMMIT;',1)[0]+'SELECT pg_sleep(9);\nCOMMIT;'
        started=perf_counter()
        with self.assertRaises(self.f.psycopg.errors.QueryCanceled),self.f.admin() as conn:conn.execute(delayed)
        timeout_seconds=perf_counter()-started
        self.assertTrue(7.5<timeout_seconds<10)
        with self.f.admin() as conn:
            self.assertIsNone(conn.execute('SELECT to_regclass(%s) i',(self.f.schema+'.'+INDEX,)).fetchone()['i'])
            conn.execute(f'CREATE INDEX {INDEX} ON {self.f.schema}.backfill_tasks_v2(id)')
        with self.assertRaises(self.f.psycopg.Error),self.f.admin() as conn:conn.execute(self.index_sql)
        with self.f.admin() as conn:
            conn.execute(f'DROP INDEX {self.f.schema}.{INDEX}')
            conn.execute(self.index_sql)
        with self.assertRaises(self.f.psycopg.Error),self.f.admin() as conn:conn.execute(self.index_sql)
        PERFORMANCE['index_failure_bounds']={'lock_seconds':lock_seconds,'postbuild_timeout_seconds':timeout_seconds,
            'no_index_after_each_failed_transaction':True}

    def test_wide_low_visibility_rewrite_and_index_are_measured_separately(self):
        scale=int(os.environ.get('ASTRA_RUNTIME_STATUS_SCALE','30000'))
        self.assertTrue(10000<=scale<=600000)
        split=scale//5
        def seed(start,end):
            with self.f.admin() as conn:
                conn.execute(f'''INSERT INTO {self.f.schema}.backfill_tasks_v2
                    (id,run_id,family,provider,kind,scope,status,next_retry_at)
                    SELECT %s||'-runtime-scale-'||g,%s,
                      CASE WHEN g%%20=0 THEN 'P01' WHEN g%%10=0 THEN 'N01' ELSE 'D01' END,
                      CASE WHEN g%%20=0 THEN 'Alpaca' WHEN g%%10=0 THEN 'Massive' ELSE 'DERIVED' END,
                      CASE WHEN g%%20=0 THEN 'alpaca_stock_bars' WHEN g%%10=0 THEN 'massive_news' ELSE 'derive_intraday' END,
                      jsonb_build_object('symbols',jsonb_build_array(CASE WHEN (g-1)%%3000=0 THEN 'AAPL' ELSE 'T'||(1+(g-1)%%3000) END),
                        'member_ids',jsonb_build_array('member-'||(1+(g-1)%%3000)),
                        'timeframe','1Min','padding',repeat(md5(g::text),30)),
                      CASE WHEN g%%997=0 THEN 'RETRY_WAIT' ELSE 'PENDING' END,'2100-01-01'
                    FROM generate_series(%s::integer,%s::integer)g''',(self.run,self.run,start,end))
        seed(1,split)
        with self.f.admin() as conn:
            conn.autocommit=True;conn.execute(f'VACUUM(ANALYZE) {self.f.schema}.backfill_tasks_v2')
        seed(split+1,scale)
        with self.f.admin() as conn:
            for n in range(120):
                conn.execute(f'''INSERT INTO {self.f.schema}.backfill_workers_v2
                    (worker_id,source_revision,supported_kinds,capability_revision,observed_at)
                    VALUES(%s,'expired',%s,'expired','2000-01-01')''',(self.run+'-oldworker-'+str(n),
                    '["derive_intraday","alpaca_stock_bars","massive_news"]'))
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_workers_v2
                (worker_id,source_revision,supported_kinds,capability_revision,observed_at)
                VALUES(%s,'fresh','["derive_intraday","alpaca_stock_bars"]','fresh','2100-01-01')''',(self.run+'-fresh',))
            conn.execute(f'ANALYZE {self.f.schema}.backfill_tasks_v2')
            conn.execute(f'ANALYZE {self.f.schema}.backfill_workers_v2')
        args={'run':self.run,'asof':datetime.now(timezone.utc)}
        timings={};baseline=None
        started=perf_counter()
        try:
            with self.f.admin() as conn:
                conn.execute("SET LOCAL statement_timeout='8s'")
                baseline=conn.execute(self.baseline_query,args).fetchone()['result']
            timings['baseline_state']='COMPLETED'
        except self.f.psycopg.errors.QueryCanceled:
            timings['baseline_state']='TIMED_OUT_AT_8_SECONDS'
        timings['baseline_seconds']=perf_counter()-started
        with self.f.admin() as conn:
            conn.execute("SET LOCAL statement_timeout='8s'")
            started=perf_counter();rewritten=conn.execute(self.candidate_query,args).fetchone()['result']
            timings['rewrite_only_seconds']=perf_counter()-started
            if baseline is not None:self.assertEqual(normalized(baseline),normalized(rewritten))
            rewrite_plan=conn.execute('EXPLAIN(ANALYZE,BUFFERS,FORMAT JSON) '+self.candidate_query,args).fetchone()['QUERY PLAN'][0]
            started=perf_counter();conn.execute(self.index_sql);timings['index_build_seconds']=perf_counter()-started
            started=perf_counter();indexed=conn.execute(self.candidate_query,args).fetchone()['result']
            timings['rewrite_plus_index_low_visibility_seconds']=perf_counter()-started
            self.assertEqual(normalized(rewritten),normalized(indexed))
            low_plan=conn.execute('EXPLAIN(ANALYZE,BUFFERS,FORMAT JSON) '+self.candidate_query,args).fetchone()['QUERY PLAN'][0]
            size=conn.execute('SELECT pg_relation_size(%s::regclass) n',(self.f.schema+'.'+INDEX,)).fetchone()['n']
        started=perf_counter();rpc=self.call('backfill_status',{'run_id':self.run},actor='api')
        timings['combined_authenticated_rpc_low_visibility_seconds']=perf_counter()-started
        self.assertEqual(normalized(indexed),normalized(rpc))
        self.assertLess(timings['combined_authenticated_rpc_low_visibility_seconds'],3)
        self.assertLess(timings['index_build_seconds'],8)
        for plan in (rewrite_plan,low_plan):
            scans=[n for n in current.nodes(plan['Plan']) if n.get('Relation Name')=='backfill_workers_v2']
            self.assertEqual(len(scans),1);self.assertEqual(scans[0]['Actual Loops'],1)
            pending=[n for n in current.nodes(plan['Plan']) if n.get('Subplan Name')=='CTE pending_kinds']
            self.assertEqual(len(pending),1);self.assertEqual(pending[0]['Actual Rows'],3)
        # Local maintenance changes visibility, never the values. Qualify both
        # prepared-plan modes once older completed pages become all-visible.
        with self.f.admin() as conn:
            conn.autocommit=True;conn.execute(f'VACUUM(ANALYZE) {self.f.schema}.backfill_tasks_v2')
        plans={}
        with self.f.admin() as conn:
            prepared=self.candidate_query.replace('%(run)s','$1').replace('%(asof)s','$2')
            conn.execute('PREPARE summary_status(text,timestamptz) AS '+prepared)
            arguments="('"+self.run+"','"+args['asof'].isoformat()+"')"
            for mode in ('force_generic_plan','force_custom_plan'):
                conn.execute('SET plan_cache_mode='+mode)
                plan=conn.execute('EXPLAIN(ANALYZE,BUFFERS,FORMAT JSON) EXECUTE summary_status'+arguments).fetchone()['QUERY PLAN'][0]
                scans=[n for n in current.nodes(plan['Plan']) if n.get('Index Name')==INDEX]
                self.assertEqual(len(scans),1)
                self.assertEqual(scans[0]['Node Type'],'Index Only Scan')
                self.assertEqual(scans[0]['Actual Rows'],scale)
                self.assertEqual(scans[0]['Actual Loops'],1)
                self.assertLess(scans[0].get('Heap Fetches',scale),scale//100)
                plans[mode]=plan
            self.assertEqual(normalized(indexed),normalized(conn.execute(self.candidate_query,args).fetchone()['result']))
        PERFORMANCE.update(scale=scale,older_visible_tasks=split,recent_unvacuumed_tasks=scale-split,
            expired_workers=120,distinct_pending_kinds=3,index_bytes=size,timings=timings,
            rewrite_only_plan=rewrite_plan,low_visibility_index_plan=low_plan,prepared_plans=plans,
            task_array_order='Unspecified by both old and new SQL; comparisons normalize the four group keys',
            complete_ordinary_values_equal=True)


if __name__=='__main__':unittest.main()
