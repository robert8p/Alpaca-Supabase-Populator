"""Actual PostgreSQL guards and behavior for additive maintenance hash indexes."""
from hashlib import sha256
import json
import os
from pathlib import Path
import threading
from time import monotonic
import unittest

import test_backfill_claim_capability_filter_v2 as base
import test_backfill_runtime_v2 as runtime

ROOT=Path(__file__).resolve().parents[2]
MANIFEST=json.loads((ROOT/'review/recovery-v72/maintenance_index_forward_derivation_v72.json').read_text())
NAMES=list(MANIFEST['expected_index_definitions'])
PATHS=[ROOT/x['path'] for x in MANIFEST['forwards']]
EVIDENCE={}


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'),'Explicit disposable PostgreSQL required')
class MaintenanceTaskIndexTests(unittest.TestCase):
    rewrite=classmethod(base.CapabilityFilterPostgreSQLTests.rewrite.__func__)
    full_query=staticmethod(base.CapabilityFilterPostgreSQLTests.full_query)
    task=runtime.BackfillRuntimeTests.task
    call=runtime.BackfillRuntimeTests.call
    claim=runtime.BackfillRuntimeTests.claim
    page=runtime.BackfillRuntimeTests.page
    fence=staticmethod(runtime.BackfillRuntimeTests.fence)
    snapshot=base.CapabilityFilterPostgreSQLTests.snapshot

    @classmethod
    def setUpClass(cls):
        base.CapabilityFilterPostgreSQLTests.setUpClass.__func__(cls)
        f=cls.fixture('runTest')
        monitor=next(x for x in json.loads((ROOT/'review/recovery-v71/live_cron_functions_1331.json').read_text())
            if x['proname']=='monitor_tick_v1')
        with f.admin() as conn:conn.execute(monitor['definition'].replace('astra_ingestion_v1',f.schema))

    def setUp(self):
        base.CapabilityFilterPostgreSQLTests.setUp(self)
        with self.f.admin() as conn:
            for name in reversed(NAMES):conn.execute('DROP INDEX IF EXISTS '+self.f.schema+'.'+name)
            # The inherited status fixture deliberately drops this original
            # index per test. Restore its retained migration in the disposable
            # fixture; the live15-index admission guard remains unchanged.
            conn.execute(self.index_sql)
            pins={signature:sha256(conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (self.f.schema+'.'+signature,)).fetchone()['d'].encode()).hexdigest()
                for signature in MANIFEST['source_pins']}
        self.forwards=[]
        for path in PATHS:
            sql=path.read_text().replace('astra_ingestion_v1',self.f.schema).replace(base.LIVE_RUN,self.run)
            for signature,live in MANIFEST['source_pins'].items():sql=sql.replace(live,pins[signature])
            self.forwards.append(sql)

    def apply_pair(self):
        with self.f.admin() as conn:
            for sql in self.forwards:conn.execute(sql)

    def index_rows(self,conn):
        return conn.execute('''SELECT c.oid,c.relname,c.relowner,c.relacl,i.indisvalid,i.indisready,i.indislive,
         a.amname,pg_get_indexdef(c.oid) definition FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
         JOIN pg_am a ON a.oid=c.relam WHERE i.indrelid=%s::regclass ORDER BY c.relname''',
            (self.f.schema+'.backfill_tasks_v2',)).fetchall()

    def test_real_forward_preserves_sources_metadata_access_and_data(self):
        with self.f.admin() as conn:
            before=self.snapshot(conn)
            funcs=conn.execute('SELECT jsonb_agg(to_jsonb(p) ORDER BY oid) value FROM pg_proc p WHERE pronamespace=%s::regnamespace',(self.f.schema,)).fetchone()['value']
            indexes=self.index_rows(conn)
            table=conn.execute('SELECT relowner,relacl,relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=%s::regclass',(self.f.schema+'.backfill_tasks_v2',)).fetchone()
        self.apply_pair()
        with self.f.admin() as conn:
            after=self.index_rows(conn)
            self.assertEqual([x for x in after if x['relname'] not in NAMES],indexes)
            created=[x for x in after if x['relname'] in NAMES]
            self.assertEqual(len(created),2)
            for row in created:
                self.assertEqual(row['amname'],'hash')
                self.assertTrue(row['indisvalid'] and row['indisready'] and row['indislive'])
                self.assertEqual(row['relowner'],table['relowner'])
                self.assertIsNone(row['relacl'])
                self.assertEqual(row['definition'],MANIFEST['expected_index_definitions'][row['relname']].replace('astra_ingestion_v1',self.f.schema))
            self.assertEqual(before,self.snapshot(conn))
            self.assertEqual(funcs,conn.execute('SELECT jsonb_agg(to_jsonb(p) ORDER BY oid) value FROM pg_proc p WHERE pronamespace=%s::regnamespace',(self.f.schema,)).fetchone()['value'])
            self.assertEqual(table,conn.execute('SELECT relowner,relacl,relrowsecurity,relforcerowsecurity FROM pg_class WHERE oid=%s::regclass',(self.f.schema+'.backfill_tasks_v2',)).fetchone())
            for role in (self.f.gateway,self.f.outsider):
                self.assertFalse(conn.execute('SELECT has_table_privilege(%s,%s,\'SELECT\') yes',(role,self.f.schema+'.backfill_tasks_v2')).fetchone()['yes'])
        EVIDENCE['preservation']={'all_function_sources_and_metadata':True,'all15_existing_indexes':True,
            'table_owner_acl_rls':True,'all_application_snapshot_tables':True,'no_gateway_or_outsider_table_access':True}

    def test_exact_replay_does_not_build_or_replace_any_index(self):
        self.apply_pair()
        with self.f.admin() as conn:before=self.index_rows(conn)
        self.apply_pair()
        with self.f.admin() as conn:self.assertEqual(before,self.index_rows(conn))
        EVIDENCE['exact_replay_same_oids_and_metadata']=True

    def test_minute_before_breadth_is_rejected(self):
        with self.f.admin() as conn:
            with self.assertRaises(self.f.psycopg.Error) as error:conn.execute(self.forwards[1])
            self.assertEqual(error.exception.sqlstate,'P0001')
            self.assertIn('breadth index first',error.exception.diag.message_primary)
            conn.rollback()
            self.assertTrue(all(x['relname'] not in NAMES for x in self.index_rows(conn)))

    def test_source_index_owner_and_lease_drift_fail_closed(self):
        cases=[
            ('function_source',f'ALTER FUNCTION {self.f.schema}.backfill_maintain_v2(integer) SET statement_timeout=\'9s\''),
            ('existing_index',f'DROP INDEX {self.f.schema}.backfill_tasks_minute_alias_status_v2'),
            ('extra_index',f'CREATE INDEX unexpected_fixture_index ON {self.f.schema}.backfill_tasks_v2(id)'),
            ('owner',f"UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=jsonb_set(metadata,'{{implementation_owner}}','\"different-owner\"') WHERE id='{self.run}'"),
            ('expired_lease',f"UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=jsonb_set(metadata,'{{implementation_lease_until}}','\"2000-01-01T00:00:00Z\"') WHERE id='{self.run}'"),
            ('paused_run',f"UPDATE {self.f.schema}.backfill_runs_v2 SET status='PAUSED' WHERE id='{self.run}'"),
            ('advanced_fence',f"UPDATE {self.f.schema}.backfill_runs_v2 SET fence=fence+1 WHERE id='{self.run}'"),
        ]
        for label,mutation in cases:
            with self.subTest(label=label),self.f.admin() as conn:
                conn.execute(mutation)
                with self.assertRaises(self.f.psycopg.Error) as error:conn.execute(self.forwards[0])
                self.assertEqual(error.exception.sqlstate,'P0001')
                conn.rollback()
                self.assertTrue(all(x['relname'] not in NAMES for x in self.index_rows(conn)))
        EVIDENCE['drift_rejections']=[x[0] for x in cases]

    def test_same_name_wrong_method_or_predicate_is_never_accepted(self):
        expected=MANIFEST['expected_index_definitions'][NAMES[0]].replace('astra_ingestion_v1',self.f.schema)
        for label,wrong in [('method',expected.replace('USING hash','USING btree')),
                            ('predicate',expected.replace("'D03'::text","'D04'::text"))]:
            with self.subTest(label=label),self.f.admin() as conn:
                conn.execute(wrong)
                with self.assertRaises(self.f.psycopg.Error) as error:conn.execute(self.forwards[0])
                self.assertIn('unexpected definition',error.exception.diag.message_primary)
                conn.rollback()
                self.assertTrue(all(x['relname'] not in NAMES for x in self.index_rows(conn)))

    def test_incomplete_fixed_cohort_rejects_without_deleting_members(self):
        incomplete=self.run+'-incomplete'
        with self.f.admin() as conn:
            # Keep the existing one-ACTIVE-run invariant in this disposable
            # fixture while constructing a distinct incomplete cohort.
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET status='PAUSED' WHERE id=%s",(self.run,))
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_runs_v2
             (id,instruction_sha256,cohort_sha256,cohort_manifest_sha256,cohort_ref,scope,metadata)
             SELECT %s,instruction_sha256,cohort_sha256,cohort_manifest_sha256,cohort_ref,scope,metadata
             FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s''',(incomplete,self.run))
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_members_v2(run_id,member_id,selection_order,anchor_ticker,anchor)
             SELECT %s,member_id,selection_order,anchor_ticker,anchor FROM {self.f.schema}.backfill_members_v2
             WHERE run_id=%s AND selection_order<=2999''',(incomplete,self.run))
        with self.f.admin() as conn:
            with self.assertRaises(self.f.psycopg.Error) as error:conn.execute(self.forwards[0].replace(self.run,incomplete))
            self.assertIn('fixed cohort differs',error.exception.diag.message_primary)
            conn.rollback()
            self.assertTrue(all(x['relname'] not in NAMES for x in self.index_rows(conn)))
        EVIDENCE['incomplete_cohort_rejected_without_mutating_members']=True

    def test_failure_after_build_and_late_source_drift_roll_back_atomically(self):
        injected=[
            ('explicit_failure',self.forwards[0].replace(' v_created:=true;'," v_created:=true; RAISE EXCEPTION 'Injected failure after build';")),
            ('late_source',self.forwards[0].replace(' v_created:=true;',f" v_created:=true; ALTER FUNCTION {self.f.schema}.backfill_maintain_v2(integer) SET statement_timeout='9s';")),
            ('source_before_snapshot',self.forwards[0].replace(' SELECT jsonb_agg(to_jsonb(p) ORDER BY p.oid) INTO v_before_functions',
                f" ALTER FUNCTION {self.f.schema}.backfill_maintain_v2(integer) SET statement_timeout='9s';\n SELECT jsonb_agg(to_jsonb(p) ORDER BY p.oid) INTO v_before_functions")),
            ('lease_after_build',self.forwards[0].replace(' v_created:=true;',
                f" v_created:=true; UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=jsonb_set(metadata,'{{implementation_lease_until}}','\"2000-01-01T00:00:00Z\"') WHERE id='{self.run}';")),
        ]
        with self.f.admin() as conn:
            before=self.index_rows(conn)
            source=conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',(self.f.schema+'.backfill_maintain_v2(integer)',)).fetchone()['d']
        for label,sql in injected:
            with self.subTest(label=label),self.f.admin() as conn:
                with self.assertRaises(self.f.psycopg.Error):conn.execute(sql)
                conn.rollback()
                self.assertEqual(before,self.index_rows(conn))
                self.assertEqual(source,conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',(self.f.schema+'.backfill_maintain_v2(integer)',)).fetchone()['d'])
        self.apply_pair()
        with self.f.admin() as conn:
            before=self.index_rows(conn)
            sql=self.forwards[0].replace(" IF to_regclass(format('%I.%I',v_namespace,v_target)) IS NOT NULL THEN",
                f" ALTER FUNCTION {self.f.schema}.backfill_maintain_v2(integer) SET statement_timeout='9s';\n IF to_regclass(format('%I.%I',v_namespace,v_target)) IS NOT NULL THEN")
            with self.assertRaises(self.f.psycopg.Error):conn.execute(sql)
            conn.rollback()
            self.assertEqual(before,self.index_rows(conn))
        EVIDENCE['postbuild_failure_rollback_and_final_source_guard']=True

    def test_existing_global_lock_budget_fails_without_any_build(self):
        ready=threading.Event()
        release=threading.Event()
        failures=[]
        def holder():
            try:
                with self.f.admin() as conn:
                    conn.execute('SELECT pg_advisory_xact_lock(706314020261028)')
                    ready.set();release.wait(5)
                    conn.rollback()
            except Exception as error:failures.append(type(error).__name__);ready.set()
        thread=threading.Thread(target=holder,daemon=True)
        thread.start();self.assertTrue(ready.wait(2))
        try:
            with self.f.admin() as conn:
                started=monotonic()
                with self.assertRaises(self.f.psycopg.Error) as error:conn.execute(self.forwards[0])
                elapsed=monotonic()-started
                self.assertEqual(error.exception.sqlstate,'55P03')
                self.assertTrue(2.7<=elapsed<4.5)
                conn.rollback()
                self.assertTrue(all(x['relname'] not in NAMES for x in self.index_rows(conn)))
        finally:release.set();thread.join(2)
        self.assertFalse(thread.is_alive());self.assertEqual(failures,[])
        EVIDENCE['lock_budget']={'sqlstate':'55P03','seconds':elapsed,'no_index_built':True}

    def test_authenticated_real_page_successor_and_lost_ack_after_indexes(self):
        self.apply_pair()
        runtime.BackfillRuntimeTests.test_real_page_auto_successor_and_lost_ack_readback(self)
        EVIDENCE['authenticated_real_page_successor_and_lost_ack']=True


if __name__=='__main__':unittest.main()
