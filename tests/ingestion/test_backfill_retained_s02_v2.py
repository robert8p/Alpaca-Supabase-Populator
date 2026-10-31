"""Verified retained Massive S02 pointers, bounded successors and logical dedup."""
import hashlib
import json
import os
from pathlib import Path
import unittest

import test_backfill_identity_v2 as identity
import test_backfill_runtime_v2 as runtime
from astra_ingestion.backfill_provider_v2 import request_for

ROOT=Path(__file__).resolve().parents[2]
ARCHIVE='massive-archive:S02:c1ed3ed6aa5bad110f122c2459ba27f6daa14a7ac484363d4915c0fc9ddb1f88'
FIRST='https://api.massive.com/stocks/v1/short-interest?settlement_date.gte=2026-07-15&settlement_date.lte=2026-09-30&sort=settlement_date.asc,ticker.asc&limit=1000'


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'),'Explicit disposable PostgreSQL required')
class RetainedS02Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        identity.IdentityPostgreSQLTests.setUpClass.__func__(cls)
        f=cls.fixture('runTest')
        cls.replacements=[('population_top3000_202608_202609_v1.massive_shortinterest_page_v1',f.schema+'.s02_page_fixture'),
                          ('population_top3000_202608_202609_v1.massive_shortinterest_record_v1',f.schema+'.s02_record_fixture'),
                          ('population_top3000_202608_202609_v1.source_document',f.schema+'.s02_document_fixture')]+cls.replacements
        with f.admin() as conn:
            conn.execute(f'''CREATE TABLE {f.schema}.s02_page_fixture(archive_key text,page_number integer,family_id text,partition_key text,
                source_id text,source_sha256 text,request_url text,next_url text,wire_sha256 text,wire_bytes bigint,result_count int,
                retrieved_at timestamptz,normalized_at timestamptz,normalized_source_records int,PRIMARY KEY(archive_key,page_number))''')
            conn.execute(f'''CREATE TABLE {f.schema}.s02_record_fixture(archive_key text,page_number integer,source_row int,source_id text,
                source_record_key text,unit_key text,raw_record jsonb,raw_record_sha256 text,PRIMARY KEY(archive_key,page_number,source_row))''')
            conn.execute(f'''CREATE TABLE {f.schema}.s02_document_fixture(source_id text PRIMARY KEY,source_sha256 text,source_uri text,
                source_provider text,retrieved_at timestamptz,source_published_at timestamptz,historical_received_at timestamptz,
                content_text text,content_bytes bigint,evidence jsonb,license_policy text)''')
            conn.execute(cls.rewrite((ROOT/'sql/astra_backfill_retained_s02_v2.sql').read_text()))

    rewrite=classmethod(identity.IdentityPostgreSQLTests.rewrite.__func__)
    task=runtime.BackfillRuntimeTests.task
    call=runtime.BackfillRuntimeTests.call
    claim=runtime.BackfillRuntimeTests.claim
    fence=staticmethod(runtime.BackfillRuntimeTests.fence)

    def setUp(self):
        runtime.BackfillRuntimeTests.setUp(self)
        with self.f.admin() as conn:
            for table in ('s02_record_fixture','s02_page_fixture','s02_document_fixture'):
                conn.execute(f'DELETE FROM {self.f.schema}.{table}')

    @staticmethod
    def record(symbol='AAPL',day='2026-07-15',amount=10):
        return {'ticker':symbol,'settlement_date':day,'short_interest':amount,'avg_daily_volume':2,'days_to_cover':5}

    def source_page(self,number,rows,next_page=None):
        request=FIRST if number==1 else f'https://api.massive.com/stocks/v1/short-interest?cursor=fixture{number}'
        next_url=f'https://api.massive.com/stocks/v1/short-interest?cursor=fixture{next_page}' if next_page else None
        source_id=f'{ARCHIVE}:page:{number}'
        body=json.dumps({'status':'OK','results':rows,'next_url':next_url})
        digest=hashlib.sha256(body.encode()).hexdigest();wire='e'*64
        evidence={'hash_representation':'EXACT_UTF8_RESPONSE_WITH_TOP_LEVEL_NEXT_URL_CREDENTIAL_REDACTION_ONLY',
                  'wire_bytes_retained':False,'original_historical_receipt':False,'wire_sha256':wire,
                  'wire_bytes':len(body.encode())+17,'stored_content_bytes':len(body.encode())}
        with self.f.admin() as conn:
            conn.execute(f'''INSERT INTO {self.f.schema}.s02_page_fixture VALUES(%s,%s,'S02','fixture',%s,%s,%s,%s,%s,%s,%s,
                '2026-10-23T14:00Z','2026-10-23T15:00Z',%s)''',(ARCHIVE,number,source_id,digest,request,next_url,wire,evidence['wire_bytes'],len(rows),len(rows)))
            conn.execute(f'''INSERT INTO {self.f.schema}.s02_document_fixture VALUES(%s,%s,%s,'Massive','2026-10-23T14:00Z',NULL,NULL,%s,%s,%s,
                'EXISTING_MASSIVE_SUBSCRIPTION_API_RESPONSE_INTERNAL_USE')''',(source_id,digest,request,body,len(body.encode()),json.dumps(evidence)))
            for n,row in enumerate(rows,1):
                conn.execute(f'''INSERT INTO {self.f.schema}.s02_record_fixture
                    SELECT %s,%s,%s,%s,'MassiveSI:business:'||encode(sha256(convert_to(jsonb_build_array(v->>'ticker',(v->>'settlement_date')::date)::text,'UTF8')),'hex'),
                    'MassiveSI:record:'||encode(sha256(convert_to(v::text,'UTF8')),'hex'),v,encode(sha256(convert_to(v::text,'UTF8')),'hex') FROM(SELECT %s::jsonb v) x''',
                    (ARCHIVE,number,n,source_id,json.dumps(row)))
        return source_id

    def seed(self,limit=2):
        with self.f.admin() as conn:
            return conn.execute(f'SELECT {self.f.schema}.backfill_s02_seed_v2(%s,%s) n',(self.run,limit)).fetchone()['n']

    def prove(self):
        c=self.claim(['retained_massive_archive']);self.assertIsNotNone(c)
        result=self.call('backfill_massive_archive_commit',{'claim':self.fence(c)})
        verified=self.call('backfill_verify',{'claim':self.fence(c),'page_no':0,'include_raw':False})
        self.assertTrue(verified['verification']['retained_s02_verification']['passed'])
        return c,result

    def report(self):
        return next(f for f in self.call('backfill_delivery_status',{'run_id':self.run},actor='api')['runs'][0]['families'] if f['family']=='S02')

    def test_one_reference_real_readback_and_provider_work_remains_open(self):
        self.source_page(1,[self.record(),self.record('T2'),self.record('OUTSIDE'),self.record(day='2026-09-15')],next_page=2)
        pending=self.task(kind='massive_short_interest',family='S02',provider='Massive',scope={'symbols':['AAPL'],'member_ids':['member-1'],'start':'2025-09-01','end':'2026-07-31'})
        self.assertEqual(self.seed(1),1)
        c,result=self.prove();self.assertEqual(result['record_count'],1);self.assertEqual(result['referenced_candidate_records'],2)
        r=self.report();self.assertEqual(r['committed_records'],2)
        self.assertEqual(r['nonminute_coverage']['physical_pointer_records'],1)
        self.assertEqual(r['nonminute_coverage']['referenced_source_observations'],2)
        self.assertFalse(r['nonminute_coverage']['full_replacement_query_satisfied'])
        self.assertIsNone(r['nonminute_coverage']['expected_applicable_records'])
        with self.f.admin() as conn:
            task=conn.execute(f'SELECT status,requests_reserved FROM {self.f.schema}.backfill_tasks_v2 WHERE id=%s',(pending,)).fetchone()
            self.assertEqual(dict(task),{'status':'PENDING','requests_reserved':0})
            rows=conn.execute(f'SELECT source_row,lineage,identity_status FROM {self.f.schema}.backfill_family_s02_v2 WHERE run_id=%s',(self.run,)).fetchall()
            self.assertEqual(len(rows),2);self.assertTrue(all(x['identity_status']=='UNRESOLVED_FROZEN_ANCHOR_CANDIDATE' for x in rows))
            self.assertTrue(all(x['lineage']['wire_bytes_retained'] is False for x in rows))
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.s02_record_fixture').fetchone()['n'],4)
            self.assertEqual(conn.execute(f'SELECT requests_reserved FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s',(self.run,)).fetchone()['requests_reserved'],0)
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_plan_units_v2 WHERE task_id=%s',(c['id'],)).fetchone()['n'],0)

    def test_lost_ack_idempotence_stale_fence_and_api_denial(self):
        self.source_page(1,[self.record()]);self.seed()
        old=self.claim(['retained_massive_archive'])
        with self.f.admin() as conn:conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",(old['id'],))
        new=self.claim(['retained_massive_archive'],worker='restarted-source-worker')
        self.assertFalse(self.f.rpc('backfill_massive_archive_commit',{'claim':self.fence(old)},actor='worker')['ok'])
        result=self.call('backfill_massive_archive_commit',{'claim':self.fence(new)})
        replay=self.call('backfill_massive_archive_commit',{'claim':self.fence(new)})
        self.assertEqual(replay['state'],'already_committed');self.assertEqual(replay['body_sha256'],result['body_sha256'])
        self.assertFalse(self.f.rpc('backfill_massive_archive_commit',{'claim':self.fence(old)},actor='worker')['ok'])
        with self.assertRaises(self.f.psycopg.Error) as denied:self.f.rpc('backfill_massive_archive_read',{'claim':self.fence(new)},actor='api')
        self.assertEqual(denied.exception.sqlstate,'PT403')
        with self.f.admin() as conn:self.assertEqual(conn.execute(f'SELECT pages_committed FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s',(self.run,)).fetchone()['pages_committed'],1)

    def test_normalized_row_or_stored_body_tamper_refuses_commit_and_later_readback(self):
        sid=self.source_page(1,[self.record()]);self.seed();c=self.claim(['retained_massive_archive'])
        with self.f.admin() as conn:conn.execute(f"UPDATE {self.f.schema}.s02_record_fixture SET raw_record=jsonb_set(raw_record,'{{short_interest}}','999')")
        self.assertFalse(self.f.rpc('backfill_massive_archive_commit',{'claim':self.fence(c)},actor='worker')['ok'])
        with self.f.admin() as conn:conn.execute(f"UPDATE {self.f.schema}.s02_record_fixture SET raw_record=jsonb_set(raw_record,'{{short_interest}}','10')")
        self.call('backfill_massive_archive_commit',{'claim':self.fence(c)})
        with self.f.admin() as conn:conn.execute(f"UPDATE {self.f.schema}.s02_document_fixture SET content_text=content_text||' ' WHERE source_id=%s",(sid,))
        refused=self.f.rpc('backfill_verify',{'claim':self.fence(c),'page_no':0},actor='worker');self.assertFalse(refused['ok'])
        with self.f.admin() as conn:
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_readbacks_v2 WHERE task_id=%s',(c['id'],)).fetchone()['n'],0)
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_s02_occurrences_v2 WHERE run_id=%s',(self.run,)).fetchone()['n'],0)

    def test_duplicate_pages_and_fresh_overlap_count_once_and_conflicts_stay_unusable(self):
        self.source_page(1,[self.record()],next_page=2);self.source_page(2,[self.record()]);self.seed(2)
        self.prove();self.prove();self.assertEqual(self.report()['committed_records'],1)
        ckey=self.task(kind='massive_short_interest',family='S02',provider='Massive',scope={'symbols':['AAPL'],'member_ids':['member-1'],'start':'2025-09-01','end':'2026-07-31'})
        c=self.claim(['massive_short_interest']);self.assertEqual(c['id'],ckey)
        self.call('backfill_reserve',{'claim':self.fence(c)})
        row=self.record(amount=11);raw=json.dumps({'status':'OK','results':[row]})
        self.call('backfill_commit',{'claim':self.fence(c),'raw_body':raw,'body_sha256':hashlib.sha256(raw.encode()).hexdigest(),
            'http_status':200,'request':request_for(c),'records':[{'symbol':'AAPL','source':row}],'next_cursor':None,'quality':[],'headers':{},
            'fetched_at':'2026-10-30T07:00Z','adapter_version':'fixture-fresh-s02'})
        self.call('backfill_verify',{'claim':self.fence(c),'page_no':0,'include_raw':False})
        cov=self.report()['nonminute_coverage'];self.assertEqual(cov['logical_output_records'],1);self.assertEqual(cov['verified_source_occurrences'],3)
        self.assertEqual(cov['conflicting_source_records'],1)
        short=next(f for f in cov['fields'] if f['field']=='short_interest');self.assertEqual(short['usable_values'],0)
        self.assertEqual(short['null_or_unusable_reasons'],{'CONFLICTING_RETAINED_OR_FRESH_SOURCE_VERSIONS':1})
        with self.f.admin() as conn:
            rows=conn.execute(f'SELECT source_row,lineage FROM {self.f.schema}.backfill_family_s02_v2 WHERE run_id=%s',(self.run,)).fetchall()
            self.assertEqual(len(rows),1);self.assertIsNone(rows[0]['source_row']['short_interest']);self.assertEqual(rows[0]['lineage']['distinct_source_value_versions'],2)

    def test_existing_monitor_admits_finite_successors_and_helpers_are_private(self):
        for n in range(1,4):self.source_page(n,[self.record(day='2026-07-15' if n<3 else '2026-07-31')],next_page=n+1 if n<3 else None)
        self.assertEqual(self.seed(1),1);self.prove()
        self.call('backfill_maintain',{'limit':1})
        with self.f.admin() as conn:
            self.assertEqual(conn.execute(f"SELECT count(*) n FROM {self.f.schema}.backfill_tasks_v2 WHERE run_id=%s AND kind='retained_massive_archive'",(self.run,)).fetchone()['n'],3)
            acl=conn.execute('SELECT has_function_privilege(%s,%s,\'EXECUTE\') allowed,has_table_privilege(%s,%s,\'SELECT\') raw',
                (self.f.gateway,self.f.schema+'.backfill_s02_source_check_v2(text)',self.f.outsider,self.f.schema+'.backfill_s02_occurrences_v2')).fetchone()
            self.assertFalse(acl['allowed']);self.assertFalse(acl['raw'])
        self.assertEqual(self.seed(8),0)
        self.prove();self.prove();self.assertIsNone(self.claim(['retained_massive_archive']))


if __name__=='__main__':unittest.main()
