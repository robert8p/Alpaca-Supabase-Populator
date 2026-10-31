"""Qualify the two-read post-install probe only in disposable PostgreSQL."""
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from time import monotonic
import unittest

HERE = Path(__file__).resolve().parent
STAGE = Path('/tmp/replacement-maintenance-index-staged-v72')
sys.path[:0] = [str(STAGE / 'tests/ingestion'), str(STAGE)]
import test_backfill_maintenance_task_indexes_v2 as indexes

SQL = HERE / 'maintenance_index_postinstall_selectors_readonly_v72.sql'
DERIVATION = json.loads((HERE / 'maintenance_index_postinstall_selector_derivation_v72.json').read_text())
BASELINE = (HERE / 'readback-transaction-race/baseline_maintain_v2.sql').read_text()
CANDIDATE = (HERE / 'readback-transaction-race/candidate_maintain_readback_transaction_v72.sql').read_text()
MARKER = 'ASTRA_MAINTENANCE_INDEX_POSTINSTALL_V72:'
RESULT = {'schema': 'astra.maintenance-index-postinstall-probe-qualification/1', 'production_calls': 0}


class Qualification(indexes.MaintenanceTaskIndexTests):
    def setUp(self):
        fixture = self.fixture('runTest')
        with fixture.admin() as conn:
            conn.execute(BASELINE.replace('astra_ingestion_v1', fixture.schema))
        super().setUp()
        self.apply_pair()
        with self.f.admin() as conn:
            conn.execute(CANDIDATE.replace('astra_ingestion_v1', self.f.schema))

    def source(self):
        sql = SQL.read_text().replace('astra_ingestion_v1', self.f.schema).replace(indexes.base.LIVE_RUN, self.run)
        with self.f.admin() as conn:
            for signature, expected in DERIVATION['source_pins'].items():
                actual = conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                    (self.f.schema + '.' + signature,)).fetchone()['d']
                sql = sql.replace(expected, sha256(actual.encode()).hexdigest())
        return sql

    def reject(self, sql, expected):
        with self.f.admin() as conn:
            with self.assertRaises(self.f.psycopg.Error) as caught:
                conn.execute(sql)
            self.assertEqual(caught.exception.sqlstate, 'P0001')
            self.assertIn(expected, caught.exception.diag.message_primary)
            self.assertFalse(caught.exception.diag.message_primary.startswith(MARKER))
            conn.rollback()

    def test_source_and_index_guards_reject_real_drift(self):
        sql = self.source()
        with self.f.admin() as conn:
            conn.execute(f"ALTER FUNCTION {self.f.schema}.backfill_maintain_v2(integer) SET statement_timeout='9s'")
        self.reject(sql, 'source changed')
        with self.f.admin() as conn:
            conn.execute(CANDIDATE.replace('astra_ingestion_v1', self.f.schema))
            conn.execute(f'DROP INDEX {self.f.schema}.backfill_tasks_minute_pending_id_v2')
        self.reject(sql, 'hash index is absent or differs')
        with self.f.admin() as conn:
            definition = DERIVATION['expected_index_definitions']['backfill_tasks_minute_pending_id_v2']
            conn.execute(definition.replace('astra_ingestion_v1', self.f.schema).replace('USING hash', 'USING btree'))
        self.reject(sql, 'hash index is absent or differs')
        RESULT['real_drift_rejections'] = ['changed maintain source', 'missing minute index', 'wrong same-name index method']

    def test_required_transaction_and_owner_bounds(self):
        original = self.source()
        variants = [
            original.replace('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;', 'BEGIN ISOLATION LEVEL REPEATABLE READ READ WRITE;').replace('SET LOCAL transaction_read_only=on;', 'SET LOCAL transaction_read_only=off;'),
            original.replace('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;', 'BEGIN ISOLATION LEVEL READ COMMITTED READ ONLY;').replace("SET LOCAL transaction_isolation='repeatable read';", "SET LOCAL transaction_isolation='read committed';"),
            original.replace("SET LOCAL statement_timeout='8s';", "SET LOCAL statement_timeout='9s';"),
            original.replace("SET LOCAL lock_timeout='3s';", "SET LOCAL lock_timeout='4s';"),
        ]
        for sql in variants:
            self.reject(sql, 'explicit bounded read-only repeatable-read')
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=jsonb_set(metadata,'{{implementation_lease_until}}','\"2000-01-01T00:00:00Z\"') WHERE id=%s", (self.run,))
        self.reject(original, 'run, owner, lease, fence or fixed cohort')
        RESULT['required_settings_and_owner'] = ['read-only', 'repeatable-read', '8s statement', '3s lock', 'unexpired owner lease']

    def test_exact_two_reads_preserve_data_catalog_and_settings(self):
        self.task()
        claim = self.claim()
        self.call('backfill_reserve', {'claim': self.fence(claim)})
        self.call('backfill_commit', self.page(claim))
        sql = self.source()
        with self.f.admin() as conn:
            before = self.snapshot(conn)
            before_functions = conn.execute('SELECT jsonb_agg(to_jsonb(p) ORDER BY oid) x FROM pg_proc p WHERE pronamespace=%s::regnamespace', (self.f.schema,)).fetchone()['x']
            before_indexes = self.index_rows(conn)
            before_settings = conn.execute("SELECT current_setting('transaction_read_only') ro,current_setting('transaction_isolation') iso,current_setting('statement_timeout') st,current_setting('lock_timeout') lt").fetchone()
            conn.commit()
            started = monotonic()
            with self.assertRaises(self.f.psycopg.Error) as caught:
                conn.execute(sql)
            elapsed = monotonic() - started
            self.assertEqual(caught.exception.sqlstate, 'P0001')
            message = caught.exception.diag.message_primary
            self.assertTrue(message.startswith(MARKER), message[:200])
            result = json.loads(message[len(MARKER):])
            conn.rollback()
            self.assertEqual(before, self.snapshot(conn))
            self.assertEqual(before_functions, conn.execute('SELECT jsonb_agg(to_jsonb(p) ORDER BY oid) x FROM pg_proc p WHERE pronamespace=%s::regnamespace', (self.f.schema,)).fetchone()['x'])
            self.assertEqual(before_indexes, self.index_rows(conn))
            self.assertEqual(before_settings, conn.execute("SELECT current_setting('transaction_read_only') ro,current_setting('transaction_isolation') iso,current_setting('statement_timeout') st,current_setting('lock_timeout') lt").fetchone())
            self.assertEqual(conn.execute("SELECT count(*) n FROM pg_locks WHERE pid=pg_backend_pid() AND locktype='advisory'").fetchone()['n'], 0)
        self.assertEqual([x['component'] for x in result['results']], ['BREADTH_PENDING', 'MINUTE_ACCOUNT_PENDING'])
        self.assertTrue(result['complete'])
        self.assertEqual(result['selector_count'], 2)
        self.assertEqual(result['source_pins_verified'], 5)
        self.assertEqual(result['exact_hash_indexes_verified'], 2)
        self.assertEqual(result['transaction_read_only'], 'on')
        self.assertEqual(result['transaction_isolation'], 'repeatable read')
        self.assertEqual(result['statement_timeout'], '8s')
        self.assertEqual(result['lock_timeout'], '3s')
        self.assertFalse(result['maintenance_functions_invoked'])
        self.assertFalse(result['advisory_lock_acquired'])
        self.assertFalse(result['raw_page_bodies_returned'])
        self.assertLess(elapsed, 8)
        self.assertLess(len(message.encode()), 65000)
        self.assertNotIn('asset-apple', message)
        self.assertNotIn('fixture-request', message)
        RESULT['probe'] = {'selectors': 2, 'elapsed_seconds': elapsed,
            'application_tables_functions_and_indexes_unchanged': True,
            'settings_restored': True, 'advisory_locks_absent_after_rollback': True,
            'real_reference_page_body_and_request_not_returned': True,
            'result_bytes': len(message.encode()),
            'limitation': 'The real committed reference page is ineligible for these two selectors; positive selector identity and hash plans are qualified separately in the existing index tests.'}
        (HERE / 'maintenance_index_postinstall_synthetic_result_v72.json').write_text(json.dumps(result, indent=2) + '\n')


