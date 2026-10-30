"""Paid-provider pacing retains durable deferrals and the existing lock boundary."""
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import threading
import unittest

import test_backfill_runtime_v2 as runtime

ROOT=Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'),'Explicit disposable PostgreSQL required')
class BackfillProviderPacingTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        runtime.BackfillRuntimeTests.setUpClass.__func__(cls)
        f=cls.fixture('runTest')
        with f.admin() as conn:
            cls.original_dispatch=conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (f.schema+'.backfill_dispatch_v2(text,jsonb)',)).fetchone()['d']

    def setUp(self):
        runtime.BackfillRuntimeTests.setUp(self)
        with self.f.admin() as conn:
            conn.execute(self.original_dispatch)

    task=runtime.BackfillRuntimeTests.task
    call=runtime.BackfillRuntimeTests.call
    claim=runtime.BackfillRuntimeTests.claim
    fence=staticmethod(runtime.BackfillRuntimeTests.fence)

    def apply(self):
        sql=(ROOT/'sql/astra_backfill_provider_pacing_v2.sql').read_text()
        sql=sql.replace('astra_ingestion_v1',self.f.schema).replace('fixed3000-20250901-20260731-v1-20261030',self.run)
        with self.f.admin() as conn:
            conn.execute(sql)

    def reserve(self,claim):
        return self.call('backfill_reserve',{'claim':self.fence(claim)})

    def test_migration_preserves_existing_deadlines_legacy_evidence_and_dispatcher(self):
        with self.f.admin() as conn:
            conn.execute(f'''INSERT INTO {self.f.schema}.jobs
                (id,request_key,scope_hash,name,spec,status,created_at,updated_at,deadline_at,request_count,record_count,receipt_bytes)
                VALUES('old-completed','old-request','old-scope','Preserved legacy canary',%s,'completed',1,2,3,3,234,456)''',
                (json.dumps({'max_requests':10,'max_records':1000,'deadline_seconds':300}),))
            conn.execute(f'UPDATE {self.f.schema}.source_limits SET next_request_at=extract(epoch FROM clock_timestamp())+90000')
            before_jobs=conn.execute(f'SELECT to_jsonb(j) value FROM {self.f.schema}.jobs j').fetchall()
            before_limits=conn.execute(f'SELECT * FROM {self.f.schema}.source_limits ORDER BY id').fetchall()
            before_dispatch=conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (self.f.schema+'.rpc_dispatch(text,jsonb)',)).fetchone()['d']
            before_counts=conn.execute(f'SELECT requests_reserved,pages_committed,records_committed FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s',(self.run,)).fetchone()
        self.apply()
        with self.f.admin() as conn:
            self.assertEqual(before_jobs,conn.execute(f'SELECT to_jsonb(j) value FROM {self.f.schema}.jobs j').fetchall())
            self.assertEqual(before_limits,conn.execute(f'SELECT * FROM {self.f.schema}.source_limits ORDER BY id').fetchall())
            self.assertEqual(before_dispatch,conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (self.f.schema+'.rpc_dispatch(text,jsonb)',)).fetchone()['d'])
            self.assertEqual(before_counts,conn.execute(f'SELECT requests_reserved,pages_committed,records_committed FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s',(self.run,)).fetchone())
            policy=conn.execute(f"SELECT metadata->'provider_pacing_policy' policy FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s",(self.run,)).fetchone()['policy']
            self.assertEqual(policy['minimum_interval_seconds'],{'Alpaca':1,'Massive':1})
        with self.assertRaises(self.f.psycopg.Error):
            self.apply()

    def test_each_provider_uses_one_second_without_burning_deferred_attempt(self):
        self.apply()
        for provider,kind in [('Alpaca','alpaca_reference'),('Massive','massive_reference')]:
            with self.subTest(provider=provider):
                first_id=self.task(provider=provider,kind=kind,priority=1)
                second_id=self.task(provider=provider,kind=kind,priority=2)
                first=self.claim([kind],worker='first-'+provider)
                self.assertEqual(first['id'],first_id)
                self.assertEqual(self.reserve(first)['state'],'reserved')
                with self.f.admin() as conn:
                    row=conn.execute(f'''SELECT l.next_request_at-extract(epoch FROM t.reserved_at) spacing
                        FROM {self.f.schema}.backfill_tasks_v2 t JOIN {self.f.schema}.source_limits l ON l.id=lower(t.provider)
                        WHERE t.id=%s''',(first_id,)).fetchone()
                    self.assertAlmostEqual(row['spacing'],1.0,places=5)
                second=self.claim([kind],worker='second-'+provider)
                self.assertEqual(second['id'],second_id)
                self.assertEqual(self.reserve(second)['state'],'request_deferred')
                with self.f.admin() as conn:
                    row=conn.execute(f'SELECT page_attempts,requests_reserved FROM {self.f.schema}.backfill_tasks_v2 WHERE id=%s',(second_id,)).fetchone()
                    self.assertEqual(dict(row),{'page_attempts':0,'requests_reserved':0})

    def test_existing_and_new_long_retry_after_deadlines_remain_provider_wide(self):
        self.task(kind='massive_reference',provider='Massive',priority=1)
        self.task(kind='massive_reference',provider='Massive',priority=2)
        first=self.claim(['massive_reference'])
        self.reserve(first)
        self.call('backfill_defer',{'claim':self.fence(first),'code':'SOURCE_RATE_LIMIT','message':'Fixture429',
            'retryable':True,'retry_after':90000,'evidence':{'http_status':429}})
        with self.f.admin() as conn:
            deadline=conn.execute(f"SELECT next_request_at FROM {self.f.schema}.source_limits WHERE id='massive'").fetchone()['next_request_at']
        self.apply()
        second=self.claim(['massive_reference'])
        deferred=self.reserve(second)
        self.assertEqual(deferred['state'],'request_deferred')
        with self.f.admin() as conn:
            self.assertEqual(deadline,conn.execute(f"SELECT next_request_at FROM {self.f.schema}.source_limits WHERE id='massive'").fetchone()['next_request_at'])
            row=conn.execute(f'''SELECT page_attempts,requests_reserved,
                extract(epoch FROM next_retry_at-clock_timestamp()) remaining FROM {self.f.schema}.backfill_tasks_v2 WHERE id=%s''',(second['id'],)).fetchone()
            self.assertEqual(row['page_attempts'],0)
            self.assertEqual(row['requests_reserved'],0)
            self.assertGreater(row['remaining'],89990)

    def test_parallel_reservations_share_existing_global_lock_and_provider_slot(self):
        self.apply()
        self.task(priority=1);self.task(priority=2)
        first=self.claim(worker='parallel-a');second=self.claim(worker='parallel-b')
        started=threading.Event()
        def attempt(claim):
            started.set()
            return self.reserve(claim)
        with ThreadPoolExecutor(max_workers=2) as pool:
            # The existing outer RPC lock must prevent admission even though
            # neither source_limits row is locked by this transaction.
            with self.f.admin() as blocker:
                blocker.execute('SELECT pg_advisory_xact_lock(706314020261028)')
                a=pool.submit(attempt,first)
                self.assertTrue(started.wait(1))
                with self.assertRaises(TimeoutError):a.result(timeout=.1)
                b=pool.submit(attempt,second)
            results=[a.result(timeout=5),b.result(timeout=5)]
        self.assertEqual(sorted(v['state'] for v in results),['request_deferred','reserved'])
        with self.f.admin() as conn:
            total=conn.execute(f'SELECT requests_reserved FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s',(self.run,)).fetchone()['requests_reserved']
            self.assertEqual(total,1)


if __name__=='__main__':unittest.main()
