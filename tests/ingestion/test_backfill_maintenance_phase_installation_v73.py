"""Exact v73 installer/restore source, real PostgreSQL guards and atomic cleanup."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re
import unittest

import test_backfill_maintenance_phase_observation_v73 as observation

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / 'review/recovery-v73/installation'
spec = importlib.util.spec_from_file_location('phase_install_builder_v73', HERE / 'build_phase_observation_installation_v73.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
MANIFEST = json.loads((HERE / 'installation_manifest_v73.json').read_text())
FORWARD = (ROOT / 'sql/astra_backfill_maintenance_phase_observation_v73.sql').read_text()
RESTORE = (ROOT / 'sql/astra_backfill_maintenance_phase_observation_restore_v73.sql').read_text()
FUTURE = '2100-01-01 00:00:00+00'
RESULT = {'schema': 'astra.maintenance-phase-installation-qualification/1', 'production_calls': 0,
          'activation_selected': False, 'fixture_adaptations': [
              'disposable schema/run/role identifiers and future observation deadline',
              'exact local function hashes, OIDs and metadata replace production catalog pins',
              'two isolated unprivileged fixture roles represent the three standard denied roles',
              'unchanged guard logic; explicit fault injection only in named negative cases']}


def digest(value):
    return sha256(value.encode()).hexdigest()


class SourceTests(unittest.TestCase):
    def test_active_bytes_pins_and_install_restore_scope(self):
        for name, value in [('forward_maintenance_phase_observation_v73.sql', FORWARD),
                            ('restore_maintenance_phase_observation_v73.sql', RESTORE)]:
            self.assertEqual((HERE / name).read_text(), value)
            self.assertEqual(digest(value), MANIFEST['artifacts'][name]['sha256'])
            self.assertEqual(value.count('EXECUTE v_replacement;'), 1)
            self.assertEqual(value.count('FOR SHARE;'), 1)
            self.assertIn("SET LOCAL statement_timeout='8s'", value)
            self.assertIn("SET LOCAL lock_timeout='3s'", value)
            self.assertIn('v_catalog_after IS DISTINCT FROM v_catalog_before', value)
            self.assertIn('v_after_metadata IS DISTINCT FROM v_expected_metadata', value)
            self.assertEqual(value.count('Fixed pins are repeated'), 1)
        self.assertEqual(FORWARD.count("id='" + builder.RUN + "' AND status='ACTIVE' AND fence=1"), 2)
        self.assertEqual(RESTORE.count("id='" + builder.RUN + "' AND fence=1"), 2)
        self.assertNotIn("fixed installation window expired", RESTORE)
        self.assertIn('restore_requires_same_unexpired_owner_lease', MANIFEST)
        self.assertEqual(MANIFEST['baseline_sha256'], observation.PIN)
        self.assertEqual(MANIFEST['candidate_sha256'], observation.DERIVATION['candidate_sha256'])
        self.assertEqual(len(MANIFEST['unchanged_function_pins']), 13)
        RESULT['exact_active_source'] = {'forward': digest(FORWARD), 'restore': digest(RESTORE)}


class PostgreSQLInstallationTests(unittest.TestCase):
    rewrite = classmethod(observation.PostgreSQLTests.rewrite.__func__)
    full_query = staticmethod(observation.PostgreSQLTests.full_query)
    task = observation.PostgreSQLTests.task
    call = observation.PostgreSQLTests.call
    claim = observation.PostgreSQLTests.claim
    page = observation.PostgreSQLTests.page
    fence = staticmethod(observation.PostgreSQLTests.fence)
    snapshot = observation.PostgreSQLTests.snapshot
    metadata = observation.PostgreSQLTests.metadata
    news_task = observation.PostgreSQLTests.news_task
    insert_page = observation.PostgreSQLTests.insert_page
    invoke_on = observation.PostgreSQLTests.invoke_on

    @classmethod
    def setUpClass(cls):
        observation.PostgreSQLTests.setUpClass.__func__(cls)
        f = cls.fixture('runTest')
        monitor = next(x['definition'] for x in json.loads(
            (ROOT / 'review/recovery-v71/live_cron_functions_1331.json').read_text()) if x['proname'] == 'monitor_tick_v1')
        with f.admin() as conn:
            conn.execute(monitor.replace('astra_ingestion_v1', f.schema))
            conn.execute(f'REVOKE ALL ON FUNCTION {f.schema}.monitor_tick_v1() FROM PUBLIC')
            RESULT['postgresql_version'] = conn.execute('SHOW server_version').fetchone()['server_version']

    def identifiers(self, sql):
        return self.rewrite(sql).replace(builder.RUN, self.run).replace(builder.DEADLINE, FUTURE).replace(
            "'anon'", "'" + self.f.gateway + "'").replace("'authenticated'", "'" + self.f.outsider + "'").replace(
            "'service_role'", "'" + self.f.outsider + "'")

    def query(self, template):
        return self.identifiers(template).replace('INTO @@VARIABLE@@', 'AS value')

    def definition(self, conn):
        return conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
            (self.f.schema + '.backfill_maintain_v2(integer)',)).fetchone()['d']

    def application_snapshot(self, conn):
        result = self.snapshot(conn)
        result['audit'] = conn.execute(f'''SELECT count(*) n,encode(sha256(convert_to(
            COALESCE(string_agg(to_jsonb(a)::text,E'\\n' ORDER BY a.id),''),'UTF8')),'hex') digest
            FROM {self.f.schema}.backfill_audit_v2 a''').fetchone()
        return result

    def setUp(self):
        observation.PostgreSQLTests.setUp(self)
        with self.f.admin() as conn:
            conn.execute(self.baseline)
            for row in MANIFEST['expected_hash_indexes']:
                conn.execute(self.identifiers(row['definition']).replace('CREATE INDEX ', 'CREATE INDEX IF NOT EXISTS ', 1))
            self.expected_metadata = self.metadata(conn)
            self.expected_audit = conn.execute(self.query(builder.AUDIT_QUERY)).fetchone()['value']
            self.expected_indexes = conn.execute(self.query(builder.INDEX_QUERY)).fetchone()['value']
            self.expected_role = conn.execute('''SELECT jsonb_build_object('oid',oid::text,'rolname',rolname,
                'rolsuper',rolsuper,'rolcanlogin',rolcanlogin,'rolbypassrls',rolbypassrls) value
                FROM pg_roles WHERE rolname=%s''', (self.f.owner,)).fetchone()['value']
            self.pin_info = {}
            for signature in MANIFEST['unchanged_function_pins']:
                actual = signature.replace('astra_ingestion_v1', self.f.schema)
                self.pin_info[actual] = conn.execute('''SELECT pg_get_functiondef(p.oid) source,
                    to_jsonb(p)-'prosrc' metadata,jsonb_build_object('acl',p.proacl,'owner',p.proowner::text,
                    'config',p.proconfig,'security_definer',p.prosecdef) partial
                    FROM pg_proc p WHERE p.oid=%s::regprocedure''', (actual,)).fetchone()
        self.forward = self.adapt(FORWARD)
        self.restore = self.adapt(RESTORE)

    def adapt(self, source):
        sql = self.identifiers(source)
        for tag, value in [('maintain_metadata', self.expected_metadata), ('audit_metadata', self.expected_audit),
                           ('index_metadata', self.expected_indexes), ('owner_metadata', self.expected_role)]:
            pattern = r'\$' + tag + r'\$.*?\$' + tag + r'\$::jsonb'
            sql, count = re.subn(pattern, lambda _: builder.json_sql(value, tag), sql, flags=re.S)
            self.assertEqual(count, 1)
        pattern = r"\('([^']+)','[0-9a-f]{64}',(true|false),\$pin_metadata\$.*?\$pin_metadata\$::jsonb\)"
        def pin(match):
            signature, full = match.group(1), match.group(2)
            value = self.pin_info[signature]
            return '(' + builder.quote(signature) + ',' + builder.quote(digest(value['source'])) + ',' + full + ',' + builder.json_sql(
                value['metadata'] if full == 'true' else value['partial'], 'pin_metadata') + ')'
        sql, count = re.subn(pattern, pin, sql, flags=re.S)
        self.assertEqual(count, 26)
        return sql.replace(observation.PIN, digest(self.baseline)).replace(
            observation.DERIVATION['candidate_sha256'], digest(self.candidate))

    def apply(self, sql):
        with self.f.admin() as conn:
            conn.execute(sql)

    def assert_rejected(self, sql, *, mutation=None, expected=None):
        with self.f.admin() as conn:
            before = self.application_snapshot(conn)
            catalog = conn.execute(self.query(builder.CATALOG_QUERY)).fetchone()['value']
            original = self.definition(conn)
            if mutation:
                conn.execute(mutation)
            with self.assertRaises(self.f.psycopg.Error):
                conn.execute(sql)
            conn.rollback()
            self.assertEqual(self.definition(conn), expected or original)
            self.assertEqual(before, self.application_snapshot(conn))
            self.assertEqual(catalog, conn.execute(self.query(builder.CATALOG_QUERY)).fetchone()['value'])

    def test_real_forward_and_restore_preserve_full_catalog_data_and_oid(self):
        with self.f.admin() as conn:
            before = self.application_snapshot(conn)
            catalog = conn.execute(self.query(builder.CATALOG_QUERY)).fetchone()['value']
            metadata = self.metadata(conn)
        self.apply(self.forward)
        with self.f.admin() as conn:
            self.assertEqual(self.definition(conn), self.candidate)
            self.assertEqual(metadata, self.metadata(conn))
            self.assertEqual(before, self.application_snapshot(conn))
            self.assertEqual(catalog, conn.execute(self.query(builder.CATALOG_QUERY)).fetchone()['value'])
        self.apply(self.restore)
        with self.f.admin() as conn:
            self.assertEqual(self.definition(conn), self.baseline)
            self.assertEqual(metadata, self.metadata(conn))
            self.assertEqual(before, self.application_snapshot(conn))
            self.assertEqual(catalog, conn.execute(self.query(builder.CATALOG_QUERY)).fetchone()['value'])
        RESULT['install_restore_full_preservation'] = True

    def test_preflight_source_metadata_permissions_index_and_owner_drift(self):
        s = self.f.schema
        mutations = {
            'source': f"ALTER FUNCTION {s}.backfill_maintain_v2(integer) SET statement_timeout='9s'",
            'metadata_acl': f'GRANT EXECUTE ON FUNCTION {s}.backfill_maintain_v2(integer) TO {self.f.outsider}',
            'audit_privilege': f'GRANT UPDATE ON {s}.backfill_audit_v2 TO {self.f.owner}',
            'audit_rls': f'ALTER TABLE {s}.backfill_audit_v2 DISABLE ROW LEVEL SECURITY',
            'hash_index': f'DROP INDEX {s}.backfill_tasks_minute_pending_id_v2',
            'owner': f"UPDATE {s}.backfill_runs_v2 SET metadata=jsonb_set(metadata,'{{implementation_owner}}','\"wrong-owner\"') WHERE id='{self.run}'",
            'lease': f"UPDATE {s}.backfill_runs_v2 SET metadata=jsonb_set(metadata,'{{implementation_lease_until}}','\"2000-01-01T00:00:00Z\"') WHERE id='{self.run}'",
            'fence': f"UPDATE {s}.backfill_runs_v2 SET fence=fence+1 WHERE id='{self.run}'",
            'paused': f"UPDATE {s}.backfill_runs_v2 SET status='PAUSED' WHERE id='{self.run}'",
        }
        for name, mutation in mutations.items():
            with self.subTest(name=name): self.assert_rejected(self.forward, mutation=mutation)
        self.assert_rejected(self.forward.replace(builder.COHORT, '0' * 64))
        RESULT['preflight_drift_rejections'] = list(mutations) + ['cohort']

    def test_atomic_postwrite_and_presnapshot_drift_rollback(self):
        s = self.f.schema
        after = ' EXECUTE v_replacement;'
        injections = {
            'explicit': "RAISE EXCEPTION 'Synthetic after replacement';",
            'catalog': f'ALTER TABLE {s}.backfill_tasks_v2 DISABLE ROW LEVEL SECURITY;',
            'metadata': f"ALTER FUNCTION {s}.backfill_maintain_v2(integer) SET lock_timeout='1s';",
            'owner': f"UPDATE {s}.backfill_runs_v2 SET metadata=jsonb_set(metadata,'{{implementation_owner}}','\"late-owner\"') WHERE id='{self.run}';",
            'lease': f"UPDATE {s}.backfill_runs_v2 SET metadata=jsonb_set(metadata,'{{implementation_lease_until}}','\"2000-01-01T00:00:00Z\"') WHERE id='{self.run}';",
        }
        for name, injection in injections.items():
            with self.subTest(name=name): self.assert_rejected(self.forward.replace(after, after + '\n ' + injection, 1))
        boundary = "SELECT jsonb_build_object(\n 'namespace'"
        changed = self.forward.replace(boundary,
            f"ALTER FUNCTION {s}.rpc_dispatch(text,jsonb) SET lock_timeout='4s';\n " + boundary, 1)
        self.assert_rejected(changed)
        RESULT['late_drift_atomic_rollback'] = list(injections) + ['source_before_catalog_snapshot']

    def test_deadline_expiry_after_replacement_rolls_back(self):
        with self.f.admin() as conn:
            deadline = conn.execute("SELECT (clock_timestamp()+interval '250 milliseconds')::text value").fetchone()['value']
        sql = self.forward.replace("IF clock_timestamp()>='" + FUTURE + "'::timestamptz",
            "IF clock_timestamp()>='" + deadline + "'::timestamptz")
        sql = sql.replace(' EXECUTE v_replacement;', ' EXECUTE v_replacement; PERFORM pg_sleep(0.4);', 1)
        self.assert_rejected(sql)
        RESULT['actual_final_install_deadline_expiry_rollback'] = True

    def test_incomplete_cohort_rejected_without_member_deletion(self):
        s = self.f.schema
        incomplete = self.run + '-incomplete'
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {s}.backfill_runs_v2 SET status='PAUSED' WHERE id=%s", (self.run,))
            conn.execute(f'''INSERT INTO {s}.backfill_runs_v2
                (id,instruction_sha256,cohort_sha256,cohort_manifest_sha256,cohort_ref,scope,metadata)
                SELECT %s,instruction_sha256,cohort_sha256,cohort_manifest_sha256,cohort_ref,scope,metadata
                FROM {s}.backfill_runs_v2 WHERE id=%s''', (incomplete, self.run))
            conn.execute(f'''INSERT INTO {s}.backfill_members_v2(run_id,member_id,selection_order,anchor_ticker)
                SELECT %s,member_id,selection_order,anchor_ticker FROM {s}.backfill_members_v2
                WHERE run_id=%s AND selection_order<3000''', (incomplete, self.run))
        self.assert_rejected(self.forward.replace(self.run, incomplete))
        RESULT['incomplete_cohort_2999_rejected'] = True

    def test_restore_paused_and_terminal_preserves_status_and_audit(self):
        self.apply(self.forward)
        observation.PostgreSQLTests.invoke(self)
        for status in ('PAUSED', 'PARTIAL_OPERATIONAL_FAILURE', 'BLOCKED_EXTERNAL', 'COMPLETE'):
            with self.subTest(status=status), self.f.admin() as conn:
                conn.execute(self.candidate)
                conn.execute(f'UPDATE {self.f.schema}.backfill_runs_v2 SET status=%s WHERE id=%s', (status, self.run))
                before = self.application_snapshot(conn)
                conn.commit()
                conn.execute(self.restore)
                self.assertEqual(self.definition(conn), self.baseline)
                self.assertEqual(before, self.application_snapshot(conn))
                self.assertEqual(conn.execute(f'SELECT status FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s',
                    (self.run,)).fetchone()['status'], status)
        RESULT['restore_existing_statuses_preserved'] = ['PAUSED','PARTIAL_OPERATIONAL_FAILURE','BLOCKED_EXTERNAL','COMPLETE']

    def test_restore_after_observation_expiry_and_drift_rejections(self):
        self.apply(self.forward)
        # Restore contains no admission deadline; prove cleanup with an actually
        # expired candidate in the disposable fixture after exercising its guards.
        self.assertNotIn('fixed installation window expired', self.restore)
        s = self.f.schema
        for field, value in [('implementation_owner','wrong-owner'),('implementation_lease_until','2000-01-01T00:00:00Z')]:
            mutation = f"UPDATE {s}.backfill_runs_v2 SET metadata=jsonb_set(metadata,'{{{field}}}',{builder.quote(json.dumps(value))}::jsonb) WHERE id='{self.run}'"
            self.assert_rejected(self.restore, mutation=mutation, expected=self.candidate)
        self.assert_rejected(self.restore, mutation=f"UPDATE {s}.backfill_runs_v2 SET fence=fence+1 WHERE id='{self.run}'", expected=self.candidate)
        self.assert_rejected(self.restore.replace(digest(self.candidate), '0' * 64), expected=self.candidate)
        self.assert_rejected(self.restore.replace(builder.COHORT, '0' * 64), expected=self.candidate)
        expired_candidate = self.candidate.replace(FUTURE, '2000-01-01 00:00:00+00')
        expired_restore = self.restore.replace(digest(self.candidate), digest(expired_candidate))
        with self.f.admin() as conn:
            conn.execute(expired_candidate)
            self.assertTrue(conn.execute("SELECT clock_timestamp()>'2000-01-01 00:00:00+00'::timestamptz expired").fetchone()['expired'])
            before = self.application_snapshot(conn)
        self.apply(expired_restore)
        with self.f.admin() as conn:
            self.assertEqual(self.definition(conn), self.baseline)
            self.assertEqual(before, self.application_snapshot(conn))
        self.assert_rejected(self.restore, expected=self.baseline)
        RESULT['restore_guards'] = ['owner','lease','fence','source','cohort','exact_replay']
        RESULT['restore_after_expired_observation'] = {'actual_candidate_deadline': '2000-01-01 00:00:00+00',
            'database_clock_confirmed_expired': True, 'only_disposable_source_hash_repinned': True,
            'application_rows_and_audit_preserved': True}

    def test_install_replay_and_explicit_bounds_rejected(self):
        for old,new in [("SET LOCAL statement_timeout='8s'", "SET LOCAL statement_timeout='9s'"),
                        ("SET LOCAL lock_timeout='3s'", "SET LOCAL lock_timeout='4s'")]:
            self.assert_rejected(self.forward.replace(old,new))
        self.apply(self.forward)
        self.assert_rejected(self.forward, expected=self.candidate)
        RESULT['install_replay_and_bounds_rejected'] = True


