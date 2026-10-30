"""Actual RPC claim semantics and the unsupported-provider backlog regression."""
import json
import os
from pathlib import Path
import unittest

import test_backfill_family_report_performance_v2 as reports
import test_backfill_retained_s02_v2 as stage3
import test_backfill_runtime_v2 as runtime

ROOT = Path(__file__).resolve().parents[2]
PERFORMANCE_EVIDENCE = {}


def nodes(plan):
    yield plan
    for child in plan.get('Plans', []):
        yield from nodes(child)


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'), 'Explicit disposable PostgreSQL required')
class ClaimPerformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reports.FamilyReportPerformanceTests.setUpClass.__func__(cls)
        f = cls.fixture('runTest')
        with f.admin() as conn:
            for name in ('astra_backfill_recovery_priority_v2.sql', 'astra_backfill_pacing_fairness_v2.sql'):
                conn.execute(cls.rewrite((ROOT / 'sql' / name).read_text()))
            cls.original_dispatch = conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (f.schema + '.backfill_dispatch_v2(text,jsonb)',)).fetchone()['d']
            cls.original_metadata = conn.execute("SELECT to_jsonb(p)-'prosrc' metadata FROM pg_proc p WHERE oid=%s::regprocedure",
                (f.schema + '.backfill_dispatch_v2(text,jsonb)',)).fetchone()['metadata']
            cls.outer_auth = conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (f.schema + '.rpc_dispatch(text,jsonb)',)).fetchone()['d']
            cls.repair = cls.rewrite((ROOT / 'sql/astra_backfill_claim_performance_v2.sql').read_text())
            conn.execute(cls.repair)
            cls.repaired_dispatch = conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (f.schema + '.backfill_dispatch_v2(text,jsonb)',)).fetchone()['d']

    rewrite = classmethod(stage3.RetainedS02Tests.rewrite.__func__)
    setUp = runtime.BackfillRuntimeTests.setUp
    task = runtime.BackfillRuntimeTests.task
    call = runtime.BackfillRuntimeTests.call
    claim = runtime.BackfillRuntimeTests.claim
    fence = staticmethod(runtime.BackfillRuntimeTests.fence)

    def candidate(self, definition):
        marker = 'SELECT q.* INTO t FROM ' + self.f.schema + '.backfill_tasks_v2 q JOIN'
        start = definition.rindex(marker)
        end = definition.index('LIMIT 1 FOR UPDATE OF q;', start) + len('LIMIT 1 FOR UPDATE OF q;')
        query = definition[start:end].replace('SELECT q.* INTO t FROM', 'SELECT q.id FROM')
        for old, new in [('v_fair_run', '$1'), ('v_fair_pick.family', '$2'), ('v_supported', '$3'), ('v_now', '$4')]:
            query = query.replace(old, new)
        return query

    def test_unsupported_news_backlog_counts_members_once_in_generic_and_custom_plans(self):
        scale = int(os.environ.get('ASTRA_CLAIM_PERFORMANCE_UNSUPPORTED', '5000'))
        self.assertTrue(1000 <= scale <= 40000)
        available = self.task(kind='alpaca_news', family='N01', priority=51)
        with self.f.admin() as conn:
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_tasks_v2(id,run_id,family,provider,kind,scope,priority)
                SELECT %s||'-unsupported-'||g,%s,'N01','Massive','massive_news',
                    jsonb_build_object('symbols',jsonb_build_array(CASE WHEN (g-1)%%3000=0 THEN 'AAPL' ELSE 'T'||(1+(g-1)%%3000) END),
                      'member_ids',jsonb_build_array('member-'||(1+(g-1)%%3000))),50
                FROM generate_series(1,%s)g''', (self.run, self.run, scale))
            for table in ('backfill_tasks_v2', 'backfill_members_v2'):
                conn.execute(f'ANALYZE {self.f.schema}.{table}')
            conn.execute('SET statement_timeout=12000')
            for label, definition in [('baseline', self.original_dispatch), ('repaired', self.repaired_dispatch)]:
                conn.execute('PREPARE claim_' + label + '(text,text,jsonb,timestamptz) AS ' + self.candidate(definition))
            plans = {}
            # Run IDs are fixture-generated hex identifiers, not external text.
            arguments = "('" + self.run + "','N01','[\"alpaca_news\",\"derive_intraday\"]'::jsonb,clock_timestamp())"
            for mode in ('force_generic_plan', 'force_custom_plan'):
                conn.execute('SET plan_cache_mode=' + mode)
                plans[mode] = {}
                for label in ('baseline', 'repaired'):
                    statement = 'EXECUTE claim_' + label + arguments
                    self.assertEqual(conn.execute(statement).fetchone()['id'], available)
                    plan = conn.execute('EXPLAIN(ANALYZE,BUFFERS,FORMAT JSON) ' + statement).fetchone()['QUERY PLAN'][0]
                    plans[mode][label] = plan
                    member_scans = [n for n in nodes(plan['Plan']) if n.get('Alias') == 'm']
                    self.assertEqual(len(member_scans), 1)
                    self.assertEqual(member_scans[0]['Actual Loops'], 1 if label == 'repaired' else scale + 1)
                self.assertLess(plans[mode]['repaired']['Execution Time'], 1500)
                self.assertLess(plans[mode]['repaired']['Execution Time'], plans[mode]['baseline']['Execution Time'] / 5)
            PERFORMANCE_EVIDENCE.update(unsupported_news_tasks=scale, fixed_members=3000, plans=plans)
        claimed = self.claim(['alpaca_news', 'derive_intraday'])
        self.assertEqual(claimed['id'], available)
        self.assertEqual(claimed['attempts'], 1)

    def test_incomplete_cohort_still_blocks_claim_until_exact_count_is_present(self):
        old_run = self.run
        self.run += '-incomplete'
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET status='PAUSED',fence=fence+1 WHERE id=%s", (old_run,))
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_runs_v2
                (id,instruction_sha256,cohort_sha256,cohort_manifest_sha256,cohort_ref,scope)
                SELECT %s,instruction_sha256,cohort_sha256,cohort_manifest_sha256,cohort_ref,scope
                FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s''', (self.run, old_run))
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_members_v2(run_id,member_id,selection_order,anchor_ticker)
                SELECT %s,member_id,selection_order,anchor_ticker FROM {self.f.schema}.backfill_members_v2
                WHERE run_id=%s AND selection_order<3000''', (self.run, old_run))
        task = self.task(kind='alpaca_news', family='N01')
        self.assertIsNone(self.claim(['alpaca_news']))
        with self.f.admin() as conn:
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_members_v2(run_id,member_id,selection_order,anchor_ticker)
                SELECT %s,member_id,selection_order,anchor_ticker FROM {self.f.schema}.backfill_members_v2
                WHERE run_id=%s AND selection_order=3000''', (self.run, old_run))
        self.assertEqual(self.claim(['alpaca_news'])['id'], task)

    def test_recovery_first_lease_fences_future_retry_and_page_accounting_are_preserved(self):
        existing = self.task(kind='alpaca_news', family='N01', priority=999)
        old = self.claim(['alpaca_news'])
        fresh = self.task(kind='alpaca_news', family='N01', priority=1)
        future = self.task(kind='alpaca_news', family='N01', priority=0)
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s", (existing,))
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET status='RETRY_WAIT',next_retry_at=clock_timestamp()+interval '1 hour' WHERE id=%s", (future,))
        resumed = self.claim(['alpaca_news'], worker='successor-existing-controller')
        self.assertEqual(resumed['id'], existing)
        self.assertGreater(resumed['generation'], old['generation'])
        rejected = self.f.rpc('backfill_reserve', {'claim':self.fence(old)}, actor='worker')
        self.assertFalse(rejected['ok'])
        self.assertEqual(self.claim(['alpaca_news'])['id'], fresh)
        self.assertIsNone(self.claim(['alpaca_news']))
        with self.f.admin() as conn:
            accounting = conn.execute(f'SELECT requests_reserved,pages_committed,records_committed FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s', (self.run,)).fetchone()
            self.assertEqual(dict(accounting), {'requests_reserved':0, 'pages_committed':0, 'records_committed':0})

    def test_dependency_gap_and_breadth_guards_keep_blocking_only_affected_work(self):
        parent = self.task(kind='alpaca_stock_bars', family='P01')
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET status='NO_DATA_RETURNED' WHERE id=%s", (parent,))
        gap = self.task(kind='alpaca_stock_bars', family='P01', scope={
            'symbols':['AAPL'], 'member_ids':['member-1'], 'reuse_parent':parent})
        derived = self.task(kind='derive_intraday', family='D01', provider='DERIVED', dependencies=[parent])
        self.task(kind='derive_breadth', provider='DERIVED', family='CTX06', scope={
            'target_start':'2025-09-02', 'target_end':'2025-09-02', 'source_month':'2025-09-01',
            'representative_security':{'member-1':{'symbol':'AAPL', 'eligible':None}}})
        news = self.task(kind='alpaca_news', family='N01')
        kinds = ['derive_intraday', 'derive_breadth', 'alpaca_news']
        self.assertEqual(self.claim(kinds)['id'], news)
        self.assertIsNone(self.claim(kinds))
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET status='NO_DATA_RETURNED' WHERE id=%s", (gap,))
        self.assertEqual(self.claim(kinds)['id'], derived)

    def test_function_identity_acl_outer_auth_and_one_time_guard_are_preserved(self):
        with self.f.admin() as conn:
            metadata = conn.execute("SELECT to_jsonb(p)-'prosrc' metadata FROM pg_proc p WHERE oid=%s::regprocedure",
                (self.f.schema + '.backfill_dispatch_v2(text,jsonb)',)).fetchone()['metadata']
            # Replacing a function changes catalogue MVCC fields only, not its
            # OID, owner, arguments, ACL, security mode or configuration.
            self.assertEqual(metadata, self.original_metadata)
            self.assertEqual(conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (self.f.schema + '.rpc_dispatch(text,jsonb)',)).fetchone()['d'], self.outer_auth)
            for role in (self.f.gateway, self.f.outsider):
                self.assertFalse(conn.execute("SELECT has_function_privilege(%s,%s,'EXECUTE') allowed",
                    (role, self.f.schema + '.backfill_dispatch_v2(text,jsonb)')).fetchone()['allowed'])
        with self.assertRaises(self.f.psycopg.Error), self.f.admin() as conn:
            conn.execute(self.repair)
        with self.f.admin() as conn:
            self.assertEqual(conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (self.f.schema + '.backfill_dispatch_v2(text,jsonb)',)).fetchone()['d'], self.repaired_dispatch)


if __name__ == '__main__':
    unittest.main()
