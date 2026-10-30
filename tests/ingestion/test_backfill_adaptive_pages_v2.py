"""Bounded source-prefix evidence and authenticated durable page-size recovery."""
import base64
import copy
import hashlib
import json
import os
from pathlib import Path
import unittest

from astra_ingestion import backfill_provider_v2 as provider
import test_backfill_provider_v2 as adapters
import test_backfill_runtime_v2 as runtime
import test_backfill_family_fairness_v2 as fairness

ROOT = Path(__file__).resolve().parents[2]


class HeaderOpener(adapters.Opener):
    def __init__(self, status=200, headers=None):
        super().__init__('x' * (provider.MAX_BODY_BYTES + 100), status)
        self.headers = headers or {}

    def open(self, req, timeout):
        self.calls.append(req)
        return adapters.Response(req.full_url, self.data, self.status, self.headers)


class AdaptiveProviderTests(unittest.TestCase):
    def test_persisted_limit_scope_cursor_and_backward_defaults(self):
        for kind, cap in provider.PAGE_LIMIT_CAPS.items():
            with self.subTest(kind=kind):
                t = adapters.task(kind, status='inactive')
                self.assertEqual(provider.request_for(t)['params']['limit'], cap)
                t.update(page_limit=3, cursor='exact-opaque-cursor')
                saved = copy.deepcopy(t)
                q = provider.request_for(t)
                self.assertEqual(q['params']['limit'], 3)
                self.assertEqual(q['params']['cursor' if kind.startswith('massive') else 'page_token'], t['cursor'])
                self.assertEqual(t, saved)
                t['page_limit'] = cap + 1
                self.assertEqual(provider.request_for(t)['params']['limit'], cap)
                for invalid in (0, -1, True, 1.5, '10'):
                    t['page_limit'] = invalid
                    with self.assertRaises(provider.ProviderProblem):
                        provider.request_for(t)
        self.assertNotIn('limit', provider.request_for(adapters.task('alpaca_reference'))['params'])

    def test_oversize_keeps_only_honest_bounded_prefix_and_finite_recovery(self):
        for kind, cursor, limit, retry in (
                ('alpaca_stock_bars', 'token-1', 1000, True),
                ('alpaca_stock_bars', 'token-1', 1, False),
                ('massive_news', None, 100, True),
                ('massive_news', 'massive-opaque', 100, False)):
            with self.subTest(kind=kind, cursor=cursor, limit=limit):
                t = adapters.task(kind)
                t.update(cursor=cursor, page_limit=limit)
                with self.assertRaises(provider.ProviderProblem) as caught:
                    provider.BackfillProvider('key', 'secret', 'massive', opener=HeaderOpener()).fetch(t)
                exc = caught.exception
                self.assertEqual(exc.code, 'SOURCE_PAGE_TOO_LARGE')
                self.assertEqual(exc.retryable, retry)
                e = exc.evidence
                self.assertIs(e['response_complete'], False)
                self.assertEqual(e['observed_prefix_bytes'], provider.MAX_BODY_BYTES + 1)
                self.assertEqual(e['observed_prefix_sha256'], hashlib.sha256(b'x' * (provider.MAX_BODY_BYTES + 1)).hexdigest())
                partial = base64.b64decode(e['partial_body_base64'])
                self.assertEqual(partial, b'x' * provider.MAX_PARTIAL_BODY_BYTES)
                self.assertEqual(hashlib.sha256(partial).hexdigest(), e['partial_body_sha256'])
                self.assertNotIn('raw_body', e)
                self.assertNotIn('body_sha256', e)
                self.assertNotIn('next_cursor', e)
                self.assertEqual(e['request'], provider.request_for(t))

    def test_oversize_error_keeps_auth_rate_limit_and_retry_after_semantics(self):
        for status, code, retry in ((403, 'BLOCKED_EXTERNAL', False), (429, 'SOURCE_RATE_LIMIT', True), (500, 'SOURCE_HTTP_ERROR', True)):
            with self.subTest(status=status):
                with self.assertRaises(provider.ProviderProblem) as caught:
                    provider.BackfillProvider('key', 'secret', opener=HeaderOpener(status, {'Retry-After':'90000'})).fetch(adapters.task())
                self.assertEqual((caught.exception.code, caught.exception.retryable, caught.exception.retry_after), (code, retry, 90000))
                self.assertFalse(caught.exception.evidence['response_complete'])


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'), 'Explicit disposable PostgreSQL required')
class AdaptivePostgreSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Install the current retained reuse/breadth/fairness/pacing forwards
        # first, proving the adaptive hooks preserve their dispatcher changes.
        fairness.FamilyFairnessTests.setUpClass.__func__(cls)
        f = cls.fixture('runTest')
        sql = (ROOT/'sql/astra_backfill_adaptive_pages_v2.sql').read_text()
        sql = sql.replace('astra_ingestion_v1', f.schema).replace('astra_ingestion_rpc_owner_v1', f.owner)
        with f.admin() as conn:
            conn.execute(sql)

    setUp = runtime.BackfillRuntimeTests.setUp
    task = runtime.BackfillRuntimeTests.task
    call = runtime.BackfillRuntimeTests.call
    claim = runtime.BackfillRuntimeTests.claim
    fence = staticmethod(runtime.BackfillRuntimeTests.fence)

    def source_task(self, kind='alpaca_stock_bars', cursor=None):
        scope = adapters.task(kind, member_ids=['member-1'], status='inactive')['scope']
        key = self.task(kind=kind, family='N01' if kind.endswith('news') else 'P01',
                        provider='Massive' if kind.startswith('massive') else 'Alpaca', scope=scope)
        if cursor is not None:
            with self.f.admin() as conn:
                conn.execute(f'UPDATE {self.f.schema}.backfill_tasks_v2 SET cursor=%s WHERE id=%s', (json.dumps(cursor), key))
        return key

    def reserve(self, claim):
        with self.f.admin() as conn:
            conn.execute(f'UPDATE {self.f.schema}.source_limits SET next_request_at=0')
        self.assertEqual(self.call('backfill_reserve', {'claim':self.fence(claim)})['state'], 'reserved')

    def failure(self, claim, delay=2):
        partial = b'synthetic-test-prefix-not-an-original-complete-response'
        return {'claim':self.fence(claim), 'code':'SOURCE_PAGE_TOO_LARGE', 'message':'fixture oversized response',
                'retryable':True, 'retry_after':delay, 'evidence':{
                    'request':provider.request_for(claim), 'http_status':200,
                    'response_complete':False, 'read_limit_bytes':provider.MAX_BODY_BYTES,
                    'observed_prefix_bytes':provider.MAX_BODY_BYTES + 1,
                    'observed_prefix_sha256':hashlib.sha256(partial + b'x' * (provider.MAX_BODY_BYTES + 1 - len(partial))).hexdigest(),
                    'partial_body_base64':base64.b64encode(partial).decode(), 'partial_body_bytes':len(partial),
                    'partial_body_sha256':hashlib.sha256(partial).hexdigest()}}

    def due(self, key):
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET next_retry_at=clock_timestamp()-interval '1 second' WHERE id=%s", (key,))

    def row(self, key):
        with self.f.admin() as conn:
            return conn.execute(f'SELECT * FROM {self.f.schema}.backfill_tasks_v2 WHERE id=%s', (key,)).fetchone()

    def test_retry_is_durable_same_cursor_fenced_and_respects_retry_after(self):
        key = self.source_task(cursor='unchanged-token')
        first = self.claim(['alpaca_stock_bars'])
        self.assertEqual(first['page_limit'], 10000)
        self.reserve(first)
        payload = self.failure(first, 90000)
        self.assertEqual(self.call('backfill_defer', payload)['state'], 'RETRY_WAIT')
        row = self.row(key)
        self.assertEqual((row['page_limit'], row['cursor'], row['page_no'], row['attempts'], row['page_attempts'], row['requests_reserved']), (1000, 'unchanged-token', 0, 1, 1, 1))
        self.assertEqual(row['scope'], first['scope'])
        with self.f.admin() as conn:
            delay = conn.execute(f'SELECT extract(epoch FROM next_retry_at-clock_timestamp()) d FROM {self.f.schema}.backfill_tasks_v2 WHERE id=%s',(key,)).fetchone()['d']
            self.assertGreater(delay, 89990)
        replay = self.f.rpc('backfill_defer', payload, actor='worker')
        self.assertFalse(replay['ok'])
        self.assertEqual(replay['error']['code'], 'lease_lost')
        self.assertIsNone(self.claim(['alpaca_stock_bars']))
        self.due(key)
        again = self.claim(['alpaca_stock_bars'])
        self.assertEqual((again['page_limit'], again['cursor'], again['page_no'], again['attempts']), (1000, 'unchanged-token', 0, 2))

    def test_reductions_terminate_without_inventing_a_page_or_absence(self):
        key = self.source_task(cursor='unchanged-token')
        for expected in (10000, 1000, 100, 10, 1):
            claim = self.claim(['alpaca_stock_bars'])
            self.assertEqual(claim['page_limit'], expected)
            self.reserve(claim)
            result = self.call('backfill_defer', self.failure(claim))
            self.assertEqual(result['state'], 'RETRY_WAIT' if expected > 1 else 'OPERATIONAL_ERROR')
            self.due(key)
        row = self.row(key)
        self.assertEqual((row['attempts'], row['page_attempts'], row['requests_reserved'], row['page_no'], row['records_committed']), (5, 5, 5, 0, 0))
        self.assertEqual(row['cursor'], 'unchanged-token')
        self.assertIsNone(self.claim(['alpaca_stock_bars']))
        with self.f.admin() as conn:
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_pages_v2 WHERE task_id=%s',(key,)).fetchone()['n'], 0)
            evidence = conn.execute(f'SELECT evidence FROM {self.f.schema}.backfill_exceptions_v2 WHERE task_id=%s ORDER BY generation DESC LIMIT 1',(key,)).fetchone()['evidence']
            self.assertTrue(evidence['not_provider_absence'])
            self.assertTrue(evidence['minimum_page_size_exhausted'])

    def test_invalid_partial_evidence_limit_and_unreserved_failure_do_not_mutate(self):
        key = self.source_task()
        claim = self.claim(['alpaca_stock_bars'])
        self.assertFalse(self.f.rpc('backfill_defer', self.failure(claim), actor='worker')['ok'])
        self.reserve(claim)
        for field, value in (('partial_body_sha256', '0'*64), ('response_complete', True)):
            payload = self.failure(claim)
            payload['evidence'][field] = value
            self.assertFalse(self.f.rpc('backfill_defer', payload, actor='worker')['ok'])
        wrong = self.failure(claim)
        wrong['evidence']['request']['params']['limit'] = 9999
        self.assertFalse(self.f.rpc('backfill_defer', wrong, actor='worker')['ok'])
        self.assertEqual(self.row(key)['page_limit'], 10000)
        self.assertEqual(self.row(key)['status'], 'RUNNING')
        with self.assertRaises(self.f.psycopg.Error) as denied:
            self.f.rpc('backfill_defer', self.failure(claim), actor='api')
        self.assertEqual(denied.exception.sqlstate, 'PT403')
        with self.f.admin() as conn:
            self.assertFalse(conn.execute('SELECT has_function_privilege(%s,%s,\'EXECUTE\') allowed',
                (self.f.gateway, self.f.schema+'.backfill_adapt_page_v2('+self.f.schema+'.backfill_tasks_v2,jsonb)')).fetchone()['allowed'])

    def test_massive_first_page_can_reduce_but_opaque_cursor_cannot(self):
        key = self.source_task('massive_news')
        claim = self.claim(['massive_news'])
        self.assertEqual(claim['page_limit'], 100)
        self.reserve(claim)
        self.assertEqual(self.call('backfill_defer', self.failure(claim))['state'], 'RETRY_WAIT')
        self.assertEqual(self.row(key)['page_limit'], 10)
        second = self.source_task('massive_news', cursor='opaque-page-settings')
        claim = self.claim(['massive_news'])
        self.assertEqual(claim['id'], second)
        self.reserve(claim)
        self.assertEqual(self.call('backfill_defer', self.failure(claim))['state'], 'OPERATIONAL_ERROR')
        self.assertEqual(self.row(second)['page_limit'], 100)
        self.assertEqual(self.row(second)['cursor'], 'opaque-page-settings')
        with self.f.admin() as conn:
            e = conn.execute(f'SELECT evidence FROM {self.f.schema}.backfill_exceptions_v2 WHERE task_id=%s',(second,)).fetchone()['evidence']
            self.assertEqual(e['operational_dependency'], 'MASSIVE_OPAQUE_CURSOR_PAGE_TOO_LARGE')
            self.assertTrue(e['cursor_controls_page_size'])

    def test_commit_requires_exact_claimed_limit_and_keeps_it_on_successor(self):
        key = self.source_task()
        first = self.claim(['alpaca_stock_bars'])
        self.reserve(first)
        self.call('backfill_defer', self.failure(first))
        self.due(key)
        claim = self.claim(['alpaca_stock_bars'])
        self.reserve(claim)
        raw = '{"bars":{},"next_page_token":"real-next-page"}'
        payload = {'claim':self.fence(claim), 'raw_body':raw, 'body_sha256':hashlib.sha256(raw.encode()).hexdigest(),
                   'http_status':200, 'request':provider.request_for(claim), 'records':[], 'quality':[],
                   'next_cursor':'real-next-page', 'headers':{}, 'fetched_at':'2026-10-30T06:00:00Z', 'adapter_version':'fixture-v2'}
        wrong = copy.deepcopy(payload)
        wrong['request']['params']['limit'] = 10000
        self.assertFalse(self.f.rpc('backfill_commit', wrong, actor='worker')['ok'])
        self.assertEqual(self.row(key)['page_no'], 0)
        self.call('backfill_commit', payload)
        following = self.claim(['alpaca_stock_bars'])
        self.assertEqual((following['page_limit'], following['cursor'], following['page_no']), (1000, 'real-next-page', 1))

    def test_eighth_attempt_stays_terminal_and_pacing_fairness_hooks_survive(self):
        key = self.source_task()
        with self.f.admin() as conn:
            conn.execute(f'UPDATE {self.f.schema}.backfill_tasks_v2 SET page_attempts=7,attempts=7 WHERE id=%s',(key,))
        claim = self.claim(['alpaca_stock_bars'])
        self.reserve(claim)
        self.assertEqual(self.call('backfill_defer', self.failure(claim))['state'], 'OPERATIONAL_ERROR')
        self.assertEqual(self.row(key)['page_limit'], 10000)
        self.assertEqual(self.row(key)['attempts'], 8)
        with self.f.admin() as conn:
            d = conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',(self.f.schema+'.backfill_dispatch_v2(text,jsonb)',)).fetchone()['d']
            self.assertIn('backfill_paid_provider_pacing_v2', d)
            self.assertIn('backfill_family_turn_v2', d)
            self.assertIn('backfill_adaptive_page_dispatch_v2', d)


if __name__ == '__main__':
    unittest.main()
