"""Bounded breadth inputs, full-cohort readiness and transactional projection."""
import hashlib
import json
import os
from pathlib import Path
import unittest

import test_backfill_delivery_v2 as delivery

ROOT=Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'), 'Explicit disposable PostgreSQL required')
class BreadthMaterialTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        delivery.BackfillDeliveryTests.setUpClass.__func__(cls)
        f=cls.fixture('runTest')
        sql=(ROOT/'sql/astra_backfill_breadth_material_v2.sql').read_text()
        sql=sql.replace('astra_ingestion_v1',f.schema).replace('astra_ingestion_rpc_owner_v1',f.owner)
        with f.admin() as conn:
            conn.execute(sql)

    cleanup_monitor=classmethod(delivery.BackfillDeliveryTests.cleanup_monitor.__func__)
    setUp=delivery.BackfillDeliveryTests.setUp
    task=delivery.BackfillDeliveryTests.task
    claim=delivery.BackfillDeliveryTests.claim
    call=delivery.BackfillDeliveryTests.call
    fence=staticmethod(delivery.BackfillDeliveryTests.fence)

    def source_page(self,member='member-1'):
        scope={'member_ids':['member-1'],'symbols':['AAPL'],'target_start':'2025-09-02','target_end':'2025-09-02',
               'source_month':'2025-09-01','market_timezone':'America/New_York'}
        self.task(family='D03',provider='DERIVED',kind='derive_daily',scope=scope)
        claim=self.claim(['derive_daily'])
        rows=[{'member_id':member,'symbol':'AAPL','market_date':'2025-09-02',
               'values':{'raw_ret_1d':0.1,'adjusted_ret_1d':None},
               'null_reasons':{'adjusted_ret_1d':'IDENTITY_CONTINUITY_UNRESOLVED'},'formula_version':'fixture-d03-v1'}]
        raw=json.dumps({'rows':rows,'formula_version':'fixture-d03-v1'})
        payload={'claim':self.fence(claim),'raw_body':raw,'body_sha256':hashlib.sha256(raw.encode()).hexdigest(),
                 'http_status':200,'fetched_at':'2026-10-30T05:00:00Z','request':{'provider':'DERIVED'},'records':rows,
                 'next_cursor':None,'quality':[],'headers':{},'adapter_version':'fixture-d03-v1'}
        return claim,payload

    def test_projection_commits_atomically_and_preserves_unknown_adjusted_return(self):
        claim,payload=self.source_page()
        self.call('backfill_commit',payload)
        with self.f.admin() as conn:
            row=conn.execute(f'SELECT * FROM {self.f.schema}.backfill_breadth_inputs_v2 WHERE run_id=%s',(self.run,)).fetchone()
            self.assertEqual(float(row['raw_ret_1d']),0.1)
            self.assertIsNone(row['adjusted_ret_1d'])
            self.assertEqual(row['adjusted_null_reason'],'IDENTITY_CONTINUITY_UNRESOLVED')
            self.assertEqual(row['body_sha256'],payload['body_sha256'])
        self.assertEqual(self.call('backfill_commit',payload)['state'],'already_committed')
        with self.f.admin() as conn:
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_breadth_inputs_v2 WHERE run_id=%s',(self.run,)).fetchone()['n'],1)

    def test_cross_member_projection_rolls_back_the_entire_page(self):
        claim,payload=self.source_page(member='member-2')
        result=self.f.rpc('backfill_commit',payload,actor='worker')
        self.assertFalse(result['ok']);self.assertEqual(result['error']['code'],'quality_hold')
        with self.f.admin() as conn:
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_pages_v2 WHERE run_id=%s',(self.run,)).fetchone()['n'],0)
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_breadth_inputs_v2 WHERE run_id=%s',(self.run,)).fetchone()['n'],0)

    def test_breadth_waits_for_complete_month_then_pages_all_fixed_members(self):
        source,payload=self.source_page();self.call('backfill_commit',payload)
        representatives={'member-'+str(i):{'symbol':'AAPL' if i==1 else 'T'+str(i),'eligible':None} for i in range(1,3001)}
        breadth_id=self.task(family='CTX06',provider='DERIVED',kind='derive_breadth',scope={
            'source_month':'2025-09-01','target_start':'2025-09-02','target_end':'2025-09-02',
            'market_timezone':'America/New_York','representative_security':representatives})
        self.assertIsNone(self.claim(['derive_breadth']))
        # Fixture establishes an already sealed plan; separate delivery tests
        # qualify the real plan-sealing guard and all-family/date accounting.
        with self.f.admin() as conn:
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_plan_manifests_v2
                (run_id,expected_task_count,expected_plan_sha256,workflow_plan,required_trading_dates,required_calendar_dates)
                VALUES(%s,1,%s,'{{}}','{{[2025-09-02,2025-09-03)}}','{{[2025-09-01,2026-08-01)}}')''',(self.run,'1'*64))
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET metadata='{{\"planning_complete\":true}}' WHERE id=%s",(self.run,))
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_tasks_v2(id,run_id,family,provider,kind,scope,status)
                SELECT %s||'-d03-'||g::text,%s,'D03','DERIVED','derive_daily',
                jsonb_build_object('member_ids',jsonb_build_array('member-'||g::text),'symbols',jsonb_build_array('T'||g::text),
                  'target_start','2025-09-01','target_end','2025-09-30','source_month','2025-09-01','market_timezone','America/New_York'),
                CASE WHEN g=3000 THEN 'PENDING' ELSE 'NO_DATA_RETURNED' END FROM generate_series(2,3000) g''',(self.run,self.run))
        self.assertIsNone(self.claim(['derive_breadth']))
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET status='NO_DATA_RETURNED' WHERE id=%s",(self.run+'-d03-3000',))
        claim=self.claim(['derive_breadth']);self.assertEqual(claim['id'],breadth_id)
        first=self.call('backfill_breadth_material',{'claim':self.fence(claim),'limit':2})
        self.assertTrue(first['ready']);self.assertFalse(first['complete']);self.assertEqual(first['next_after'],2)
        self.assertEqual(first['rows'][0]['member_id'],'member-1')
        self.assertAlmostEqual(first['rows'][0]['values']['raw_ret_1d'],0.1)
        self.assertIsNone(first['rows'][1]['values']['raw_ret_1d'])
        self.assertEqual(first['rows'][1]['null_reasons']['raw_ret_1d'],'NO_PROJECTED_D03_OBSERVATION')
        last=self.call('backfill_breadth_material',{'claim':self.fence(claim),'after':2998,'limit':1000})
        self.assertTrue(last['complete']);self.assertIsNone(last['next_after']);self.assertEqual(len(last['rows']),2)
        with self.assertRaises(self.f.psycopg.Error):
            self.f.rpc('backfill_breadth_material',{'claim':self.fence(claim),'limit':1},actor='api')


if __name__=='__main__':
    unittest.main()
