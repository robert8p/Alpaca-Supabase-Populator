"""Scoped real-PostgreSQL replacement queue and authenticated receipt tests."""
import hashlib
import json
import os
from pathlib import Path
import re
import unittest
import uuid

import test_rpc_postgres as legacy

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'), 'Explicit disposable PostgreSQL required')
class BackfillRuntimeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.fixture = type('ReplacementRuntimeFixture', (legacy.RPCPostgreSQLTests,), {})
        cls.fixture.setUpClass()
        cls.addClassCleanup(cls.fixture.cleanup)
        f = cls.fixture('runTest')
        with f.admin() as conn:
            for filename in ('astra_ingestion_supersede_gate_v2.sql', 'astra_backfill_runtime_v2.sql'):
                sql = (ROOT / 'sql' / filename).read_text()
                sql = sql.replace('astra_ingestion_v1', f.schema).replace('astra_ingestion_rpc_owner_v1', f.owner)
                conn.execute(sql)

    def setUp(self):
        self.f = self.fixture('runTest')
        self.f.setUp()
        self.run = 'run-' + uuid.uuid4().hex
        with self.f.admin() as conn:
            conn.execute(f'UPDATE {self.f.schema}.source_limits SET next_request_at=0')
            conn.execute(f"UPDATE {self.f.schema}.backfill_workers_v2 SET observed_at=clock_timestamp()-interval '11 minutes'")
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET status='PAUSED',fence=fence+1 WHERE status='ACTIVE'")
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_runs_v2
                (id,instruction_sha256,cohort_sha256,cohort_manifest_sha256,cohort_ref,scope)
                VALUES(%s,%s,%s,%s,%s,%s)''', (self.run, '1'*64,
                '2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec',
                '4134b415e2c26fcde9fced749c0d54ef51376e23f0d2f8c6ce9ef562f9fab99f', 'fixture-fixed-cohort', '{}'))
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_members_v2(run_id,member_id,selection_order,anchor_ticker)
                SELECT %s,'member-'||g::text,g,CASE WHEN g=1 THEN 'AAPL' ELSE 'T'||g::text END FROM generate_series(1,3000) g''', (self.run,))

    def task(self, *, kind='alpaca_reference', family='REF01', provider='Alpaca', scope=None, dependencies=None, priority=100):
        key = 'task-' + uuid.uuid4().hex
        scope = scope or {'symbols': ['AAPL'], 'member_ids': ['member-1']}
        with self.f.admin() as conn:
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_tasks_v2
                (id,run_id,family,provider,kind,scope,dependencies,priority)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s)''',
                (key,self.run,family,provider,kind,json.dumps(scope),dependencies or [],priority))
        return key

    def call(self, operation, payload, actor='worker'):
        return self.f.ok(operation, payload, actor=actor)

    def claim(self, kinds=None, worker='replacement-worker'):
        return self.call('backfill_claim', {'worker_id':worker,'lease_seconds':120,
            'supported_kinds':kinds or ['alpaca_reference'],'source_revision':'test-revision'})

    @staticmethod
    def fence(task):
        return {k: task[k] for k in ('id','run_id','owner','generation','run_fence','page_no')}

    def page(self, claim, *, symbol='AAPL', next_cursor=None):
        raw = json.dumps({'id':'asset-apple','symbol':symbol})
        request = {'provider':'Alpaca','method':'GET','host':'paper-api.alpaca.markets',
                   'path':'/v2/assets/AAPL','params':{}}
        if claim.get('cursor') is not None:
            request['params']['page_token'] = claim['cursor']
        return {'claim':self.fence(claim),'raw_body':raw,
                'body_sha256':hashlib.sha256(raw.encode()).hexdigest(), 'http_status':200,
                'request_id':'fixture-request','fetched_at':'2026-10-30T05:00:00Z',
                'request':request,'records':[{'symbol':symbol,'source':json.loads(raw)}],
                'next_cursor':next_cursor,'quality':[],'headers':{},'adapter_version':'test-v2'}

    def test_real_page_auto_successor_and_lost_ack_readback(self):
        first, second = self.task(priority=1), self.task(priority=2)
        claim = self.claim()
        self.assertEqual(claim['id'],first)
        self.assertEqual(self.call('backfill_reserve',{'claim':self.fence(claim)})['state'],'reserved')
        self.assertEqual(self.call('backfill_reserve',{'claim':self.fence(claim)})['state'],'already_reserved')
        payload=self.page(claim)
        result=self.call('backfill_commit',payload)
        self.assertEqual(result['task_status'],'INGESTED')
        self.assertEqual(self.call('backfill_commit',payload)['state'],'already_committed')
        readback=self.call('backfill_verify',{'claim':self.fence(claim),'page_no':0})
        self.assertEqual(readback['body_sha256'],readback['readback_sha256'])
        self.assertEqual(readback['raw_body'],payload['raw_body'])
        self.assertEqual(self.claim()['id'],second)
        with self.f.admin() as conn:
            row=conn.execute(f'SELECT requests_reserved,pages_committed,records_committed FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s',(self.run,)).fetchone()
            self.assertEqual(dict(row),dict(requests_reserved=1,pages_committed=1,records_committed=1))

    def test_stale_restart_and_deferred_retry_keep_original_cursor(self):
        self.task()
        old=self.claim(); self.call('backfill_reserve',{'claim':self.fence(old)})
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",(old['id'],))
        new=self.claim(worker='replacement-after-restart')
        self.assertGreater(new['generation'],old['generation'])
        refused=self.f.rpc('backfill_commit',self.page(old),actor='worker')
        self.assertFalse(refused['ok']);self.assertEqual(refused['error']['code'],'lease_lost')
        waiting=self.call('backfill_defer',{'claim':self.fence(new),'code':'PROVIDER_RATE_LIMIT','message':'fixture429','retryable':True,'retry_after':60,'evidence':{'http_status':429}})
        self.assertEqual(waiting['state'],'RETRY_WAIT')
        self.assertIsNone(self.claim())
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET next_retry_at=clock_timestamp()-interval '1 second' WHERE id=%s",(old['id'],))
        again=self.claim();self.assertEqual(again['id'],old['id']);self.assertEqual(again['page_no'],0)

    def test_auth_boundary_scope_and_source_evidence_rejection(self):
        self.task();claim=self.claim()
        with self.assertRaises(self.f.psycopg.Error) as denied:
            self.f.rpc('backfill_claim',{'worker_id':'api-pretender','lease_seconds':120,'supported_kinds':['alpaca_reference'],'source_revision':'test'},actor='api')
        self.assertEqual(denied.exception.sqlstate,'PT403')
        self.call('backfill_reserve',{'claim':self.fence(claim)})
        changed=self.page(claim);changed['records'][0]['source']['symbol']='UNREQUESTED'
        result=self.f.rpc('backfill_commit',changed,actor='worker')
        self.assertFalse(result['ok']);self.assertEqual(result['error']['code'],'quality_hold')
        changed=self.page(claim);changed['request']['host']='untrusted.example'
        self.assertFalse(self.f.rpc('backfill_commit',changed,actor='worker')['ok'])
        with self.f.admin() as conn:
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_pages_v2 WHERE run_id=%s',(self.run,)).fetchone()['n'],0)
            acl=conn.execute('SELECT has_table_privilege(%s,%s,\'SELECT\') can_read,has_function_privilege(%s,%s,\'EXECUTE\') can_call',
                (self.f.gateway,self.f.schema+'.backfill_pages_v2',self.f.gateway,self.f.schema+'.backfill_dispatch_v2(text,jsonb)')).fetchone()
            self.assertFalse(acl['can_read']);self.assertFalse(acl['can_call'])

    def test_empty_source_is_terminal_without_blocking_other_tasks(self):
        scope={'symbols':['AAPL'],'member_ids':['member-1'],'start':'2025-09-02T04:00:00-04:00','end':'2025-09-02T20:00:00-04:00','timeframe':'1Min','adjustment':'raw'}
        empty=self.task(kind='alpaca_stock_bars',family='P01',scope=scope,priority=1)
        next_task=self.task(priority=2)
        claim=self.claim(['alpaca_stock_bars','alpaca_reference']);self.call('backfill_reserve',{'claim':self.fence(claim)})
        raw='{"bars":{},"next_page_token":null}'
        payload=self.page(claim)
        payload.update(raw_body=raw,body_sha256=hashlib.sha256(raw.encode()).hexdigest(),records=[],request={'provider':'Alpaca','method':'GET','host':'data.alpaca.markets','path':'/v2/stocks/bars','params':{'symbols':'AAPL','start':scope['start'],'end':scope['end'],'timeframe':'1Min','adjustment':'raw','feed':'sip'}})
        self.assertEqual(self.call('backfill_commit',payload)['task_status'],'NO_DATA_RETURNED')
        self.assertEqual(self.claim(['alpaca_stock_bars','alpaca_reference'])['id'],next_task)

    def test_derived_material_uses_original_page_cursor_and_bounded_renewal(self):
        source=self.task()
        first=self.claim();self.call('backfill_reserve',{'claim':self.fence(first)})
        self.call('backfill_commit',self.page(first,next_cursor='next-page'))
        with self.f.admin() as conn:
            conn.execute(f'UPDATE {self.f.schema}.source_limits SET next_request_at=0')
        second=self.claim();self.call('backfill_reserve',{'claim':self.fence(second)})
        self.call('backfill_commit',self.page(second))
        self.task(kind='derive_daily',family='D02',provider='DERIVED',dependencies=[source])
        derived=self.claim(['derive_daily'])
        material=self.call('backfill_material',{'claim':self.fence(derived),'limit':1})
        self.assertIsNone(material['pages'][0]['task']['cursor'])
        self.assertFalse(material['complete'])
        next_page=self.call('backfill_material',{'claim':self.fence(derived),'limit':1,'after':material['next_after']})
        self.assertEqual(next_page['pages'][0]['task']['cursor'],'next-page')
        self.assertTrue(next_page['complete'])

    def test_options_enumeration_creates_scoped_executable_successor(self):
        scope={'symbols':['AAPL'],'member_ids':['member-1'],'status':'inactive'}
        self.task(kind='alpaca_option_contracts',family='CTX02',scope=scope)
        claim=self.claim(['alpaca_option_contracts'])
        self.call('backfill_reserve',{'claim':self.fence(claim)})
        contract={'symbol':'AAPL260117C00200000','underlying_symbol':'AAPL','id':'option-1'}
        raw=json.dumps({'option_contracts':[contract],'next_page_token':None})
        payload=self.page(claim)
        payload.update(raw_body=raw,body_sha256=hashlib.sha256(raw.encode()).hexdigest(),
            records=[{'symbol':contract['symbol'],'underlying_symbol':'AAPL','source':contract}],
            request={'provider':'Alpaca','method':'GET','host':'paper-api.alpaca.markets','path':'/v2/options/contracts','params':{'underlying_symbols':'AAPL','status':'inactive'}})
        self.assertEqual(self.call('backfill_commit',payload)['task_status'],'INGESTED')
        child=self.claim(['alpaca_option_bars'])
        self.assertEqual(child['scope']['symbols'],[contract['symbol']])
        self.assertEqual(child['scope']['member_ids'],['member-1'])
        self.assertEqual(child['family'],'CTX02')

    def test_status_reports_missing_capability_and_stop_fences_writes(self):
        self.task(kind='massive_reference',provider='Massive',scope={'symbols':['AAPL'],'member_ids':['member-1'],'asof':'2025-09-02'})
        self.assertIsNone(self.claim(['alpaca_reference']))
        result=self.call('backfill_status',{'run_id':self.run},actor='api')
        self.assertIn('massive_reference',result['runs'][0]['unsupported_pending_kinds'])
        self.task();claim=self.claim();self.call('backfill_reserve',{'claim':self.fence(claim)})
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET status='PAUSED',fence=fence+1 WHERE id=%s",(self.run,))
        rejected=self.f.rpc('backfill_commit',self.page(claim),actor='worker')
        self.assertFalse(rejected['ok']);self.assertEqual(rejected['error']['code'],'lease_lost')
        self.assertIsNone(self.claim())

    def test_derived_commit_needs_no_provider_reservation_and_is_counted_separately(self):
        self.task(kind='derive_daily',family='D02',provider='DERIVED')
        claim=self.claim(['derive_daily'])
        rows=[{'member_id':'member-1','market_date':'2025-09-02','close':100,'missing_reason':None}]
        raw=json.dumps({'rows':rows,'formula_version':'fixture-derived-v1','input_lineage':[],'limitations':[]})
        payload=self.page(claim)
        payload.update(raw_body=raw,body_sha256=hashlib.sha256(raw.encode()).hexdigest(),records=rows,
            request={'provider':'DERIVED','kind':'derive_daily'})
        self.assertEqual(self.call('backfill_commit',payload)['task_status'],'INGESTED')
        with self.f.admin() as conn:
            run=conn.execute(f'SELECT requests_reserved,pages_committed FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s',(self.run,)).fetchone()
            self.assertEqual(run['requests_reserved'],0);self.assertEqual(run['pages_committed'],1)

    def test_pacing_defers_without_attempt_burn_and_retry_after_is_provider_wide(self):
        self.task(priority=1);self.task(priority=2)
        first=self.claim();self.call('backfill_reserve',{'claim':self.fence(first)})
        self.call('backfill_defer',{'claim':self.fence(first),'code':'SOURCE_RATE_LIMIT','message':'fixture429',
            'retryable':True,'retry_after':90000,'evidence':{'http_status':429}})
        second=self.claim()
        deferred=self.call('backfill_reserve',{'claim':self.fence(second)})
        self.assertEqual(deferred['state'],'request_deferred')
        with self.f.admin() as conn:
            row=conn.execute(f'''SELECT page_attempts,requests_reserved,
                extract(epoch FROM next_retry_at-clock_timestamp()) delay FROM {self.f.schema}.backfill_tasks_v2 WHERE id=%s''',(second['id'],)).fetchone()
            self.assertEqual(row['page_attempts'],0);self.assertEqual(row['requests_reserved'],0)
            self.assertGreater(row['delay'],89990)

    def test_provider_dependency_holds_until_changed_capability_evidence(self):
        self.task(priority=1);second=self.task(priority=2)
        first=self.claim()
        blocked=self.call('backfill_defer',{'claim':self.fence(first),'code':'BLOCKED_EXTERNAL','message':'Missing configured credential',
            'retryable':False,'evidence':{'dependency':'ALPACA_WORKER_CREDENTIAL'}})
        self.assertEqual(blocked['state'],'BLOCKED_EXTERNAL')
        self.assertIsNone(self.claim())
        with self.f.admin() as conn:
            row=conn.execute(f'SELECT attempts,requests_reserved FROM {self.f.schema}.backfill_tasks_v2 WHERE id=%s',(second,)).fetchone()
            self.assertEqual(row['attempts'],0);self.assertEqual(row['requests_reserved'],0)
        changed=self.call('backfill_claim',{'worker_id':'replacement-worker','lease_seconds':120,
            'supported_kinds':['alpaca_reference'],'source_revision':'test-revision','capability_revision':'configured-credential-revision-2'})
        self.assertEqual(changed['id'],first['id'])
        status=self.call('backfill_status',{'run_id':self.run},actor='api')
        self.assertEqual(status['runs'][0]['provider_dependencies'][0]['state'],'AVAILABLE')


if __name__=='__main__':
    unittest.main()
