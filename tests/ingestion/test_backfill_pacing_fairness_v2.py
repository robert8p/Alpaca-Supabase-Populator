"""Real RPC reproduction of claim-fair but reservation-starved options work."""
import os
from pathlib import Path
import time
import unittest

import test_backfill_family_fairness_v2 as fairness
import test_backfill_runtime_v2 as runtime

ROOT=Path(__file__).resolve().parents[2]
KINDS=['alpaca_reference','alpaca_option_contracts']


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'), 'Explicit disposable PostgreSQL required')
class ShortPacingFairnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        fairness.FamilyFairnessTests.setUpClass.__func__(cls)
        f=cls.fixture('runTest')
        with f.admin() as conn:
            for name in ('astra_backfill_adaptive_pages_v2.sql','astra_backfill_canonical_performance_v2.sql',
                         'astra_backfill_recovery_priority_v2.sql'):
                sql=(ROOT/'sql'/name).read_text().replace('astra_ingestion_v1',f.schema).replace('astra_ingestion_rpc_owner_v1',f.owner)
                conn.execute(sql)
            cls.stage2_dispatch=conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (f.schema+'.backfill_dispatch_v2(text,jsonb)',)).fetchone()['d']

    def setUp(self):
        fairness.FamilyFairnessTests.setUp(self)
        with self.f.admin() as conn:
            conn.execute(self.stage2_dispatch)

    task=runtime.BackfillRuntimeTests.task
    call=runtime.BackfillRuntimeTests.call
    claim=runtime.BackfillRuntimeTests.claim
    fence=staticmethod(runtime.BackfillRuntimeTests.fence)
    page=runtime.BackfillRuntimeTests.page

    def apply(self):
        sql=(ROOT/'sql/astra_backfill_pacing_fairness_v2.sql').read_text()
        sql=sql.replace('astra_ingestion_v1',self.f.schema).replace('fixed3000-20250901-20260731-v1-20261030',self.run)
        with self.f.admin() as conn:
            conn.execute(sql)

    def options(self):
        return self.task(kind='alpaca_option_contracts',family='CTX02',scope={
            'symbols':['AAPL'],'member_ids':['member-1'],'status':'inactive'})

    def reserve(self,claim):
        return self.call('backfill_reserve',{'claim':self.fence(claim)})

    def turn(self):
        with self.f.admin() as conn:
            return conn.execute(f'SELECT * FROM {self.f.schema}.backfill_family_turn_v2 WHERE run_id=%s',(self.run,)).fetchone()

    def accounting(self):
        with self.f.admin() as conn:
            return conn.execute(f'''SELECT requests_reserved,pages_committed,records_committed,source_bytes,last_progress_at
                FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s''',(self.run,)).fetchone()

    def source_deadline(self,provider='alpaca'):
        with self.f.admin() as conn:
            return conn.execute(f'SELECT next_request_at FROM {self.f.schema}.source_limits WHERE id=%s',(provider,)).fetchone()['next_request_at']

    def test_stage2_reproduces_repeated_options_deferral_while_reference_progresses(self):
        for _ in range(3):self.task(priority=1)
        option_id=self.options()
        generations=[]
        for cycle in range(3):
            reference=self.claim(KINDS)
            self.assertEqual(reference['family'],'REF01')
            self.assertEqual(self.reserve(reference)['state'],'reserved')
            self.assertEqual(self.call('backfill_commit',self.page(reference))['task_status'],'INGESTED')
            options=self.claim(KINDS)
            self.assertEqual(options['id'],option_id)
            self.assertEqual(self.reserve(options)['state'],'request_deferred')
            self.assertEqual(self.turn()['next_family_index'],16)
            generations.append(options['generation'])
            if cycle<2:time.sleep(2.05)  # Existing worker's real two-second waiting cadence.
        with self.f.admin() as conn:
            row=conn.execute(f'SELECT status,generation,page_attempts,requests_reserved FROM {self.f.schema}.backfill_tasks_v2 WHERE id=%s',(option_id,)).fetchone()
        self.assertEqual(dict(row),{'status':'RETRY_WAIT','generation':3,'page_attempts':0,'requests_reserved':0})
        self.assertEqual(generations,[1,2,3])
        self.assertEqual(self.accounting()['pages_committed'],3)
        self.assertEqual(self.accounting()['requests_reserved'],3)

    def test_short_deferral_retains_turn_then_the_same_options_family_reserves(self):
        self.apply()
        self.task(priority=1);self.task(priority=2)
        option_id=self.options()
        reference=self.claim(KINDS)
        self.reserve(reference)
        self.call('backfill_commit',self.page(reference))
        options=self.claim(KINDS)
        before_counts=self.accounting();before_deadline=self.source_deadline();before_turn=self.turn()
        deferred=self.reserve(options)
        self.assertEqual(deferred['state'],'request_deferred')
        after_turn=self.turn()
        self.assertEqual(after_turn['next_family_index'],15)
        self.assertEqual(after_turn['last_claimed_task_id'],option_id)
        self.assertEqual(after_turn['claim_turns'],before_turn['claim_turns'])
        self.assertEqual(self.source_deadline(),before_deadline)
        self.assertEqual(self.accounting(),before_counts)
        with self.f.admin() as conn:
            row=conn.execute(f'SELECT status,owner,lease_until,page_attempts,requests_reserved,attempts FROM {self.f.schema}.backfill_tasks_v2 WHERE id=%s',(option_id,)).fetchone()
        self.assertEqual(dict(row),{'status':'RETRY_WAIT','owner':None,'lease_until':None,'page_attempts':0,'requests_reserved':0,'attempts':1})
        time.sleep(2.05)
        resumed=self.claim(KINDS,worker='same-existing-loop')
        self.assertEqual(resumed['id'],option_id)
        self.assertEqual(resumed['generation'],options['generation']+1)
        self.assertEqual((resumed['page_no'],resumed['cursor']),(options['page_no'],options['cursor']))
        self.assertEqual(self.reserve(resumed)['state'],'reserved')
        self.assertEqual(self.accounting()['requests_reserved'],before_counts['requests_reserved']+1)
        self.assertEqual(self.turn()['next_family_index'],16)
        self.assertEqual(self.claim(KINDS)['family'],'REF01')

    def test_long_retry_after_preserves_deadline_and_rotates_to_other_provider(self):
        self.apply()
        self.task(priority=1);self.options()
        reference=self.claim(KINDS)
        self.reserve(reference)
        self.call('backfill_defer',{'claim':self.fence(reference),'code':'SOURCE_RATE_LIMIT','message':'Fixture429',
            'retryable':True,'retry_after':90000,'evidence':{'http_status':429}})
        before_deadline=self.source_deadline()
        options=self.claim(KINDS)
        before_turn=self.turn();before_counts=self.accounting()
        self.assertEqual(self.reserve(options)['state'],'request_deferred')
        self.assertEqual(self.turn(),before_turn)
        self.assertEqual(self.accounting(),before_counts)
        self.assertEqual(self.source_deadline(),before_deadline)
        healthy_id=self.task(kind='massive_short_volume',provider='Massive',family='S01')
        healthy=self.claim(KINDS+['massive_short_volume'])
        self.assertEqual(healthy['id'],healthy_id)
        self.assertEqual(self.reserve(healthy)['state'],'reserved')
        self.assertEqual(self.source_deadline(),before_deadline)

    def test_interleaved_later_claim_and_stale_owner_cannot_rewind_the_cursor(self):
        self.apply()
        self.task(priority=1);self.task(priority=2);self.options()
        first=self.claim(KINDS,worker='first')
        options=self.claim(KINDS,worker='interleaved-options')
        latest=self.claim(KINDS,worker='latest-reference')
        self.assertNotEqual(first['id'],latest['id'])
        self.assertEqual(latest['family'],'REF01')
        self.reserve(latest)
        before=self.turn();deadline=self.source_deadline();counts=self.accounting()
        self.assertEqual(self.reserve(options)['state'],'request_deferred')
        self.assertEqual(self.turn(),before)
        self.assertEqual(self.source_deadline(),deadline)
        self.assertEqual(self.accounting(),counts)
        rejected=self.f.rpc('backfill_reserve',{'claim':self.fence(options)},actor='worker')
        self.assertFalse(rejected['ok']);self.assertEqual(rejected['error']['code'],'lease_lost')
        self.assertEqual(self.turn(),before)

    def test_stopped_run_is_fenced_and_cannot_adjust_any_family_turn(self):
        self.apply()
        self.options()
        options=self.claim(KINDS)
        before=self.turn()
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.source_limits SET next_request_at=extract(epoch FROM clock_timestamp())+0.75 WHERE id='alpaca'")
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET status='PAUSED',fence=fence+1 WHERE id=%s",(self.run,))
        rejected=self.f.rpc('backfill_reserve',{'claim':self.fence(options)},actor='worker')
        self.assertFalse(rejected['ok']);self.assertEqual(rejected['error']['code'],'lease_lost')
        self.assertEqual(self.turn(),before)

    def test_forward_install_preserves_existing_task_deadline_cursor_and_counters(self):
        self.options()
        options=self.claim(KINDS)
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.source_limits SET next_request_at=extract(epoch FROM clock_timestamp())+90000 WHERE id='alpaca'")
        self.reserve(options)
        before_counts=self.accounting();before_turn=self.turn();before_deadline=self.source_deadline()
        with self.f.admin() as conn:
            before_task=conn.execute(f'SELECT to_jsonb(t) value FROM {self.f.schema}.backfill_tasks_v2 t WHERE id=%s',(options['id'],)).fetchone()['value']
        self.apply()
        self.assertEqual(self.accounting(),before_counts)
        self.assertEqual(self.turn(),before_turn)
        self.assertEqual(self.source_deadline(),before_deadline)
        with self.f.admin() as conn:
            self.assertEqual(before_task,conn.execute(f'SELECT to_jsonb(t) value FROM {self.f.schema}.backfill_tasks_v2 t WHERE id=%s',(options['id'],)).fetchone()['value'])
        with self.assertRaises(self.f.psycopg.Error):self.apply()


if __name__=='__main__':unittest.main()
