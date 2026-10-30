"""Bounded keyed shared refresh: exact outputs, private ACLs and real query plans."""
import json
import os
from pathlib import Path
import re
from time import perf_counter
import unittest

import test_backfill_runtime_v2 as runtime
import test_backfill_shared_records_v2 as shared

ROOT=Path(__file__).resolve().parents[2]
PERFORMANCE={}


def nodes(plan):
    yield plan
    for child in plan.get('Plans',[]):
        yield from nodes(child)


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'),'Explicit disposable PostgreSQL required')
class SharedRefreshPerformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        shared.SharedRecordsTests.setUpClass.__func__(cls)
        original=(ROOT/'sql/astra_backfill_shared_records_v2.sql').read_text()
        start=original.index('CREATE FUNCTION astra_ingestion_v1.backfill_shared_refresh_v2(')
        end=original.index('\nCREATE FUNCTION astra_ingestion_v1.backfill_shared_project_v2(',start)
        cls.baseline=cls.rewrite(original[start:end].replace('CREATE FUNCTION','CREATE OR REPLACE FUNCTION',1))
        cls.forward=cls.rewrite((ROOT/'sql/astra_backfill_shared_refresh_performance_v2.sql').read_text())
        f=cls.fixture('runTest')
        with f.admin() as conn:
            cls.candidate=conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (f.schema+'.backfill_shared_refresh_v2(text,jsonb)',)).fetchone()['d']

    rewrite=classmethod(shared.SharedRecordsTests.rewrite.__func__)
    task=shared.SharedRecordsTests.task
    call=shared.SharedRecordsTests.call
    claim=shared.SharedRecordsTests.claim
    fence=staticmethod(shared.SharedRecordsTests.fence)
    new=shared.SharedRecordsTests.new
    commit=shared.SharedRecordsTests.commit
    verify=shared.SharedRecordsTests.verify
    report=shared.SharedRecordsTests.report
    rows=shared.SharedRecordsTests.rows
    article=staticmethod(shared.SharedRecordsTests.article)

    def setUp(self):
        runtime.BackfillRuntimeTests.setUp(self)
        with self.f.admin() as conn:conn.execute(self.candidate)

    def snapshot(self):
        tables=('backfill_shared_records_v2','backfill_shared_links_v2','backfill_shared_counts_v2',
                'backfill_shared_fields_v2','backfill_shared_dates_v2','backfill_shared_versions_v2',
                'backfill_shared_occurrences_v2','backfill_shared_version_links_v2','backfill_shared_pages_v2',
                'backfill_pages_v2','backfill_readbacks_v2')
        with self.f.admin() as conn:
            return {table:conn.execute(f"SELECT COALESCE(jsonb_agg(to_jsonb(x) ORDER BY to_jsonb(x)::text),'[]') value FROM {self.f.schema}.{table} x WHERE run_id=%s",
                                      (self.run,)).fetchone()['value'] for table in tables}

    def keys(self):
        with self.f.admin() as conn:
            return conn.execute(f"SELECT COALESCE(jsonb_agg(record_key ORDER BY record_key),'[]') keys FROM {self.f.schema}.backfill_shared_records_v2 WHERE run_id=%s",
                                (self.run,)).fetchone()['keys']

    def test_exact_existing_conflicts_versions_links_counters_and_receipts_are_preserved(self):
        with self.f.admin() as conn:conn.execute(self.baseline)
        self.commit(self.new(),[self.article(id='conflict',tickers=['AAPL']),
            self.article(id='ordered',updated_utc='2026-07-31T15:00:00Z')])
        self.commit(self.new(symbol='T2',member='member-2'),[self.article(id='conflict',title='Disagrees',tickers=['T2']),
            self.article(id='ordered',title='Newer',updated_utc='2026-07-31T16:00:00Z')])
        self.commit(self.new(kind='alpaca_actions',family='N02',start='2025-06-05',end='2026-10-30'),
            {'forward_splits':[{'id':'split-1','symbol':'AAPL','process_date':'2026-08-02','ex_date':'2026-07-31','old_rate':1,'new_rate':2}]})
        before=self.snapshot();keys=self.keys()
        with self.f.admin() as conn:
            conn.execute(self.forward)
            conn.execute(f'SELECT {self.f.schema}.backfill_shared_refresh_v2(%s,%s::jsonb)',(self.run,json.dumps(keys)))
            conn.execute(f'SELECT {self.f.schema}.backfill_shared_refresh_v2(%s,%s::jsonb)',(self.run,json.dumps(keys)))
        self.assertEqual(before,self.snapshot())
        self.commit(self.new(),[self.article(id='ordered',title='Newest',updated_utc='2026-07-31T17:00:00Z')])
        after_new=self.snapshot()
        # Independently recompute the newly arrived version with the old rules.
        with self.f.admin() as conn:
            conn.execute(self.baseline)
            conn.execute(f'SELECT {self.f.schema}.backfill_shared_refresh_v2(%s,%s::jsonb)',(self.run,json.dumps(self.keys())))
        self.assertEqual(after_new,self.snapshot())

    def test_function_metadata_private_acl_and_atomic_replay_guard(self):
        function=self.f.schema+'.backfill_shared_refresh_v2(text,jsonb)'
        with self.f.admin() as conn:
            conn.execute(self.baseline)
            before=conn.execute("SELECT to_jsonb(p)-'prosrc' m FROM pg_proc p WHERE oid=%s::regprocedure",(function,)).fetchone()['m']
            conn.execute(self.forward)
            after=conn.execute("SELECT to_jsonb(p)-'prosrc' m FROM pg_proc p WHERE oid=%s::regprocedure",(function,)).fetchone()['m']
            source=conn.execute('SELECT prosrc FROM pg_proc WHERE oid=%s::regprocedure',(function,)).fetchone()['prosrc']
            self.assertEqual(before,after)
            for role in (self.f.gateway,self.f.outsider):
                self.assertFalse(conn.execute('SELECT has_function_privilege(%s,%s,\'EXECUTE\') allowed',(role,function)).fetchone()['allowed'])
        with self.assertRaises(self.f.psycopg.Error):
            with self.f.admin() as conn:conn.execute(self.forward)
        with self.f.admin() as conn:
            self.assertEqual(source,conn.execute('SELECT prosrc FROM pg_proc WHERE oid=%s::regprocedure',(function,)).fetchone()['prosrc'])

    def test_analyzed_archive_keeps_bounded_rpc_and_keyed_generic_custom_plans(self):
        symbols=['AAPL270117C'+str(2000000+i).zfill(8) for i in range(100)]
        dates=[e['date'] for e in json.loads((ROOT/'evidence/replacement-calendar-v1.json').read_text())['sessions']
               if '2025-09-01'<=e['date']<='2026-07-31'][:100]
        bars={symbol:[{'t':day+'T13:30:00Z','o':1,'h':2,'l':1,'c':2,'v':5,'n':2,'vw':1.5} for day in dates] for symbol in symbols}
        self.commit(self.new(kind='alpaca_option_bars',family='CTX02',symbols=symbols),bars)
        with self.f.admin() as conn:
            for row in conn.execute("SELECT relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname=%s AND c.relkind='r'",(self.f.schema,)).fetchall():
                conn.execute(f'ANALYZE {self.f.schema}.{row["relname"]}')
        runtime.BackfillRuntimeTests.setUp(self)
        claim=self.new();rows=[self.article(id='article-'+str(i)) for i in range(1000)]
        start=perf_counter();self.commit(claim,rows);elapsed=perf_counter()-start
        self.assertLess(elapsed,12,{'phase_seconds':self._commit_timings})
        self.assertEqual(self.report()['N01']['committed_records'],1000)
        keys=self.keys();measurements=[]
        with self.f.admin() as conn:
            body=conn.execute('SELECT prosrc FROM pg_proc WHERE oid=%s::regprocedure',
                (self.f.schema+'.backfill_shared_refresh_v2(text,jsonb)',)).fetchone()['prosrc']
            delete=body.index('\n DELETE FROM')
            first=body[body.index(' WITH keys AS'):delete]
            second=body[body.index(' WITH keys AS',delete):body.rindex('\nEND')]
            # Readback invokes refresh under the existing shared project's
            # SECURITY DEFINER owner; the RPC owner has read-only table access.
            project_owner=conn.execute('SELECT pg_get_userbyid(proowner) owner FROM pg_proc WHERE oid=%s::regprocedure',
                (self.f.schema+'.backfill_shared_project_v2(text,integer)',)).fetchone()['owner']
            conn.execute(self.f.psycopg.sql.SQL('SET LOCAL ROLE {}').format(self.f.psycopg.sql.Identifier(project_owner)))
            conn.execute("SET LOCAL statement_timeout='10s'")
            for label,query in (('records',first),('links',second)):
                query=re.sub(r'\bp_run\b','$1',query)
                query=re.sub(r'\bp_keys\b','$2',query)
                name='shared_projection_'+label
                conn.execute(f'PREPARE {name}(text,jsonb) AS '+query)
                for mode in ('force_generic_plan','force_custom_plan'):
                    conn.execute('SET LOCAL plan_cache_mode='+mode)
                    conn.execute('SAVEPOINT shared_plan_measurement')
                    if label=='links':
                        conn.execute(f'DELETE FROM {self.f.schema}.backfill_shared_links_v2 WHERE run_id=%s AND record_key=ANY(%s)',(self.run,keys))
                    command=self.f.psycopg.sql.SQL('EXPLAIN(ANALYZE,BUFFERS,FORMAT JSON) EXECUTE {} ({},{})').format(
                        self.f.psycopg.sql.Identifier(name),self.f.psycopg.sql.Literal(self.run),self.f.psycopg.sql.Literal(json.dumps(keys)))
                    plan=conn.execute(command).fetchone()['QUERY PLAN'][0]
                    conn.execute('ROLLBACK TO SAVEPOINT shared_plan_measurement')
                    conn.execute('RELEASE SAVEPOINT shared_plan_measurement')
                    rows=list(nodes(plan['Plan']))
                    repeated_groups=[{k:n[k] for k in ('Node Type','Actual Rows','Actual Loops') if k in n}
                        for n in rows if n.get('Node Type') in ('Aggregate','GroupAggregate','HashAggregate')
                        and n.get('Actual Rows',0)>1 and n.get('Actual Loops',0)>1]
                    self.assertEqual(repeated_groups,[],{'label':label,'mode':mode,'repeated_groups':repeated_groups})
                    self.assertTrue(all(n.get('Actual Loops',0)<=1 for n in rows if n.get('Node Type')=='CTE Scan'),
                                    {'label':label,'mode':mode,'repeated_ctes':[(n.get('CTE Name'),n.get('Actual Loops')) for n in rows if n.get('Node Type')=='CTE Scan']})
                    archive_nodes=[n for n in rows if 'Scan' in n.get('Node Type','') and n.get('Relation Name') in ('backfill_shared_versions_v2','backfill_shared_records_v2',
                        'backfill_shared_version_links_v2','backfill_shared_occurrences_v2')]
                    self.assertTrue(archive_nodes)
                    self.assertTrue(all('record_key' in n.get('Index Cond','') for n in archive_nodes),
                                    {'label':label,'mode':mode,'nodes':archive_nodes})
                    self.assertLess(plan['Execution Time'],2500)
                    measurements.append({'query':label,'mode':mode,'milliseconds':plan['Execution Time'],
                        'cost':plan['Plan']['Total Cost'],'archive_lookups':len(archive_nodes),
                        'repeated_grouped_results':len(repeated_groups),'maximum_cte_scan_loops':max(n.get('Actual Loops',0) for n in rows if n.get('Node Type')=='CTE Scan')})
        PERFORMANCE.update(news_rpc_seconds=elapsed,phase_seconds=self._commit_timings,prior_option_records=10000,
                           news_records=1000,analyzed_fixture=True,plans=measurements)


if __name__=='__main__':unittest.main()
