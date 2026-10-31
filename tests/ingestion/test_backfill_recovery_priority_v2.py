"""Due recovery must not wait behind an ever-growing pending family backlog."""
import json
import os
from pathlib import Path
import unittest

import test_backfill_family_fairness_v2 as fairness

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'), 'Explicit disposable PostgreSQL required')
class RecoveryPriorityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fairness.FamilyFairnessTests.setUpClass.__func__(cls)
        f=cls.fixture('runTest')
        with f.admin() as conn:
            cls.original_dispatch=conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (f.schema+'.backfill_dispatch_v2(text,jsonb)',)).fetchone()['d']

    def setUp(self):
        fairness.FamilyFairnessTests.setUp(self)
        with self.f.admin() as conn:
            conn.execute(self.original_dispatch)
            conn.execute(f'DROP INDEX IF EXISTS {self.f.schema}.backfill_tasks_recovery_turn_v2')

    task=fairness.FamilyFairnessTests.task
    call=fairness.FamilyFairnessTests.call
    claim=fairness.FamilyFairnessTests.claim
    fence=staticmethod(fairness.FamilyFairnessTests.fence)

    def apply(self):
        sql=(ROOT/'sql/astra_backfill_recovery_priority_v2.sql').read_text()
        sql=sql.replace('astra_ingestion_v1',self.f.schema).replace('fixed3000-20250901-20260731-v1-20261030',self.run)
        with self.f.admin() as conn:
            conn.execute(sql)

    def backlog(self, count=100):
        template=self.task(priority=1)
        with self.f.admin() as conn:
            conn.execute(f'''UPDATE {self.f.schema}.backfill_tasks_v2
                SET created_at=clock_timestamp()-interval '1 hour',next_retry_at=clock_timestamp()-interval '1 hour' WHERE id=%s''',(template,))
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_tasks_v2
                (id,run_id,family,provider,kind,scope,priority,created_at,next_retry_at)
                SELECT run_id||'-pending-'||i,run_id,family,provider,kind,scope,1,created_at,next_retry_at
                FROM {self.f.schema}.backfill_tasks_v2 CROSS JOIN generate_series(1,%s) i WHERE id=%s''',(count-1,template))
        return template

    def accounting(self):
        with self.f.admin() as conn:
            return conn.execute(f'''SELECT requests_reserved,pages_committed,records_committed,source_bytes,last_progress_at
                FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s''',(self.run,)).fetchone()

    def test_real_pacing_deferral_resumes_when_due_before_one_hundred_pending_tasks(self):
        retry_id=self.task(priority=900)
        original=self.claim()
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.source_limits SET next_request_at=extract(epoch FROM clock_timestamp())+30 WHERE id='alpaca'")
        deferred=self.call('backfill_reserve',{'claim':self.fence(original)})
        self.assertEqual(deferred['state'],'request_deferred')
        with self.f.admin() as conn:
            # Advance the fixture clock conditions without a real sleep.
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET next_retry_at=clock_timestamp()-interval '1 second' WHERE id=%s",(retry_id,))
            conn.execute(f"UPDATE {self.f.schema}.source_limits SET next_request_at=extract(epoch FROM clock_timestamp())-1 WHERE id='alpaca'")
            before=conn.execute(f'SELECT to_jsonb(t) row FROM {self.f.schema}.backfill_tasks_v2 t WHERE id=%s',(retry_id,)).fetchone()['row']
        self.backlog()
        accounting=self.accounting()
        self.apply()
        with self.f.admin() as conn:
            self.assertEqual(before,conn.execute(f'SELECT to_jsonb(t) row FROM {self.f.schema}.backfill_tasks_v2 t WHERE id=%s',(retry_id,)).fetchone()['row'])
        self.assertEqual(accounting,self.accounting())
        resumed=self.claim(worker='after-pacing-deadline')
        self.assertEqual(resumed['id'],retry_id)
        self.assertGreater(resumed['generation'],original['generation'])
        self.assertEqual(resumed['page_no'],original['page_no'])
        self.assertEqual(resumed['cursor'],original['cursor'])
        self.assertEqual(resumed['requests_reserved'],0)
        self.assertEqual(resumed['page_attempts'],1)
        self.assertEqual(accounting,self.accounting())
        self.assertEqual(self.call('backfill_reserve',{'claim':self.fence(resumed)})['state'],'reserved')
        self.assertEqual(self.accounting()['requests_reserved'],1)

    def test_expired_lease_resumes_before_pending_and_old_owner_is_fenced(self):
        task_id=self.task(priority=900)
        old=self.claim(worker='stopped-worker')
        self.call('backfill_reserve',{'claim':self.fence(old)})
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",(task_id,))
        self.backlog()
        before=self.accounting()
        self.apply()
        resumed=self.claim(worker='existing-successor')
        self.assertEqual(resumed['id'],task_id)
        self.assertGreater(resumed['generation'],old['generation'])
        self.assertEqual(resumed['requests_reserved'],1)
        self.assertEqual(before,self.accounting())
        rejected=self.f.rpc('backfill_reserve',{'claim':self.fence(old)},actor='worker')
        self.assertFalse(rejected['ok'])
        self.assertEqual(rejected['error']['code'],'lease_lost')

    def test_live_lease_and_future_retry_are_excluded_and_long_provider_wait_is_preserved(self):
        live_id=self.task(priority=0)
        live=self.claim(worker='live-owner')
        future_id=self.task(priority=0)
        future=self.claim(worker='waiting-owner')
        self.call('backfill_reserve',{'claim':self.fence(future)})
        self.call('backfill_defer',{'claim':self.fence(future),'code':'SOURCE_RATE_LIMIT','message':'Fixture429',
            'retryable':True,'retry_after':90000,'evidence':{'http_status':429}})
        self.backlog()
        with self.f.admin() as conn:
            before_limit=conn.execute(f"SELECT next_request_at FROM {self.f.schema}.source_limits WHERE id='alpaca'").fetchone()['next_request_at']
            before_future=conn.execute(f'SELECT to_jsonb(t) row FROM {self.f.schema}.backfill_tasks_v2 t WHERE id=%s',(future_id,)).fetchone()['row']
        before=self.accounting()
        self.apply()
        claimed=self.claim(worker='available-worker')
        self.assertEqual(claimed['priority'],1)
        self.assertNotIn(claimed['id'],[live_id,future_id])
        self.assertEqual(self.call('backfill_reserve',{'claim':self.fence(claimed)})['state'],'request_deferred')
        self.assertEqual(before,self.accounting())
        with self.f.admin() as conn:
            self.assertEqual(before_limit,conn.execute(f"SELECT next_request_at FROM {self.f.schema}.source_limits WHERE id='alpaca'").fetchone()['next_request_at'])
            self.assertEqual(before_future,conn.execute(f'SELECT to_jsonb(t) row FROM {self.f.schema}.backfill_tasks_v2 t WHERE id=%s',(future_id,)).fetchone()['row'])
            row=conn.execute(f'SELECT owner,generation FROM {self.f.schema}.backfill_tasks_v2 WHERE id=%s',(live_id,)).fetchone()
            self.assertEqual((row['owner'],row['generation']),(live['owner'],live['generation']))

    def test_due_recovery_preserves_dependency_breadth_and_family_rotation(self):
        dependency=self.backlog()
        blocked=self.task(kind='derive_intraday',provider='DERIVED',family='D01',dependencies=[dependency],priority=0)
        breadth=self.task(kind='derive_breadth',provider='DERIVED',family='CTX06',scope={
            'target_start':'2025-09-02','target_end':'2025-09-02','source_month':'2025-09-01',
            'representative_security':{'member-1':{'symbol':'AAPL','eligible':None}}},priority=0)
        news=self.task(kind='alpaca_news',family='N01',priority=900)
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET status='RETRY_WAIT',next_retry_at=clock_timestamp()-interval '1 second' WHERE id=ANY(%s)",([blocked,breadth,news],))
        self.apply()
        kinds=['alpaca_reference','alpaca_news','derive_intraday','derive_breadth']
        self.assertEqual(self.claim(kinds)['family'],'REF01')
        self.assertEqual(self.claim(kinds)['id'],news)
        with self.f.admin() as conn:
            rows=conn.execute(f'SELECT attempts,requests_reserved FROM {self.f.schema}.backfill_tasks_v2 WHERE id=ANY(%s)',([blocked,breadth],)).fetchall()
            self.assertTrue(all(row['attempts']==0 and row['requests_reserved']==0 for row in rows))

    def test_recovery_probe_uses_its_partial_index_without_sorting_pending_backlog(self):
        retry=self.task(priority=900)
        self.backlog(6000)
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET status='RETRY_WAIT',next_retry_at=clock_timestamp()-interval '1 second' WHERE id=%s",(retry,))
            conn.execute(f'ANALYZE {self.f.schema}.backfill_tasks_v2')
        self.apply()
        with self.f.admin() as conn:
            definition=conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (self.f.schema+'.backfill_dispatch_v2(text,jsonb)',)).fetchone()['d']
            start=definition.index('SELECT q.* INTO t FROM '+self.f.schema+'.backfill_tasks_v2 q JOIN')
            end=definition.index('LIMIT 1 FOR UPDATE OF q;',start)+len('LIMIT 1 FOR UPDATE OF q;')
            query=definition[start:end].replace('SELECT q.* INTO t FROM','SELECT q.* FROM')
            for old,new in (('v_fair_run','%(run)s'),('v_fair_pick.family','%(family)s'),
                            ('v_supported','%(supported)s::jsonb'),('v_now','clock_timestamp()')):
                query=query.replace(old,new)
            plan=conn.execute('EXPLAIN (ANALYZE,FORMAT JSON) '+query,
                {'run':self.run,'family':'REF01','supported':json.dumps(['alpaca_reference'])}).fetchone()['QUERY PLAN'][0]
        def descendants(node):
            yield node
            for child in node.get('Plans',[]):
                yield from descendants(child)
        nodes=list(descendants(plan['Plan']))
        scan=next(node for node in nodes if node.get('Alias')=='q')
        self.assertEqual(scan.get('Index Name'),'backfill_tasks_recovery_turn_v2')
        self.assertEqual(scan['Actual Rows'],1)
        self.assertFalse(any(node['Node Type'] in ('Sort','Incremental Sort') for node in nodes))


if __name__=='__main__':unittest.main()
