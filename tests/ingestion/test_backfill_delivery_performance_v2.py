"""Completion probes avoid full-plan work while any task remains runnable."""
from pathlib import Path
import os
import unittest

import test_backfill_delivery_v2 as delivery

ROOT=Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'), 'Explicit disposable PostgreSQL required')
class DeliveryPerformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        delivery.BackfillDeliveryTests.setUpClass.__func__(cls)
        f=cls.fixture('runTest')
        sql=(ROOT/'sql/astra_backfill_delivery_performance_v2.sql').read_text()
        sql=sql.replace('astra_ingestion_v1',f.schema).replace('astra_ingestion_rpc_owner_v1',f.owner)
        with f.admin() as conn:
            conn.execute(sql)

    cleanup_monitor=classmethod(delivery.BackfillDeliveryTests.cleanup_monitor.__func__)
    setUp=delivery.BackfillDeliveryTests.setUp
    task=delivery.BackfillDeliveryTests.task
    call=delivery.BackfillDeliveryTests.call

    def test_pending_work_short_circuits_plan_scan_and_status_avoids_scope_materialization(self):
        self.task()
        with self.f.admin() as conn:
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_plan_manifests_v2
                (run_id,expected_task_count,expected_plan_sha256,workflow_plan,required_trading_dates,required_calendar_dates)
                VALUES(%s,999999,%s,'{{}}','{{[2025-09-02,2025-09-03)}}','{{[2025-09-01,2026-08-01)}}')''',(self.run,'1'*64))
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET metadata='{{\"planning_complete\":true}}' WHERE id=%s",(self.run,))
            definition=conn.execute('SELECT pg_get_viewdef(%s::regclass,true) d',(self.f.schema+'.backfill_family_status_v2',)).fetchone()['d']
            mapped=definition.split('), units AS')[0]
            self.assertNotIn('t.dependencies',mapped)
            self.assertNotIn('t.error_message',mapped)
            self.assertNotIn('t.attempt_deadline',mapped)
        self.assertEqual(self.call('backfill_finalize',{'run_id':self.run})['state'],'WORK_REMAINS')


if __name__=='__main__':
    unittest.main()
