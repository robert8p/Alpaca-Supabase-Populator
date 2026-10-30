"""Read-only verification of immutable retained pointers after lease release."""
import hashlib
import json
import os
from pathlib import Path
import unittest

import test_backfill_retained_reuse_v2 as reuse

ROOT=Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'),'Explicit disposable PostgreSQL required')
class RetainedPointerVerificationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reuse.RetainedReuseTests.setUpClass.__func__(cls)
        f=cls.fixture('runTest')
        sql=(ROOT/'sql/astra_backfill_reuse_verify_v2.sql').read_text()
        for old,new in [
            ('market_fixed_20250901_20260831.alpaca_sip_bars_1m',f.schema+'.retained_bars_fixture'),
            ('reference.alpaca_fixed_window_instruments_v1',f.schema+'.retained_instruments_fixture'),
            ('market_provenance.alpaca_populator_jobs_v1',f.schema+'.retained_jobs_fixture'),
            ('astra_ingestion_v1',f.schema),('astra_ingestion_rpc_owner_v1',f.owner)]:
            sql=sql.replace(old,new)
        with f.admin() as conn:
            conn.execute(sql)

    setUp=reuse.RetainedReuseTests.setUp
    task=reuse.RetainedReuseTests.task
    call=reuse.RetainedReuseTests.call
    claim=reuse.RetainedReuseTests.claim
    fence=staticmethod(reuse.RetainedReuseTests.fence)
    owned=reuse.RetainedReuseTests.owned

    def commit_pointer(self, tamper=None):
        claim=self.owned()
        summary=self.call('backfill_reuse_read',{'claim':self.fence(claim)})
        pointer={k:v for k,v in summary.items() if k not in ('rows','mode','state','next_after','has_more')}
        pointer.update(record_type='RETAINED_SOURCE_POINTER',reused_records=summary['record_count'])
        if tamper is not None: tamper(pointer)
        raw=json.dumps({'rows':[pointer],'reused_records':pointer['reused_records']})
        self.call('backfill_commit',{'claim':self.fence(claim),'raw_body':raw,
            'body_sha256':hashlib.sha256(raw.encode()).hexdigest(),'http_status':200,
            'request_id':None,'fetched_at':'2026-10-30T05:00:00Z',
            'request':{'provider':'REUSE'},'records':[pointer],'next_cursor':None,
            'quality':[{'state':'IDENTITY_OR_QUALITY_UNRESOLVED','reason':'fixture mapping unresolved'}],
            'headers':{},'adapter_version':'fixture-retained-v1'})
        return claim,pointer

    def verify(self, claim):
        return self.call('backfill_reuse_verify',{'task_id':claim['id'],'page_no':0})

    def test_released_claim_and_paused_run_need_no_reopen_for_readback(self):
        claim,pointer=self.commit_pointer()
        with self.f.admin() as conn:
            task=conn.execute(f'SELECT status,owner,lease_until FROM {self.f.schema}.backfill_tasks_v2 WHERE id=%s',(claim['id'],)).fetchone()
            self.assertEqual(task['status'],'IDENTITY_OR_QUALITY_UNRESOLVED')
            self.assertIsNone(task['owner']);self.assertIsNone(task['lease_until'])
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET status='PAUSED',fence=fence+1 WHERE id=%s",(self.run,))
        result=self.verify(claim)
        self.assertTrue(result['passed'])
        self.assertEqual(result['state'],'REUSE_SOURCE_VERIFIED')
        self.assertEqual(result['mismatched_fields'],[])
        self.assertEqual(result['source_digest'],pointer['source_digest'])
        self.assertEqual((result['record_count'],result['reused_records'],result['receipt_record_count']),(5,5,1))
        with self.f.admin() as conn:
            after=conn.execute(f'SELECT status,owner,lease_until FROM {self.f.schema}.backfill_tasks_v2 WHERE id=%s',(claim['id'],)).fetchone()
            self.assertEqual(dict(after),dict(task))

    def test_fresh_source_change_is_detected_after_pointer_commit(self):
        claim,pointer=self.commit_pointer()
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.retained_bars_fixture SET close=100.75 WHERE bar_ts='2025-09-02T13:30:00Z'")
        result=self.verify(claim)
        self.assertFalse(result['passed'])
        self.assertEqual(result['state'],'REUSE_SOURCE_MISMATCH')
        self.assertIn('source_digest',result['mismatched_fields'])
        self.assertNotEqual(result['source_digest'],pointer['source_digest'])

    def test_receipt_count_tampering_is_not_hidden_by_matching_source_digest(self):
        claim,_=self.commit_pointer(lambda pointer:pointer.update(usable_rth_count=999))
        result=self.verify(claim)
        self.assertFalse(result['passed'])
        self.assertIn('usable_rth_count',result['mismatched_fields'])

    def test_verifier_is_worker_only_and_rejects_uncommitted_reference(self):
        claim,_=self.commit_pointer()
        with self.assertRaises(self.f.psycopg.Error) as denied:
            self.f.rpc('backfill_reuse_verify',{'task_id':claim['id'],'page_no':0},actor='api')
        self.assertEqual(denied.exception.sqlstate,'PT403')
        with self.f.admin() as conn:
            acl=conn.execute("SELECT has_function_privilege(%s,%s,'EXECUTE') allowed",
                (self.f.gateway,self.f.schema+'.backfill_reuse_verify_v2(text,integer)')).fetchone()
            self.assertFalse(acl['allowed'])
        rejected=self.f.rpc('backfill_reuse_verify',{'task_id':claim['id'],'page_no':99},actor='worker')
        self.assertFalse(rejected['ok'])


if __name__=='__main__':
    unittest.main()
