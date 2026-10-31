"""Real PostgreSQL proof for scoped, nonduplicating retained-source reads."""
import hashlib
import json
import os
from pathlib import Path
import unittest

import test_backfill_runtime_v2 as runtime

ROOT = Path(__file__).resolve().parents[2]
ASSET = '00000000-0000-0000-0000-000000000041'
JOB = '00000000-0000-0000-0000-000000000001'


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'), 'Explicit disposable PostgreSQL required')
class RetainedReuseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        runtime.BackfillRuntimeTests.setUpClass.__func__(cls)
        f = cls.fixture('runTest')
        with f.admin() as conn:
            conn.execute(f'''CREATE TABLE {f.schema}.retained_instruments_fixture(
                instrument_key integer PRIMARY KEY, symbol text UNIQUE, alpaca_asset_id uuid, provenance jsonb)''')
            conn.execute(f'''CREATE TABLE {f.schema}.retained_jobs_fixture(
                id uuid PRIMARY KEY,config jsonb,status text)''')
            conn.execute(f'''CREATE TABLE {f.schema}.retained_bars_fixture(
                instrument_key integer,bar_ts timestamptz,session_label text,
                open double precision,high double precision,low double precision,close double precision,
                volume bigint,trade_count bigint,vwap double precision,
                loaded_by_job_id uuid,source_loaded_at timestamptz,PRIMARY KEY(instrument_key,bar_ts))''')
            sql = (ROOT/'sql/astra_backfill_retained_reuse_v2.sql').read_text()
            for old,new in [
                ('market_fixed_20250901_20260831.alpaca_sip_bars_1m',f.schema+'.retained_bars_fixture'),
                ('reference.alpaca_fixed_window_instruments_v1',f.schema+'.retained_instruments_fixture'),
                ('market_provenance.alpaca_populator_jobs_v1',f.schema+'.retained_jobs_fixture'),
                ('astra_ingestion_v1',f.schema),('astra_ingestion_rpc_owner_v1',f.owner)]:
                sql = sql.replace(old,new)
            conn.execute(sql)

    task = runtime.BackfillRuntimeTests.task
    call = runtime.BackfillRuntimeTests.call
    claim = runtime.BackfillRuntimeTests.claim
    fence = staticmethod(runtime.BackfillRuntimeTests.fence)

    def setUp(self):
        runtime.BackfillRuntimeTests.setUp(self)
        self.scope = {'member_ids':['member-1'],'symbol':'AAPL','instrument_key':41,
                      'alpaca_asset_id':ASSET,'start':'2025-09-01T04:00:00Z',
                      'end_exclusive':'2025-10-01T04:00:00Z',
                      'calendar':[{'date':'2025-09-02','open':'09:30','close':'16:00'},
                                  {'date':'2025-09-03','open':'09:30','close':'16:00'}]}
        with self.f.admin() as conn:
            for table in ['retained_bars_fixture','retained_instruments_fixture','retained_jobs_fixture']:
                conn.execute(f'DELETE FROM {self.f.schema}.{table}')
            conn.execute(f'INSERT INTO {self.f.schema}.retained_instruments_fixture VALUES(41,\'AAPL\',%s,\'{{"source":"fixture"}}\')',(ASSET,))
            conn.execute(f'INSERT INTO {self.f.schema}.retained_jobs_fixture VALUES(%s,%s,\'completed\')',
                         (JOB,json.dumps({'feed':'sip','adjustment':'raw','timeframes':['1Min'],
                                          'start_date':'2025-09-01','end_date':'2025-09-30'})))
            for timestamp,session in [('2025-09-02T08:00:00Z','premarket'),
                                      ('2025-09-02T13:30:00Z','regular'),
                                      ('2025-09-02T13:31:00Z','regular'),
                                      ('2025-09-02T20:00:00Z','postmarket'),
                                      ('2025-09-03T01:00:00Z','overnight')]:
                conn.execute(f'''INSERT INTO {self.f.schema}.retained_bars_fixture
                    VALUES(41,%s,%s,100,102,99,101,10,5,100.5,%s,'2026-08-05T00:00:00Z')''',
                    (timestamp,session,JOB))

    def owned(self, scope=None):
        self.task(kind='retained_reuse',provider='REUSE',family='P01',scope=scope or self.scope)
        return self.claim(['retained_reuse'])

    def test_whole_summary_matches_material_keyset_without_copying_source_rows(self):
        task = self.owned()
        summary = self.call('backfill_reuse_read',{'claim':self.fence(task),'mode':'summary'})
        self.assertEqual(summary['state'],'RETAINED_SOURCE_READ')
        self.assertEqual(summary['rows'],[])
        self.assertEqual((summary['record_count'],summary['qualifying_profile_count'],summary['usable_source_count']),(5,5,5))
        self.assertEqual((summary['rth_count'],summary['pre_count'],summary['post_count'],summary['overnight_count']),(2,1,1,1))
        self.assertEqual((summary['qualified_rth_count'],summary['qualified_pre_count'],summary['qualified_post_count']),(2,1,1))
        self.assertEqual((summary['usable_rth_count'],summary['usable_pre_count'],summary['usable_post_count']),(2,1,1))
        self.assertEqual(summary['mapping_state'],'IDENTITY_OR_QUALITY_UNRESOLVED')
        self.assertEqual(summary['days_without_retained_rows'],['2025-09-03'])
        self.assertEqual(summary['session_coverage'][0]['market_date'],'2025-09-02')
        self.assertEqual(summary['session_coverage'][0]['record_count'],5)
        digests, timestamps, after = [], [], None
        for _ in range(3):
            args={'claim':self.fence(task),'mode':'material','limit':2}
            if after is not None: args['after']=after
            page=self.call('backfill_reuse_read',args)
            self.assertLessEqual(len(page['rows']),2)
            digests.extend(row['source_row_sha256'] for row in page['rows'])
            timestamps.extend(row['timestamp'] for row in page['rows'])
            after=page['next_after']
            if not page['has_more']: break
        self.assertIsNone(after)
        self.assertEqual(len(timestamps),5)
        self.assertEqual(len(set(timestamps)),5)
        self.assertEqual(summary['source_digest'],hashlib.sha256(''.join(digests).encode()).hexdigest())
        with self.f.admin() as conn:
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.retained_bars_fixture').fetchone()['n'],5)
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_pages_v2 WHERE run_id=%s',(self.run,)).fetchone()['n'],0)

    def test_private_permissions_api_denial_and_stale_claim_fence(self):
        task=self.owned()
        with self.assertRaises(self.f.psycopg.Error) as denied:
            self.f.rpc('backfill_reuse_read',{'claim':self.fence(task)},actor='api')
        self.assertEqual(denied.exception.sqlstate,'PT403')
        with self.f.admin() as conn:
            acl=conn.execute("SELECT has_function_privilege(%s,%s,'EXECUTE') allowed",
                 (self.f.gateway,self.f.schema+'.backfill_reuse_read_v2(jsonb)')).fetchone()
            self.assertFalse(acl['allowed'])
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",(task['id'],))
        replacement=self.claim(['retained_reuse'],worker='replacement-reuse-worker')
        self.assertGreater(replacement['generation'],task['generation'])
        rejected=self.f.rpc('backfill_reuse_read',{'claim':self.fence(task)},actor='worker')
        self.assertFalse(rejected['ok'])
        self.assertEqual(rejected['error']['code'],'lease_lost')

    def test_wrong_asset_binding_cannot_read_another_provider_security(self):
        scope=dict(self.scope,alpaca_asset_id='00000000-0000-0000-0000-000000000099')
        task=self.owned(scope)
        self.assertFalse(self.f.rpc('backfill_reuse_read',{'claim':self.fence(task)},actor='worker')['ok'])

    def test_missing_retained_rows_are_not_provider_absence(self):
        scope=dict(self.scope,start='2025-10-01T04:00:00Z',end_exclusive='2025-11-01T04:00:00Z')
        task=self.owned(scope)
        result=self.call('backfill_reuse_read',{'claim':self.fence(task)})
        self.assertEqual(result['state'],'NO_RETAINED_ROWS')
        self.assertEqual(result['record_count'],0)
        self.assertEqual(result['coverage_state'],'UNKNOWN_PROVIDER_OBSERVATION_DENOMINATOR')

    def test_nonqualifying_profile_is_retained_but_not_counted_as_usable_reuse(self):
        task=self.owned()
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.retained_jobs_fixture SET config=jsonb_set(config,'{{feed}}','\"iex\"')")
        result=self.call('backfill_reuse_read',{'claim':self.fence(task)})
        self.assertEqual((result['record_count'],result['qualifying_profile_count'],result['usable_source_count']),(5,0,0))
        self.assertEqual(result['days_with_unqualified_profile'],['2025-09-02'])
        self.assertEqual((result['qualified_rth_count'],result['qualified_pre_count'],result['qualified_post_count']),(0,0,0))
        self.assertEqual((result['usable_rth_count'],result['usable_pre_count'],result['usable_post_count']),(0,0,0))

    def test_derived_material_requires_direct_dependency_and_same_frozen_member(self):
        source=self.owned()
        summary=self.call('backfill_reuse_read',{'claim':self.fence(source)})
        pointer={'source_relation':summary['source_relation'],'source_digest':summary['source_digest'],
                 'reused_records':summary['record_count']}
        raw=json.dumps({'rows':[pointer]})
        self.call('backfill_commit',{'claim':self.fence(source),'raw_body':raw,
            'body_sha256':hashlib.sha256(raw.encode()).hexdigest(),'http_status':200,
            'request_id':None,'fetched_at':'2026-10-30T05:00:00Z',
            'request':{'provider':'REUSE'},'records':[pointer],'next_cursor':None,
            'quality':[],'headers':{},'adapter_version':'fixture-retained-v1'})
        self.task(kind='derive_intraday',family='D01',provider='DERIVED',
            scope={'member_ids':['member-1'],'symbols':['AAPL'],
                   'input_start':'2025-09-02','target_end':'2025-09-02'},dependencies=[source['id']])
        derived=self.claim(['derive_intraday'])
        material=self.call('backfill_reuse_read',{'claim':self.fence(derived),
            'mode':'material','source_task_id':source['id'],'limit':2})
        self.assertEqual(material['task_id'],derived['id'])
        self.assertEqual(material['source_task_id'],source['id'])
        self.assertEqual(material['record_count'],2)
        self.assertFalse(self.f.rpc('backfill_reuse_read',{'claim':self.fence(derived),
            'mode':'material','source_task_id':'not-a-dependency'},actor='worker')['ok'])
        self.assertFalse(self.f.rpc('backfill_reuse_read',{'claim':self.fence(derived),
            'mode':'summary','source_task_id':source['id']},actor='worker')['ok'])


if __name__=='__main__':
    unittest.main()
