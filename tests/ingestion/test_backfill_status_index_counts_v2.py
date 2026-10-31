"""Index-backed task counts retain complete delivery JSON and alias semantics."""
from hashlib import sha256
import json
import os
from pathlib import Path
import unittest

import test_backfill_claim_performance_v2 as current
import test_backfill_runtime_v2 as runtime

ROOT = Path(__file__).resolve().parents[2]
PERFORMANCE = {}


def nodes(plan):
    yield plan
    for child in plan.get('Plans', []):
        yield from nodes(child)


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'), 'Explicit disposable PostgreSQL required')
class StatusIndexCountsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        current.ClaimPerformanceTests.setUpClass.__func__(cls)
        f = cls.fixture('runTest')
        with f.admin() as conn:
            conn.execute(cls.rewrite((ROOT / 'sql/astra_backfill_shared_refresh_performance_v2.sql').read_text()))
            receipt = conn.execute('SELECT pg_get_viewdef(%s::regclass,true) d',
                (f.schema + '.backfill_family_receipt_status_v2',)).fetchone()['d']
            cls.outer_before = conn.execute('SELECT pg_get_viewdef(%s::regclass,true) d',
                (f.schema + '.backfill_family_status_v2',)).fetchone()['d']
            conn.execute(f'CREATE VIEW {f.schema}.status_original_receipt_v2 WITH(security_invoker=true) AS ' + receipt)
            original_family = cls.outer_before.replace(f.schema + '.backfill_family_receipt_status_v2',
                f.schema + '.status_original_receipt_v2')
            cls.original_family_name = f.schema + '.status_original_family_v2'
            conn.execute('CREATE VIEW ' + cls.original_family_name + ' WITH(security_invoker=true) AS ' + original_family)
            cls.receipt_metadata = conn.execute('SELECT oid,relowner,relacl,reloptions FROM pg_class WHERE oid=%s::regclass',
                (f.schema + '.backfill_family_receipt_status_v2',)).fetchone()
            cls.receipt_columns = conn.execute('''SELECT attname,atttypid,atttypmod,attcollation FROM pg_attribute
                WHERE attrelid=%s::regclass AND attnum>0 AND NOT attisdropped ORDER BY attnum''',
                (f.schema + '.backfill_family_receipt_status_v2',)).fetchall()
            cls.status_sql = conn.execute('SELECT prosrc FROM pg_proc WHERE oid=%s::regprocedure',
                (f.schema + '.backfill_delivery_status_v2(text)',)).fetchone()['prosrc']
            cls.outer_rpc = conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (f.schema + '.rpc_dispatch(text,jsonb)',)).fetchone()['d']
            cls.repair = cls.rewrite((ROOT / 'sql/astra_backfill_status_index_counts_v2.sql').read_text())
            conn.execute(cls.repair)

    rewrite = classmethod(current.ClaimPerformanceTests.rewrite.__func__)
    setUp = runtime.BackfillRuntimeTests.setUp
    task = runtime.BackfillRuntimeTests.task

    def family_rows(self, original=False):
        view = self.original_family_name if original else self.f.schema + '.backfill_family_status_v2'
        with self.f.admin() as conn:
            return conn.execute(f'SELECT to_jsonb(v) value FROM {view} v WHERE run_id=%s ORDER BY family', (self.run,)).fetchall()

    def equivalent(self):
        new = self.family_rows()
        self.assertEqual(new, self.family_rows(original=True))
        self.assertEqual(len(new), 16)
        return {row['value']['family']:row['value'] for row in new}

    def test_all_statuses_and_native_p02_alias_exclusions_preserve_full_family_json(self):
        states = ['PENDING', 'RUNNING', 'RETRY_WAIT', 'INGESTED', 'NO_DATA_RETURNED', 'NOT_APPLICABLE',
                  'PROVIDER_LIMITATION', 'IDENTITY_OR_QUALITY_UNRESOLVED', 'OPERATIONAL_ERROR',
                  'BLOCKED_EXTERNAL', 'SUPERSEDED_BY_SCOPE_CHANGE']
        cases = [('P01', 'alpaca_stock_bars', 'Alpaca', {'timeframe':'1Min'}),
                 ('P01', 'retained_reuse', 'REUSE', {}),
                 ('P01', 'alpaca_stock_bars', 'Alpaca', {'timeframe':'1Day'}),
                 ('P01', 'derive_intraday', 'DERIVED', {'timeframe':'1Min'}),
                 ('P02', 'alpaca_stock_bars', 'Alpaca', {'timeframe':'1Min'}),
                 ('N01', 'massive_news', 'Massive', {})]
        with self.f.admin() as conn:
            for i, (family, kind, provider, extra) in enumerate(cases):
                scope = {'symbols':['AAPL'], 'member_ids':['member-1'], **extra}
                for j, state in enumerate(states):
                    conn.execute(f'''INSERT INTO {self.f.schema}.backfill_tasks_v2
                        (id,run_id,family,provider,kind,scope,status,owner,lease_until,next_retry_at)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                        (self.run + f'-state-{i}-{j}', self.run, family, provider, kind, json.dumps(scope), state,
                         'fixture-owner' if state == 'RUNNING' else None,
                         '2027-01-01T00:00Z' if state == 'RUNNING' else None, '2026-10-30T11:00Z'))
        report = self.equivalent()
        self.assertEqual(report['P01']['planned_units'], 44)
        self.assertEqual(report['P02']['planned_units'], 33)
        self.assertEqual(report['P02']['retry_wait_units'], 3)
        self.assertEqual(report['P02']['terminal_units'], 15)

    def test_retry_minimum_combines_native_and_only_qualifying_aliases_and_preserves_null(self):
        definitions = [
            ('P01', 'alpaca_stock_bars', 'Alpaca', {'timeframe':'1Day'}, '09:00'),
            ('P01', 'derive_intraday', 'DERIVED', {'timeframe':'1Min'}, '09:10'),
            ('P01', 'retained_reuse', 'REUSE', {}, '12:00'),
            ('P02', 'alpaca_stock_bars', 'Alpaca', {'timeframe':'1Min'}, '11:00'),
        ]
        keys = []
        with self.f.admin() as conn:
            for i, (family, kind, provider, extra, stamp) in enumerate(definitions):
                key = self.run + '-retry-' + str(i)
                keys.append(key)
                conn.execute(f'''INSERT INTO {self.f.schema}.backfill_tasks_v2
                    (id,run_id,family,provider,kind,scope,status,next_retry_at)
                    VALUES(%s,%s,%s,%s,%s,%s,'RETRY_WAIT',%s)''',
                    (key, self.run, family, provider, kind,
                     json.dumps({'symbols':['AAPL'], 'member_ids':['member-1'], **extra}), '2026-10-30T' + stamp + 'Z'))
        report = self.equivalent()
        self.assertTrue(report['P01']['next_retry_at'].startswith('2026-10-30T09:00'))
        self.assertTrue(report['P02']['next_retry_at'].startswith('2026-10-30T11:00'))
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET next_retry_at='2026-10-30T10:00Z' WHERE id=%s", (keys[2],))
        self.assertTrue(self.equivalent()['P02']['next_retry_at'].startswith('2026-10-30T10:00'))
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET status='PENDING' WHERE run_id=%s", (self.run,))
        report = self.equivalent()
        self.assertIsNone(report['P01']['next_retry_at'])
        self.assertIsNone(report['P02']['next_retry_at'])

    def test_view_identity_columns_permissions_outer_wrappers_and_replay_guard_are_unchanged(self):
        with self.f.admin() as conn:
            self.assertEqual(conn.execute('SELECT oid,relowner,relacl,reloptions FROM pg_class WHERE oid=%s::regclass',
                (self.f.schema + '.backfill_family_receipt_status_v2',)).fetchone(), self.receipt_metadata)
            self.assertEqual(conn.execute('''SELECT attname,atttypid,atttypmod,attcollation FROM pg_attribute
                WHERE attrelid=%s::regclass AND attnum>0 AND NOT attisdropped ORDER BY attnum''',
                (self.f.schema + '.backfill_family_receipt_status_v2',)).fetchall(), self.receipt_columns)
            self.assertEqual(conn.execute('SELECT pg_get_viewdef(%s::regclass,true) d',
                (self.f.schema + '.backfill_family_status_v2',)).fetchone()['d'], self.outer_before)
            self.assertEqual(conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (self.f.schema + '.rpc_dispatch(text,jsonb)',)).fetchone()['d'], self.outer_rpc)
            for role in (self.f.gateway, self.f.outsider):
                self.assertFalse(conn.execute("SELECT has_table_privilege(%s,%s,'SELECT') allowed",
                    (role, self.f.schema + '.backfill_family_receipt_status_v2')).fetchone()['allowed'])
        with self.assertRaises(self.f.psycopg.Error), self.f.admin() as conn:
            conn.execute(self.repair)
        self.equivalent()

    def test_wide_task_plan_uses_existing_status_index_and_preserves_complete_status(self):
        scale = int(os.environ.get('ASTRA_STATUS_INDEX_SCALE', '30000'))
        self.assertTrue(10000 <= scale <= 600000)
        split = scale * 3 // 5
        def seed(start, end):
            with self.f.admin() as conn:
                conn.execute(f'''INSERT INTO {self.f.schema}.backfill_tasks_v2
                    (id,run_id,family,provider,kind,scope,status,next_retry_at)
                    SELECT %s||'-scale-'||g,%s,
                        CASE WHEN g%%20=0 THEN 'P01' WHEN g%%10=0 THEN 'N01' ELSE 'D01' END,
                        CASE WHEN g%%20=0 THEN 'Alpaca' WHEN g%%10=0 THEN 'Massive' ELSE 'DERIVED' END,
                        CASE WHEN g%%20=0 THEN 'alpaca_stock_bars' WHEN g%%10=0 THEN 'massive_news' ELSE 'derive_intraday' END,
                        jsonb_build_object('symbols',jsonb_build_array(CASE WHEN (g-1)%%3000=0 THEN 'AAPL' ELSE 'T'||(1+(g-1)%%3000) END),
                          'member_ids',jsonb_build_array('member-'||(1+(g-1)%%3000)),
                          'timeframe',CASE WHEN g%%40=0 THEN '1Day' ELSE '1Min' END,'padding',repeat(md5(g::text),30)),
                        CASE WHEN g%%997=0 THEN 'RETRY_WAIT' ELSE 'PENDING' END,'2026-10-30T12:00Z'
                    FROM generate_series(%s::integer,%s::integer)g''', (self.run, self.run, start, end))
        seed(1, split)
        with self.f.admin() as conn:
            conn.autocommit = True
            conn.execute(f'VACUUM (ANALYZE) {self.f.schema}.backfill_tasks_v2')
        seed(split + 1, scale)
        with self.f.admin() as conn:
            conn.execute(f'ANALYZE {self.f.schema}.backfill_tasks_v2')
            query = self.status_sql.replace('p_run_id', '%(run)s::text')
            baseline = query.replace(self.f.schema + '.backfill_family_status_v2', self.original_family_name)
            old = conn.execute(baseline, {'run':self.run}).fetchone()
            new = conn.execute(query, {'run':self.run}).fetchone()
            old_json, new_json = next(iter(old.values())), next(iter(new.values()))
            old_json.pop('observed_at'); new_json.pop('observed_at')
            self.assertEqual(old_json, new_json)
            plans = {}
            for label, statement in [('baseline', baseline), ('candidate', query)]:
                plans[label] = conn.execute('EXPLAIN(ANALYZE,BUFFERS,FORMAT JSON) ' + statement,
                    {'run':self.run}).fetchone()['QUERY PLAN'][0]
            candidate_nodes = list(nodes(plans['candidate']['Plan']))
            indexed = [n for n in candidate_nodes if n.get('Relation Name') == 'backfill_tasks_v2'
                       and n.get('Node Type') == 'Index Only Scan' and n.get('Index Name') == 'backfill_tasks_family_v2'
                       and n.get('Actual Rows', 0) >= scale]
            self.assertEqual(len(indexed), 1)
            self.assertEqual(indexed[0]['Actual Loops'], 1)
            self.assertLess(indexed[0].get('Heap Fetches', scale), scale * 0.5)
            self.assertFalse(any(n.get('Relation Name') == 'backfill_tasks_v2' and n.get('Node Type') == 'Seq Scan'
                                 and n.get('Actual Rows', 0) >= scale * 0.9 for n in candidate_nodes))
            self.assertLess(plans['candidate']['Execution Time'], 8000)
            PERFORMANCE.update(scale=scale, older_visible_tasks=split, recent_tasks=scale-split,
                existing_index='backfill_tasks_family_v2', indexed_heap_fetches=indexed[0].get('Heap Fetches'),
                baseline_ms=plans['baseline']['Execution Time'], candidate_ms=plans['candidate']['Execution Time'],
                complete_status_equal=True, status_sha256=sha256(json.dumps(new_json, sort_keys=True).encode()).hexdigest(),
                plans=plans)


if __name__ == '__main__':
    unittest.main()
