"""Real local PostgreSQL transaction-race regression; never production."""
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import threading
from time import monotonic, sleep
import unittest

HERE = Path(__file__).resolve().parent
STAGED = Path('/tmp/replacement-claim-capability-staged-v71')
sys.path[:0] = [str(STAGED / 'tests/ingestion'), str(STAGED)]
import test_backfill_claim_capability_filter_v2 as base

EXPECTED_LOCAL_URL = 'postgresql://postgres@127.0.0.1:55432/astra_ingestion_qualification'
BASELINE = (HERE / 'baseline_maintain_v2.sql').read_text()
CANDIDATE = (HERE / 'candidate_maintain_readback_transaction_v72.sql').read_text()
RECHECK = (HERE / 'unchanged_recheck_page_v2.sql').read_text()
FORWARD = (HERE / 'forward_readback_transaction_race_v72.sql').read_text()
MANIFEST = json.loads((HERE / 'derivation_v72.json').read_text())
OLD = MANIFEST['predicate_change']['before']
NEW = MANIFEST['predicate_change']['after']
LOCK = 706314020261028
REASON = 'Independent readback requires a subsequent transaction'
RESULT = {'schema': 'astra.readback-transaction-race-qualification/1',
          'production_calls': 0, 'activation_selected': False}


def digest(value):
    return sha256(value.encode()).hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'))


class SourceTests(unittest.TestCase):
    def test_exact_single_predicate_and_unchanged_verifier(self):
        self.assertEqual(digest(BASELINE), MANIFEST['baseline_sha256'])
        self.assertEqual(digest(CANDIDATE), MANIFEST['candidate_sha256'])
        self.assertEqual(digest(RECHECK), MANIFEST['unchanged_recheck_sha256'])
        self.assertEqual(BASELINE.count(OLD), 1)
        self.assertEqual(CANDIDATE.count(NEW), 1)
        self.assertEqual(CANDIDATE.replace(NEW, OLD), BASELINE)
        self.assertIn("IF p.committed_at>=transaction_timestamp() THEN RAISE EXCEPTION USING ERRCODE='AI005'", RECHECK)
        self.assertIn("a.action='READBACK_FAILURE'", CANDIDATE)
        self.assertIn('LIMIT GREATEST(1,LEAST(p_limit,8))', CANDIDATE)
        self.assertEqual(FORWARD.count('EXECUTE v_after;'), 1)
        self.assertIn('v_after_metadata IS DISTINCT FROM v_before_metadata', FORWARD)
        self.assertIn('v_other_after IS DISTINCT FROM v_other_before', FORWARD)
        self.assertNotRegex(FORWARD, r'(?im)^\s*(INSERT|UPDATE|DELETE|GRANT|REVOKE|ALTER|CREATE\s+(TABLE|INDEX|ROLE))\b')
        RESULT['source'] = {'one_predicate_only': True, 'exact_reverse_to_retained_baseline': True,
                            'recheck_guard_unchanged': True, 'no_telemetry_or_other_repair': True}


