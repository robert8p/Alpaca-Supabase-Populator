"""The existing scheduled maintainer gets a bounded turn under worker load."""
import concurrent.futures
import os
from pathlib import Path
import threading
import time
import unittest

import test_backfill_retained_s02_v2 as retained

ROOT = Path(__file__).resolve().parents[2]
LOCK = 706314020261028


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'),
                     'Explicit disposable PostgreSQL required')
class MaintenanceFairnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        retained.RetainedS02Tests.setUpClass.__func__(cls)
        f = cls.fixture('runTest')
        with f.admin() as conn:
            cls.original = conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (f.schema + '.backfill_maintain_v2(integer)',)).fetchone()['d']

    rewrite = classmethod(retained.RetainedS02Tests.rewrite.__func__)
    source_page = retained.RetainedS02Tests.source_page
    record = staticmethod(retained.RetainedS02Tests.record)

    def setUp(self):
        retained.RetainedS02Tests.setUp(self)
        with self.f.admin() as conn:
            conn.execute(self.original)

    def apply(self):
        with self.f.admin() as conn:
            conn.execute(self.rewrite((ROOT/'sql/astra_backfill_maintenance_fairness_v2.sql').read_text())
                         .replace('fixed3000-20250901-20260731-v1-20261030', self.run))

    def metadata(self, conn):
        return dict(conn.execute('SELECT proowner,proacl,prosecdef,proconfig FROM pg_proc WHERE oid=%s::regprocedure',
            (self.f.schema + '.backfill_maintain_v2(integer)',)).fetchone())

    def test_busy_worker_releases_and_same_monitor_call_admits_durable_successor(self):
        self.source_page(1, [self.record()])
        with self.f.admin() as blocker, self.f.admin() as monitor:
            blocker.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK,))
            start = time.monotonic()
            before = monitor.execute(f'SELECT {self.f.schema}.backfill_maintain_v2(1) v').fetchone()['v']
            self.assertEqual(before['state'], 'BUSY')
            self.assertLess(time.monotonic() - start, 0.5)
            monitor.commit()
            blocker.commit()
        self.apply()
        started = threading.Event()
        holder = {}
        def maintain():
            with self.f.admin() as conn:
                holder['pid'] = conn.execute('SELECT pg_backend_pid() pid').fetchone()['pid']
                started.set()
                return conn.execute(f'SELECT {self.f.schema}.backfill_maintain_v2(1) v').fetchone()['v']
        with self.f.admin() as blocker, concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            blocker.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK,))
            future = pool.submit(maintain)
            self.assertTrue(started.wait(2))
            waiting = False
            for _ in range(50):
                waiting = blocker.execute("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=%s AND locktype='advisory' AND NOT granted) v",
                                          (holder['pid'],)).fetchone()['v']
                if waiting:
                    break
                time.sleep(0.01)
            self.assertTrue(waiting, 'Maintainer should queue behind the existing worker lock')
            blocker.commit()
            result = future.result(timeout=4)
            self.assertEqual(result['state'], 'OBSERVED')
        with self.f.admin() as conn:
            self.assertEqual(conn.execute(f"SELECT count(*) n FROM {self.f.schema}.backfill_tasks_v2 WHERE run_id=%s AND kind='retained_massive_archive'",
                                          (self.run,)).fetchone()['n'], 1)

    def test_continuously_busy_worker_returns_bounded_busy_without_seed_writes(self):
        self.source_page(1, [self.record()]); self.apply()
        with self.f.admin() as blocker, self.f.admin() as monitor:
            blocker.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK,))
            start = time.monotonic()
            value = monitor.execute(f'SELECT {self.f.schema}.backfill_maintain_v2(1) v').fetchone()['v']
            elapsed = time.monotonic() - start
            self.assertEqual(value, {'state': 'BUSY', 'reason': 'BOUNDED_WORKER_LOCK_WAIT_EXHAUSTED'})
            self.assertGreaterEqual(elapsed, 1.7); self.assertLess(elapsed, 3.5)
            self.assertEqual(monitor.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_s02_seed_cursor_v2 WHERE run_id=%s',
                                            (self.run,)).fetchone()['n'], 0)

    def test_existing_owner_permissions_and_reentrant_gateway_lock_preserved(self):
        with self.f.admin() as conn:
            before = self.metadata(conn)
            progress = conn.execute(f'SELECT last_progress_at,pages_committed,records_committed,requests_reserved FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s',
                                    (self.run,)).fetchone()
        self.apply()
        with self.f.admin() as conn:
            self.assertEqual(self.metadata(conn), before)
            after = conn.execute(f'SELECT last_progress_at,pages_committed,records_committed,requests_reserved FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s',
                                 (self.run,)).fetchone()
            self.assertEqual(after, progress)
            conn.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK,))
            self.assertEqual(conn.execute(f'SELECT {self.f.schema}.backfill_maintain_v2(1) v').fetchone()['v']['state'], 'OBSERVED')
        with self.assertRaises(self.f.psycopg.Error):
            self.apply()


if __name__ == '__main__':
    unittest.main()
