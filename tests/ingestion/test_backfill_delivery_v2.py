"""Queryable family delivery and strict finalization on disposable PostgreSQL."""
import hashlib
import json
from pathlib import Path
import unittest

from test_backfill_runtime_v2 import BackfillRuntimeTests
import test_rpc_postgres as legacy

ROOT = Path(__file__).resolve().parents[2]


class BackfillDeliveryTests(BackfillRuntimeTests):
    @classmethod
    def setUpClass(cls):
        cls.fixture=type('ReplacementDeliveryFixture',(legacy.RPCPostgreSQLTests,),{})
        cls.fixture.setUpClass()
        cls.addClassCleanup(cls.fixture.cleanup)
        f=cls.fixture('runTest')
        cls.monitor_role=f.owner.replace('_owner_','_monitor_')
        cls.addClassCleanup(cls.cleanup_monitor)
        observer=(ROOT/'sql/astra_ingestion_observer_v1.sql').read_text()
        observer=observer.replace('astra_ingestion_v1',f.schema).replace('astra_ingestion_monitor_owner_v1',cls.monitor_role)
        sql=(ROOT/'sql/astra_backfill_delivery_v2.sql').read_text()
        sql=sql.replace('astra_ingestion_v1',f.schema).replace('astra_ingestion_rpc_owner_v1',f.owner).replace('astra_ingestion_monitor_owner_v1',cls.monitor_role)
        with f.admin() as conn:
            conn.execute(observer)
            for filename in ('astra_ingestion_supersede_gate_v2.sql','astra_backfill_runtime_v2.sql'):
                runtime=(ROOT/'sql'/filename).read_text().replace('astra_ingestion_v1',f.schema).replace('astra_ingestion_rpc_owner_v1',f.owner)
                conn.execute(runtime)
            conn.execute(sql)

    @classmethod
    def cleanup_monitor(cls):
        if not hasattr(cls,'monitor_role'):
            return
        with cls.fixture.admin() as conn:
            if conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(cls.monitor_role,)).fetchone():
                conn.execute(f'DROP OWNED BY {cls.monitor_role}')
                conn.execute(f'DROP ROLE {cls.monitor_role}')

    def commit_minute_page(self,calendar=None):
        scope={'symbols':['AAPL'],'member_ids':['member-1'],'start':'2025-11-28T04:00:00-05:00',
               'end':'2025-11-28T20:00:00-05:00','timeframe':'1Min','adjustment':'raw',
               'calendar':calendar or [{'date':'2025-11-28','open':'09:30','close':'13:00'}]}
        self.task(kind='alpaca_stock_bars',family='P01',scope=scope)
        claim=self.claim(['alpaca_stock_bars'])
        self.call('backfill_reserve',{'claim':self.fence(claim)})
        bars=[{'t':stamp,'o':100,'h':101,'l':99,'c':100,'v':20} for stamp in (
            '2025-11-28T09:00:00Z','2025-11-28T17:59:00Z','2025-11-28T18:00:00Z','2025-11-29T01:00:00Z')]
        raw=json.dumps({'bars':{'AAPL':bars},'next_page_token':None})
        payload=self.page(claim)
        payload.update(raw_body=raw,body_sha256=hashlib.sha256(raw.encode()).hexdigest(),
            records=[{'symbol':'AAPL','source':bar} for bar in bars],
            request={'provider':'Alpaca','method':'GET','host':'data.alpaca.markets','path':'/v2/stocks/bars',
                     'params':{'symbols':'AAPL','start':scope['start'],'end':scope['end'],'timeframe':'1Min','adjustment':'raw','feed':'sip'}})
        self.call('backfill_commit',payload)
        return claim

    def test_regular_and_extended_views_share_one_archive_with_actual_early_close(self):
        claim=self.commit_minute_page()
        verified=self.call('backfill_verify',{'claim':self.fence(claim),'page_no':0})
        self.assertEqual(verified['verification']['state'],'VERIFIED')
        self.assertEqual(verified['verification']['rth_records'],1)
        self.assertEqual(verified['verification']['pre_records'],1)
        self.assertEqual(verified['verification']['post_records'],1)
        self.assertEqual(verified['verification']['unclassified_session_records'],1)
        with self.f.admin() as conn:
            for family,expected in [('p01',1),('p02',2)]:
                n=conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_family_{family}_v2 WHERE run_id=%s',(self.run,)).fetchone()['n']
                self.assertEqual(n,expected)
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_pages_v2 WHERE run_id=%s',(self.run,)).fetchone()['n'],1)
        status=self.call('backfill_delivery_status',{'run_id':self.run},actor='api')['runs'][0]
        families={row['family']:row for row in status['families']}
        self.assertEqual(len(families),16)
        self.assertEqual(families['P01']['committed_records'],1)
        self.assertEqual(families['P02']['committed_records'],2)
        self.assertGreaterEqual(families['REF03']['committed_records'],2)
        self.assertFalse(families['P01']['counts_are_additive_across_families'])

    def test_finalization_requires_planning_all_families_and_independent_readback(self):
        claim=self.commit_minute_page()
        self.assertEqual(self.call('backfill_finalize',{'run_id':self.run})['state'],'PLANNING_INCOMPLETE')
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET metadata='{{\"planning_complete\":true}}' WHERE id=%s",(self.run,))
        self.assertEqual(self.call('backfill_finalize',{'run_id':self.run})['state'],'FULL_PLAN_NOT_SEALED')
        calendar=json.loads((ROOT/'evidence/replacement-calendar-v1.json').read_text())
        workflow={'version':'synthetic-workflow-test-v1','target_start':'2025-09-01','target_end':'2026-07-31',
            'market_timezone':'America/New_York','representative_policy':'One representative and one vote for each frozen company',
            'session_dates':[r['date'] for r in calendar['sessions'] if '2025-09-01'<=r['date']<='2026-07-31']}
        def seal():
            with self.f.admin() as conn:
                planned=conn.execute(f'SELECT task_id,definition_sha256 FROM {self.f.schema}.backfill_plan_units_v2 WHERE run_id=%s ORDER BY task_id',(self.run,)).fetchall()
            manifest='\n'.join(r['task_id']+':'+r['definition_sha256'] for r in planned)
            return self.call('backfill_seal_plan',{'run_id':self.run,'expected_task_count':len(planned),
                'expected_plan_sha256':hashlib.sha256(manifest.encode()).hexdigest(),'workflow_plan':workflow})
        self.assertEqual(seal()['state'],'INCOMPLETE_MEMBER_DATE_WORKFLOWS')
        # Synthetic terminal fixture units qualify state transitions only. They
        # are not represented as provider acquisitions or populated observations.
        for family in ('REF01','P01','D01','D02','D03','D04','D05','N01','N02','N03','S01','S02','CTX02','CTX06'):
            scope={'symbols':['AAPL'],'member_ids':['member-'+str(i) for i in range(1,3001)],
                   'target_start':'2025-09-01','target_end':'2026-07-31','market_timezone':'America/New_York'}
            if family=='CTX06':
                scope['representative_security']={'member-'+str(i):{'symbol':'AAPL' if i==1 else 'T'+str(i),'eligible':None} for i in range(1,3001)}
            task=self.task(family=family,kind='alpaca_stock_bars' if family=='P01' else 'alpaca_reference',scope=scope)
            with self.f.admin() as conn:
                conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET status='NO_DATA_RETURNED' WHERE id=%s",(task,))
        self.assertEqual(seal()['state'],'FULL_PLAN_SEALED')
        self.assertEqual(self.call('backfill_finalize',{'run_id':self.run})['state'],'READBACK_PENDING')
        verified=self.call('backfill_verify',{'claim':self.fence(claim),'page_no':0,'include_raw':False})
        self.assertNotIn('raw_body',verified)
        self.assertEqual(verified['run_disposition']['state'],'COMPLETE_WITH_DOCUMENTED_GAPS')
        with self.f.admin() as conn:
            reason=conn.execute(f"SELECT metadata->>'coverage_disposition_reason' reason FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s",(self.run,)).fetchone()['reason']
            self.assertEqual(reason,'APPLICABLE_DATA_COVERAGE_NOT_ESTABLISHED')
        self.assertIsNone(self.claim())

    def test_supervised_repair_preserves_cursor_counters_and_requires_deployed_revision(self):
        self.task();claim=self.claim()
        self.call('backfill_defer',{'claim':self.fence(claim),'code':'SOURCE_PARSE_ERROR','message':'fixture adapter defect',
            'retryable':False,'evidence':{'response_sha256':'1'*64}})
        recovery={'run_id':self.run,'task_id':claim['id'],'expected_generation':claim['generation'],
                  'repair_revision':'fixed-parser-revision','repair_kind':'ADAPTER_FIX',
                  'evidence':{'verification':'Exact repaired parser passed the retained-response regression test'}}
        self.assertFalse(self.f.rpc('backfill_recover',recovery,actor='worker')['ok'])
        self.call('backfill_claim',{'worker_id':'repaired-worker','source_revision':'fixed-parser-revision',
            'supported_kinds':['alpaca_reference'],'lease_seconds':120})
        result=self.call('backfill_recover',recovery)
        self.assertEqual(result['state'],'RECOVERY_QUEUED')
        again=self.claim()
        self.assertEqual(again['id'],claim['id'])
        self.assertEqual(again['page_no'],claim['page_no'])
        self.assertEqual(again['attempts'],claim['attempts']+1)
        self.assertEqual(again['requests_reserved'],0)

    def test_delivery_acl_and_maintenance_are_bounded(self):
        claim=self.commit_minute_page()
        result=self.call('backfill_maintain',{'limit':1})
        self.assertEqual(result['verified_pages'],1)
        with self.f.admin() as conn:
            acl=conn.execute("SELECT has_sequence_privilege(%s,%s,'USAGE') seq,has_table_privilege(%s,%s,'SELECT') view",
                (self.f.outsider,self.f.schema+'.backfill_audit_v2_id_seq',self.f.outsider,self.f.schema+'.backfill_family_p01_v2')).fetchone()
            self.assertFalse(acl['seq']);self.assertFalse(acl['view'])
        with self.assertRaises(self.f.psycopg.Error):
            self.f.rpc('backfill_recover',{},actor='api')

    def test_existing_monitor_runs_only_the_bounded_extension(self):
        self.commit_minute_page()
        with self.f.admin() as conn:
            before=conn.execute(f'SELECT count(*) n FROM {self.f.schema}.jobs').fetchone()['n']
            result=conn.execute(f'SELECT {self.f.schema}.monitor_tick_v1() result').fetchone()['result']
            self.assertEqual(result['state'],'observed')
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.jobs').fetchone()['n'],before)
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_readbacks_v2 WHERE run_id=%s',(self.run,)).fetchone()['n'],1)
            rights=conn.execute("SELECT has_table_privilege(%s,%s,'UPDATE') mutation,has_function_privilege(%s,%s,'EXECUTE') helper",
                (self.monitor_role,self.f.schema+'.backfill_tasks_v2',self.monitor_role,self.f.schema+'.backfill_maintain_v2(integer)')).fetchone()
            self.assertFalse(rights['mutation']);self.assertTrue(rights['helper'])

    def test_failed_readback_is_isolated_until_explicit_repair(self):
        claim=self.commit_minute_page(calendar=[{'date':'2025-11-28','open':'invalid-time','close':'13:00'}])
        first=self.call('backfill_maintain',{'limit':1})
        self.assertEqual(first['readback_errors'],1)
        again=self.call('backfill_maintain',{'limit':1})
        self.assertEqual(again['readback_errors'],0)
        self.assertEqual(again['verified_pages'],0)
        with self.f.admin() as conn:
            self.assertEqual(conn.execute(f"SELECT count(*) n FROM {self.f.schema}.backfill_audit_v2 WHERE run_id=%s AND action='READBACK_FAILURE'",(self.run,)).fetchone()['n'],1)
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_pages_v2 WHERE run_id=%s',(self.run,)).fetchone()['n'],1)


if __name__=='__main__':
    unittest.main()
