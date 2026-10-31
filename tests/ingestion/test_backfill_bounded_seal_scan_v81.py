"""Focused real-PG risks of the bounded SEAL algorithm, with retained validators.

All task/coverage data are synthetic. Existing admitted schema guards remain in
force; selected fixture insertions temporarily suppress only the snapshot trigger
to model preexisting or missed snapshots. No provider or production call occurs.
"""
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path
import re
import unittest

import test_backfill_planner_v2 as planner
import test_rpc_defer_lock_abort_retry_v77 as current
import test_backfill_seal_dynamic_exclusions_v78 as prior
from astra_ingestion.backfill_worker_v2 import BackfillWorker

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = 'review/recovery-v81/bounded-seal-scan/candidate_archive_v81.json'
FORWARD = 'sql/astra_backfill_bounded_seal_scan_v81.sql'
RESTORE = 'sql/astra_backfill_bounded_seal_scan_restore_v81.sql'
KEY = 'planner_seal_snapshot_scan_v81'
RESULT = {'production_calls': 0, 'provider_calls': 0, 'http_used': False,
          'fixture_semantics': 'Synthetic workflows with real retained scope, snapshot, count/hash, coverage and map validators',
          'cases': {}}


def archive():
    value = json.loads((ROOT / ARCHIVE).read_text())
    row = value['functions'][0]
    assert sha256(row['original_definition'].encode()).hexdigest() == row['source_sha256']
    assert sha256(row['candidate_definition'].encode()).hexdigest() == row['candidate_source_sha256']
    return value


def bind_literal(sql, name, value):
    literal = "'" + json.dumps(value, separators=(',', ':')).replace("'", "''") + "'::jsonb;"
    sql, count = re.subn(name + r" jsonb:='(?:''|[^'])*'::jsonb;", lambda _: name + ' jsonb:=' + literal, sql, count=1)
    assert count == 1, name
    return sql


class BoundedSealSourceTests(unittest.TestCase):
    def test_exact_one_branch_inverse_and_original_final_checks(self):
        value = archive(); row = value['functions'][0]
        self.assertEqual(len(value['functions']), 1)
        self.assertEqual(row['candidate_definition'].replace(value['new_branch'], value['old_branch'], 1), row['original_definition'])
        self.assertEqual(row['candidate_definition'].count('astra_ingestion_v1.backfill_plan_snapshot_v2(r.id,500)'), 1)
        old_suffix = row['original_definition'].split(value['old_branch'], 1)[1]
        self.assertEqual(row['candidate_definition'].split(value['new_branch'], 1)[1], old_suffix)
        self.assertEqual(len(value['protected_function_pins']), 17)
        self.assertEqual(len(value['trigger_pins']), 5)
        for name, proof in value['files'].items():
            raw = (ROOT / name).read_bytes()
            self.assertEqual(sha256(raw).hexdigest(), proof['sha256']); self.assertEqual(len(raw), proof['bytes'])


