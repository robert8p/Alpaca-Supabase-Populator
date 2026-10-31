"""Exact v76 cursor semantics, authenticated claim behavior and atomic SQL guards.

The database tests use only the explicitly configured disposable PostgreSQL.
Retained production sources are renamed into its isolated fixture. No provider,
HTTP server, deployment, production connection or runtime retry change occurs.
"""
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch

import test_rpc_lock_abort_retry_postgres as live

ROOT = Path(__file__).resolve().parents[2]
REVIEW = ROOT / 'review/recovery-v76/claim-cursor-repair'
FORWARD = ROOT / 'sql/astra_backfill_claim_provider_cursor_v76.sql'
RESTORE = ROOT / 'sql/astra_backfill_claim_provider_cursor_restore_v76.sql'
BASE = '28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44'
AFTER = 'dbe8eb5a563eaf9e8e00678045f8a28da65c8c4b83b4a3295c4eb32c05f50fbf'
RUN = 'fixed3000-20250901-20260731-v1-20261030'
OWNER = 'root-replacement-20261030T042603Z'
TARGET = 'astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'
RESULT = {'production': 'NOT_RUN', 'postgresql': 'ACTUAL_DISPOSABLE', 'http': 'NOT_USED', 'cases': {}}


def digest(text):
    return sha256(text.encode()).hexdigest()


def compact(value):
    return json.dumps(value, separators=(',', ':'), sort_keys=True)


def cursor(source):
    return re.search(r'  FOR v_dependency IN\n(.*?)\n  LOOP\n', source, re.S).group(1)


class ClaimCursorSourceTests(unittest.TestCase):
    def test_exact_inverse_and_reproducible_guarded_sources(self):
        before = (REVIEW / 'baseline_private_dispatch_v76.sql').read_text()
        after = (REVIEW / 'candidate_private_claim_cursor_v76.sql').read_text()
        self.assertEqual((digest(before), digest(after)), (BASE, AFTER))
        self.assertEqual(after.replace(cursor(after), cursor(before), 1), before)
        spec = importlib.util.spec_from_file_location('claim_cursor_builder_v76', REVIEW / 'build_claim_cursor_repair_v76.py')
        builder = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(builder)
        self.assertEqual(FORWARD.read_text(), builder.build())
        self.assertEqual(RESTORE.read_text(), builder.build(True))
        for path in (FORWARD, RESTORE):
            text = path.read_text()
            shell = re.sub(r'\$claim_replacement\$.*?\$claim_replacement\$', "'reviewed source'", text, flags=re.S)
            self.assertEqual(shell.count('EXECUTE v_replacement;'), 1)
            self.assertNotRegex(shell, r'(?im)^\s*(GRANT|REVOKE|INSERT|UPDATE|DELETE|ALTER|CREATE)\b')
            self.assertLess(shell.index('PERFORM pg_catalog.pg_advisory_xact_lock('), shell.index('PERFORM 1 FROM astra_ingestion_v1.backfill_runs_v2'))
            self.assertEqual(shell.count("current_setting('statement_timeout')<>'8s'"), 1)
            self.assertEqual(shell.count('v_pin_metadata IS DISTINCT FROM'), 2)
            self.assertIn('v_run_after IS DISTINCT FROM v_run_before', shell)
        RESULT['cases']['exact_source_inverse'] = {'before': BASE, 'after': AFTER, 'changed_blocks': 1}

    def test_dsn_admission_both_workflow_contexts(self):
        with patch.dict(os.environ, {'GITHUB_WORKFLOW': 'ASTRA ingestion qualification'}, clear=True):
            with self.assertRaisesRegex(RuntimeError, 'ASTRA_INGESTION_POSTGRES_TEST_URL is required'):
                ClaimCursorPostgreSQLTests.setUpClass()
        for values in ({}, {'GITHUB_WORKFLOW': 'release-gate'}):
            with patch.dict(os.environ, values, clear=True):
                with self.assertRaisesRegex(unittest.SkipTest, 'dedicated ASTRA ingestion qualification gate'):
                    ClaimCursorPostgreSQLTests.setUpClass()


class ClaimCursorPostgreSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        live.PostgreSQLLockAbortTests.setUpClass.__func__(cls)
        f = cls.fixture('runTest')
        cls.raw_before = (REVIEW / 'baseline_private_dispatch_v76.sql').read_text()
        cls.raw_after = (REVIEW / 'candidate_private_claim_cursor_v76.sql').read_text()
        assert digest(cls.raw_before) == BASE and digest(cls.raw_after) == AFTER
        cls.before = cls.adapt(cls.raw_before)
        cls.after = cls.adapt(cls.raw_after)
        cls.pins = json.loads((REVIEW / 'claim_cursor_guard_pins_v76.json').read_text())
        with f.admin() as conn:
            shared = (ROOT / 'review/recovery-v74/shared-field-cache/candidate_shared_refresh_field_cache_v74.sql').read_text()
            assert digest(shared) == '7f538bf47cb5e74050c20266e01cbe9d6521c1a65663aaf2e0fe38d62041f1a4'
            conn.execute(cls.adapt(shared))
            maintain = (ROOT / 'review/recovery-v72/readback-transaction-race/candidate_maintain_readback_transaction_v72.sql').read_text()
            assert digest(maintain) == '6c880114a645c8a9167d5260c4aeabf58a10617c4244cf0340be1d6cf4bf0ce7'
            conn.execute(cls.adapt(maintain))
            source_capture = ROOT / 'review/rpc-lock-rollback-retry-proposal/retry_closure_sources.json'
            assert sha256(source_capture.read_bytes()).hexdigest() == 'e0c98a675ee0dd27ec18853f8fc74c2ad9cdf14923812a7a5899f678fd46fd88'
            recheck = next(r['definition'] for r in json.loads(source_capture.read_text())['functions'] if r['signature']=='astra_ingestion_v1.backfill_recheck_page_v2(text,integer)')
            assert digest(recheck) == '0ccd4018d16e3ed3932176d2886fe78c2c1b442d70473d71e137d86e7b6dfb37'
            conn.execute(cls.adapt(recheck))
            actual = conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d', (cls.adapt(TARGET),)).fetchone()['d']
            assert cls.normalize(actual) == cls.raw_before
            cls.actual_metadata = conn.execute("SELECT to_jsonb(p)-'prosrc' m FROM pg_proc p WHERE oid=%s::regprocedure", (cls.adapt(TARGET),)).fetchone()['m']
            cls.actual_pins = []
            for row in cls.pins['pins']:
                actual = conn.execute("SELECT pg_get_functiondef(p.oid) d,to_jsonb(p)-'prosrc' m FROM pg_proc p WHERE oid=%s::regprocedure", (cls.adapt(row['signature']),)).fetchone()
                assert digest(cls.normalize(actual['d'])) == row['sha256'], row['signature']
                pin = dict(signature=cls.adapt(row['signature']), sha256=digest(actual['d']))
                if 'metadata_sha256' in row:
                    pin.update(oid=actual['m']['oid'], metadata_sha256=conn.execute("SELECT encode(sha256(convert_to((to_jsonb(p)-'prosrc')::text,'UTF8')),'hex') h FROM pg_proc p WHERE oid=%s::regprocedure", (cls.adapt(row['signature']),)).fetchone()['h'])
                else:
                    pin['metadata'] = actual['m']
                cls.actual_pins.append(pin)
            RESULT['postgresql_version'] = conn.execute('SHOW server_version').fetchone()['server_version']
        cls.forward_template = cls.wrapper(FORWARD.read_text())
        cls.restore_template = cls.wrapper(RESTORE.read_text())

    rewrite = classmethod(live.PostgreSQLLockAbortTests.rewrite.__func__)
    full_query = staticmethod(live.PostgreSQLLockAbortTests.full_query)
    task = live.PostgreSQLLockAbortTests.task
    call = live.PostgreSQLLockAbortTests.call
    claim = live.PostgreSQLLockAbortTests.claim
    page = live.PostgreSQLLockAbortTests.page
    fence = staticmethod(live.PostgreSQLLockAbortTests.fence)

    @classmethod
    def adapt(cls, text):
        f = cls.fixture('runTest')
        return re.sub(r'\banon\b', f.gateway, cls.rewrite(text).replace('public.astra_ingestion_rpc_v1', 'public.' + f.endpoint))

    @classmethod
    def normalize(cls, text):
        for local, production in cls.production_normalization.items():
            text = text.replace(local, production)
        return text

    @classmethod
    def wrapper(cls, text):
        # Only disposable identifiers and exact renamed-source/metadata pins
        # change. Every admission, lock, catalog and final-boundary check stays.
        text = cls.adapt(text)
        text = re.sub(r'\$claim_pins\$.*?\$claim_pins\$', '$claim_pins$' + compact(cls.actual_pins) + '$claim_pins$', text, count=1, flags=re.S)
        text = re.sub(r'\$claim_metadata\$.*?\$claim_metadata\$', '$claim_metadata$' + compact(cls.actual_metadata) + '$claim_metadata$', text, count=1, flags=re.S)
        return text.replace(BASE, digest(cls.before)).replace(AFTER, digest(cls.after))

    def setUp(self):
        live.base.runtime.BackfillRuntimeTests.setUp(self)
        self.forward = self.forward_template.replace(RUN, self.run)
        self.restore = self.restore_template.replace(RUN, self.run)
        with self.f.admin() as conn:
            conn.execute(f'DROP TRIGGER IF EXISTS claim_cursor_late_abort ON {self.f.schema}.backfill_tasks_v2')
            conn.execute(self.before)
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=jsonb_build_object('implementation_owner',%s::text,'implementation_lease_until',clock_timestamp()+interval '30 minutes') WHERE id=%s", (OWNER, self.run))

    def definition(self, conn):
        return conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d', (self.adapt(TARGET),)).fetchone()['d']

    def snapshot(self, conn):
        out = {}
        for table in ('backfill_runs_v2','backfill_members_v2','backfill_tasks_v2','backfill_workers_v2','backfill_provider_dependencies_v2','backfill_family_turn_v2','backfill_pages_v2','backfill_readbacks_v2','backfill_audit_v2'):
            out[table] = conn.execute(f"SELECT count(*) n,encode(sha256(convert_to(COALESCE(string_agg(to_jsonb(x)::text,E'\\n' ORDER BY to_jsonb(x)::text),''),'UTF8')),'hex') digest FROM {self.f.schema}.{table} x").fetchone()
        return out

    def install(self):
        with self.f.admin() as conn:
            conn.execute(self.forward)

    def test_forward_restore_preserve_data_oid_metadata_and_permissions(self):
        self.task()
        with self.f.admin() as conn:
            before = self.snapshot(conn)
            conn.commit()
            conn.execute(self.forward)
            self.assertEqual(self.definition(conn), self.after)
            self.assertEqual(before, self.snapshot(conn))
            self.assertEqual(conn.execute("SELECT to_jsonb(p)-'prosrc' m FROM pg_proc p WHERE oid=%s::regprocedure", (self.adapt(TARGET),)).fetchone()['m'], self.actual_metadata)
            for role in (self.f.gateway, self.f.outsider):
                self.assertFalse(conn.execute("SELECT has_function_privilege(%s,%s,'EXECUTE') a", (role,self.adapt(TARGET))).fetchone()['a'])
            conn.commit()
            conn.execute(self.restore)
            self.assertEqual(self.definition(conn), self.before)
            self.assertEqual(before, self.snapshot(conn))
        RESULT['cases']['forward_restore'] = {'all_sampled_rows_unchanged': True, 'full_metadata_oid_acl': True, 'catalog_guards': True}

    def test_semantic_matrix_empty_null_duplicate_status_provider_and_run(self):
        with self.f.admin() as conn:
            conn.execute('CREATE TEMP TABLE cc_runs(id text,status text); CREATE TEMP TABLE cc_tasks(run_id text,provider text,status text,kind text)')
            old = cursor(self.raw_before).replace('astra_ingestion_v1.backfill_runs_v2','cc_runs').replace('astra_ingestion_v1.backfill_tasks_v2','cc_tasks')
            new = cursor(self.raw_after).replace('astra_ingestion_v1.backfill_runs_v2','cc_runs').replace('astra_ingestion_v1.backfill_tasks_v2','cc_tasks')
            cases = [([], []), ([('r','ACTIVE')], []), ([('r','PAUSED')], [('r','Alpaca','PENDING','k')]),
                ([('r','ACTIVE')], [('r','Alpaca','PENDING','k')]*7+[('r','Massive','RETRY_WAIT','k')]*3),
                ([('r','ACTIVE'),('s','PAUSED'),(None,'ACTIVE')], [(r,p,s,'k') for r in ('r','s','other',None) for p in ('Alpaca','Massive','Other',None) for s in ('PENDING','RETRY_WAIT','BLOCKED_EXTERNAL','RUNNING','INGESTED',None)])]
            for runs,tasks in cases:
                conn.execute('TRUNCATE cc_runs,cc_tasks')
                for row in runs: conn.execute('INSERT INTO cc_runs VALUES(%s,%s)',row)
                for row in tasks: conn.execute('INSERT INTO cc_tasks VALUES(%s,%s,%s,%s)',row)
                a = conn.execute(old+' ORDER BY run_id,provider').fetchall()
                b = conn.execute(new+' ORDER BY run_id,provider').fetchall()
                self.assertEqual(a,b)
                self.assertEqual(len(b),len({(r['run_id'],r['provider']) for r in b}))
        RESULT['cases']['semantic_matrix'] = {'cases': len(cases), 'duplicates_nulls_statuses_providers_runs': True}

    def test_custom_and_generic_plans_keep_correlated_existing_index_lookups(self):
        with self.f.admin() as conn:
            conn.execute('CREATE TEMP TABLE cp_runs(id text PRIMARY KEY,status text); CREATE TEMP TABLE cp_tasks(run_id text,provider text,status text,kind text); CREATE INDEX cp_provider ON cp_tasks(run_id,provider,status,kind)')
            conn.execute("INSERT INTO cp_runs VALUES('active','ACTIVE'); INSERT INTO cp_tasks SELECT 'other-'||g::text,'Massive','PENDING','k' FROM generate_series(1,20000) g; INSERT INTO cp_tasks SELECT 'active',p,'RUNNING','k' FROM (VALUES('Alpaca'),('Massive')) v(p) CROSS JOIN generate_series(1,4000) g; INSERT INTO cp_tasks VALUES('active','Alpaca','PENDING','k'),('active','Massive','RETRY_WAIT','k'); ANALYZE cp_runs; ANALYZE cp_tasks")
            query = cursor(self.raw_after).replace('astra_ingestion_v1.backfill_runs_v2','cp_runs').replace('astra_ingestion_v1.backfill_tasks_v2','cp_tasks')
            conn.execute('PREPARE claim_cursor_plan AS '+query)
            plans = {}
            for mode in ('force_custom_plan','force_generic_plan'):
                conn.execute('SET LOCAL plan_cache_mode='+mode)
                plan = conn.execute('EXPLAIN (ANALYZE,BUFFERS,FORMAT JSON) EXECUTE claim_cursor_plan').fetchone()['QUERY PLAN'][0]
                nodes = []
                def visit(node):
                    if node.get('Index Name')=='cp_provider': nodes.append(node)
                    for child in node.get('Plans',[]): visit(child)
                visit(plan['Plan'])
                self.assertEqual(len(nodes),1)
                self.assertEqual(nodes[0]['Actual Loops'],2)
                self.assertLessEqual(nodes[0]['Actual Rows'],1)
                for part in ('run_id','provider'): self.assertIn(part,nodes[0]['Index Cond'])
                # PostgreSQL may keep the unchanged status restriction as an
                # index-node filter. Correlation is the portable shape claim;
                # LIMIT bounds emitted witnesses, not every examined entry.
                self.assertIn('status',nodes[0]['Index Cond']+' '+nodes[0].get('Filter',''))
                self.assertEqual(plan['Plan']['Actual Rows'],2)
                plans[mode] = plan
        RESULT['cases']['unforced_index_method_plans'] = {'plans':plans,
            'limitations':'No query parameters: these are planner-mode observations, not a distinct SPI cache test. Status may remain an index-node filter; full work and Rows Removed by Filter are retained. No production timing ratio or total-claim recovery is asserted.'}

    def test_guard_rejections_and_final_boundary_rollback(self):
        schema = self.f.schema
        source_drift = self.before.replace('DECLARE','DECLARE\n -- fixture-only drift',1)
        auth_sig = schema+'.rpc_dispatch(text,jsonb)'
        before_marker = f"WHERE id='{self.run}' FOR SHARE;"
        cases = {
            'source_drift': self.forward.replace(before_marker,before_marker+'\n EXECUTE $drift$'+source_drift+'$drift$;'),
            'target_metadata': self.forward.replace(before_marker,before_marker+f'\n ALTER FUNCTION {self.adapt(TARGET)} COST 101;'),
            'wrong_owner': self.forward.replace(before_marker,before_marker+f"\n UPDATE {schema}.backfill_runs_v2 SET metadata=jsonb_set(metadata,'{{implementation_owner}}','\"other\"') WHERE id='{self.run}';"),
            'expired_lease': self.forward.replace(before_marker,before_marker+f"\n UPDATE {schema}.backfill_runs_v2 SET metadata=jsonb_set(metadata,'{{implementation_lease_until}}','\"2000-01-01Z\"') WHERE id='{self.run}';"),
            'infinite_lease': self.forward.replace(before_marker,before_marker+f"\n UPDATE {schema}.backfill_runs_v2 SET metadata=jsonb_set(metadata,'{{implementation_lease_until}}','\"infinity\"') WHERE id='{self.run}';"),
            'wrong_fence': self.forward.replace('AND fence=1','AND fence=2'),
            'wrong_cohort': self.forward.replace("cohort_sha256='2dc0f", "cohort_sha256='3dc0f"),
            'wrong_members': self.forward.replace(')<>3000 THEN',')<>2999 THEN'),
            'inactive_install': self.forward.replace(before_marker,before_marker+f"\n UPDATE {schema}.backfill_runs_v2 SET status='PAUSED' WHERE id='{self.run}';"),
            'wrong_index': self.forward.replace("AND a.amname='btree'", "AND a.amname='hash'"),
            'wrong_timeout': self.forward.replace("SET LOCAL statement_timeout='8s'", "SET LOCAL statement_timeout='7s'"),
            'repeatable_read': self.forward.replace('BEGIN;','BEGIN ISOLATION LEVEL REPEATABLE READ;',1),
            'read_only': self.forward.replace('BEGIN;','BEGIN READ ONLY;',1),
            'pre_snapshot_auth_drift': self.forward.replace('-- CLAIM_CURSOR_BEFORE_CATALOG_SNAPSHOT',f'ALTER FUNCTION {auth_sig} COST 101;\n -- CLAIM_CURSOR_BEFORE_CATALOG_SNAPSHOT'),
            'pre_snapshot_index_drift': self.forward.replace('-- CLAIM_CURSOR_BEFORE_CATALOG_SNAPSHOT',f'DROP INDEX {schema}.backfill_tasks_provider_v2; CREATE INDEX backfill_tasks_provider_v2 ON {schema}.backfill_tasks_v2(run_id,provider,status);\n -- CLAIM_CURSOR_BEFORE_CATALOG_SNAPSHOT'),
            'after_auth_drift': self.forward.replace('-- CLAIM_CURSOR_AFTER_REPLACEMENT',f'ALTER FUNCTION {auth_sig} COST 101;\n -- CLAIM_CURSOR_AFTER_REPLACEMENT'),
            'after_catalog_drift': self.forward.replace('-- CLAIM_CURSOR_AFTER_REPLACEMENT',f'CREATE INDEX fixture_unexpected ON {schema}.backfill_workers_v2(observed_at);\n -- CLAIM_CURSOR_AFTER_REPLACEMENT'),
            'after_lease_expiry': self.forward.replace('-- CLAIM_CURSOR_AFTER_REPLACEMENT',f"UPDATE {schema}.backfill_runs_v2 SET metadata=jsonb_set(metadata,'{{implementation_lease_until}}','\"2000-01-01Z\"') WHERE id='{self.run}';\n -- CLAIM_CURSOR_AFTER_REPLACEMENT"),
            'after_run_mutation': self.forward.replace('-- CLAIM_CURSOR_AFTER_REPLACEMENT',f"UPDATE {schema}.backfill_runs_v2 SET metadata=metadata||'{{\"unexpected\":true}}'::jsonb WHERE id='{self.run}';\n -- CLAIM_CURSOR_AFTER_REPLACEMENT"),
        }
        with self.f.admin() as conn: before = self.snapshot(conn)
        checked = []
        for name,query in cases.items():
            with self.subTest(name=name):
                with self.assertRaises(self.f.psycopg.Error), self.f.admin() as conn: conn.execute(query)
                with self.f.admin() as conn:
                    self.assertEqual(self.definition(conn),self.before)
                    self.assertEqual(self.snapshot(conn),before)
                checked.append(name)
        RESULT['cases']['atomic_guard_rejections'] = checked

    def test_replay_and_paused_terminal_restore_preserve_status(self):
        self.install()
        with self.assertRaises(self.f.psycopg.Error), self.f.admin() as conn: conn.execute(self.forward)
        for status in ('PAUSED','PARTIAL_OPERATIONAL_FAILURE'):
            with self.subTest(status=status):
                with self.f.admin() as conn:
                    conn.execute(self.after)
                    conn.execute(f'UPDATE {self.f.schema}.backfill_runs_v2 SET status=%s WHERE id=%s',(status,self.run))
                    before = self.snapshot(conn)
                    conn.commit()
                    conn.execute(self.restore)
                    self.assertEqual(self.definition(conn),self.before)
                    self.assertEqual(before,self.snapshot(conn))
        with self.assertRaises(self.f.psycopg.Error), self.f.admin() as conn: conn.execute(self.restore)
        with self.f.admin() as conn:
            conn.execute(self.after)
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=jsonb_set(metadata,'{{implementation_owner}}','\"other\"') WHERE id=%s",(self.run,))
        with self.assertRaises(self.f.psycopg.Error), self.f.admin() as conn: conn.execute(self.restore)
        RESULT['cases']['restore_status_policy'] = {'statuses':['PAUSED','PARTIAL_OPERATIONAL_FAILURE'],'replay_rejected':True,'wrong_owner_rejected':True}

    def test_actual_authenticated_claim_provider_resolution_fairness_attempts_and_fence(self):
        observations = []
        for version in ('baseline','candidate'):
            if version=='candidate': self.setUp(); self.install()
            alpaca = self.task(priority=1)
            news = self.task(kind='alpaca_news',family='N01',priority=1)
            massive = self.task(kind='massive_reference',family='REF03',provider='Massive',priority=1)
            first = self.claim(['alpaca_reference','alpaca_news'],worker='cursor-alpaca')
            self.assertEqual(first['id'],alpaca)
            with self.f.admin() as conn:
                dep = conn.execute(f"SELECT state,code FROM {self.f.schema}.backfill_provider_dependencies_v2 WHERE run_id=%s AND provider='Massive'",(self.run,)).fetchone()
                self.assertEqual(dep,{'state':'BLOCKED_EXTERNAL','code':'RUNTIME_CAPABILITY_UNAVAILABLE'})
                conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET status='BLOCKED_EXTERNAL',error_code='MISSING_PROVIDER_CREDENTIAL' WHERE id=%s",(massive,))
            second = self.claim(['alpaca_reference','alpaca_news'],worker='cursor-alpaca')
            self.assertEqual(second['id'],news)
            third = self.claim(['massive_reference'],worker='cursor-massive')
            self.assertEqual(third['id'],massive)
            for claim in (first,second,third):
                self.assertEqual((claim['generation'],claim['page_attempts'],claim['attempts'],claim['run_fence']),(1,1,1,1))
            with self.f.admin() as conn:
                self.assertEqual(conn.execute(f"SELECT state FROM {self.f.schema}.backfill_provider_dependencies_v2 WHERE run_id=%s AND provider='Massive'",(self.run,)).fetchone()['state'],'AVAILABLE')
                turn = conn.execute(f'SELECT claim_turns,last_family FROM {self.f.schema}.backfill_family_turn_v2 WHERE run_id=%s',(self.run,)).fetchone()
                self.assertEqual(turn,{'claim_turns':3,'last_family':'REF03'})
                self.assertEqual(conn.execute(f'SELECT requests_reserved FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s',(self.run,)).fetchone()['requests_reserved'],0)
            with self.assertRaises(self.f.psycopg.Error) as denied:
                self.f.rpc('backfill_claim',{'worker_id':'api','supported_kinds':['alpaca_reference'],'source_revision':'v76'},actor='api')
            self.assertEqual(denied.exception.sqlstate,'PT403')
            wrong = self.fence(third); wrong['run_fence']=2
            refusal = self.f.rpc('backfill_reserve',{'claim':wrong},actor='worker')
            self.assertFalse(refusal['ok']); self.assertEqual(refusal['error']['code'],'lease_lost')
            observations.append(dict(version=version,order=['REF01','N01','REF03'],turns=3,attempts=[1,1,1],provider_resolved=True))
        RESULT['cases']['actual_claim_equivalence'] = observations

    def test_native_late_abort_rolls_back_worker_dependencies_fairness_and_attempt(self):
        self.install()
        task = self.task()
        self.task(kind='massive_reference',family='REF03',provider='Massive')
        with self.f.admin() as conn:
            conn.execute(f"CREATE OR REPLACE FUNCTION {self.f.schema}.claim_cursor_abort_fn() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $fault$ BEGIN IF NEW.status='RUNNING' THEN INSERT INTO {self.f.schema}.retry_fault_probe(note) VALUES('claim write reached'); PERFORM pg_catalog.pg_advisory_xact_lock(706314020269976); END IF; RETURN NEW; END $fault$")
            conn.execute(f'CREATE TRIGGER claim_cursor_late_abort AFTER UPDATE ON {self.f.schema}.backfill_tasks_v2 FOR EACH ROW EXECUTE FUNCTION {self.f.schema}.claim_cursor_abort_fn()')
            before = self.snapshot(conn)
        holder = self.f.admin()
        try:
            holder.execute('SELECT pg_advisory_xact_lock(706314020269976)')
            with self.assertRaises(self.f.psycopg.Error) as failed: self.claim(worker='cursor-native-abort')
            self.assertEqual(failed.exception.sqlstate,'55P03')
            with self.f.admin() as conn:
                self.assertEqual(before,self.snapshot(conn))
                self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.retry_fault_probe').fetchone()['n'],0)
        finally:
            holder.rollback(); holder.close()
        with self.f.admin() as conn: conn.execute(f'DROP TRIGGER claim_cursor_late_abort ON {self.f.schema}.backfill_tasks_v2')
        after = self.claim(worker='cursor-native-abort')
        self.assertEqual((after['id'],after['generation'],after['attempts'],after['page_attempts']),(task,1,1,1))
        RESULT['cases']['native_late_abort'] = {'sqlstate':'55P03','domain_rows_rolled_back':True,'next_claim_generation_attempts':1,'sequence_gaps_not_claimed_rolled_back':True}


if __name__ == '__main__':
    unittest.main()
