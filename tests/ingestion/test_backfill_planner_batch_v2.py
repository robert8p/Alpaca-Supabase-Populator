"""Atomic smaller planner batches retain identical tasks, hashes and successors."""
from hashlib import sha256
import json
import os
from pathlib import Path
from time import perf_counter
import unittest

import test_backfill_claim_performance_v2 as current
import test_backfill_planner_v2 as planner

ROOT = Path(__file__).resolve().parents[2]
KINDS = [kind for kind in planner.KINDS if not kind.startswith('massive_')]
QUALIFICATION = {}


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'), 'Explicit disposable PostgreSQL required')
class PlannerBatchTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        current.ClaimPerformanceTests.setUpClass.__func__(cls)
        f = cls.fixture('runTest')
        with f.admin() as conn:
            conn.execute(cls.rewrite((ROOT / 'sql/astra_backfill_planner_v2.sql').read_text()))
            cls.original_planner = conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (f.schema + '.backfill_plan_next_v2(jsonb)',)).fetchone()['d']
            cls.planner_metadata = conn.execute("SELECT to_jsonb(p)-'prosrc' metadata FROM pg_proc p WHERE oid=%s::regprocedure",
                (f.schema + '.backfill_plan_next_v2(jsonb)',)).fetchone()['metadata']
            cls.outer_auth_after_planner = conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (f.schema + '.rpc_dispatch(text,jsonb)',)).fetchone()['d']
            cls.batch_repair = cls.rewrite((ROOT / 'sql/astra_backfill_planner_batch_v2.sql').read_text())
            conn.execute(cls.batch_repair)
            cls.repaired_planner = conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (f.schema + '.backfill_plan_next_v2(jsonb)',)).fetchone()['d']

    rewrite = classmethod(current.ClaimPerformanceTests.rewrite.__func__)
    setUp = planner.BackfillPlannerTests.setUp
    plan = planner.BackfillPlannerTests.plan

    def snapshot(self, conn):
        result = {}
        result['tasks'] = [r['record'] for r in conn.execute(f'''SELECT jsonb_build_object(
            'id',id,'run_id',run_id,'family',family,'provider',provider,'kind',kind,'scope',scope,
            'dependencies',dependencies,'priority',priority,'run_fence',run_fence) record
            FROM {self.f.schema}.backfill_tasks_v2 WHERE run_id=%s ORDER BY id''', (self.run,))]
        result['units'] = [r['record'] for r in conn.execute(f'''SELECT to_jsonb(u)-'recorded_at' record
            FROM {self.f.schema}.backfill_plan_units_v2 u WHERE run_id=%s ORDER BY task_id''', (self.run,))]
        result['coverage'] = [r['record'] for r in conn.execute(f'''SELECT to_jsonb(c) record
            FROM {self.f.schema}.backfill_plan_coverage_v2 c WHERE run_id=%s ORDER BY family,member_id''', (self.run,))]
        result['cursor'] = conn.execute(f'''SELECT jsonb_build_object(
            'phase',metadata->'planner_phase','next',metadata->'planner_next_selection_order',
            'breadth',metadata->'planner_next_breadth_index','expected',metadata->'planner_expected_static_count',
            'complete',metadata->'planning_complete') record
            FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s''', (self.run,)).fetchone()['record']
        return result

    def connected_plan(self, conn, limit):
        conn.execute(f'SET LOCAL ROLE {self.f.gateway}')
        conn.execute("SELECT set_config('request.headers',%s,true),set_config('request.jwt.claims',%s,true),set_config('request.method','POST',true),set_config('request.jwt.claim.sub','',true)",
            (json.dumps({'x-astra-ingestion-token':self.f.tokens['worker']}), json.dumps({'role':self.f.gateway})))
        result = conn.execute(f'SELECT public.{self.f.endpoint}(%s,%s::jsonb) value',
            ('backfill_plan_next', json.dumps({'run_id':self.run, 'member_limit':limit, 'supported_kinds':KINDS}))).fetchone()['value']
        conn.execute('RESET ROLE')
        self.assertTrue(result['ok'], result)
        return result['result']

    def test_five_durable_one_member_calls_equal_original_batch_definitions_hashes_and_coverage(self):
        with self.f.admin() as conn:
            conn.execute("SET LOCAL statement_timeout='10s'")
            conn.execute('SAVEPOINT original_five_member_batch')
            conn.execute(self.original_planner)
            started = perf_counter()
            original = self.connected_plan(conn, 5)
            baseline_seconds = perf_counter() - started
            expected = self.snapshot(conn)
            self.assertEqual(original['members_admitted_this_call'], 5)
            self.assertEqual(len(expected['tasks']), 1650)
            conn.execute('ROLLBACK TO SAVEPOINT original_five_member_batch')
            self.assertEqual(self.snapshot(conn)['tasks'], [])
        times = []
        for member in range(1, 6):
            started = perf_counter()
            result = self.plan(limit=5, kinds=KINDS)
            times.append(perf_counter() - started)
            self.assertEqual(result['members_admitted_this_call'], 1)
            self.assertEqual(result['planned_members'], member)
            self.assertEqual(result['next_selection_order'], member + 1)
            self.assertEqual(result['inserted_tasks'], 330)
            self.assertFalse(result['plan_complete'])
        with self.f.admin() as conn:
            actual = self.snapshot(conn)
            self.assertEqual(actual, expected)
            sealed = conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_plan_manifests_v2 WHERE run_id=%s', (self.run,)).fetchone()['n']
            self.assertEqual(sealed, 0)
        self.assertLess(max(times), 5)
        QUALIFICATION['five_member_equivalence'] = {
            'baseline_seconds':baseline_seconds, 'successor_call_seconds':times,
            'task_count':len(actual['tasks']), 'definition_hash_count':len(actual['units']),
            'exact_task_definition_plan_unit_coverage_cursor_equality':True,
            'snapshot_sha256':sha256(json.dumps(actual, sort_keys=True, separators=(',', ':')).encode()).hexdigest()}

    def test_mid_member_definition_conflict_rolls_back_new_tasks_and_cursor(self):
        member = planner.COHORT['members'][0]
        with self.f.admin() as conn:
            task_id = conn.execute(f'SELECT {self.f.schema}.backfill_plan_task_id_v2(%s,%s) id',
                (self.run, member['member_id'] + ':D01:2025-09-10')).fetchone()['id']
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_tasks_v2(id,run_id,family,provider,kind,scope)
                VALUES(%s,%s,'REF01','Alpaca','alpaca_reference',%s)''',
                (task_id, self.run, json.dumps({'member_ids':[member['member_id']], 'symbols':[member['symbol']]})))
            before = self.snapshot(conn)
        result = self.f.rpc('backfill_plan_next', {'run_id':self.run, 'member_limit':5, 'supported_kinds':KINDS}, actor='worker')
        self.assertFalse(result['ok'])
        with self.f.admin() as conn:
            self.assertEqual(self.snapshot(conn), before)
        QUALIFICATION['mid_member_conflict'] = 'Prior immutable task retained; all new admission and cursor writes rolled back.'

    def test_last_member_transitions_and_existing_five_session_breadth_bound_is_unchanged(self):
        # This isolated fixture establishes the phase boundary without claiming
        # that the preceding2999 members or the full plan are already complete.
        with self.f.admin() as conn:
            conn.execute(f'UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=%s WHERE id=%s',
                (json.dumps({'planner_version':'fixed3000-plan-v2.1', 'planner_phase':'MEMBERS',
                             'planner_next_selection_order':3000, 'planner_next_breadth_index':0,
                             'planner_expected_static_count':0}), self.run))
        last = self.plan(limit=100, kinds=KINDS)
        self.assertEqual(last['members_admitted_this_call'], 1)
        self.assertEqual(last['next_selection_order'], 3001)
        self.assertEqual(last['phase'], 'BREADTH')
        breadth = self.plan(limit=5, kinds=KINDS)
        self.assertEqual(breadth['breadth_sessions'], 5)
        self.assertFalse(breadth['plan_complete'])
        with self.f.admin() as conn:
            rows = conn.execute(f'''SELECT scope->'representative_security' representatives
                FROM {self.f.schema}.backfill_tasks_v2 WHERE run_id=%s AND family='CTX06' ORDER BY id''',
                (self.run,)).fetchall()
            self.assertEqual(len(rows), 5)
            self.assertTrue(all(len(row['representatives']) == 3000 for row in rows))
        QUALIFICATION['breadth_boundary'] = 'One last complete member; subsequent existing call still admits five full-cohort breadth sessions.'

    def test_permissions_deadlines_outer_auth_input_validation_and_apply_once_are_unchanged(self):
        with self.f.admin() as conn:
            self.assertEqual(conn.execute("SELECT to_jsonb(p)-'prosrc' metadata FROM pg_proc p WHERE oid=%s::regprocedure",
                (self.f.schema + '.backfill_plan_next_v2(jsonb)',)).fetchone()['metadata'], self.planner_metadata)
            self.assertEqual(conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (self.f.schema + '.rpc_dispatch(text,jsonb)',)).fetchone()['d'], self.outer_auth_after_planner)
            for role in (self.f.gateway, self.f.outsider):
                self.assertFalse(conn.execute("SELECT has_function_privilege(%s,%s,'EXECUTE') allowed",
                    (role, self.f.schema + '.backfill_plan_next_v2(jsonb)')).fetchone()['allowed'])
        with self.assertRaises(self.f.psycopg.Error) as denied:
            self.f.rpc('backfill_plan_next', {'run_id':self.run}, actor='api')
        self.assertEqual(denied.exception.sqlstate, 'PT403')
        invalid = self.f.rpc('backfill_plan_next',
            {'run_id':self.run, 'member_limit':'not-an-integer', 'supported_kinds':KINDS}, actor='worker')
        self.assertFalse(invalid['ok'])
        self.assertEqual(invalid['error']['code'], 'conflict')
        with self.assertRaises(self.f.psycopg.Error), self.f.admin() as conn:
            conn.execute(self.batch_repair)
        with self.f.admin() as conn:
            self.assertEqual(conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (self.f.schema + '.backfill_plan_next_v2(jsonb)',)).fetchone()['d'], self.repaired_planner)


if __name__ == '__main__':
    unittest.main()
