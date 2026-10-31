"""Delivery integration keeps physical pointers and retained observations separate."""
from pathlib import Path
import unittest

import test_backfill_reuse_verify_v2 as verification

ROOT=Path(__file__).resolve().parents[2]


class DeliveryReuseTests(verification.RetainedPointerVerificationTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        f=cls.fixture('runTest')
        sql=(ROOT/'sql/astra_backfill_delivery_v2.sql').read_text()
        sql=sql.replace('astra_ingestion_v1',f.schema).replace('astra_ingestion_rpc_owner_v1',f.owner)
        with f.admin() as conn:
            conn.execute(sql)

    def test_verified_pointer_counts_reused_sessions_without_copying_bars(self):
        claim,pointer=self.commit_pointer()
        result=self.call('backfill_verify',{'claim':self.fence(claim),'page_no':0,'include_raw':False})
        self.assertNotIn('raw_body',result)
        verified=result['verification']
        self.assertEqual(verified['actual_records'],1)
        self.assertEqual(verified['reused_records'],5)
        self.assertEqual(verified['reused_qualified_records'],5)
        self.assertEqual(verified['reused_usable_records'],5)
        self.assertEqual((verified['rth_records'],verified['pre_records'],verified['post_records']),(2,1,1))
        self.assertTrue(verified['retained_source_verification']['passed'])
        report=self.call('backfill_delivery_status',{'run_id':self.run},actor='api')['runs'][0]
        families={row['family']:row for row in report['families']}
        self.assertEqual(families['P01']['committed_records'],2)
        self.assertEqual(families['P02']['committed_records'],2)
        self.assertEqual(families['P01']['usable_minute_records'],2)
        self.assertEqual(report['physical_totals']['physical_source_and_derived_records'],1)
        with self.f.admin() as conn:
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.retained_bars_fixture').fetchone()['n'],5)
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_pages_v2 WHERE run_id=%s',(self.run,)).fetchone()['n'],1)

    def test_changed_retained_source_cannot_pass_delivery_readback(self):
        claim,_=self.commit_pointer()
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.retained_bars_fixture SET close=100.75 WHERE bar_ts='2025-09-02T13:30:00Z'")
        result=self.f.rpc('backfill_verify',{'claim':self.fence(claim),'page_no':0,'include_raw':False},actor='worker')
        self.assertFalse(result['ok'])
        self.assertEqual(result['error']['code'],'quality_hold')
        with self.f.admin() as conn:
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_readbacks_v2 WHERE run_id=%s',(self.run,)).fetchone()['n'],0)


if __name__=='__main__':
    unittest.main()