class BoundedSealPostgreSQLTests(unittest.TestCase):
    rewrite = classmethod(current.DeferPostgreSQLTests.rewrite.__func__)
    full_query = staticmethod(current.DeferPostgreSQLTests.full_query)
    adapt_definition = classmethod(prior.SealPostgreSQLTests.adapt_definition.__func__)
    normalized = prior.SealPostgreSQLTests.normalized
    function_rows = prior.SealPostgreSQLTests.function_rows
    execute_migration = prior.SealPostgreSQLTests.execute_migration
    metadata = prior.SealPostgreSQLTests.metadata
    set_metadata = prior.SealPostgreSQLTests.set_metadata
    rows = prior.SealPostgreSQLTests.rows
    plan = prior.SealPostgreSQLTests.plan
    dynamic_identity = prior.SealPostgreSQLTests.dynamic_identity
    manifest_arguments = prior.SealPostgreSQLTests.manifest_arguments
    seal_direct = prior.SealPostgreSQLTests.seal_direct
    seed_complete_static_workflows = prior.SealPostgreSQLTests.seed_complete_static_workflows

    @classmethod
    def setUpClass(cls):
        current.DeferPostgreSQLTests.setUpClass.__func__(cls)
        cls.candidate = archive()
        with cls.fixture('runTest').admin() as conn:
            RESULT['postgresql_version'] = conn.execute('SHOW server_version').fetchone()['server_version']

    def setUp(self):
        planner.BackfillPlannerTests.setUp(self)
        self.install_metadata = {'implementation_owner': prior.OWNER, 'implementation_lease_until': '2099-01-01T00:00:00Z',
            'implementation_reporting_policy': {'mode': 'DOT_CONSOLIDATED_CHECKPOINTS_ONLY'},
            'planner_phase': 'SEAL', 'planning_complete': False, 'planner_next_selection_order': 3001,
            'planner_next_breadth_index': 230, 'planner_expected_static_count': 979516,
            'planner_preexisting_static_count': 0, 'planner_version': 'fixed3000-plan-v2.1'}
        with self.f.admin() as conn:
            for row in prior.archive()['functions']:
                conn.execute(self.adapt_definition(row['candidate_definition']))
            conn.execute(self.adapt_definition(self.candidate['functions'][0]['original_definition']))
            conn.execute(f'UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=%s WHERE id=%s', (json.dumps(self.install_metadata), self.run))
        self.forward, self.restore = self.bound_migrations()

    def bound_migrations(self):
        actual = {r['signature']: r for r in self.function_rows()}; before, after, normalized = [], [], {}
        changed = self.candidate['functions'][0]
        for pin in self.candidate['protected_function_pins']:
            row = actual[pin['signature']]
            normalized[pin['signature']] = sha256(self.normalized(row['definition']).encode()).hexdigest()
            self.assertEqual(normalized[pin['signature']], pin['source_sha256'], pin['signature'])
            local = {'signature': self.adapt_definition(pin['signature']), 'oid': row['oid'],
                     'source_sha256': sha256(row['definition'].encode()).hexdigest(), 'metadata_sha256': row['metadata_sha256']}
            before.append(local); revised = dict(local)
            if pin['signature'] == changed['signature']:
                revised['source_sha256'] = sha256(self.adapt_definition(changed['candidate_definition']).encode()).hexdigest()
            after.append(revised)
        RESULT['normalized_guard_dependency_sources'] = normalized
        with self.f.admin() as conn:
            keys = [dict(r) for r in conn.execute("""SELECT c.oid::text relation_oid,c.relname relation_name,
                i.indexrelid::text index_oid,ic.relname index_name,
                encode(sha256(convert_to(pg_get_indexdef(i.indexrelid),'UTF8')),'hex') index_definition_sha256,
                a.attname attribute,a.atttypid::text type_oid,a.atttypmod typmod,a.attcollation::text collation_oid
                FROM pg_class c JOIN pg_index i ON i.indrelid=c.oid JOIN pg_class ic ON ic.oid=i.indexrelid
                JOIN pg_attribute a ON a.attrelid=c.oid AND a.attnum=i.indkey[0]
                WHERE c.relnamespace=%s::regnamespace AND c.relname IN('backfill_tasks_v2','backfill_plan_units_v2')
                AND i.indisprimary ORDER BY c.relname""", (self.f.schema,)).fetchall()]
            triggers = []
            for pin in self.candidate['trigger_pins']:
                table = self.adapt_definition(pin['table_name'])
                row = conn.execute("""SELECT t.oid::text trigger_oid,t.tgrelid::text relation_oid,t.tgfoid::text function_oid,
                    t.tgname trigger_name,t.tgenabled,t.tgtype,t.tgisinternal,pg_get_triggerdef(t.oid,true) definition,
                    encode(sha256(convert_to(to_jsonb(t)::text,'UTF8')),'hex') full_trigger_metadata_sha256
                    FROM pg_trigger t WHERE t.tgrelid=%s::regclass AND t.tgname=%s""", (table, pin['trigger_name'])).fetchone()
                self.assertIsNotNone(row); self.assertEqual(row['tgenabled'], 'O')
                triggers.append(dict(row, table_name=table, found=True))
        self.assertEqual(len(keys), 2); self.assertEqual(len(triggers), 5)
        def prepare(path, b, a):
            sql = self.adapt_definition((ROOT / path).read_text())
            guard_row = "WHERE id='" + prior.RUN + "' FOR UPDATE"
            self.assertEqual(sql.count(guard_row), 1)
            sql = sql.replace(guard_row, "WHERE id='" + self.run + "' FOR UPDATE", 1)
            for label, value in [('before_pins', b), ('after_pins', a), ('primary_key_pins', keys), ('trigger_pins', triggers)]:
                sql = bind_literal(sql, label, value)
            return sql
        return prepare(FORWARD, before, after), prepare(RESTORE, after, before)

    def begin_scan(self, expected=0):
        self.execute_migration(self.forward)
        metadata = self.metadata(); metadata['planner_expected_static_count'] = expected; self.set_metadata(metadata)

    def scope(self, **extra):
        return {'symbols': [planner.COHORT['members'][0]['symbol']], 'member_ids': [planner.COHORT['members'][0]['member_id']],
                'target_start': '2025-09-01', 'target_end': '2026-07-31', 'market_timezone': 'America/New_York', **extra}

    def insert(self, ids, *, kind='alpaca_reference', scope=None, run=None, snapshot=True, provider='Alpaca'):
        with self.f.admin() as conn:
            if not snapshot:
                conn.execute(f'ALTER TABLE {self.f.schema}.backfill_tasks_v2 DISABLE TRIGGER backfill_static_plan_snapshot_v2')
            with conn.cursor() as cur:
                cur.executemany(f"INSERT INTO {self.f.schema}.backfill_tasks_v2(id,run_id,family,provider,kind,scope,attempts,requests_reserved,records_committed) VALUES(%s,%s,'REF01',%s,%s,%s,3,2,7)",
                                [(key, run or self.run, provider, kind, json.dumps(scope or self.scope())) for key in ids])
            if not snapshot:
                conn.execute(f'ALTER TABLE {self.f.schema}.backfill_tasks_v2 ENABLE TRIGGER backfill_static_plan_snapshot_v2')

    def scan_to_end(self, *, first=None):
        results = [] if first is None else [first]
        for _ in range(30):
            if results and results[-1].get('scan_complete') is True:
                break
            value = self.plan(); results.append(value)
            self.assertIs(value['plan_complete'], False)
            self.assertLessEqual(value['examined_ids_this_call'], 500)
            self.assertNotIn('upper_id', value); self.assertNotIn('last_examined_id', value)
        else:
            self.fail('Synthetic bounded fixture did not finish within its concrete small page bound')
        self.assertEqual(results[-1]['state'], 'SEAL_SNAPSHOT_SCAN_COMPLETE_CHECKS_PENDING')
        return results

    def unchanged_acquisition(self):
        with self.f.admin() as conn:
            return conn.execute(f"SELECT to_jsonb(r)-'metadata' row FROM {self.f.schema}.backfill_runs_v2 r WHERE id=%s", (self.run,)).fetchone()['row']

    def unit_ids(self):
        with self.f.admin() as conn:
            return [r['task_id'] for r in conn.execute(f'SELECT task_id FROM {self.f.schema}.backfill_plan_units_v2 WHERE run_id=%s ORDER BY task_id', (self.run,)).fetchall()]

    def test_01_global_pages_exclusions_foreign_suppression_and_deleted_upper(self):
        self.begin_scan()
        matched = ['10000000-matched-' + str(i).zfill(4) for i in range(510)]
        excluded = ['20000000-excluded-' + str(i).zfill(4) for i in range(30)]
        eligible = ['00000000'] + ['30000000-eligible-' + str(i).zfill(4) for i in range(25)]
        self.insert(matched); self.insert(excluded, scope=self.scope(identity_refresh_of=None), snapshot=False)
        self.insert(eligible, scope=self.scope(plan_static=False), snapshot=False)
        foreign = self.run + '-foreign'
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET status='PAUSED' WHERE id=%s", (self.run,))
            conn.execute(f"""INSERT INTO {self.f.schema}.backfill_runs_v2(id,instruction_sha256,cohort_sha256,cohort_manifest_sha256,cohort_ref,scope,status)
                SELECT %s,instruction_sha256,cohort_sha256,cohort_manifest_sha256,cohort_ref,scope,'ACTIVE' FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s""", (foreign, self.run))
            conn.execute(f"""INSERT INTO {self.f.schema}.backfill_members_v2(run_id,member_id,selection_order,anchor_ticker,anchor)
                SELECT %s,member_id,selection_order,anchor_ticker,anchor FROM {self.f.schema}.backfill_members_v2 WHERE run_id=%s""", (foreign, self.run))
        self.insert(['25000000-foreign-' + str(i).zfill(4) for i in range(20)], run=foreign, snapshot=False)
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET status='PAUSED' WHERE id=%s", (foreign,))
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET status='ACTIVE' WHERE id=%s", (self.run,))
        victim = '31000000-global-unit'; self.insert([victim], snapshot=False)
        with self.f.admin() as conn:
            conn.execute(f"""INSERT INTO {self.f.schema}.backfill_plan_units_v2(run_id,task_id,family,definition_sha256)
                SELECT %s,id,family,{self.f.schema}.backfill_task_definition_sha256_v2(t)
                FROM {self.f.schema}.backfill_tasks_v2 t WHERE id=%s""", (foreign, victim))
        upper = 'zzzzzzzz-v81-deleted-upper'; self.insert([upper], scope=self.scope(reuse_parent=False), snapshot=False)
        before = self.unchanged_acquisition(); first = self.plan()
        self.assertEqual(first['examined_ids_this_call'], 500); self.assertFalse(first['scan_complete'])
        self.assertEqual(self.metadata()[KEY]['upper_id'], upper)
        with self.f.admin() as conn:
            conn.execute(f'DELETE FROM {self.f.schema}.backfill_tasks_v2 WHERE id=%s', (upper,))
        pages = self.scan_to_end(first=first)
        progress = self.metadata()[KEY]
        self.assertNotEqual(progress['last_examined_id'], upper); self.assertTrue(progress['complete'])
        self.assertEqual(progress['snapshots_added'], len(eligible))
        self.assertEqual(set(self.unit_ids()), set(matched + eligible))
        self.assertEqual(self.unchanged_acquisition(), before)
        RESULT['cases']['global_pages'] = {'page_examined': [p['examined_ids_this_call'] for p in pages],
            'successful_snapshot_returns': len(eligible), 'foreign_unit_globally_suppressed': True,
            'false_null_keys_excluded': True, 'short_page_below_deleted_upper_finishes': True,
            'acquisition_fields_preserved': True}

    def test_02_enabled_insert_trigger_handles_behind_and_beyond_range(self):
        self.begin_scan(); count = self.seed_complete_static_workflows()
        metadata = self.metadata(); metadata['planner_expected_static_count'] = count + 2; self.set_metadata(metadata)
        first = self.plan(); self.assertFalse(first['scan_complete']); progress = self.metadata()[KEY]
        behind, beyond = '!!!!!!!!-v81-behind', progress['upper_id'] + '-v81-beyond'
        with self.f.admin() as conn:
            self.assertTrue(conn.execute('SELECT %s::text<%s::text AND %s::text>%s::text ok', (behind, progress['last_examined_id'], beyond, progress['upper_id'])).fetchone()['ok'])
        self.insert([behind, beyond]); self.assertTrue({behind, beyond}.issubset(self.unit_ids()))
        self.scan_to_end(first=first)
        sealed = self.plan(); self.assertEqual(sealed['state'], 'FULL_PLAN_SEALED'); self.assertIs(sealed['plan_complete'], True)
        committed = self.rows(); self.execute_migration(self.restore); self.assertEqual(self.rows(), committed)
        RESULT['cases']['new_inserted_ids'] = {'behind_and_beyond_snapshotted_atomically': True,
            'real_final_sealer_passed': True, 'inverse_preserves_committed_manifest': True}

    def test_03_missed_inserts_behind_or_beyond_cannot_bypass_final_sealer(self):
        outcomes = []
        for index, position in enumerate(('behind', 'beyond')):
            if index:
                self.setUp()
            self.begin_scan(); self.seed_complete_static_workflows()
            first = self.plan(); self.assertFalse(first['scan_complete']); progress = self.metadata()[KEY]
            key = '!!!!!!!3-v81-missed' if position == 'behind' else progress['upper_id'] + '-v81-missed'
            self.insert([key], snapshot=False)
            self.scan_to_end(first=first); before = self.rows()
            result = self.f.rpc('backfill_plan_next', {'run_id': self.run, 'member_limit': 1, 'supported_kinds': planner.KINDS}, actor='worker')
            self.assertFalse(result['ok']); self.assertEqual(self.rows(), before)
            self.assertNotIn(key, self.unit_ids()); self.assertEqual(self.rows()['backfill_plan_manifests_v2'], [])
            outcomes.append(position)
        RESULT['cases']['missed_insert_final_check'] = {'separately_rejected': outcomes, 'completed_scan_retained_without_manifest': True}

    def test_04_real_snapshot_and_cursor_faults_rollback_then_lost_ack_resumes(self):
        self.begin_scan()
        ids = ['!!!!atomic-v81-' + str(i) for i in range(3)]; self.insert(ids, snapshot=False)
        before = self.rows()
        for point in ('snapshot', 'cursor'):
            with self.f.admin() as conn:
                if point == 'snapshot':
                    body = "IF NEW.task_id='" + ids[1] + "' THEN IF NOT EXISTS(SELECT 1 FROM " + self.f.schema + ".backfill_plan_units_v2 WHERE task_id='" + ids[0] + "') THEN RAISE EXCEPTION 'prior snapshot was not visible'; END IF; RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='v81 late snapshot fault'; END IF; RETURN NEW;"
                    table, event = 'backfill_plan_units_v2', 'INSERT'
                else:
                    body = "IF NEW.id='" + self.run + "' AND NEW.metadata ? '" + KEY + "' THEN IF NOT EXISTS(SELECT 1 FROM " + self.f.schema + ".backfill_plan_units_v2 WHERE task_id='" + ids[0] + "') THEN RAISE EXCEPTION 'snapshot missing before cursor fault'; END IF; RAISE EXCEPTION USING ERRCODE='AI005',MESSAGE='v81 late cursor fault'; END IF; RETURN NEW;"
                    table, event = 'backfill_runs_v2', 'UPDATE'
                conn.execute(f'CREATE FUNCTION {self.f.schema}.v81_injected_fault() RETURNS trigger LANGUAGE plpgsql AS $fault$ BEGIN {body} END $fault$')
                conn.execute(f'CREATE TRIGGER v81_injected_fault AFTER {event} ON {self.f.schema}.{table} FOR EACH ROW EXECUTE FUNCTION {self.f.schema}.v81_injected_fault()')
            try:
                with self.assertRaisesRegex(self.f.psycopg.Error, 'v81 late ' + point + ' fault'):
                    with self.f.admin() as conn:
                        conn.execute(f'SELECT {self.f.schema}.backfill_plan_next_v2(%s)', (json.dumps({'run_id': self.run, 'member_limit': 1, 'supported_kinds': planner.KINDS}),))
                self.assertEqual(self.rows(), before)
            finally:
                with self.f.admin() as conn:
                    conn.execute(f'DROP TRIGGER v81_injected_fault ON {self.f.schema}.{table}')
                    conn.execute(f'DROP FUNCTION {self.f.schema}.v81_injected_fault()')
        self.plan()  # Simulate a committed call whose acknowledgment is not consumed.
        acknowledged_later = self.metadata()[KEY]; units = self.unit_ids()
        self.assertEqual(acknowledged_later['snapshots_added'], len(ids)); self.assertTrue(set(ids).issubset(units))
        next_page = self.plan()
        self.assertEqual(next_page['snapshotted_this_call'], 0)
        self.assertEqual(self.unit_ids(), units)
        self.assertGreater(self.metadata()[KEY]['batches'], acknowledged_later['batches'])
        RESULT['cases']['atomicity_and_lost_ack'] = {'late_snapshot_and_cursor_faults_rolled_back': True,
                                                   'committed_cursor_reused_without_double_count': True}

    def test_05_malformed_or_stale_progress_fails_without_reset(self):
        self.begin_scan(); self.plan(); original = self.metadata(); progress = original[KEY]
        self.assertFalse(progress['complete'])
        variants = {'non_object': None, 'version': {**progress, 'version': 'other'},
            'cohort': {**progress, 'cohort_sha256': '0' * 64}, 'fence': {**progress, 'run_fence': 2},
            'source_premise': {**progress, 'basis_sha256': '0' * 64},
            'expected_count': {**progress, 'expected_static_count': 1},
            'missing_key': {k: v for k, v in progress.items() if k != 'batches'},
            'unknown_key': {**progress, 'extra': True}, 'null_counter': {**progress, 'examined_ids': None},
            'negative_counter': {**progress, 'snapshots_added': -1}, 'fractional_counter': {**progress, 'batches': 1.5},
            'null_lower_after_work': {**progress, 'last_examined_id': None},
            'lower_above_upper': {**progress, 'last_examined_id': progress['upper_id'] + '-after'},
            'impossible_completed_history': {**progress, 'complete': True, 'batches': 1000},
            'full_terminal_below_upper': {**progress, 'complete': True},
            'infinite_timestamp': {**progress, 'last_scan_at': 'infinity'}}
        for name, value in variants.items():
            with self.subTest(name=name):
                self.set_metadata({**original, KEY: value}); before = self.rows()
                outcome = self.f.rpc('backfill_plan_next', {'run_id': self.run, 'member_limit': 1, 'supported_kinds': planner.KINDS}, actor='worker')
                self.assertFalse(outcome['ok']); self.assertEqual(self.rows(), before)
        self.set_metadata(original)
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET status='PAUSED' WHERE id=%s", (self.run,))
        stopped = self.rows(); self.assertEqual(self.plan()['state'], 'PLANNING_PAUSED'); self.assertEqual(self.rows(), stopped)
        RESULT['cases']['malformed_progress'] = {'rejected': list(variants), 'no_silent_reset_or_business_mutation': True,
                                                 'paused_run_stops_before_scan': True}

    def test_06_final_page_survives_accounting_failure_and_worker_can_claim(self):
        # New trigger preconditions fail before a replacement, with rollback.
        original_functions = self.function_rows(); before = self.rows()
        with self.assertRaisesRegex(self.f.psycopg.Error, 'trigger definition, enabled state or full metadata changed'):
            with self.f.admin() as conn:
                conn.execute(f'ALTER TABLE {self.f.schema}.backfill_tasks_v2 DISABLE TRIGGER backfill_static_plan_snapshot_v2')
                conn.execute(self.forward)
        self.assertEqual(self.function_rows(), original_functions); self.assertEqual(self.rows(), before)
        self.begin_scan(); count = self.seed_complete_static_workflows()
        # Keep one legitimate task pending so the final scan work is observable.
        key = 'zzzzzzzz-v81-final-qualified'; self.insert([key], snapshot=False)
        metadata = self.metadata(); metadata['planner_expected_static_count'] = count; self.set_metadata(metadata)
        first = self.plan(); self.assertIs(first['plan_complete'], False)
        class Provider:
            def supported_kinds(self): return ()
        class Store:
            def __init__(self, response): self.response, self.calls = response, []
            def _call(self, operation, payload):
                self.calls.append(operation)
                if operation == 'backfill_plan_next': return self.response
                if operation == 'backfill_claim': return None
                raise AssertionError(operation)
        store = Store(first); worker = BackfillWorker(store, Provider(), planning_enabled=True)
        self.assertEqual(worker.run_once(), {'state': 'idle'})
        self.assertEqual(store.calls, ['backfill_plan_next', 'backfill_claim']); self.assertFalse(worker.plan_complete)
        self.scan_to_end(first=first); committed = self.rows()
        self.assertIn(key, self.unit_ids()); self.assertIs(self.metadata()[KEY]['complete'], True)
        outcome = self.f.rpc('backfill_plan_next', {'run_id': self.run, 'member_limit': 1, 'supported_kinds': planner.KINDS}, actor='worker')
        self.assertFalse(outcome['ok']); self.assertEqual(self.rows(), committed)
        # The exact original hash validation still rejects a wrong digest.
        with self.assertRaises(self.f.psycopg.Error): self.seal_direct(digest='0' * 64)
        self.assertEqual(self.rows(), committed)
        # Restore must preserve the committed scan and qualified final snapshot.
        self.execute_migration(self.restore); self.assertEqual(self.rows(), committed)
        self.assertEqual(self.function_rows(), original_functions)
        RESULT['cases']['final_page_and_worker'] = {'final_snapshot_survives_later_count_hash_failure': True,
            'actual_worker_claim_path_after_false_response': True, 'inverse_preserves_scan_and_snapshots': True,
            'disabled_trigger_installation_rejected': True}
