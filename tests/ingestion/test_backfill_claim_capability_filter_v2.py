"""Actual PostgreSQL qualification of the two-predicate capability filter repair."""
from hashlib import sha256
import json
import os
from pathlib import Path
import unittest

import test_backfill_claim_performance_v2 as claims
import test_backfill_runtime_status_performance_v2 as current
import test_backfill_runtime_v2 as runtime

ROOT = Path(__file__).resolve().parents[2]
FORWARD = ROOT / 'sql/astra_backfill_claim_capability_filter_v2.sql'
OLD = 'q.kind IN (SELECT jsonb_array_elements_text(v_supported))'
NEW = 'q.kind = ANY(ARRAY(SELECT jsonb_array_elements_text(v_supported)))'
LIVE_BEFORE = '136871b8ca305ae69c661541d9c2684e71b1d5e6fe84a6ec9b8b594b1da56d02'
LIVE_AFTER = '28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44'
LIVE_AUTH = 'a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520'
LIVE_STATUS = 'cee8f62d034a88e3fb5166fce2b4b4903cdd1aee802e2efebfc3f08cf6c0a5de'
LIVE_RUN = 'fixed3000-20250901-20260731-v1-20261030'
OWNER = 'root-replacement-20261030T042603Z'
KINDS = ['alpaca_reference', 'alpaca_stock_bars', 'alpaca_news', 'alpaca_actions',
         'alpaca_option_contracts', 'alpaca_option_bars', 'derive_daily', 'derive_intraday',
         'derive_breadth', 'retained_reuse', 'retained_identity', 'retained_massive_archive']
EVIDENCE = {}


def digest(value):
    return sha256(value.encode()).hexdigest()


def candidates(definition, schema):
    marker = 'SELECT q.* INTO t FROM ' + schema + '.backfill_tasks_v2'
    queries = []
    pos = 0
    for _ in range(2):
        start = definition.index(marker, pos)
        end = definition.index(' LIMIT 1 FOR UPDATE OF q;', start) + len(' LIMIT 1 FOR UPDATE OF q;')
        query = definition[start:end].replace(' INTO t ', ' ')
        for old, new in [('v_fair_run', '$1'), ('v_fair_pick.family', '$2'), ('v_supported', '$3'), ('v_now', '$4')]:
            query = query.replace(old, new)
        queries.append(query)
        pos = end
    return queries


