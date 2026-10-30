"""Real news-sized payload regression and byte-identical canonical encoding."""
import hashlib
import json
import os
from pathlib import Path
import random
import time
import unittest

import test_backfill_runtime_v2 as runtime
from astra_ingestion.backfill_provider_v2 import parse_response, request_for

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'), 'Explicit disposable PostgreSQL required')
class CanonicalPerformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.runtime = type('CanonicalRuntimeFixture', (runtime.BackfillRuntimeTests,), {})
        cls.runtime.setUpClass()
        cls.addClassCleanup(cls.runtime.doClassCleanups)
        f = cls.runtime.fixture('runTest')
        with f.admin() as conn:
            original = conn.execute('select pg_get_functiondef(%s::regprocedure) d',
                                    (f.schema+'.rpc_ascii_string(text)',)).fetchone()['d']
            conn.execute(original.replace('.rpc_ascii_string(', '.rpc_ascii_string_baseline('))
            conn.execute((ROOT/'sql/astra_backfill_canonical_performance_v2.sql').read_text()
                         .replace('astra_ingestion_v1', f.schema))

    def setUp(self):
        self.r = self.runtime('runTest')
        self.r.setUp()
        self.f = self.r.f

    def test_identical_to_original_and_python_for_unicode_and_json_escapes(self):
        rng = random.Random(5243)
        chars = ''.join(chr(n) for n in range(1,256)) + 'café Ελληνικά 中文 😀\u2028\u2029'
        cases = ['', 'quote " slash \\ newline\n tab\t carriage\r', chars,
                 ''.join(chr(n) for n in (127,128,2047,2048,55295,57344,65535,65536,1114111))]
        cases += [''.join(rng.choice(chars) for _ in range(rng.randint(1,100))) for _ in range(100)]
        with self.f.admin() as conn:
            for value in cases:
                x = conn.execute(f'SELECT {self.f.schema}.rpc_ascii_string(%s) current, '
                                 f'{self.f.schema}.rpc_ascii_string_baseline(%s) original', (value,value)).fetchone()
                self.assertEqual(x['current'], x['original'])
                self.assertEqual(x['current'], json.dumps(value,ensure_ascii=True))
            payload = {'quoted"key':['ASCII', 'café 😀', '\n\r\t'], 'z':12, 'a':True}
            got = conn.execute(f'SELECT {self.f.schema}.rpc_canonical(%s::jsonb) value',
                               (json.dumps(payload),)).fetchone()['value']
            self.assertEqual(got, json.dumps(payload,ensure_ascii=True,sort_keys=True,separators=(',',':')))

    def test_real_authenticated_news_commit_and_readback_fit_bounded_transaction(self):
        scope = {'symbols':['AAPL'],'member_ids':['member-1'],
                 'start':'2025-09-01T00:00:00Z','end':'2025-09-30T23:59:59Z'}
        self.r.task(kind='alpaca_news', family='N01', scope=scope)
        claim = self.r.claim(['alpaca_news'])
        self.r.call('backfill_reserve',{'claim':self.r.fence(claim)})
        content = ('<p>Market earnings article: price, volume and outlook. café — 😀</p>\n'*320)
        body = {'news':[{'id':i,'headline':'Earnings update','symbols':['AAPL'],
                         'created_at':'2025-09-02T12:00:00Z','updated_at':'2025-09-02T12:00:01Z',
                         'content':content, 'source':'fixture-publisher'} for i in range(50)],
                'next_page_token':'news-next-page'}
        raw = json.dumps(body,ensure_ascii=False,separators=(',',':'))
        request = request_for(claim)
        records,cursor,quality = parse_response(claim,request,raw)
        payload = {'claim':self.r.fence(claim),'raw_body':raw,
                   'body_sha256':hashlib.sha256(raw.encode()).hexdigest(),'http_status':200,
                   'request_id':'bounded-news-fixture','fetched_at':'2026-10-30T06:45:00Z',
                   'request':request,'records':records,'next_cursor':cursor,'quality':quality,
                   'headers':{},'adapter_version':'canonical-performance-fixture'}
        started = time.monotonic()
        result = self.r.call('backfill_commit',payload)
        elapsed = time.monotonic()-started
        self.assertEqual(result['record_count'],50)
        self.assertEqual(result['next_cursor'],'news-next-page')
        self.assertLess(elapsed,8,'News receipt must fit the existing finite transaction budget')
        check = self.r.call('backfill_verify',{'claim':self.r.fence(claim),'page_no':0})
        self.assertEqual(check['raw_body'],raw)
        self.assertEqual(check['body_sha256'],check['readback_sha256'])
        with self.f.admin() as conn:
            expected = conn.execute(f"SELECT encode(sha256(convert_to({self.f.schema}.rpc_canonical(%s::jsonb),'UTF8')),'hex') value",
                                    (json.dumps(records,ensure_ascii=False),)).fetchone()['value']
        self.assertEqual(check['records_sha256'],expected)
        self.assertEqual(self.r.call('backfill_commit',payload)['state'],'already_committed')
        successor = self.r.claim(['alpaca_news'])
        self.assertEqual(successor['page_no'],1)
        self.assertEqual(successor['cursor'],'news-next-page')
        print(json.dumps({'canonical_news_bytes':len(raw.encode()),'commit_seconds':round(elapsed,3)}))


if __name__=='__main__':
    unittest.main()