if __name__ == '__main__':
    if os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL') != 'postgresql://postgres@127.0.0.1:55432/astra_ingestion_qualification':
        raise RuntimeError('This qualifier accepts only the explicit disposable loopback database')
    started = monotonic()
    names = ['test_source_and_index_guards_reject_real_drift', 'test_required_transaction_and_owner_bounds', 'test_exact_two_reads_preserve_data_catalog_and_settings']
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Qualification(name) for name in names))
    passed = result.wasSuccessful() and result.testsRun == 3 and not result.skipped
    RESULT.update(passed=passed, tests=result.testsRun, errors=len(result.errors), failures=len(result.failures),
        skipped=len(result.skipped), elapsed_seconds=monotonic() - started,
        sql_sha256=sha256(SQL.read_bytes()).hexdigest(), test_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        fixture_adaptation='Exact index forwards and race candidate installed only in disposable fixture; schema/run/source hashes map to corresponding local definitions. Read-only probe logic remains exact.')
    path = HERE / 'maintenance_index_postinstall_probe_qualification_v72.json'
    path.write_text(json.dumps(RESULT, indent=2) + '\n')
    print(json.dumps({'passed': passed, 'receipt': str(path), 'sha256': sha256(path.read_bytes()).hexdigest()}))
    raise SystemExit(0 if passed else 1)
