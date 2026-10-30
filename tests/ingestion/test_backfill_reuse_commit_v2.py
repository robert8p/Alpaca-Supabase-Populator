"""Atomic retained pointer, executable gap child and lost-ack qualification."""
import hashlib
import json
import os
from pathlib import Path
import unittest

import test_backfill_retained_reuse_v2 as reuse

ROOT=Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'),'Explicit disposable PostgreSQL required')
class RetainedReuseCommitTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reuse.RetainedReuseTests.setUpClass.__func__(cls)
        f=cls.fixture('runTest')
        for filename in ('astra_backfill_reuse_commit_v2.sql','astra_backfill_reuse_verify_v2.sql'):
            sql=(ROOT/'sql'/filename).read_text()
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

    def commit(self, claim):
        return self.call('backfill_reuse_commit',{'claim':self.fence(claim)})

    def children(self, task_id):
        with self.f.admin() as conn:
            return conn.execute(f'''SELECT id,kind,family,provider,status,scope FROM {self.f.schema}.backfill_tasks_v2
                WHERE run_id=%s AND scope->>'reuse_parent'=%s ORDER BY id''',(self.run,task_id)).fetchall()

    def complete_empty_provider_page(self, claim):
        self.call('backfill_reserve',{'claim':self.fence(claim)})
        scope=claim['scope']; raw='{"bars":{},"next_page_token":null}'
        return self.call('backfill_commit',{'claim':self.fence(claim),'raw_body':raw,
            'body_sha256':hashlib.sha256(raw.encode()).hexdigest(),'http_status':200,
            'request_id':'fixture-exhausted-gap-query','fetched_at':'2026-10-30T05:00:00Z',
            'request':{'provider':'Alpaca','method':'GET','host':'data.alpaca.markets','path':'/v2/stocks/bars',
                       'params':{'symbols':','.join(scope['symbols']),'start':scope['start'],'end':scope['end'],
                                 'timeframe':'1Min','feed':'sip','adjustment':'raw'}},
            'records':[],'next_cursor':None,'quality':[],'headers':{},'adapter_version':'fixture-gap-v1'})

    def test_pointer_is_one_audit_record_and_post_commit_source_verifier_agrees(self):
        claim=self.owned(); result=self.commit(claim)
        self.assertEqual(result['record_count'],1)
        self.assertEqual(result['reused_records'],5)
        self.assertEqual(result['new_market_rows_written'],0)
        with self.f.admin() as conn:
            page=conn.execute(f'SELECT record_count,raw_body FROM {self.f.schema}.backfill_pages_v2 WHERE task_id=%s',(claim['id'],)).fetchone()
            body=json.loads(page['raw_body'])
            self.assertEqual(page['record_count'],1);self.assertEqual(body['reused_records'],5)
            self.assertEqual(len(body['rows']),1)
            self.assertEqual(body['rows'][0]['record_type'],'RETAINED_SOURCE_POINTER')
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.retained_bars_fixture').fetchone()['n'],5)
            run=conn.execute(f'SELECT requests_reserved,pages_committed,records_committed FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s',(self.run,)).fetchone()
            self.assertEqual(dict(run),{'requests_reserved':0,'pages_committed':1,'records_committed':1})
        verified=self.call('backfill_reuse_verify',{'task_id':claim['id'],'page_no':0})
        self.assertTrue(verified['passed'],verified)
        self.assertEqual(verified['mismatched_fields'],[])

    def test_missing_session_has_executable_child_and_derivation_waits_then_reads_it(self):
        source=self.owned()
        self.task(kind='derive_intraday',family='D01',provider='DERIVED',
            scope={'symbols':['AAPL'],'member_ids':['member-1'],'input_start':'2025-09-01','target_end':'2025-09-30'},
            dependencies=[source['id']])
        result=self.commit(source);children=self.children(source['id'])
        self.assertEqual(len(children),1)
        child=children[0]
        self.assertEqual((child['kind'],child['provider'],child['status']),('alpaca_stock_bars','Alpaca','PENDING'))
        self.assertEqual(child['scope']['member_ids'],['member-1'])
        self.assertEqual(child['scope']['symbols'],['AAPL'])
        self.assertEqual(child['scope']['start'],'2025-09-03T08:00:00.000000Z')
        self.assertEqual(child['scope']['end'],'2025-09-03T23:59:59.999999Z')
        self.assertEqual(result['provider_children'],[child['id']])
        self.assertIsNone(self.claim(['derive_intraday']))
        gap=self.claim(['alpaca_stock_bars']);self.assertEqual(gap['id'],child['id'])
        self.assertEqual(self.complete_empty_provider_page(gap)['task_status'],'NO_DATA_RETURNED')
        derived=self.claim(['derive_intraday']);self.assertIsNotNone(derived)
        material=self.call('backfill_material',{'claim':self.fence(derived),'limit':4})
        self.assertEqual({x['task_id'] for x in material['pages']},{source['id'],child['id']})

    def test_bad_profile_and_invalid_day_are_isolated_and_deduplicated_in_gap_queue(self):
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.retained_jobs_fixture SET config=jsonb_set(config,'{{feed}}','\"iex\"')")
            conn.execute(f"UPDATE {self.f.schema}.retained_bars_fixture SET close=999 WHERE bar_ts='2025-09-02T13:30:00Z'")
        source=self.owned();self.commit(source)
        children=self.children(source['id'])
        self.assertEqual(len(children),2)
        self.assertEqual({c['scope']['calendar'][0]['date'] for c in children},{'2025-09-02','2025-09-03'})
        with self.f.admin() as conn:
            page=conn.execute(f'SELECT raw_body FROM {self.f.schema}.backfill_pages_v2 WHERE task_id=%s',(source['id'],)).fetchone()
            pointer=json.loads(page['raw_body'])['rows'][0]
            self.assertEqual(pointer['reused_records'],5)
            self.assertEqual(pointer['qualifying_profile_count'],0)
            self.assertEqual(pointer['usable_rth_count'],0)

    def test_empty_retained_month_creates_real_acquisition_not_provider_absence(self):
        scope=dict(self.scope,start='2025-10-01T04:00:00Z',end_exclusive='2025-11-01T04:00:00Z',
                   calendar=[{'date':'2025-10-01','open':'09:30','close':'16:00'},
                             {'date':'2025-10-02','open':'09:30','close':'16:00'}])
        source=self.owned(scope);result=self.commit(source)
        self.assertEqual(result['reused_records'],0)
        self.assertEqual(result['task_status'],'IDENTITY_OR_QUALITY_UNRESOLVED')
        children=self.children(source['id']);self.assertEqual(len(children),1)
        self.assertEqual(children[0]['scope']['gap_reason'],'NO_RETAINED_ROWS')
        self.assertEqual(children[0]['scope']['start'],'2025-10-01T04:00:00.000000Z')
        self.assertEqual(children[0]['scope']['end'],'2025-11-01T03:59:59.999999Z')
        self.assertEqual(self.claim(['alpaca_stock_bars'])['id'],children[0]['id'])

    def test_lost_ack_is_idempotent_for_pointer_counters_and_children(self):
        source=self.owned();first=self.commit(source);children=self.children(source['id'])
        again=self.commit(source)
        self.assertEqual(again['state'],'already_committed')
        self.assertEqual(again['body_sha256'],first['body_sha256'])
        self.assertEqual(again['reused_records'],5)
        self.assertEqual([c['id'] for c in self.children(source['id'])],[c['id'] for c in children])
        with self.f.admin() as conn:
            count=conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_pages_v2 WHERE task_id=%s',(source['id'],)).fetchone()['n']
            self.assertEqual(count,1)
            run=conn.execute(f'SELECT requests_reserved,pages_committed,records_committed FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s',(self.run,)).fetchone()
            self.assertEqual(dict(run),{'requests_reserved':0,'pages_committed':1,'records_committed':1})


if __name__=='__main__':
    unittest.main()