class CapabilityFilterSourceTests(unittest.TestCase):
    def test_forward_pins_exact_dual_change_and_security_boundaries(self):
        sql = FORWARD.read_text()
        for pin in (LIVE_BEFORE, LIVE_AFTER, LIVE_AUTH, LIVE_STATUS, LIVE_RUN, OWNER):
            self.assertIn(pin, sql)
        self.assertIn("SET LOCAL statement_timeout='8s'", sql)
        self.assertIn("SET LOCAL lock_timeout='3s'", sql)
        self.assertEqual(sql.count('EXECUTE after_definition;'), 1)
        self.assertNotRegex(sql, r'(?im)^\s*(GRANT|REVOKE|INSERT|UPDATE|DELETE|CREATE\s+(TABLE|INDEX|ROLE))\b')
        self.assertIn('after_metadata IS DISTINCT FROM before_metadata', sql)
        self.assertIn('current_auth_metadata IS DISTINCT FROM auth_metadata', sql)
        self.assertIn('FOR SHARE;', sql)
        self.assertIn("<>2", sql)


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'), 'Explicit disposable PostgreSQL required')
class CapabilityFilterPostgreSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        current.RuntimeStatusPerformanceTests.setUpClass.__func__(cls)
        f = cls.fixture('runTest')
        with f.admin() as conn:
            cls.before = conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (f.schema + '.backfill_dispatch_v2(text,jsonb)',)).fetchone()['d']
            cls.auth = conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (f.schema + '.rpc_dispatch(text,jsonb)',)).fetchone()['d']
        assert cls.before.count(OLD) == 2
        cls.after = cls.before.replace(OLD, NEW)
        cls.forward_template = cls.rewrite(FORWARD.read_text())
        # Only fixture identifiers and content pins are adapted. The admission,
        # exact transformation, postconditions and transaction execute unchanged.
        for old, new in [(LIVE_BEFORE, digest(cls.before)), (LIVE_AFTER, digest(cls.after)),
                         (LIVE_AUTH, digest(cls.auth)), (LIVE_STATUS, digest(current.branch(cls.before)))]:
            cls.forward_template = cls.forward_template.replace(old, new)

    rewrite = classmethod(current.RuntimeStatusPerformanceTests.rewrite.__func__)
    full_query = staticmethod(current.RuntimeStatusPerformanceTests.full_query)
    task = runtime.BackfillRuntimeTests.task
    call = runtime.BackfillRuntimeTests.call
    claim = runtime.BackfillRuntimeTests.claim
    page = runtime.BackfillRuntimeTests.page
    fence = staticmethod(runtime.BackfillRuntimeTests.fence)

    def setUp(self):
        current.RuntimeStatusPerformanceTests.setUp(self)
        self.forward = self.forward_template.replace(LIVE_RUN, self.run)
        with self.f.admin() as conn:
            conn.execute(self.before)
            conn.execute(f'''UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=jsonb_build_object(
                'implementation_owner',%s::text,'implementation_lease_until',clock_timestamp()+interval '30 minutes')
                WHERE id=%s''', (OWNER, self.run))
            conn.commit()
            conn.execute(self.forward)

    def definition(self, conn, name='backfill_dispatch_v2'):
        return conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
            (self.f.schema + '.' + name + '(text,jsonb)',)).fetchone()['d']

    def snapshot(self, conn):
        out = {}
        for table in ('backfill_runs_v2', 'backfill_members_v2', 'backfill_tasks_v2',
                      'backfill_provider_dependencies_v2', 'backfill_workers_v2',
                      'backfill_family_turn_v2', 'backfill_pages_v2', 'backfill_readbacks_v2'):
            out[table] = conn.execute(f'''SELECT count(*) n,encode(sha256(convert_to(
                COALESCE(string_agg(to_jsonb(x)::text,E'\n' ORDER BY to_jsonb(x)::text),''),'UTF8')),'hex') digest
                FROM {self.f.schema}.{table} x''').fetchone()
        return out

    def test_forward_preserves_all_other_source_metadata_auth_status_and_data(self):
        with self.f.admin() as conn:
            conn.execute(self.before)
            before = self.snapshot(conn)
            metadata = conn.execute("SELECT to_jsonb(p)-'prosrc' m FROM pg_proc p WHERE oid=ANY(%s::regprocedure[]) ORDER BY oid",
                ([self.f.schema + '.backfill_dispatch_v2(text,jsonb)', self.f.schema + '.rpc_dispatch(text,jsonb)'],)).fetchall()
            conn.commit()
            conn.execute(self.forward)
            actual = self.definition(conn)
            self.assertEqual(actual, self.after)
            self.assertEqual(actual.replace(NEW, OLD), self.before)
            self.assertEqual(current.branch(actual), current.branch(self.before))
            self.assertEqual(self.definition(conn, 'rpc_dispatch'), self.auth)
            self.assertEqual(metadata, conn.execute("SELECT to_jsonb(p)-'prosrc' m FROM pg_proc p WHERE oid=ANY(%s::regprocedure[]) ORDER BY oid",
                ([self.f.schema + '.backfill_dispatch_v2(text,jsonb)', self.f.schema + '.rpc_dispatch(text,jsonb)'],)).fetchall())
            self.assertEqual(before, self.snapshot(conn))
            for role in (self.f.gateway, self.f.outsider):
                self.assertFalse(conn.execute("SELECT has_function_privilege(%s,%s,'EXECUTE') allowed",
                    (role, self.f.schema + '.backfill_dispatch_v2(text,jsonb)')).fetchone()['allowed'])
        EVIDENCE['preservation'] = {'only_two_predicates': True, 'metadata_oid_acl_owner_config': True,
            'outer_authentication': True, 'status_branch': True, 'data_tables_unchanged': True}

    def test_fail_closed_replay_drift_ownership_cohort_and_postwrite_rollback(self):
        with self.assertRaises(self.f.psycopg.Error), self.f.admin() as conn:
            conn.execute(self.forward)
        with self.f.admin() as conn:
            self.assertEqual(self.definition(conn), self.after)
            conn.execute(self.before)
            pristine_run = conn.execute(f'SELECT metadata FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s',
                (self.run,)).fetchone()['metadata']
        checks = []
        cases = [
            ('source_pin', self.forward.replace(digest(self.before), '0' * 64), None),
            ('auth_pin', self.forward.replace(digest(self.auth), '0' * 64), None),
            ('status_pin', self.forward.replace(digest(current.branch(self.before)), '0' * 64), None),
            ('postimage_pin', self.forward.replace(digest(self.after), '0' * 64), None),
            ('wrong_owner', self.forward, "metadata=jsonb_set(metadata,'{implementation_owner}','\"different-owner\"')"),
            ('expired_lease', self.forward, "metadata=jsonb_set(metadata,'{implementation_lease_until}','\"2000-01-01T00:00:00Z\"')"),
            ('run_stop', self.forward, "status='PAUSED'"),
            ('postwrite_rollback', self.forward.replace('END $repair$;',
                "RAISE EXCEPTION 'injected failure after verified function replacement';\nEND $repair$;"), None),
        ]
        for label, sql, mutation in cases:
            with self.subTest(label=label):
                with self.f.admin() as conn:
                    conn.execute(self.before)
                    conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=%s,status='ACTIVE',fence=1 WHERE id=%s",
                        (json.dumps(pristine_run), self.run))
                    if mutation:
                        conn.execute(f'UPDATE {self.f.schema}.backfill_runs_v2 SET {mutation} WHERE id=%s', (self.run,))
                with self.assertRaises(self.f.psycopg.Error), self.f.admin() as conn:
                    conn.execute(sql)
                with self.f.admin() as conn:
                    self.assertEqual(self.definition(conn), self.before)
                    self.assertEqual(self.definition(conn, 'rpc_dispatch'), self.auth)
                checks.append(label)
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=%s,status='ACTIVE',fence=1 WHERE id=%s",
                (json.dumps(pristine_run), self.run))
            # Frozen members cannot be deleted. Build a distinct incomplete
            # fixture run, then append its final member after testing rejection.
            original_run = self.run
            self.run += '-incomplete'
            self.forward = self.forward.replace(original_run, self.run)
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET status='PAUSED',fence=fence+1 WHERE id=%s", (original_run,))
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_runs_v2
                (id,instruction_sha256,cohort_sha256,cohort_manifest_sha256,cohort_ref,scope,metadata)
                SELECT %s,instruction_sha256,cohort_sha256,cohort_manifest_sha256,cohort_ref,scope,metadata
                FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s''', (self.run, original_run))
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_members_v2(run_id,member_id,selection_order,anchor_ticker)
                SELECT %s,member_id,selection_order,anchor_ticker FROM {self.f.schema}.backfill_members_v2
                WHERE run_id=%s AND selection_order<3000''', (self.run, original_run))
        with self.assertRaises(self.f.psycopg.Error), self.f.admin() as conn:
            conn.execute(self.forward)
        with self.f.admin() as conn:
            self.assertEqual(self.definition(conn), self.before)
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_members_v2(run_id,member_id,selection_order,anchor_ticker)
                VALUES(%s,'member-3000',3000,'T3000')''', (self.run,))
            drift = self.before.replace(OLD, NEW, 1)
            conn.execute(drift)
        # Adapt only the initial source pin to prove the multiplicity check itself
        # fails even if a future operator mistakenly repins a one-sided mutation.
        with self.assertRaises(self.f.psycopg.Error), self.f.admin() as conn:
            conn.execute(self.forward.replace(digest(self.before), digest(drift)))
        with self.f.admin() as conn:
            self.assertEqual(self.definition(conn), drift)
            conn.execute(self.before)
            conn.commit()
            conn.execute(self.forward)
            conn.execute(self.before)
            # A real fence is monotonic. Exercise this rejection last rather
            # than attempting an invalid fixture reset from fence 2 to fence 1.
            conn.execute(f'UPDATE {self.f.schema}.backfill_runs_v2 SET fence=2 WHERE id=%s', (self.run,))
        with self.assertRaises(self.f.psycopg.Error), self.f.admin() as conn:
            conn.execute(self.forward)
        with self.f.admin() as conn:
            self.assertEqual(self.definition(conn), self.before)
        EVIDENCE['fail_closed'] = checks + ['replay', '2999_members', 'predicate_multiplicity', 'run_fence']

    def test_three_valued_membership_and_unchanged_capability_admission(self):
        values = [[], [None], ['alpaca_news'], ['alpaca_news', 'alpaca_news'],
                  ['other', None], ['alpaca_news', None], [1, True, {}, [], None],
                  ['1', 1], ['true', True], ['{"a": 1}', {'a': 1}], ['["x"]', ['x']]]
        lhs = [None, 'alpaca_news', 'other', '1', 'true', '{"a": 1}', '["x"]', 'é']
        checked = 0
        with self.f.admin() as conn:
            for kinds in values:
                for kind in lhs:
                    row = conn.execute('''SELECT %s::text IN(SELECT jsonb_array_elements_text(%s::jsonb)) old,
                        %s::text = ANY(ARRAY(SELECT jsonb_array_elements_text(%s::jsonb))) new''',
                        (kind, json.dumps(kinds), kind, json.dumps(kinds))).fetchone()
                    self.assertIs(row['old'], row['new'])
                    checked += 1
        task = self.task(kind='alpaca_news', family='N01')
        for value in [None, {}, 'alpaca_news', 123, ['alpaca_news'] * 33]:
            reply = self.f.rpc('backfill_claim', {'worker_id':'shape-fixture', 'source_revision':'fixture', 'supported_kinds':value}, actor='worker')
            self.assertFalse(reply['ok'])
        for value in [[], [None], ['other', None]]:
            self.assertIsNone(self.call('backfill_claim', {'worker_id':'shape-fixture', 'source_revision':'fixture', 'supported_kinds':value}))
        got = self.call('backfill_claim', {'worker_id':'shape-fixture', 'source_revision':'fixture', 'supported_kinds':[None, 'alpaca_news', 'alpaca_news']})
        self.assertEqual(got['id'], task)
        EVIDENCE['semantics'] = {'three_valued_cases':checked, 'invalid_shapes_and_33_elements_rejected':True,
            'empty_null_nonmatch_return_no_claim':True, 'duplicate_match_claims_once':True}

    def test_news_prefix_with_73_reuse_children_keeps_normal_and_recovery_selection(self):
        unsupported, supported, gap_count = 22121, 21922, 73
        with self.f.admin() as conn:
            for label, kind, provider, priority, count in [
                ('unsupported', 'massive_news', 'Massive', 50, unsupported),
                ('supported', 'alpaca_news', 'Alpaca', 51, supported)]:
                conn.execute(f'''INSERT INTO {self.f.schema}.backfill_tasks_v2
                    (id,run_id,family,provider,kind,scope,priority,created_at,next_retry_at)
                    SELECT %s||'-'||%s||'-'||lpad(g::text,5,'0'),%s,'N01',%s,%s,
                      '{{"symbols":["AAPL"],"member_ids":["member-1"]}}'::jsonb,
                      %s,'2026-10-30T06:00:00Z','2026-10-30T06:00:00Z'
                    FROM generate_series(1,%s)g''', (self.run, label, self.run, provider, kind, priority, count))
            # These are unfinished retained-data gap children, as in the live
            # index. News tasks have no dependencies: they must scan or dismiss
            # the same 73 rows but none may become blocked by an unrelated gap.
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_tasks_v2
                (id,run_id,family,provider,kind,scope,priority,next_retry_at)
                SELECT %s||'-gap-'||g,%s,'P01','Alpaca','alpaca_stock_bars',
                  jsonb_build_object('reuse_parent',%s||'-parent-'||g,'symbols',jsonb_build_array('AAPL'),
                    'member_ids',jsonb_build_array('member-1')),10,'2100-01-01'
                FROM generate_series(1,%s)g''', (self.run, self.run, self.run, gap_count))
            conn.execute(self.index_sql)
            for table in ('backfill_tasks_v2', 'backfill_members_v2'):
                conn.execute(f'ANALYZE {self.f.schema}.{table}')
            conn.commit()
            for label, definition in [('baseline', self.before), ('candidate', self.after)]:
                for branch, query in zip(('recovery', 'normal'), candidates(definition, self.f.schema)):
                    conn.execute(f'PREPARE capability_{label}_{branch}(text,text,jsonb,timestamptz) AS ' + query)
            conn.execute("SET statement_timeout='8s'")
            arguments = "('" + self.run + "','N01','" + json.dumps(KINDS, separators=(',', ':')) + "'::jsonb,'2026-10-30T12:23:40Z'::timestamptz)"
            plans = {}
            for branch in ('normal', 'recovery'):
                if branch == 'recovery':
                    conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET status='RETRY_WAIT' WHERE run_id=%s AND family='N01'", (self.run,))
                    conn.execute(f'ANALYZE {self.f.schema}.backfill_tasks_v2')
                plans[branch] = {}
                for mode in ('force_generic_plan', 'force_custom_plan'):
                    conn.execute('SET plan_cache_mode=' + mode)
                    plans[branch][mode] = {}
                    for label in ('baseline', 'candidate'):
                        query = 'EXECUTE capability_' + label + '_' + branch + arguments
                        got = conn.execute(query).fetchone()
                        self.assertEqual(got['id'], self.run + '-supported-00001')
                        plan = conn.execute('EXPLAIN(ANALYZE,BUFFERS,TIMING FALSE,SETTINGS TRUE,FORMAT JSON) ' + query).fetchone()['QUERY PLAN'][0]
                        plans[branch][mode][label] = plan
                        all_nodes = list(claims.nodes(plan['Plan']))
                        self.assertTrue(any(n['Node Type'] == 'LockRows' for n in all_nodes))
                        if label == 'candidate':
                            dependency_scans = [n for n in all_nodes if n.get('Alias') == 'dep']
                            self.assertEqual(len(dependency_scans), 1)
                            self.assertEqual(dependency_scans[0]['Actual Loops'], 1)
            conn.commit()
        # The installed function is also exercised through the authenticated RPC,
        # rather than inferring claim correctness from the isolated SELECT alone.
        got = self.claim(KINDS)
        self.assertEqual(got['id'], self.run + '-supported-00001')
        self.assertEqual(got['attempts'], 1)
        self.assertEqual(got['page_no'], 0)
        with self.f.admin() as conn:
            row = conn.execute(f'SELECT requests_reserved,pages_committed,records_committed FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s', (self.run,)).fetchone()
            self.assertEqual(dict(row), {'requests_reserved':0, 'pages_committed':0, 'records_committed':0})
            self.assertEqual(conn.execute(f"SELECT count(*) n FROM {self.f.schema}.backfill_tasks_v2 WHERE run_id=%s AND scope ? 'reuse_parent'", (self.run,)).fetchone()['n'], gap_count)
        EVIDENCE['backlog'] = {'unsupported':unsupported, 'supported':supported, 'unfinished_reuse_children':gap_count,
            'same_candidate_normal_and_recovery':True, 'row_lock_preserved':True, 'authenticated_rpc_claim':True,
            'accounting_unchanged':True, 'plans':plans}

    # Existing meaningful behavior checks run against the newly installed
    # forward, keeping their original assertions rather than mirroring SQL.
    test_recovery_first_fences_and_accounting = claims.ClaimPerformanceTests.test_recovery_first_lease_fences_future_retry_and_page_accounting_are_preserved
    test_dependency_gap_and_breadth_guards = claims.ClaimPerformanceTests.test_dependency_gap_and_breadth_guards_keep_blocking_only_affected_work
    test_incomplete_cohort_blocks_claim = claims.ClaimPerformanceTests.test_incomplete_cohort_still_blocks_claim_until_exact_count_is_present
    test_real_page_successor_and_lost_ack = runtime.BackfillRuntimeTests.test_real_page_auto_successor_and_lost_ack_readback


if __name__ == '__main__':
    unittest.main()