class PostgreSQLTests(base.CapabilityFilterPostgreSQLTests):
    def setUp(self):
        super().setUp()
        self.baseline = BASELINE.replace('astra_ingestion_v1', self.f.schema)
        self.candidate = CANDIDATE.replace('astra_ingestion_v1', self.f.schema)
        self.recheck = RECHECK.replace('astra_ingestion_v1', self.f.schema)
        with self.f.admin() as conn:
            conn.execute(self.baseline)
            conn.execute(self.recheck)
            self.local_metadata = self.metadata(conn)
            self.forward = FORWARD.replace('astra_ingestion_v1', self.f.schema).replace(base.LIVE_RUN, self.run)
            self.forward = self.forward.replace(canonical(MANIFEST['expected_maintain_metadata']), canonical(self.local_metadata))
            self.forward = self.forward.replace(MANIFEST['baseline_sha256'], digest(self.baseline))
            self.forward = self.forward.replace(MANIFEST['candidate_sha256'], digest(self.candidate))
            for signature, pinned in MANIFEST['function_pins'].items():
                local_source = conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                    (self.f.schema + '.' + signature,)).fetchone()['d']
                self.forward = self.forward.replace(pinned, digest(local_source))
            self.assertEqual(self.definition(conn, 'backfill_recheck_page_v2(text,integer)'), self.recheck)
            RESULT['local_postgresql_version'] = conn.execute('SHOW server_version').fetchone()['server_version']

    def definition(self, conn, signature='backfill_maintain_v2(integer)'):
        return conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
            (self.f.schema + '.' + signature,)).fetchone()['d']

    def metadata(self, conn):
        return conn.execute("SELECT to_jsonb(p)-'prosrc' m FROM pg_proc p WHERE oid=%s::regprocedure",
            (self.f.schema + '.backfill_maintain_v2(integer)',)).fetchone()['m']

    def snapshot_with_audit(self, conn):
        rows = self.snapshot(conn)
        rows['backfill_audit_v2'] = conn.execute(f'''SELECT count(*) n,encode(sha256(convert_to(
            COALESCE(string_agg(to_jsonb(x)::text,E'\n' ORDER BY to_jsonb(x)::text),''),'UTF8')),'hex') digest
            FROM {self.f.schema}.backfill_audit_v2 x''').fetchone()
        return rows

    def install(self, candidate=True):
        with self.f.admin() as conn:
            conn.execute(self.candidate if candidate else self.baseline)

    def maintain(self, limit=2):
        with self.f.admin() as conn:
            conn.execute(f'SET LOCAL ROLE {self.f.owner}')
            return conn.execute(f'SELECT {self.f.schema}.backfill_maintain_v2(%s) value', (limit,)).fetchone()['value']

    def news_task(self):
        task = self.task(kind='massive_news', family='N01', provider='Massive',
            scope={'symbols': ['AAPL'], 'member_ids': ['member-1'], 'start': '2025-09-01', 'end': '2026-07-31'})
        with self.f.admin() as conn:
            conn.execute(f'UPDATE {self.f.schema}.backfill_tasks_v2 SET generation=1,run_fence=1 WHERE id=%s', (task,))
        return task

    def insert_page(self, conn, task, page_no=0, *, committed_at=None):
        # Synthetic provider page only: no provider fetch, transport, or credential.
        rows = [{'id': f'{task}-{page_no}-{n}', 'title': 'Synthetic news regression',
                 'tickers': ['AAPL'], 'published_utc': '2025-09-02T12:00:00Z'} for n in range(100)]
        raw = canonical({'results': rows, 'status': 'OK'})
        request = canonical({'provider': 'Massive', 'method': 'GET', 'host': 'api.massive.com',
                             'path': '/v2/reference/news', 'params': {'ticker': 'AAPL'}})
        return conn.execute(f'''INSERT INTO {self.f.schema}.backfill_pages_v2
            (task_id,page_no,run_id,generation,run_fence,provider,request,http_status,request_id,
             fetched_at,committed_at,raw_body,body_sha256,records_sha256,record_count,source_bytes,adapter_version)
            VALUES(%s,%s,%s,1,1,'Massive',%s,200,'synthetic-readback-race',
             '2026-10-30T05:00:00Z',COALESCE(%s::timestamptz,clock_timestamp()),%s,%s,%s,100,%s,'synthetic-race-v72')
            RETURNING committed_at,body_sha256,record_count''',
            (task, page_no, self.run, request, committed_at, raw, digest(raw), digest(canonical(rows)), len(raw.encode()))).fetchone()

    def audits(self, conn, task):
        return conn.execute(f'''SELECT id,evidence,recorded_at FROM {self.f.schema}.backfill_audit_v2
            WHERE task_id=%s AND action='READBACK_FAILURE' ORDER BY id''', (task,)).fetchall()

    def race(self, candidate):
        self.install(candidate)
        task = self.news_task()
        started = threading.Event()
        observed = {}

        def monitor():
            with self.f.admin() as conn:
                conn.execute(f'SET LOCAL ROLE {self.f.owner}')
                observed.update(conn.execute("""SELECT pg_backend_pid() monitor_pid,transaction_timestamp() monitor_started,
                    current_setting('transaction_isolation') isolation""").fetchone())
                started.set()
                return conn.execute(f'SELECT {self.f.schema}.backfill_maintain_v2(2) value').fetchone()['value']

        with self.f.admin() as worker, ThreadPoolExecutor(max_workers=1) as pool:
            worker.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK,))
            observed['worker_pid'] = worker.execute('SELECT pg_backend_pid() pid').fetchone()['pid']
            future = pool.submit(monitor)
            try:
                self.assertTrue(started.wait(2), 'Monitor transaction did not start')
                deadline = monotonic() + 1
                queued = False
                while monotonic() < deadline:
                    queued = worker.execute("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=%s AND locktype='advisory' AND NOT granted) waiting",
                        (observed['monitor_pid'],)).fetchone()['waiting']
                    if queued:
                        break
                    sleep(0.005)
                self.assertTrue(queued, 'Monitor must actually wait behind the existing global gate')
                observed['page'] = self.insert_page(worker, task)
                self.assertGreater(observed['page']['committed_at'], observed['monitor_started'])
                worker.commit()
                answer = future.result(timeout=5)
            finally:
                worker.rollback()
        self.assertNotEqual(observed['worker_pid'], observed['monitor_pid'])
        self.assertEqual(observed['isolation'], 'read committed')
        observed['actual_advisory_wait_observed'] = True
        observed['first_call_result'] = answer
        with self.f.admin() as conn:
            observed['first_call_failures'] = self.audits(conn, task)
            observed['first_call_readbacks'] = conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_readbacks_v2 WHERE task_id=%s', (task,)).fetchone()['n']
            self.assertEqual(self.definition(conn, 'backfill_recheck_page_v2(text,integer)'), self.recheck)
        return task, observed

    def test_old_selector_reproduces_real_guard_failure_and_permanent_exclusion(self):
        task, proof = self.race(False)
        self.assertEqual(proof['first_call_result']['verified_pages'], 0)
        self.assertEqual(proof['first_call_result']['readback_errors'], 1)
        self.assertEqual(proof['first_call_readbacks'], 0)
        self.assertEqual(len(proof['first_call_failures']), 1)
        failure = proof['first_call_failures'][0]
        self.assertEqual(failure['evidence']['sqlstate'], 'AI005')
        self.assertEqual(failure['evidence']['reason'], REASON)
        later = self.maintain()
        self.assertEqual((later['verified_pages'], later['readback_errors']), (0, 0))
        with self.f.admin() as conn:
            self.assertEqual(self.audits(conn, task), [failure])
        proof['later_original_call_still_excluded'] = True
        RESULT['old_race'] = proof

    def test_candidate_defers_race_without_failure_then_next_transaction_verifies(self):
        task, proof = self.race(True)
        self.assertEqual((proof['first_call_result']['verified_pages'], proof['first_call_result']['readback_errors']), (0, 0))
        self.assertEqual(proof['first_call_readbacks'], 0)
        self.assertEqual(proof['first_call_failures'], [])
        later = self.maintain()
        self.assertEqual((later['verified_pages'], later['readback_errors']), (1, 0))
        with self.f.admin() as conn:
            b = conn.execute(f'SELECT body_sha256,readback_sha256,expected_records,actual_records FROM {self.f.schema}.backfill_readbacks_v2 WHERE task_id=%s AND page_no=0', (task,)).fetchone()
            self.assertEqual(b['body_sha256'], proof['page']['body_sha256'])
            self.assertEqual(b['readback_sha256'], proof['page']['body_sha256'])
            self.assertEqual((b['expected_records'], b['actual_records']), (100, 100))
            self.assertEqual(self.audits(conn, task), [])
        proof['later_call_result'] = later
        proof['later_independent_readback'] = b
        RESULT['candidate_race'] = proof

    def test_equality_and_newer_timestamps_are_deferred_under_unchanged_guard(self):
        self.install()
        task = self.news_task()
        with self.f.admin() as conn:
            stamp = conn.execute('SELECT transaction_timestamp() t').fetchone()['t']
            self.insert_page(conn, task, 0, committed_at=stamp)
            self.insert_page(conn, task, 1, committed_at=stamp + timedelta(microseconds=1))
            for page_no in (0, 1):
                with self.assertRaises(self.f.psycopg.Error) as caught:
                    with conn.transaction():
                        conn.execute(f'SELECT {self.f.schema}.backfill_recheck_page_v2(%s,%s)', (task, page_no))
                self.assertEqual(caught.exception.sqlstate, 'AI005')
                self.assertEqual(caught.exception.diag.message_primary, REASON)
            answer = conn.execute(f'SELECT {self.f.schema}.backfill_maintain_v2(8) value').fetchone()['value']
            self.assertEqual((answer['verified_pages'], answer['readback_errors']), (0, 0))
            self.assertEqual(self.audits(conn, task), [])
        self.assertEqual(self.maintain(8)['verified_pages'], 2)
        RESULT['timestamp_boundary'] = {'equality_and_plus_one_microsecond_deferred': True,
            'real_unchanged_guard_rejects_both_in_old_transaction': True, 'later_transaction_verifies_both': True}

    def test_page_bounds_and_existing_failure_exclusion_remain(self):
        self.install()
        task = self.news_task()
        with self.f.admin() as conn:
            for page_no in range(11):
                self.insert_page(conn, task, page_no)
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_audit_v2(run_id,task_id,action,evidence)
                VALUES(%s,%s,'READBACK_FAILURE','{{"page_no":10,"sqlstate":"AI002","reason":"retained synthetic quality hold"}}')''', (self.run, task))
            original_failure = self.audits(conn, task)
        outcomes = [self.maintain(limit) for limit in (0, 999, 2, 2)]
        self.assertEqual([x['verified_pages'] for x in outcomes], [1, 8, 1, 0])
        self.assertEqual([x['readback_errors'] for x in outcomes], [0, 0, 0, 0])
        with self.f.admin() as conn:
            self.assertEqual(self.audits(conn, task), original_failure)
            self.assertIsNone(conn.execute(f'SELECT 1 FROM {self.f.schema}.backfill_readbacks_v2 WHERE task_id=%s AND page_no=10', (task,)).fetchone())
        RESULT['bounds_and_existing_failures'] = {'limits': [0, 999, 2, 2], 'verified_pages': [1, 8, 1, 0],
            'existing_failure_and_exclusion_unchanged': True}

    def test_forward_preserves_every_other_function_metadata_and_application_rows(self):
        with self.f.admin() as conn:
            before_data = self.snapshot_with_audit(conn)
            before_meta = self.metadata(conn)
            before_other = conn.execute(f"SELECT jsonb_agg(to_jsonb(p) ORDER BY oid) j FROM pg_proc p WHERE pronamespace='{self.f.schema}'::regnamespace AND oid<>'{self.f.schema}.backfill_maintain_v2(integer)'::regprocedure").fetchone()['j']
            conn.commit()
            conn.execute(self.forward)
            self.assertEqual(self.definition(conn), self.candidate)
            self.assertEqual(self.metadata(conn), before_meta)
            self.assertEqual(self.snapshot_with_audit(conn), before_data)
            self.assertEqual(conn.execute(f"SELECT jsonb_agg(to_jsonb(p) ORDER BY oid) j FROM pg_proc p WHERE pronamespace='{self.f.schema}'::regnamespace AND oid<>'{self.f.schema}.backfill_maintain_v2(integer)'::regprocedure").fetchone()['j'], before_other)
            for role in (self.f.gateway, self.f.outsider):
                self.assertFalse(conn.execute("SELECT has_function_privilege(%s,%s,'EXECUTE') allowed", (role, self.f.schema + '.backfill_maintain_v2(integer)')).fetchone()['allowed'])
            self.assertEqual(before_meta['proconfig'], ['search_path=""', 'statement_timeout=8s', 'lock_timeout=2s'])
        RESULT['forward_preservation'] = {'exact_candidate_installed_locally': True, 'all_function_metadata_unchanged': True,
            'all_other_functions_unchanged': True, 'application_rows_and_run_owner_metadata_unchanged': True,
            'gateway_and_outsider_execute_still_denied': True}

    def test_forward_guards_and_atomic_postwrite_rollback(self):
        with self.f.admin() as conn:
            original_run = conn.execute(f'SELECT metadata FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s', (self.run,)).fetchone()['metadata']
        cases = [
            ('baseline_pin', self.forward.replace(digest(self.baseline), '0' * 64), None),
            ('verifier_pin', self.forward.replace(digest(self.recheck), '0' * 64), None),
            ('candidate_pin', self.forward.replace(digest(self.candidate), '0' * 64), None),
            ('metadata_pin', self.forward.replace(canonical(self.local_metadata), canonical({**self.local_metadata, 'proowner': 0})), None),
            ('postwrite_rollback', self.forward.replace(' EXECUTE v_after;', " EXECUTE v_after;\n RAISE EXCEPTION 'synthetic failure after function replacement';"), None),
            ('wrong_owner', self.forward, "metadata=jsonb_set(metadata,'{implementation_owner}','\"different-owner\"')"),
            ('expired_lease', self.forward, "metadata=jsonb_set(metadata,'{implementation_lease_until}','\"2000-01-01T00:00:00Z\"')"),
            ('paused_run', self.forward, "status='PAUSED'"),
        ]
        checked = []
        for label, sql, mutation in cases:
            with self.subTest(label=label):
                with self.f.admin() as conn:
                    conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=%s,status='ACTIVE' WHERE id=%s", (canonical(original_run), self.run))
                    if mutation:
                        conn.execute(f'UPDATE {self.f.schema}.backfill_runs_v2 SET {mutation} WHERE id=%s', (self.run,))
                with self.assertRaises(self.f.psycopg.Error), self.f.admin() as conn:
                    conn.execute(sql)
                with self.f.admin() as conn:
                    self.assertEqual(self.definition(conn), self.baseline)
                    self.assertEqual(self.metadata(conn), self.local_metadata)
                    self.assertEqual(self.definition(conn, 'backfill_recheck_page_v2(text,integer)'), self.recheck)
                checked.append(label)
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=%s,status='ACTIVE' WHERE id=%s", (canonical(original_run), self.run))
            incomplete = self.run + '-incomplete'
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET status='PAUSED' WHERE id=%s", (self.run,))
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_runs_v2
                (id,instruction_sha256,cohort_sha256,cohort_manifest_sha256,cohort_ref,scope,metadata)
                SELECT %s,instruction_sha256,cohort_sha256,cohort_manifest_sha256,cohort_ref,scope,metadata
                FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s''', (incomplete, self.run))
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_members_v2(run_id,member_id,selection_order,anchor_ticker)
                SELECT %s,member_id,selection_order,anchor_ticker FROM {self.f.schema}.backfill_members_v2
                WHERE run_id=%s AND selection_order<3000''', (incomplete, self.run))
        with self.assertRaises(self.f.psycopg.Error), self.f.admin() as conn:
            conn.execute(self.forward.replace(self.run, incomplete))
        checked.append('2999_members')
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET status='PAUSED' WHERE id=%s", (incomplete,))
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET status='ACTIVE' WHERE id=%s", (self.run,))
            conn.execute(self.forward)
        with self.assertRaises(self.f.psycopg.Error), self.f.admin() as conn:
            conn.execute(self.forward)
        checked.append('replay')
        with self.f.admin() as conn:
            conn.execute(self.baseline)
            conn.execute(f'UPDATE {self.f.schema}.backfill_runs_v2 SET fence=2 WHERE id=%s', (self.run,))
        with self.assertRaises(self.f.psycopg.Error), self.f.admin() as conn:
            conn.execute(self.forward)
        checked.append('fence')
        RESULT['forward_fail_closed'] = checked

    def test_existing_two_second_gate_wait_and_busy_return_remain(self):
        self.install()
        with self.f.admin() as blocker:
            blocker.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK,))
            started = monotonic()
            result = self.maintain()
            elapsed = monotonic() - started
        self.assertEqual(result, {'state': 'BUSY', 'reason': 'BOUNDED_WORKER_LOCK_WAIT_EXHAUSTED'})
        self.assertGreaterEqual(elapsed, 1.7)
        self.assertLess(elapsed, 3.5)
        RESULT['gate_bounds'] = {'elapsed_seconds': elapsed, 'unchanged_busy_result': result}


if __name__ == '__main__':
    if os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL') != EXPECTED_LOCAL_URL:
        raise SystemExit('Only the known disposable loopback PostgreSQL fixture is allowed')
    started = monotonic()
    suite = unittest.TestSuite()
    for cls in (SourceTests, PostgreSQLTests):
        suite.addTests(cls(name) for name in cls.__dict__ if name.startswith('test_'))
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    passed = result.wasSuccessful() and not result.skipped
    RESULT.update(passed=passed, tests=result.testsRun, errors=len(result.errors), failures=len(result.failures),
        skipped=len(result.skipped), elapsed_seconds=monotonic() - started,
        baseline_sha256=digest(BASELINE), candidate_sha256=digest(CANDIDATE),
        unchanged_recheck_sha256=digest(RECHECK), forward_sha256=digest(FORWARD),
        test_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        fixture_adaptation='Isolated schema/run identifiers, exact local catalog metadata and source hashes; real retained recheck guard/body unchanged except schema namespace.',
        synthetic_page_note='Two actual database connections commit synthetic100-record Massive N01 pages after the monitor transaction begins and queues on the real advisory gate. No provider request or production row is used.',
        fixture_dependency_root=str(STAGED), production_activation=False,
        fixture_correction='Initial guard-only fixture attempted two ACTIVE runs and hit the existing uniqueness guard. The incomplete-cohort fixture now pauses the original before activating its distinct run, then restores the original after the rejection test; initial receipt retained.',
        errors_detail=[text for _, text in result.errors], failures_detail=[text for _, text in result.failures])
    attempt = len(list(HERE.glob('qualification_attempt_*.json'))) + 1
    data = json.dumps(RESULT, indent=2, default=str) + '\n'
    (HERE / f'qualification_attempt_{attempt}.json').write_text(data)
    path = HERE / 'qualification_v72.json'
    path.write_text(data)
    print(json.dumps({'passed': passed, 'receipt': str(path), 'sha256': digest(data), 'attempt': attempt}))
    raise SystemExit(0 if passed else 1)
