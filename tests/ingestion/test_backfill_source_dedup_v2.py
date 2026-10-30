"""Real PostgreSQL canonical retained/fresh minute delivery without row copying."""
from hashlib import sha256
import json
import os
from pathlib import Path
import unittest

import test_backfill_reuse_commit_v2 as reuse

ROOT=Path(__file__).resolve().parents[2]

@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'),'Explicit disposable PostgreSQL required')
class MinuteSourceDedupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reuse.RetainedReuseCommitTests.setUpClass.__func__(cls)
        f=cls.fixture('runTest')
        for filename in ('astra_backfill_delivery_v2.sql','astra_backfill_delivery_performance_v2.sql','astra_backfill_source_dedup_v2.sql'):
            sql=(ROOT/'sql'/filename).read_text()
            for old,new in [
                ('market_fixed_20250901_20260831.alpaca_sip_bars_1m',f.schema+'.retained_bars_fixture'),
                ('reference.alpaca_fixed_window_instruments_v1',f.schema+'.retained_instruments_fixture'),
                ('market_provenance.alpaca_populator_jobs_v1',f.schema+'.retained_jobs_fixture'),
                ('astra_ingestion_v1',f.schema),('astra_ingestion_rpc_owner_v1',f.owner)]:
                sql=sql.replace(old,new)
            with f.admin() as conn: conn.execute(sql)

    setUp=reuse.RetainedReuseCommitTests.setUp
    task=reuse.RetainedReuseCommitTests.task
    call=reuse.RetainedReuseCommitTests.call
    claim=reuse.RetainedReuseCommitTests.claim
    fence=staticmethod(reuse.RetainedReuseCommitTests.fence)
    owned=reuse.RetainedReuseCommitTests.owned
    commit=reuse.RetainedReuseCommitTests.commit

    def readback(self,claim):
        return self.call('backfill_verify',{'claim':self.fence(claim),'page_no':claim['page_no'],'include_raw':False})

    def prices(self,family='p01'):
        with self.f.admin() as conn:
            return conn.execute(f'SELECT task_id,source_row,lineage FROM {self.f.schema}.backfill_family_{family}_v2 WHERE run_id=%s ORDER BY source_row->>\'t\'',(self.run,)).fetchall()

    def report(self):
        result=self.call('backfill_delivery_status',{'run_id':self.run},actor='api')['runs'][0]
        return {r['family']:r for r in result['families']}

    def repair(self,parent):
        scope={'symbols':['AAPL'],'symbol':'AAPL','member_ids':['member-1'],
            'start':'2025-09-02T08:00:00Z','end':'2025-09-02T23:59:59Z',
            'timeframe':'1Min','feed':'sip','adjustment':'raw','reuse_parent':parent['id'],
            'calendar':[{'date':'2025-09-02','open':'09:30','close':'16:00'}]}
        task=self.task(kind='alpaca_stock_bars',family='P01',provider='Alpaca',scope=scope,priority=1)
        c=self.claim(['alpaca_stock_bars']);self.assertEqual(c['id'],task)
        return c

    def provider_page(self,claim,bars,cursor=None):
        with self.f.admin() as conn: conn.execute(f'UPDATE {self.f.schema}.source_limits SET next_request_at=0')
        self.call('backfill_reserve',{'claim':self.fence(claim)})
        raw=json.dumps({'bars':{'AAPL':bars},'next_page_token':cursor})
        scope=claim['scope'];params={'symbols':'AAPL','start':scope['start'],'end':scope['end'],'timeframe':'1Min','feed':'sip','adjustment':'raw'}
        if claim.get('cursor'):params['page_token']=claim['cursor']
        payload={'claim':self.fence(claim),'raw_body':raw,'body_sha256':sha256(raw.encode()).hexdigest(),
            'http_status':200,'request_id':'fixture-page','fetched_at':'2026-10-30T06:00:00Z',
            'request':{'provider':'Alpaca','method':'GET','host':'data.alpaca.markets','path':'/v2/stocks/bars','params':params},
            'records':[{'symbol':'AAPL','source':bar} for bar in bars],'next_cursor':cursor,
            'terminal_state':'INGESTED' if bars else 'NO_DATA_RETURNED','quality':[],'headers':{},'adapter_version':'fixture-v2'}
        self.call('backfill_commit',payload);self.readback(claim)

    @staticmethod
    def bar(minute,close):
        return {'t':f'2025-09-02T13:{minute:02}:00Z','o':100,'h':105,'l':99,'c':close,'v':10,'n':5,'vw':101}

    def test_retained_views_expand_actual_bars_and_deduplicate_overlapping_pointers(self):
        first=self.owned();self.commit(first);self.readback(first)
        second=self.owned();self.commit(second);self.readback(second)
        self.assertEqual(len(self.prices()),2)
        self.assertEqual(len(self.prices('p02')),2)
        families=self.report()
        self.assertEqual(families['P01']['committed_records'],2)
        self.assertEqual(families['P02']['committed_records'],2)
        self.assertEqual(families['P01']['referenced_existing_records'],2)
        self.assertEqual(families['P02']['referenced_existing_records'],2)
        self.assertTrue(all(r['lineage']['original_source_unchanged'] for r in self.prices()))
        with self.f.admin() as conn:
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.retained_bars_fixture').fetchone()['n'],5)
            denied=conn.execute('SELECT has_function_privilege(%s,%s,\'EXECUTE\') allowed',(self.f.gateway,self.f.schema+'.backfill_retained_session_rows_v2(text,date)')).fetchone()
            self.assertFalse(denied['allowed'])

    def test_partial_repair_preserves_retained_then_exhausted_query_replaces_once(self):
        source=self.owned();self.commit(source);self.readback(source)
        repair=self.repair(source)
        self.provider_page(repair,[self.bar(30,102)],'next')
        rows=self.prices();self.assertEqual(len(rows),2)
        self.assertEqual({r['task_id'] for r in rows},{source['id']})
        self.assertEqual(self.report()['P01']['committed_records'],2)
        again=self.claim(['alpaca_stock_bars']);self.assertEqual(again['id'],repair['id'])
        self.provider_page(again,[self.bar(31,103)])
        rows=self.prices();self.assertEqual(len(rows),2)
        self.assertEqual({r['task_id'] for r in rows},{repair['id']})
        self.assertEqual([r['source_row']['c'] for r in rows],[102,103])
        self.assertEqual(self.report()['P01']['committed_records'],2)
        self.assertEqual(self.report()['P01']['referenced_existing_records'],0)
        self.assertEqual(len(self.prices('p02')),0)

    def test_exhausted_empty_repair_and_source_tampering_have_honest_outcomes(self):
        source=self.owned();self.commit(source);self.readback(source)
        repair=self.repair(source);self.provider_page(repair,[])
        self.assertEqual(self.prices(),[])
        self.assertEqual(self.report()['P01']['committed_records'],0)
        with self.f.admin() as conn:
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.retained_bars_fixture').fetchone()['n'],5)
            conn.execute(f"UPDATE {self.f.schema}.retained_bars_fixture SET close=100.75 WHERE bar_ts='2025-09-02T13:30:00Z'")
            with self.assertRaises(self.f.psycopg.Error):
                conn.execute(f'SELECT * FROM {self.f.schema}.backfill_retained_session_rows_v2(%s,%s)',(source['id'],'2025-09-02')).fetchall()

    def test_conflicting_cross_page_values_are_null_with_reason_and_not_usable(self):
        source=self.owned();self.commit(source);self.readback(source)
        repair=self.repair(source);self.provider_page(repair,[self.bar(30,102)],'next')
        again=self.claim(['alpaca_stock_bars']);self.provider_page(again,[self.bar(30,103)])
        rows=self.prices();self.assertEqual(len(rows),1)
        self.assertIsNone(rows[0]['source_row']['c'])
        self.assertEqual(rows[0]['source_row']['null_reason'],'CONFLICTING_PROVIDER_DUPLICATE')
        self.assertEqual(rows[0]['lineage']['source_value_versions'],2)
        self.assertEqual(self.report()['P01']['committed_records'],1)
        self.assertEqual(self.report()['P01']['usable_minute_records'],0)

if __name__=='__main__':unittest.main()
