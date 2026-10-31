"""Qualify the passive gate capture in disposable PostgreSQL only."""
from hashlib import sha256
import json
from pathlib import Path
import sys
import threading
from time import monotonic
import unittest

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
STAGED = Path('/tmp/replacement-claim-capability-staged-v71')
sys.path[:0] = [str(STAGED / 'tests/ingestion'), str(STAGED)]
import test_backfill_claim_capability_filter_v2 as base

MARKER = 'ASTRA_GATE_LOCK_CAPTURE_V71:'
CAPTURE = HERE / 'capture_gate_lock_contention_readonly_v71.sql'
RESULT = {}
GATE = 706314020261028
SENTINEL = 'PRIVATE_FIXTURE_TOKEN_AND_PAYLOAD_MUST_NEVER_BE_RETURNED_7269c6'


class Qualification(base.CapabilityFilterPostgreSQLTests):
    def source(self):
        return CAPTURE.read_text().replace('astra_ingestion_v1', self.f.schema).replace(
            base.LIVE_AFTER, base.digest(self.after)).replace(base.LIVE_AUTH, base.digest(self.auth)).replace(base.LIVE_RUN, self.run)

    def test_live_holder_waiter_and_safe_bounded_result(self):
        with self.f.admin() as before:
            rows_before = self.snapshot(before)
        holder_ready = threading.Event()
        waiter_started = threading.Event()
        fixture = {}
        failures = []

        def holder():
            try:
                with self.f.admin() as conn:
                    fixture['holder_pid'] = conn.info.backend_pid
                    conn.execute("SELECT set_config('application_name',%s,true)", (SENTINEL,))
                    conn.execute('SELECT pg_advisory_xact_lock(%s)', (GATE,))
                    holder_ready.set()
                    # Keep a real transaction-owned lock while a known harmless
                    # query is active. Its SQL comment and app name must be hidden.
                    conn.execute('SELECT pg_sleep(6.8) /* ' + SENTINEL + ' */')
                    conn.rollback()
            except Exception as error:
                failures.append(type(error).__name__)
                holder_ready.set()

        def waiter():
            try:
                with self.f.admin() as conn:
                    fixture['waiter_pid'] = conn.info.backend_pid
                    conn.execute("SET LOCAL lock_timeout='3s'")
                    waiter_started.set()
                    started = monotonic()
                    try:
                        conn.execute('SELECT pg_advisory_xact_lock(%s)', (GATE,))
                        fixture['waiter_unexpectedly_acquired'] = True
                    except self.f.psycopg.Error as error:
                        fixture['waiter_sqlstate'] = error.sqlstate
                        fixture['waiter_elapsed_seconds'] = monotonic() - started
                        conn.rollback()
            except Exception as error:
                failures.append(type(error).__name__)
                waiter_started.set()

        holder_thread = threading.Thread(target=holder, daemon=True)
        waiter_thread = threading.Thread(target=waiter, daemon=True)
        holder_thread.start()
        self.assertTrue(holder_ready.wait(2))
        waiter_thread.start()
        self.assertTrue(waiter_started.wait(2))
        with self.f.admin() as conn:
            capture_pid = conn.info.backend_pid
            before_settings = conn.execute("SELECT current_setting('transaction_read_only') ro,current_setting('transaction_isolation') iso,current_setting('statement_timeout') statement,current_setting('lock_timeout') lock").fetchone()
            conn.commit()
            started = monotonic()
            with self.assertRaises(self.f.psycopg.Error) as captured:
                conn.execute(self.source())
            elapsed = monotonic() - started
            self.assertEqual(captured.exception.sqlstate, 'P0001')
            message = captured.exception.diag.message_primary
            self.assertTrue(message.startswith(MARKER))
            self.assertNotIn(SENTINEL, message)
            result = json.loads(message[len(MARKER):])
            conn.rollback()
            self.assertEqual(before_settings, conn.execute("SELECT current_setting('transaction_read_only') ro,current_setting('transaction_isolation') iso,current_setting('statement_timeout') statement,current_setting('lock_timeout') lock").fetchone())
        holder_thread.join(timeout=2)
        waiter_thread.join(timeout=2)
        self.assertFalse(holder_thread.is_alive())
        self.assertFalse(waiter_thread.is_alive())
        self.assertEqual(failures, [])
        self.assertEqual(fixture.get('waiter_sqlstate'), '55P03')
        self.assertFalse(fixture.get('waiter_unexpectedly_acquired', False))
        self.assertTrue(2.7 <= fixture['waiter_elapsed_seconds'] <= 4.0)
        self.assertEqual(result['transaction_read_only'], 'on')
        self.assertEqual(result['transaction_isolation'], 'repeatable read')
        self.assertEqual(result['sample_count'], 20)
        self.assertTrue(result['capture_complete'])
        self.assertFalse(result['output_limited'])
        self.assertFalse(result['raw_query_returned'])
        self.assertFalse(result['raw_headers_or_payload_returned'])
        self.assertTrue(5.5 <= elapsed < 8)
        simultaneous = []
        activity_fields = {'pid','backend_start','xact_start','query_start','state_change','state',
            'wait_event_type','wait_event','backend_type','query_id','application_is_postgrest',
            'session_is_authenticator','session_is_postgres','query_shape'}
        shapes = {'COMMIT','ROLLBACK','TRANSACTION_START','DDL','PUBLIC_INGESTION_RPC',
                  'PRIVATE_RPC_DISPATCH','DIRECT_ADVISORY_STATEMENT','OTHER_OR_REDACTED'}
        for sample in result['samples']:
            locks = sample['gate_locks']
            self.assertLessEqual(len(locks), 8)
            self.assertFalse(any(x['pid'] == capture_pid for x in locks))
            if (any(x['pid'] == fixture['holder_pid'] and x['granted'] for x in locks)
                and any(x['pid'] == fixture['waiter_pid'] and not x['granted']
                        and fixture['holder_pid'] in x['blockers'] for x in locks)):
                simultaneous.append(sample['sample'])
            for row in sample['related_activity']:
                self.assertEqual(set(row), activity_fields)
                self.assertIn(row['query_shape'], shapes)
        self.assertTrue(simultaneous)
        with self.f.admin() as after:
            self.assertEqual(rows_before, self.snapshot(after))
            self.assertEqual(after.execute("SELECT count(*) n FROM pg_locks WHERE locktype='advisory' AND database=(SELECT oid FROM pg_database WHERE datname=current_database()) AND classid::bigint=164451 AND objid::bigint=2353466532 AND objsubid=1").fetchone()['n'], 0)
        RESULT['capture'] = {'passed':True,'sample_count':20,'elapsed_seconds':elapsed,
            'matching_holder_waiter_samples':simultaneous,'waiter_sqlstate':fixture['waiter_sqlstate'],
            'waiter_lock_budget_seconds':3,'waiter_elapsed_seconds':fixture['waiter_elapsed_seconds'],
            'read_only_asserted':True,'repeatable_read_asserted':True,'source_pins_asserted':True,
            'query_and_application_name_sentinels_absent':True,'only_allowlisted_activity_fields':True,
            'capture_never_acquired_gate_lock':True,'data_tables_unchanged':True,
            'transaction_settings_restored_after_rollback':True,'locks_released_by_fixture':True,
            'result_bytes':len(message.encode()),'raw_capture_sha256':sha256(message.encode()).hexdigest()}
        # This synthetic result contains no token; retain it for independent
        # review without exporting the underlying SQL or application-name text.
        (HERE / 'gate_lock_capture_synthetic_result_v71.json').write_text(json.dumps(result, indent=2) + '\n')

    def test_changed_source_rejects_before_sampling(self):
        with self.f.admin() as conn:
            with self.assertRaises(self.f.psycopg.Error) as rejected:
                conn.execute(self.source().replace(base.digest(self.after), '0' * 64))
            self.assertEqual(rejected.exception.sqlstate, 'P0001')
            self.assertFalse(rejected.exception.diag.message_primary.startswith(MARKER))
            self.assertIn('source changed', rejected.exception.diag.message_primary)
            conn.rollback()
        RESULT['changed_source_rejects_before_sampling'] = True

    def test_missing_readonly_mode_rejects_before_sampling(self):
        sql = self.source().replace('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;',
            'BEGIN ISOLATION LEVEL REPEATABLE READ READ WRITE;').replace('SET LOCAL transaction_read_only=on;', 'SET LOCAL transaction_read_only=off;')
        with self.f.admin() as conn:
            with self.assertRaises(self.f.psycopg.Error) as rejected:
                conn.execute(sql)
            self.assertFalse(rejected.exception.diag.message_primary.startswith(MARKER))
            self.assertIn('explicit bounded read-only', rejected.exception.diag.message_primary)
            conn.rollback()
        RESULT['missing_readonly_rejects_before_sampling'] = True


if __name__ == '__main__':
    started = monotonic()
    suite = unittest.TestSuite(Qualification(name) for name in [
        'test_changed_source_rejects_before_sampling',
        'test_missing_readonly_mode_rejects_before_sampling',
        'test_live_holder_waiter_and_safe_bounded_result'])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    RESULT.update(schema='astra.gate-lock-readonly-qualification/1',passed=result.wasSuccessful(),
        tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),skipped=len(result.skipped),
        elapsed_seconds=monotonic()-started,production_calls=0,
        sql_sha256=sha256(CAPTURE.read_bytes()).hexdigest(),
        test_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    output = HERE / 'gate_lock_capture_qualification_v71.json'
    output.write_text(json.dumps(RESULT, indent=2) + '\n')
    print(json.dumps({'passed':result.wasSuccessful(),'receipt':str(output),
        'sha256':sha256(output.read_bytes()).hexdigest()}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
