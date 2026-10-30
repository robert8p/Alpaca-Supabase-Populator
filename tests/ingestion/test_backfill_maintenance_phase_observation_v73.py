"""Actual-role, concurrency and failure qualification of bounded v73 telemetry."""
from concurrent.futures import ThreadPoolExecutor
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import threading
from time import monotonic, perf_counter, sleep
import unittest

import test_backfill_claim_capability_filter_v2 as base
import test_backfill_readback_transaction_race_v2 as race

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / 'review/recovery-v73'
BASELINE = (HERE / 'baseline_maintain_installed_v73.sql').read_text()
CANDIDATE = (HERE / 'candidate_maintain_phase_observation_v73.sql').read_text()
DERIVATION = json.loads((HERE / 'maintenance_phase_observation_derivation_v73.json').read_text())
PIN = '6c880114a645c8a9167d5260c4aeabf58a10617c4244cf0340be1d6cf4bf0ce7'
DEADLINE = DERIVATION['observation_deadline_utc']
PROBE = DERIVATION['probe_id']
ACTION = DERIVATION['action']
LOCK = 706314020261028
SENTINEL = 'PRIVATE_SYNTHETIC_ERROR_OR_PAYLOAD_MUST_NOT_BE_EXPORTED'
RESULT = {'schema': 'astra.maintenance-phase-observation-qualification/1',
          'production_calls': 0, 'activation_selected': False,
          'fixture_adaptations': ['unique disposable schema/run identifiers',
                                 'future deadline2100 for positive tests; explicit past/during-call boundary cases',
                                 'synthetic helper faults only in named fault-injection cases']}


def digest(value):
    return sha256(value.encode()).hexdigest()


class SourceTests(unittest.TestCase):
    def test_exact_installed_body_reversal_and_unchanged_settings(self):
        self.assertEqual(digest(BASELINE), PIN)
        self.assertEqual(digest(CANDIDATE), DERIVATION['candidate_sha256'])
        self.assertEqual(re.sub(r'^ -- PHASE_OBSERVATION_V73_BEGIN [^\n]+\n.*?^ -- PHASE_OBSERVATION_V73_END [^\n]+\n',
            '', CANDIDATE, flags=re.M | re.S), BASELINE)
        self.assertEqual(CANDIDATE.count('pg_advisory_xact_lock(706314020261028)'), 1)
        self.assertEqual(CANDIDATE.count('WHEN query_canceled OR assert_failure THEN RAISE'), 2)
        self.assertIn("pg.committed_at<transaction_timestamp()", CANDIDATE)
        self.assertIn("current_setting('transaction_isolation')='read committed'", CANDIDATE)
        self.assertNotRegex(CANDIDATE, r'(?im)^\s*(GRANT|REVOKE|ALTER|CREATE\s+(TABLE|ROLE|INDEX))\b')
        self.assertEqual(CANDIDATE.count('SET statement_timeout'), 1)
        self.assertEqual(CANDIDATE.count('SET lock_timeout'), 1)
        RESULT['exact_source_preservation'] = True


class PostgreSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'):
            if os.environ.get('GITHUB_WORKFLOW') == 'ASTRA ingestion qualification':
                raise RuntimeError('ASTRA_INGESTION_POSTGRES_TEST_URL is required by ASTRA ingestion qualification')
            raise unittest.SkipTest('Disposable PostgreSQL is exercised by the dedicated ASTRA ingestion qualification gate')
        base.CapabilityFilterPostgreSQLTests.setUpClass.__func__(cls)
        f = cls.fixture('runTest')
        with f.admin() as conn:
            cls.helper = conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (f.schema + '.backfill_breadth_project_pending_v2(integer)',)).fetchone()['d']
            RESULT['local_postgresql_version'] = conn.execute('SHOW server_version').fetchone()['server_version']

    rewrite = classmethod(base.CapabilityFilterPostgreSQLTests.rewrite.__func__)
    full_query = staticmethod(base.CapabilityFilterPostgreSQLTests.full_query)
    task = base.CapabilityFilterPostgreSQLTests.task
    call = base.CapabilityFilterPostgreSQLTests.call
    claim = base.CapabilityFilterPostgreSQLTests.claim
    page = base.CapabilityFilterPostgreSQLTests.page
    fence = staticmethod(base.CapabilityFilterPostgreSQLTests.fence)
    snapshot = base.CapabilityFilterPostgreSQLTests.snapshot
    news_task = race.PostgreSQLTests.news_task
    insert_page = race.PostgreSQLTests.insert_page

    def setUp(self):
        base.CapabilityFilterPostgreSQLTests.setUp(self)
        self.baseline = BASELINE.replace('astra_ingestion_v1', self.f.schema)
        self.candidate = CANDIDATE.replace('astra_ingestion_v1', self.f.schema).replace(base.LIVE_RUN, self.run).replace(DEADLINE, '2100-01-01 00:00:00+00')
        with self.f.admin() as conn:
            conn.execute(self.helper)
            conn.execute(f'DROP TRIGGER IF EXISTS phase_fixture_fault ON {self.f.schema}.backfill_audit_v2')
            conn.execute(f'GRANT SELECT,INSERT ON {self.f.schema}.backfill_audit_v2 TO {self.f.owner}')
            conn.execute(f'GRANT USAGE ON SEQUENCE {self.f.schema}.backfill_audit_v2_id_seq TO {self.f.owner}')
            conn.execute(f'ALTER POLICY backfill_delivery_insert ON {self.f.schema}.backfill_audit_v2 WITH CHECK(true)')
            conn.execute(self.baseline)
            # Warm only the fixture's ordinary initial cursor/seed setup.
            self.original_result = conn.execute(f'SELECT {self.f.schema}.backfill_maintain_v2(2) r').fetchone()['r']
            self.original_metadata = self.metadata(conn)
            self.original_auth = conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (self.f.schema + '.rpc_dispatch(text,jsonb)',)).fetchone()['d']
            conn.execute(self.candidate)

    def metadata(self, conn):
        return conn.execute("SELECT to_jsonb(p)-'prosrc' m FROM pg_proc p WHERE oid=%s::regprocedure",
            (self.f.schema + '.backfill_maintain_v2(integer)',)).fetchone()['m']

    def invoke_on(self, conn, limit=2):
        conn.execute(f'SET LOCAL ROLE {self.f.owner}')
        return conn.execute(f'SELECT {self.f.schema}.backfill_maintain_v2(%s) r', (limit,)).fetchone()['r']

    def invoke(self, limit=2, isolation=None, timeout=None):
        with self.f.admin() as conn:
            if isolation:
                conn.execute('SET TRANSACTION ISOLATION LEVEL ' + isolation)
            if timeout:
                conn.execute("SELECT set_config('statement_timeout',%s,true)", (timeout,))
            return self.invoke_on(conn, limit)

    def events(self, conn=None):
        if conn is None:
            with self.f.admin() as owned:
                return self.events(owned)
        return conn.execute(f'''SELECT action,source_revision,evidence FROM {self.f.schema}.backfill_audit_v2
            WHERE run_id=%s AND action=%s AND source_revision=%s ORDER BY id''',
            (self.run, ACTION, PROBE)).fetchall()

    def install(self, definition):
        with self.f.admin() as conn:
            conn.execute(definition)

    def helper_injection(self, code):
        self.install(self.helper.replace('BEGIN\n', 'BEGIN\n ' + code + '\n', 1))

    def fault(self, code):
        with self.f.admin() as conn:
            conn.execute(f'''CREATE OR REPLACE FUNCTION {self.f.schema}.phase_fixture_fault_fn()
                RETURNS trigger LANGUAGE plpgsql AS $test$ BEGIN
                IF NEW.action='{ACTION}' THEN {code} END IF; RETURN NEW; END $test$''')
            conn.execute(f'''CREATE TRIGGER phase_fixture_fault BEFORE INSERT ON {self.f.schema}.backfill_audit_v2
                FOR EACH ROW EXECUTE FUNCTION {self.f.schema}.phase_fixture_fault_fn()''')

    def assert_real_readback(self, task):
        with self.f.admin() as conn:
            row = conn.execute(f'''SELECT body_sha256,readback_sha256,expected_records,actual_records
                FROM {self.f.schema}.backfill_readbacks_v2 WHERE task_id=%s AND page_no=0''', (task,)).fetchone()
            self.assertIsNotNone(row)
            self.assertEqual(row['body_sha256'], row['readback_sha256'])
            self.assertEqual((row['expected_records'], row['actual_records']), (100, 100))

    def new_page(self):
        task = self.news_task()
        with self.f.admin() as conn:
            self.insert_page(conn, task, committed_at='2026-10-30 05:00:01+00')
        return task

    def test_actual_owner_rls_sequence_permissions_and_safe_event(self):
        with self.f.admin() as conn:
            privileges = conn.execute('''SELECT r.rolsuper,r.rolbypassrls,r.rolcanlogin,
                c.relowner<>r.oid audit_owned_elsewhere,c.relrowsecurity audit_rls,
                has_table_privilege(r.oid,c.oid,'SELECT') audit_select,
                has_table_privilege(r.oid,c.oid,'INSERT') audit_insert,
                has_table_privilege(r.oid,c.oid,'UPDATE') audit_update,
                has_table_privilege(r.oid,c.oid,'DELETE') audit_delete,
                has_sequence_privilege(r.oid,%s,'USAGE') sequence_usage,
                has_sequence_privilege(r.oid,%s,'UPDATE') sequence_update
                FROM pg_roles r CROSS JOIN pg_class c WHERE r.rolname=%s AND c.oid=%s::regclass''',
                (self.f.schema+'.backfill_audit_v2_id_seq', self.f.schema+'.backfill_audit_v2_id_seq',
                 self.f.owner, self.f.schema+'.backfill_audit_v2')).fetchone()
            self.assertEqual(privileges, dict(rolsuper=False,rolbypassrls=False,rolcanlogin=False,
                audit_owned_elsewhere=True,audit_rls=True,audit_select=True,audit_insert=True,
                audit_update=False,audit_delete=False,sequence_usage=True,sequence_update=False))
            effective = conn.execute('''SELECT p.prosecdef,p.provolatile,r.rolname,r.rolsuper,r.rolbypassrls
                FROM pg_proc p JOIN pg_roles r ON r.oid=p.proowner WHERE p.oid=%s::regprocedure''',
                (self.f.schema+'.backfill_maintain_v2(integer)',)).fetchone()
            self.assertEqual(effective,dict(prosecdef=True,provolatile='v',rolname=self.f.owner,rolsuper=False,rolbypassrls=False))
            for role in (self.f.gateway, self.f.outsider):
                self.assertFalse(conn.execute("SELECT has_function_privilege(%s,%s,'EXECUTE') p",
                    (role,self.f.schema+'.backfill_maintain_v2(integer)')).fetchone()['p'])
            before = self.snapshot(conn)
            ref_before = conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_family_ref03_v2 WHERE run_id=%s', (self.run,)).fetchone()['n']
        self.assertEqual(self.invoke(), self.original_result)
        event = self.events()[0]['evidence']
        self.assertEqual(set(event), {'probe_id','timing_scope','backend_pid','total_ms','telemetry_admission_ms','phases_ms'})
        self.assertEqual(event['timing_scope'], 'GLOBAL_MAINTENANCE_BEFORE_TELEMETRY')
        self.assertEqual(set(event['phases_ms']), {'gate_admission_ms'}|{x+'_ms' for x in DERIVATION['helper_and_loop_phases']})
        self.assertTrue(all(isinstance(x,(int,float)) and x>=0 for x in event['phases_ms'].values()))
        self.assertIsInstance(event['backend_pid'], int)
        self.assertLess(abs(sum(event['phases_ms'].values())+event['telemetry_admission_ms']-event['total_ms']), 0.02)
        self.assertLess(len(json.dumps(event).encode()), 1800)
        self.assertNotIn(SENTINEL, json.dumps(event))
        with self.f.admin() as conn:
            self.assertEqual(before, self.snapshot(conn))
            self.assertEqual(self.original_metadata, self.metadata(conn))
            self.assertEqual(self.original_auth, conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (self.f.schema+'.rpc_dispatch(text,jsonb)',)).fetchone()['d'])
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_family_ref03_v2 WHERE run_id=%s', (self.run,)).fetchone()['n']-ref_before, 1)
        RESULT['actual_permissions_and_event'] = {'privileges': privileges, 'event': event,
            'source_snapshot_unchanged': True, 'ref03_evidence_increment_only': 1}

    def test_same_transaction_and_later_calls_stop_at_four(self):
        with self.f.admin() as conn:
            for _ in range(6):
                self.assertEqual(self.invoke_on(conn), self.original_result)
            self.assertEqual(len(self.events(conn)), 4)
        for _ in range(2):
            self.assertEqual(self.invoke(), self.original_result)
        self.assertEqual(len(self.events()), 4)
        RESULT['same_transaction_cap'] = {'calls': 8, 'committed_events': 4}

    def near_cap(self, rollback):
        for _ in range(3): self.invoke()
        self.assertEqual(len(self.events()), 3)
        started = threading.Event()
        facts = {}
        def waiter():
            with self.f.admin() as conn:
                facts.update(conn.execute('SELECT pg_backend_pid() waiter_pid,transaction_timestamp() waiter_started').fetchone())
                started.set()
                return self.invoke_on(conn)
        with self.f.admin() as holder, ThreadPoolExecutor(max_workers=1) as pool:
            holder.execute('SELECT pg_advisory_xact_lock(%s)', (LOCK,))
            facts['holder_started'] = holder.execute('SELECT transaction_timestamp() t').fetchone()['t']
            future = pool.submit(waiter)
            self.assertTrue(started.wait(2))
            deadline = monotonic()+1
            waited = False
            while monotonic()<deadline:
                waited = holder.execute("SELECT EXISTS(SELECT 1 FROM pg_locks WHERE pid=%s AND locktype='advisory' AND NOT granted) w",
                    (facts['waiter_pid'],)).fetchone()['w']
                if waited: break
                sleep(0.005)
            self.assertTrue(waited)
            self.assertEqual(self.invoke_on(holder), self.original_result)
            self.assertEqual(len(self.events(holder)), 4)
            if rollback: holder.rollback()
            else: holder.commit()
            self.assertEqual(future.result(timeout=5), self.original_result)
        self.assertEqual(len(self.events()), 4)
        facts.update(actual_gate_wait=True, first_holder_rolled_back=rollback, committed_events=4)
        return facts

    def test_prestarted_rc_waiter_sees_committed_fourth_after_gate(self):
        RESULT['concurrent_cap_commit'] = self.near_cap(False)

    def test_rolled_back_fourth_allows_waiter_without_exceeding_cap(self):
        RESULT['concurrent_cap_rollback'] = self.near_cap(True)

    def test_stronger_isolation_skips_only_telemetry_and_keeps_real_readback(self):
        for isolation in ('REPEATABLE READ', 'SERIALIZABLE'):
            task = self.new_page()
            answer = self.invoke(isolation=isolation)
            self.assertEqual((answer['verified_pages'],answer['readback_errors']), (1,0))
            self.assert_real_readback(task)
        self.assertEqual(self.events(), [])
        RESULT['stronger_isolation'] = ['REPEATABLE READ real readback without telemetry',
                                       'SERIALIZABLE real readback without telemetry']

    def test_deadline_owner_and_lease_skip_telemetry_only(self):
        task = self.new_page()
        self.install(self.candidate.replace('2100-01-01 00:00:00+00','2000-01-01 00:00:00+00'))
        self.assertEqual(self.invoke()['verified_pages'],1)
        self.assert_real_readback(task)
        self.assertEqual(self.events(), [])
        self.install(self.candidate)
        with self.f.admin() as conn:
            saved = conn.execute(f'SELECT metadata FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s', (self.run,)).fetchone()['metadata']
        for field,value in [('implementation_owner','different-owner'),('implementation_lease_until','2000-01-01T00:00:00Z')]:
            changed = dict(saved);changed[field]=value
            with self.f.admin() as conn:
                conn.execute(f'UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=%s WHERE id=%s', (json.dumps(changed),self.run))
            self.assertEqual(self.invoke(),self.original_result)
            self.assertEqual(self.events(),[])
        with self.f.admin() as conn:
            conn.execute(f'UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=%s WHERE id=%s', (json.dumps(saved),self.run))
        # Both scope constants fail closed without modifying immutable cohort data.
        for value in (self.candidate.replace(self.run,self.run+'-absent'),
                      self.candidate.replace(DERIVATION['cohort_sha256'],'0'*64)):
            self.install(value)
            self.assertEqual(self.invoke(),self.original_result)
            self.assertEqual(self.events(),[])
        self.install(self.candidate)
        with self.f.admin() as conn:
            conn.execute(f'UPDATE {self.f.schema}.backfill_runs_v2 SET fence=2 WHERE id=%s', (self.run,))
        self.assertEqual(self.invoke(),self.original_result)
        self.assertEqual(self.events(),[])
        RESULT['admission_scope_and_time'] = ['expired deadline','wrong owner','expired lease','absent run','wrong cohort','advanced fence']

    def test_deadline_and_lease_are_rechecked_after_helper_work(self):
        self.helper_injection('PERFORM pg_sleep(0.12);')
        with self.f.admin() as conn:
            expiry = str(conn.execute("SELECT clock_timestamp()+interval '65 milliseconds' t").fetchone()['t'])
            conn.execute(self.candidate.replace('2100-01-01 00:00:00+00',expiry))
        self.assertEqual(self.invoke(),self.original_result)
        self.assertEqual(self.events(),[])
        self.install(self.candidate)
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=jsonb_set(metadata,'{{implementation_lease_until}}',to_jsonb(clock_timestamp()+interval '65 milliseconds')) WHERE id=%s", (self.run,))
        self.assertEqual(self.invoke(),self.original_result)
        self.assertEqual(self.events(),[])
        RESULT['late_expiry'] = {'deadline':True,'owner_lease':True,'original_result_preserved':True}

    def test_audit_table_nowait_uses_existing_insert_privilege(self):
        started = perf_counter()
        with self.f.admin() as holder:
            holder.execute(f'LOCK TABLE {self.f.schema}.backfill_audit_v2 IN SHARE MODE')
            self.assertEqual(self.invoke(),self.original_result)
        elapsed = perf_counter()-started
        self.assertLess(elapsed,1)
        self.assertEqual(self.events(),[])
        RESULT['audit_nowait'] = {'seconds':elapsed,'ordinary_result_preserved':True}

    def test_expiry_during_optional_insert_rolls_back_only_telemetry(self):
        self.fault('PERFORM pg_sleep(1.10);')
        task = self.new_page()
        with self.f.admin() as conn:
            before_id=conn.execute(f'SELECT last_value n FROM {self.f.schema}.backfill_audit_v2_id_seq').fetchone()['n']
            expiry = str(conn.execute("SELECT clock_timestamp()+interval '1 second' t").fetchone()['t'])
            conn.execute(self.candidate.replace('2100-01-01 00:00:00+00',expiry))
        answer=self.invoke()
        self.assertEqual((answer['verified_pages'],answer['readback_errors']),(1,0))
        self.assert_real_readback(task)
        self.assertEqual(self.events(),[])
        with self.f.admin() as conn:
            after_id=conn.execute(f'SELECT last_value n FROM {self.f.schema}.backfill_audit_v2_id_seq').fetchone()['n']
        self.assertEqual(after_id-before_id,1,'Identity allocation proves INSERT was reached before its expiry rollback')
        self.install(self.candidate)
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=jsonb_set(metadata,'{{implementation_lease_until}}',to_jsonb(clock_timestamp()+interval '1 second')) WHERE id=%s", (self.run,))
        self.assertEqual(self.invoke(),self.original_result)
        self.assertEqual(self.events(),[])
        with self.f.admin() as conn:
            final_id=conn.execute(f'SELECT last_value n FROM {self.f.schema}.backfill_audit_v2_id_seq').fetchone()['n']
        self.assertEqual(final_id-after_id,1)
        RESULT['expiry_inside_insert']={'deadline_and_lease_both_rechecked_after_insert':True,
            'only_diagnostic_subtransaction_rolled_back':True,'real_readback_retained':True,
            'two_nontransactional_identity_gaps_prove_both_insert_attempts_reached':True,
            'later_outer_commit_duration_not_claimed_bounded':True}

    def test_telemetry_insert_and_rls_denials_do_not_change_main_readback(self):
        cases = [
            ('audit_insert', f'REVOKE INSERT ON {self.f.schema}.backfill_audit_v2 FROM {self.f.owner}',
             f'GRANT INSERT ON {self.f.schema}.backfill_audit_v2 TO {self.f.owner}'),
            ('insert_rls', f'ALTER POLICY backfill_delivery_insert ON {self.f.schema}.backfill_audit_v2 WITH CHECK(false)',
             f'ALTER POLICY backfill_delivery_insert ON {self.f.schema}.backfill_audit_v2 WITH CHECK(true)'),
        ]
        for label,deny,restore in cases:
            task = self.new_page()
            with self.f.admin() as conn: conn.execute(deny)
            try:
                answer = self.invoke()
                self.assertEqual((answer['verified_pages'],answer['readback_errors']),(1,0))
                self.assert_real_readback(task)
                self.assertEqual(self.events(),[])
            finally:
                with self.f.admin() as conn: conn.execute(restore)
        RESULT['ordinary_permission_denials'] = [x[0] for x in cases]

    def test_identity_generation_is_distinct_from_direct_sequence_access(self):
        with self.f.admin() as conn:
            self.assertEqual(conn.execute('''SELECT attidentity FROM pg_attribute
                WHERE attrelid=%s::regclass AND attname='id' ''',
                (self.f.schema+'.backfill_audit_v2',)).fetchone()['attidentity'],'a')
            conn.execute(f'REVOKE USAGE ON SEQUENCE {self.f.schema}.backfill_audit_v2_id_seq FROM {self.f.owner}')
        try:
            with self.assertRaises(self.f.psycopg.Error) as caught,self.f.admin() as conn:
                conn.execute(f'SET LOCAL ROLE {self.f.owner}')
                conn.execute('SELECT nextval(%s::regclass)',(self.f.schema+'.backfill_audit_v2_id_seq',))
            self.assertEqual(caught.exception.sqlstate,'42501')
            self.assertEqual(self.invoke(),self.original_result)
            self.assertEqual(len(self.events()),1)
        finally:
            with self.f.admin() as conn:
                conn.execute(f'GRANT USAGE ON SEQUENCE {self.f.schema}.backfill_audit_v2_id_seq TO {self.f.owner}')
        RESULT['identity_and_sequence'] = {'audit_id_generated_always':True,
            'without_usage_direct_nextval_sqlstate':'42501','identity_insert_still_permitted':True,
            'production_existing_usage_grant_unchanged':True,
            'initial_fixture_assumption_rejected':'USAGE revocation was incorrectly expected to block automatic identity generation'}

    def test_ordinary_telemetry_error_does_not_leak_or_rollback_main_work(self):
        self.fault("RAISE EXCEPTION USING ERRCODE='22023',MESSAGE='"+SENTINEL+"';")
        task = self.new_page()
        answer = self.invoke()
        self.assertEqual((answer['verified_pages'],answer['readback_errors']),(1,0))
        self.assert_real_readback(task)
        self.assertEqual(self.events(),[])
        self.assertNotIn(SENTINEL,json.dumps(answer))
        RESULT['ordinary_telemetry_error'] = {'main_real_readback_committed':True,'no_error_or_payload_export':True}

    def test_telemetry_cancellation_and_assertion_propagate(self):
        for state in ('57014','P0004'):
            with self.f.admin() as conn:
                conn.execute(f'DROP TRIGGER IF EXISTS phase_fixture_fault ON {self.f.schema}.backfill_audit_v2')
            self.fault("RAISE EXCEPTION USING ERRCODE='"+state+"',MESSAGE='"+SENTINEL+"';")
            with self.assertRaises(self.f.psycopg.Error) as caught:self.invoke()
            self.assertEqual(caught.exception.sqlstate,state)
            self.assertEqual(self.events(),[])
        RESULT['telemetry_fatal_errors'] = ['57014','P0004']

    def test_original_helper_errors_keep_identical_sqlstate(self):
        for state in ('22023','57014','P0004'):
            self.helper_injection("RAISE EXCEPTION USING ERRCODE='"+state+"',MESSAGE='"+SENTINEL+"';")
            for definition in (self.baseline,self.candidate):
                self.install(definition)
                with self.assertRaises(self.f.psycopg.Error) as caught:self.invoke()
                self.assertEqual(caught.exception.sqlstate,state)
        self.assertEqual(self.events(),[])
        RESULT['original_helper_errors'] = ['22023','57014','P0004']

    def test_observer_write_can_still_hit_unchanged_caller_deadline(self):
        self.fault('PERFORM pg_sleep(0.35);')
        self.install(self.baseline)
        self.assertEqual(self.invoke(timeout='150ms'),self.original_result)
        self.install(self.candidate)
        started = perf_counter()
        with self.assertRaises(self.f.psycopg.Error) as caught:self.invoke(timeout='150ms')
        self.assertEqual(caught.exception.sqlstate,'57014')
        self.assertEqual(self.events(),[])
        RESULT['observer_risk_demonstrated'] = {'kind':'ADDITIONAL_AUDIT_WORK_CAN_EXHAUST_CALLER_DEADLINE',
            'fixture_caller_budget':'150ms','runtime_function_config':'unchanged8s/2s',
            'seconds':perf_counter()-started,'cancellation_not_suppressed':True,
            'interpretation':'Risk disclosure; not a promise of zero observer effect.'}

    def test_restore_exact_installed_definition_preserves_existing_event(self):
        self.invoke()
        saved = self.events()
        self.install(self.baseline)
        self.assertEqual(self.invoke(),self.original_result)
        self.assertEqual(self.events(),saved)
        with self.f.admin() as conn:
            self.assertEqual(conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (self.f.schema+'.backfill_maintain_v2(integer)',)).fetchone()['d'],self.baseline)
            self.assertEqual(self.metadata(conn),self.original_metadata)
        RESULT['restore'] = {'exact6c880_schema_adjusted':True,'immutable_events_retained':True}
