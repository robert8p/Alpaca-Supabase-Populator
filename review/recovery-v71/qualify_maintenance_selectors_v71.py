"""Exercise the fixed read-only selector probe in disposable PostgreSQL."""
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import monotonic
import unittest

HERE = Path(__file__).resolve().parent
STAGED = Path('/tmp/replacement-claim-capability-staged-v71')
sys.path[:0] = [str(STAGED / 'tests/ingestion'), str(STAGED)]
import test_backfill_claim_capability_filter_v2 as base

SQL = HERE / 'maintenance_selectors_readonly_v71.sql'
DERIVATION = json.loads((HERE / 'maintenance_selector_derivation_v71.json').read_text())
MARKER = 'ASTRA_MAINTENANCE_SELECTORS_V71:'
RESULT = {}


class Qualification(base.CapabilityFilterPostgreSQLTests):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        # The focused existing fixture omits the legacy monitor. Install its
        # retained definition for the source guard only; it is never invoked.
        f = cls.fixture('runTest')
        monitor = next(x for x in json.loads((HERE/'live_cron_functions_1331.json').read_text())
                       if x['proname']=='monitor_tick_v1')
        with f.admin() as conn:
            conn.execute(monitor['definition'].replace('astra_ingestion_v1',f.schema))

    def source(self):
        sql = SQL.read_text().replace('astra_ingestion_v1', self.f.schema).replace(base.LIVE_RUN, self.run)
        with self.f.admin() as conn:
            for signature, live_hash in DERIVATION['source_pins'].items():
                local_definition = conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                    (self.f.schema + '.' + signature,)).fetchone()['d']
                sql = sql.replace(live_hash, base.digest(local_definition))
        return sql

    def test_source_drift_fails_closed(self):
        sql = self.source().replace(base.digest(self.after), '0' * 64)
        with self.f.admin() as conn:
            with self.assertRaises(self.f.psycopg.Error) as caught:
                conn.execute(sql)
            self.assertEqual(caught.exception.sqlstate, 'P0001')
            self.assertIn('source changed', caught.exception.diag.message_primary)
            self.assertFalse(caught.exception.diag.message_primary.startswith(MARKER))
            conn.rollback()
        RESULT['source_drift_rejected'] = True

    def test_missing_readonly_fails_closed(self):
        sql = self.source().replace('BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;',
            'BEGIN ISOLATION LEVEL REPEATABLE READ READ WRITE;').replace('SET LOCAL transaction_read_only=on;',
            'SET LOCAL transaction_read_only=off;')
        with self.f.admin() as conn:
            with self.assertRaises(self.f.psycopg.Error) as caught:
                conn.execute(sql)
            self.assertIn('explicit bounded read-only', caught.exception.diag.message_primary)
            self.assertFalse(caught.exception.diag.message_primary.startswith(MARKER))
            conn.rollback()
        RESULT['read_only_required'] = True

    def test_real_selectors_run_without_writes_or_lock(self):
        self.task()
        claim = self.claim()
        self.call('backfill_reserve', {'claim':self.fence(claim)})
        self.call('backfill_commit', self.page(claim))
        sql = self.source()
        with self.f.admin() as conn:
            before = self.snapshot(conn)
            before_settings = conn.execute("SELECT current_setting('transaction_read_only') ro,current_setting('transaction_isolation') iso,current_setting('statement_timeout') st,current_setting('lock_timeout') lt").fetchone()
            conn.commit()
            started = monotonic()
            with self.assertRaises(self.f.psycopg.Error) as caught:
                conn.execute(sql)
            elapsed = monotonic()-started
            self.assertEqual(caught.exception.sqlstate, 'P0001')
            message = caught.exception.diag.message_primary
            self.assertTrue(message.startswith(MARKER), message[:200])
            result = json.loads(message[len(MARKER):])
            conn.rollback()
            self.assertEqual(before_settings, conn.execute("SELECT current_setting('transaction_read_only') ro,current_setting('transaction_isolation') iso,current_setting('statement_timeout') st,current_setting('lock_timeout') lt").fetchone())
            self.assertEqual(before, self.snapshot(conn))
            self.assertEqual(conn.execute("SELECT count(*) n FROM pg_locks WHERE pid=pg_backend_pid() AND locktype='advisory'").fetchone()['n'], 0)
        self.assertTrue(result['complete'])
        self.assertEqual(result['selector_count'],10)
        self.assertEqual(result['transaction_read_only'],'on')
        self.assertEqual(result['transaction_isolation'],'repeatable read')
        self.assertEqual([r['component'] for r in result['results']],DERIVATION['component_names'])
        self.assertFalse(result['maintenance_functions_invoked'])
        self.assertFalse(result['advisory_lock_acquired'])
        self.assertFalse(result['raw_page_bodies_returned'])
        self.assertLess(elapsed,8)
        self.assertLess(len(message.encode()),125000)
        missing = next(x for x in result['results'] if x['component']=='MISSING_READBACK')
        self.assertEqual(missing['plan'][0]['Plan']['Actual Rows'],1)
        self.assertNotIn('asset-apple',message)
        self.assertNotIn('fixture-request',message)
        RESULT['probe']={'passed':True,'selectors':10,'elapsed_seconds':elapsed,
            'real_committed_unread_page_selected':True,'application_tables_unchanged':True,
            'settings_restored_after_rollback':True,'no_advisory_lock':True,
            'no_returned_page_body_or_request_id':True,'result_bytes':len(message.encode())}
        (HERE/'maintenance_selectors_synthetic_result_v71.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    started=monotonic()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Qualification(name) for name in [
        'test_source_drift_fails_closed','test_missing_readonly_fails_closed','test_real_selectors_run_without_writes_or_lock']))
    RESULT.update(schema='astra.maintenance-selector-qualification/1',passed=result.wasSuccessful(),
        tests=result.testsRun,errors=len(result.errors),failures=len(result.failures),skipped=len(result.skipped),
        elapsed_seconds=monotonic()-started,production_calls=0,sql_sha256=sha256(SQL.read_bytes()).hexdigest(),
        test_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        fixture_adaptation='Only schema/run identifiers and live source hashes are mapped to corresponding local fixture definitions.')
    RESULT['initial_fixture_correction']='Initial run had three setup errors because the existing focused fixture omits monitor_tick_v1. The retained monitor definition is now created in the disposable schema for its source guard only, never invoked; initial receipt is preserved.'
    path=HERE/'maintenance_selectors_qualification_v71.json'
    path.write_text(json.dumps(RESULT,indent=2)+'\n')
    print(json.dumps({'passed':result.wasSuccessful(),'receipt':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
