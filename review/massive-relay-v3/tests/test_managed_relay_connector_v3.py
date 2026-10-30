"""Actual PostgreSQL qualification of a separately approved v3 transport installer.

Synthetic approvals and loopback-only fixture; no production calls or credentials.
Runtime authorization/fence/integrity tests are inherited unchanged from frozen v2.
"""
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import unittest
import test_backfill_massive_relay_postgres_v2 as v2
import test_backfill_retained_s02_v2 as retained

ROOT=Path(__file__).resolve().parents[3]
V3=ROOT/'review/massive-relay-v3'
FIXED_RUN=v2.FIXED_RUN
PLACEHOLDER=v2.PLACEHOLDER
REVIEW_ID='managed-massive-relay-v3-review-20261030'
REVIEW_HASH='a40f86ad49918644c5443586644b66ca9748ede1a91ffb8a09cdca0b522963d5'


def synthetic_approval(**changes):
    return {**v2.synthetic_approval(), 'review_id':REVIEW_ID, 'scope_sha256':REVIEW_HASH, **changes}


class ConnectorCompatibleRelayPostgresTests(v2.ManagedRelayPostgresTests):
    @classmethod
    def setUpClass(cls):
        # Latest qualified stage3: feature reuse, identity, nonminute coverage,
        # retained S02, plus bounded planning/adaptive/fair recovery forwards.
        retained.RetainedS02Tests.setUpClass.__func__(cls)
        f = cls.fixture('runTest')
        def rendered(filename):
            return ((V3/'candidates/sql'/filename) if filename=='astra_backfill_massive_relay_v3.sql' else (ROOT/'sql'/filename)).read_text().replace('astra_ingestion_v1',f.schema).replace('astra_ingestion_rpc_owner_v1',f.owner).replace(FIXED_RUN,PLACEHOLDER).replace('supabase_migrations.schema_migrations',f.schema+'.migration_history_fixture')
        cls.migration=rendered('astra_backfill_massive_relay_v3.sql')
        with f.admin() as conn:
            for name in ('astra_backfill_planner_v2.sql','astra_backfill_adaptive_pages_v2.sql','astra_backfill_recovery_priority_v2.sql'):
                conn.execute(cls.rewrite((ROOT/'sql'/name).read_text()))
            conn.execute(rendered('astra_backfill_pacing_fairness_v2.sql'))
            conn.execute(f'''CREATE TABLE {f.schema}.migration_history_fixture(version text,name text,statements text[],
                created_by text,idempotency_key text UNIQUE,rollback text)''')
            conn.execute(f'''INSERT INTO {f.schema}.backfill_runs_v2(id,instruction_sha256,cohort_sha256,cohort_manifest_sha256,cohort_ref,scope)
                VALUES(%s,%s,%s,%s,'synthetic-review-gate','{{}}')''',(PLACEHOLDER,'1'*64,
                '2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec',
                '4134b415e2c26fcde9fced749c0d54ef51376e23f0d2f8c6ce9ef562f9fab99f'))
            cls.outer_before = conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (f.schema+'.rpc_dispatch(text,jsonb)',)).fetchone()['d']
            cls.outer_metadata_before = conn.execute("SELECT to_jsonb(p)-'prosrc' value FROM pg_proc p WHERE oid=%s::regprocedure",
                (f.schema+'.rpc_dispatch(text,jsonb)',)).fetchone()['value']
        cls.migration=cls.migration.replace('0616b84ec99710083681c2ed7bc2b7dd7acff9ef2f809d84b84c5f724a71fe96',sha256(cls.outer_before.encode()).hexdigest())
        cls.gate_rejections=[]
        cls.synthetic_approved=synthetic_approval(approved_migration_sha256=sha256(cls.migration.encode()).hexdigest(),
            approved_rpc_dispatch_sha256=sha256(cls.outer_before.encode()).hexdigest(),
            approved_edge_index_sha256=sha256((ROOT/'supabase/functions/population-top3000-news-v1/index.ts').read_bytes()).hexdigest(),
            approved_edge_module_sha256=sha256((ROOT/'supabase/functions/population-top3000-news-v1/replacement-relay-v2.mjs').read_bytes()).hexdigest(),
            approved_python_adapter_sha256=sha256((ROOT/'astra_ingestion/backfill_massive_relay_v2.py').read_bytes()).hexdigest(),
            approved_worker_base_sha256=sha256((ROOT/'astra_ingestion/backfill_worker_v2.py').read_bytes()).hexdigest(),
            approved_worker_integration_sha256=sha256((ROOT/'review/massive-relay-v2/worker-integration.patch').read_bytes()).hexdigest(),
            approved_worker_source_sha256=sha256((ROOT/'review/massive-relay-v2/backfill_worker_v2.py.proposed').read_bytes()).hexdigest())
        now=datetime.now(timezone.utc)
        invalid_changes=[
            {'state':'AWAITING_ACTION_TIME_CONFIRMATION'},
            {'review_id':'managed-massive-relay-v2-review-20261030'},
            {'scope_sha256':'7e253852f3173c9c3b7ba6d919e4d8abe82cb949424096beee56ddc0e2c20fbe'},
            {'review_id':'managed-massive-relay-v2-review-20261030','scope_sha256':'7e253852f3173c9c3b7ba6d919e4d8abe82cb949424096beee56ddc0e2c20fbe'},
            {'scope_sha256':'f'*64},
            {'confirmation_source':'BLANKET_PRIOR_APPROVAL'},
            {'confirmation_ref':''},{'confirmation_ref':'x'*513},
            {'approved_at':'2026-10-30T09:53:00Z'},
            {'approved_at':(now-timedelta(minutes=15,seconds=1)).isoformat()},
            {'approved_at':(now+timedelta(minutes=1,seconds=30)).isoformat()},
            {'approved_at':None},{'approved_at':'not-a-timestamp'},
            {'candidate_applied':True},
            *[{field:'f'*64} for field in (
                'approved_migration_sha256','approved_rpc_dispatch_sha256','approved_edge_index_sha256',
                'approved_edge_module_sha256','approved_python_adapter_sha256','approved_worker_base_sha256',
                'approved_worker_integration_sha256','approved_worker_source_sha256')]
        ]
        invalid=[{},*[{**cls.synthetic_approved,**change} for change in invalid_changes]]
        for approval in invalid:
            with f.admin() as conn:
                conn.execute(f'UPDATE {f.schema}.backfill_runs_v2 SET metadata=%s::jsonb WHERE id=%s',
                    (json.dumps({'massive_relay_security_confirmation':approval}),PLACEHOLDER))
            try:
                with f.admin() as conn:conn.execute(cls.migration)
            except f.psycopg.Error as error:
                assert 'exact current action-time security confirmation' in str(error),str(error)
                cls.gate_rejections.append(approval)
            else:
                raise AssertionError('Held candidate installed without exact action-time confirmation')
            with f.admin() as conn:
                assert conn.execute('SELECT to_regclass(%s) obj',(f.schema+'.backfill_relay_dispatches_v2',)).fetchone()['obj'] is None
                assert conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                    (f.schema+'.rpc_dispatch(text,jsonb)',)).fetchone()['d']==cls.outer_before
        with f.admin() as conn:
            conn.execute(f'UPDATE {f.schema}.backfill_runs_v2 SET metadata=%s::jsonb WHERE id=%s',
                (json.dumps({'massive_relay_security_confirmation':cls.synthetic_approved}),PLACEHOLDER))
        wrapper_template=(V3/'apply-migration-wrapper-no-final-lf.txt').read_text()
        wrapper_template=wrapper_template.replace('supabase_migrations.schema_migrations',f.schema+'.migration_history_fixture')
        wrapper_template=wrapper_template.replace('<ACCOUNT_IDENTIFIER>','fixture-local-actor')
        cls.wrapped_migration=wrapper_template.replace('<EXACT_APPROVED_MIGRATION_BYTES>',cls.migration)
        assert cls.wrapped_migration.endswith('commit;')
        start='-- ASTRA_RELAY_REVIEW_SQL_BEGIN_V3\n'
        extra_boundary=cls.migration.replace(start,start+start,1)
        wrong_history=cls.wrapped_migration.replace('array[$USQrtAZZkmYPmewYmQrd$'+cls.migration,
            'array[$USQrtAZZkmYPmewYmQrd$'+cls.migration+'\n-- changed history copy\n',1)
        cls.wrapper_candidates={
            'duplicate_executable_boundary':wrapper_template.replace('<EXACT_APPROVED_MIGRATION_BYTES>',extra_boundary),
            'changed_history_copy':wrong_history,
            'trailing_sql':cls.wrapped_migration+'SELECT 1;\n',
            'injected_between_body_and_history':cls.wrapped_migration.replace(cls.migration+';',cls.migration+';SELECT 1;',1),
            'wrong_migration_name':wrapper_template.replace('astra_backfill_massive_relay_v3','unreviewed_migration').replace('<EXACT_APPROVED_MIGRATION_BYTES>',cls.migration),
            'old_migration_name':wrapper_template.replace('astra_backfill_massive_relay_v3','astra_backfill_massive_relay_v2').replace('<EXACT_APPROVED_MIGRATION_BYTES>',cls.migration),
            'short_tag':cls.wrapped_migration.replace('$USQrtAZZkmYPmewYmQrd$','$bad$'),
            'account_newline':cls.wrapped_migration.replace('fixture-local-actor','fixture\nactor'),
            'account_space':cls.wrapped_migration.replace('fixture-local-actor','fixture actor'),
            'account_empty':cls.wrapped_migration.replace('fixture-local-actor',''),
            'account_overlong':cls.wrapped_migration.replace('fixture-local-actor','a'*255),
            'two_final_lf':cls.wrapped_migration+'\n\n',
            'final_crlf':cls.wrapped_migration+'\r\n',
            'final_space':cls.wrapped_migration+' ',
            'final_tab':cls.wrapped_migration+'\t',
            'trailing_comment':cls.wrapped_migration+'\n-- trailing comment\n',
            'prefix_comment':'-- extra prefix\n'+cls.wrapped_migration,
            'prefix_space':' '+cls.wrapped_migration,
            'changed_wrapper_case':cls.wrapped_migration.replace('begin;\n','BEGIN;\n',1),
            'changed_wrapper_separator':cls.wrapped_migration.replace('-- apply sql from post body\n','-- apply sql from post body\n\n',1),
            'raw_extra_lf':cls.migration+'\n',
            'raw_trailing_comment':cls.migration+'\n-- changed candidate\n',
            'raw_trailing_sql':cls.migration+'SELECT 1;',
            'raw_missing_final_lf':cls.migration[:-1],
            'changed_body_and_history':wrapper_template.replace('<EXACT_APPROVED_MIGRATION_BYTES>',cls.migration.replace('-- Stateless managed-key','-- Changed managed-key',1)),
        }
        cls.wrapper_rejections=[]
        for label,candidate in cls.wrapper_candidates.items():
            with f.assertRaises(f.psycopg.Error),f.admin() as conn:conn.execute(candidate)
            cls.wrapper_rejections.append({'case':label,'sha256':sha256(candidate.encode()).hexdigest()})
            with f.admin() as conn:
                assert conn.execute('SELECT to_regclass(%s) obj',(f.schema+'.backfill_relay_dispatches_v2',)).fetchone()['obj'] is None
                assert conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                    (f.schema+'.rpc_dispatch(text,jsonb)',)).fetchone()['d']==cls.outer_before
                assert conn.execute(f'SELECT count(*) n FROM {f.schema}.migration_history_fixture').fetchone()['n']==0
                assert conn.execute(f"SELECT metadata->'massive_relay_security_confirmation' a FROM {f.schema}.backfill_runs_v2 WHERE id=%s",(PLACEHOLDER,)).fetchone()['a']==cls.synthetic_approved
        # Both exact wrapper variants and exact raw-file transport pass preflight.
        # Existing internal RPC owner remains denied CREATE; this proves positive
        # transport admission without allowing a second installation.
        cls.positive_preflights=[]
        for label,candidate in [('EXACT_RAW_REVIEWED_FILE',cls.migration),
                ('EXACT_WRAPPER_FINAL_LF',cls.wrapped_migration+'\n'),
                ('EXACT_WRAPPER_NO_FINAL_LF',cls.wrapped_migration)]:
            try:
                with f.admin() as conn:
                    conn.execute(f'SET LOCAL ROLE {f.owner}')
                    conn.execute(candidate)
            except f.psycopg.Error as error:
                assert error.sqlstate=='42501' and 'permission denied for schema' in str(error),(label,str(error))
                cls.positive_preflights.append(label)
            else: raise AssertionError('Existing RPC owner unexpectedly gained schema CREATE permission')
        cls.raw_preflight_passed=True
        with f.admin() as conn:
            conn.execute(cls.wrapped_migration)
            cls.history_record=conn.execute(f'SELECT * FROM {f.schema}.migration_history_fixture').fetchone()
            cls.applied_approval=conn.execute(f'SELECT metadata->\'massive_relay_security_confirmation\' value FROM {f.schema}.backfill_runs_v2 WHERE id=%s',
                (PLACEHOLDER,)).fetchone()['value']
            cls.install_audits=conn.execute(f"SELECT count(*) n FROM {f.schema}.backfill_audit_v2 WHERE run_id=%s AND action='MANAGED_MASSIVE_RELAY_REVIEW_APPLIED'",
                (PLACEHOLDER,)).fetchone()['n']
            cls.outer_after = conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (f.schema+'.rpc_dispatch(text,jsonb)',)).fetchone()['d']
            cls.outer_metadata_after = conn.execute("SELECT to_jsonb(p)-'prosrc' value FROM pg_proc p WHERE oid=%s::regprocedure",
                (f.schema+'.rpc_dispatch(text,jsonb)',)).fetchone()['value']
            cls.relay_definition = conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (f.schema + '.backfill_relay_v2(text,jsonb)',)).fetchone()['d']

    def test_held_installer_fails_before_any_grant_or_dispatch_extension(self):
        self.assertEqual(len(self.gate_rejections),23)
        self.assertTrue(self.applied_approval['candidate_applied'])
        self.assertEqual(self.applied_approval['applied_migration_sha256'],sha256(self.migration.encode()).hexdigest())
        self.assertEqual(self.install_audits,1)
        with self.assertRaises(self.f.psycopg.Error),self.f.admin() as conn:conn.execute(self.migration)
        scope=json.loads((ROOT/'evidence/replacement-managed-relay-review-scope-v3.json').read_text())
        actual=sha256(json.dumps(scope,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
        self.assertEqual(actual,REVIEW_HASH)
        self.assertIn(REVIEW_HASH,(V3/'candidates/sql/astra_backfill_massive_relay_v3.sql').read_text())

    def test_exact_supabase_transport_preserves_the_reviewed_bytes_and_rejects_extra_sql(self):
        self.assertEqual(len(self.wrapper_rejections),25)
        self.assertEqual(len(self.positive_preflights),3)
        self.assertTrue(self.raw_preflight_passed)
        self.assertEqual(self.history_record['name'],'astra_backfill_massive_relay_v3')
        self.assertEqual(self.history_record['statements'],[self.migration])
        self.assertEqual(self.history_record['created_by'],'fixture-local-actor')
        self.assertEqual(self.applied_approval['applied_migration_sha256'],sha256(self.migration.encode()).hexdigest())

    def test_runtime_old_review_or_scope_is_not_v3_authority(self):
        claim=self.owned()
        cases=[{'review_id':'managed-massive-relay-v2-review-20261030'},
               {'scope_sha256':'7e253852f3173c9c3b7ba6d919e4d8abe82cb949424096beee56ddc0e2c20fbe'},
               {'confirmation_source':'BLANKET_PRIOR_APPROVAL'}, {'state':'HELD_APPROVAL_EXPIRED_TRANSPORT_MISMATCH'}]
        for changes in cases:
            with self.subTest(changes=changes):
                with self.f.admin() as conn:
                    conn.execute(f'UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=%s::jsonb WHERE id=%s',
                        (json.dumps({'massive_relay_security_confirmation':{**self.synthetic_approved,**changes}}),self.run))
                probe=self.f.rpc('backfill_relay_probe',{},actor='worker')
                self.assertFalse(probe['ok']);self.assertEqual(probe['error']['code'],'conflict')
                self.rejected(self.payload(claim),'conflict')
        self.assertEqual(self.audit(),[])

    def test_readonly_probe_uses_exact_parser_and_always_aborts_before_history(self):
        probe=(V3/'transport_readonly_probe_v3.sql').read_text().replace('supabase_migrations.schema_migrations',self.f.schema+'.migration_history_fixture')
        wrapper=(V3/'apply-migration-wrapper-no-final-lf.txt').read_text().replace('supabase_migrations.schema_migrations',self.f.schema+'.migration_history_fixture')
        wrapper=wrapper.replace('astra_backfill_massive_relay_v3','astra_backfill_massive_relay_v3_transport_probe').replace('<ACCOUNT_IDENTIFIER>','fixture-local-actor')
        with self.f.admin() as conn:
            before=conn.execute(f"SELECT metadata FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s",(self.run,)).fetchone()['metadata']
            history=conn.execute(f'SELECT count(*) n FROM {self.f.schema}.migration_history_fixture').fetchone()['n']
            definition=conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',(self.f.schema+'.rpc_dispatch(text,jsonb)',)).fetchone()['d']
        for variant,candidate in [
            ('EXACT_RAW_REVIEWED_FILE',probe),
            ('EXACT_WRAPPER_NO_FINAL_LF',wrapper.replace('<EXACT_APPROVED_MIGRATION_BYTES>',probe)),
            ('EXACT_WRAPPER_FINAL_LF',wrapper.replace('<EXACT_APPROVED_MIGRATION_BYTES>',probe)+'\n')]:
            with self.subTest(variant=variant):
                with self.assertRaises(self.f.psycopg.Error) as error,self.f.admin() as conn:conn.execute(candidate)
                self.assertEqual(error.exception.sqlstate,'P0001')
                message=error.exception.diag.message_primary
                self.assertTrue(message.startswith('ASTRA_RELAY_V3_TRANSPORT_PROBE_ACCEPTED '),message)
                receipt=json.loads(message.split(' ',1)[1])
                self.assertEqual(receipt['probe_sha256'],sha256(probe.encode()).hexdigest())
                self.assertEqual(receipt['probe_bytes'],len(probe.encode()))
                self.assertEqual(receipt['final_body_byte_ascii'],10)
                self.assertEqual(receipt['wrapper_variant'],variant)
                self.assertTrue(receipt['read_only'])
                self.assertFalse(receipt['migration_applied'])
                self.assertFalse(receipt['approval_modified'])
                self.assertEqual(receipt['provider_requests'],0)
                with self.f.admin() as conn:
                    self.assertEqual(conn.execute(f"SELECT metadata FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s",(self.run,)).fetchone()['metadata'],before)
                    self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.migration_history_fixture').fetchone()['n'],history)
                    self.assertEqual(conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',(self.f.schema+'.rpc_dispatch(text,jsonb)',)).fetchone()['d'],definition)
        malformed=wrapper.replace('<EXACT_APPROVED_MIGRATION_BYTES>',probe)+'\n\n'
        with self.assertRaises(self.f.psycopg.Error) as error,self.f.admin() as conn:conn.execute(malformed)
        self.assertNotIn('ASTRA_RELAY_V3_TRANSPORT_PROBE_ACCEPTED',error.exception.diag.message_primary)


if __name__=='__main__': unittest.main()
