"""Actual capability RPC / single-use dispatch admission, with no provider calls."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import unittest
import uuid

from astra_ingestion.backfill_provider_v2 import request_for
from astra_ingestion.backfill_provider_v2 import ProviderProblem
import test_backfill_family_fairness_v2 as fairness
import test_backfill_massive_relay_v2 as relay_fixture
import test_backfill_retained_s02_v2 as retained
import test_backfill_runtime_v2 as runtime

ROOT = Path(__file__).resolve().parents[2]
FIXED_RUN = 'fixed3000-20250901-20260731-v1-20261030'
PLACEHOLDER = 'relay-qualification-fixed-run'
REVIEW_ID = 'managed-massive-relay-v2-review-20261030'
REVIEW_HASH = '7e253852f3173c9c3b7ba6d919e4d8abe82cb949424096beee56ddc0e2c20fbe'


def synthetic_approval(**changes):
    return {'state':'APPROVED_AT_ACTION_TIME','review_id':REVIEW_ID,'scope_sha256':REVIEW_HASH,
        'confirmation_source':'EXPLICIT_USER_ACTION_TIME_CONFIRMATION','confirmation_ref':'SYNTHETIC_LOCAL_TEST_ONLY',
        'candidate_applied':False,'approved_at':datetime.now(timezone.utc).isoformat(),**changes}


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'), 'Explicit disposable PostgreSQL required')
class ManagedRelayPostgresTests(unittest.TestCase):
    rewrite=classmethod(retained.RetainedS02Tests.rewrite.__func__)

    @classmethod
    def setUpClass(cls):
        # Latest qualified stage3: feature reuse, identity, nonminute coverage,
        # retained S02, plus bounded planning/adaptive/fair recovery forwards.
        retained.RetainedS02Tests.setUpClass.__func__(cls)
        f = cls.fixture('runTest')
        def rendered(filename):
            return (ROOT/'sql'/filename).read_text().replace('astra_ingestion_v1',f.schema).replace('astra_ingestion_rpc_owner_v1',f.owner).replace(FIXED_RUN,PLACEHOLDER).replace('supabase_migrations.schema_migrations',f.schema+'.migration_history_fixture')
        cls.migration=rendered('astra_backfill_massive_relay_v2.sql')
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
            approved_worker_base_sha256=sha256((ROOT/'review/massive-relay-v3/activation/baseline_backfill_worker_v2.py').read_bytes()).hexdigest(),
            approved_worker_integration_sha256=sha256((ROOT/'review/massive-relay-v2/worker-integration.patch').read_bytes()).hexdigest(),
            approved_worker_source_sha256=sha256((ROOT/'review/massive-relay-v2/backfill_worker_v2.py.proposed').read_bytes()).hexdigest())
        invalid=[{},*[{**cls.synthetic_approved,**change} for change in (
            {'state':'AWAITING_ACTION_TIME_CONFIRMATION'},{'scope_sha256':'f'*64},
            {'confirmation_source':'BLANKET_PRIOR_APPROVAL'},
            {'approved_at':(datetime.now(timezone.utc)-timedelta(hours=1)).isoformat()},
            {'approved_migration_sha256':'f'*64},{'approved_rpc_dispatch_sha256':'f'*64},
            {'approved_edge_module_sha256':'f'*64},{'approved_worker_integration_sha256':'f'*64},{'candidate_applied':True})]]
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
        # Even a comment change requires a new exact migration approval.
        with f.assertRaises(f.psycopg.Error),f.admin() as conn:conn.execute(cls.migration+'\n-- changed candidate\n')
        wrapper_template=(ROOT/'evidence/replacement-apply-migration-wrapper-template.txt').read_text()
        wrapper_template=wrapper_template.replace('supabase_migrations.schema_migrations',f.schema+'.migration_history_fixture')
        wrapper_template=wrapper_template.replace('astra_backfill_retained_s02_v2','astra_backfill_massive_relay_v2')
        wrapper_template=wrapper_template.replace('<ACCOUNT_IDENTIFIER>','fixture-local-actor')
        cls.wrapped_migration=wrapper_template.replace('<EXACT_APPROVED_MIGRATION_BYTES>',cls.migration)
        start='-- ASTRA_RELAY_REVIEW_SQL_BEGIN_V2\n'
        extra_boundary=cls.migration.replace(start,start+start,1)
        wrong_history=cls.wrapped_migration.replace('array[$USQrtAZZkmYPmewYmQrd$'+cls.migration,
            'array[$USQrtAZZkmYPmewYmQrd$'+cls.migration+'\n-- changed history copy\n',1)
        candidates=[
            wrapper_template.replace('<EXACT_APPROVED_MIGRATION_BYTES>',extra_boundary),
            wrong_history,
            cls.wrapped_migration+'SELECT 1;\n',
            cls.wrapped_migration.replace(cls.migration+';',cls.migration+';SELECT 1;',1),
            wrapper_template.replace('astra_backfill_massive_relay_v2','unreviewed_migration').replace('<EXACT_APPROVED_MIGRATION_BYTES>',cls.migration),
            cls.wrapped_migration.replace('$USQrtAZZkmYPmewYmQrd$','$bad$',6),
            cls.wrapped_migration.replace('fixture-local-actor','fixture\nactor'),
        ]
        cls.wrapper_rejections=[]
        for candidate in candidates:
            with f.assertRaises(f.psycopg.Error),f.admin() as conn:conn.execute(candidate)
            cls.wrapper_rejections.append(sha256(candidate.encode()).hexdigest())
            with f.admin() as conn:
                assert conn.execute('SELECT to_regclass(%s) obj',(f.schema+'.backfill_relay_dispatches_v2',)).fetchone()['obj'] is None
        # Raw exact-file transport also passes the preflight. The unprivileged
        # existing RPC owner then fails at CREATE TABLE, before any new access.
        try:
            with f.admin() as conn:
                conn.execute(f'SET LOCAL ROLE {f.owner}')
                conn.execute(cls.migration)
        except f.psycopg.Error as error:
            assert error.sqlstate=='42501' and 'permission denied for schema' in str(error),str(error)
            cls.raw_preflight_passed=True
        else: raise AssertionError('Existing RPC owner unexpectedly gained schema CREATE permission')
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

    def setUp(self):
        fairness.FamilyFairnessTests.setUp(self)
        with self.f.admin() as conn:
            conn.execute(self.relay_definition.replace(PLACEHOLDER, self.run))
            conn.execute(f'UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=%s::jsonb WHERE id=%s',
                (json.dumps({'massive_relay_security_confirmation':self.synthetic_approved}),self.run))

    task = runtime.BackfillRuntimeTests.task
    call = runtime.BackfillRuntimeTests.call
    claim = runtime.BackfillRuntimeTests.claim
    fence = staticmethod(runtime.BackfillRuntimeTests.fence)

    def owned(self, kind='massive_news', reserve=True, scope_changes=None, family_override=None):
        family = {'massive_news':'N01','massive_reference':'REF01','massive_dividends':'N02',
                  'massive_splits':'N03','massive_short_volume':'S01','massive_short_interest':'S02'}[kind]
        scope={'symbols':['AAPL'],'member_ids':['member-1'], 'asof':'2025-09-01', 'start':'2025-09-01', 'end':'2025-09-30',
            'target_start':'2025-09-01','target_end':'2026-07-31','archive_date_filter':'UNBOUNDED_PROVIDER_EVENT_HISTORY',
            'retain_boundary_crossing_events':True}
        if kind=='massive_news':scope.update(start='2025-09-01T04:00:00Z',end='2025-10-01T03:59:59.999999Z')
        scope.update(scope_changes or {})
        self.task(kind=kind, family=family_override or family, provider='Massive', scope=scope)
        claim = self.claim([kind])
        if reserve:
            with self.f.admin() as conn:
                conn.execute(f"UPDATE {self.f.schema}.source_limits SET next_request_at=0 WHERE id='massive'")
            self.assertEqual(self.call('backfill_reserve', {'claim':self.fence(claim)})['state'], 'reserved')
        return claim

    def payload(self, claim):
        return {'claim':self.fence(claim), 'request':request_for(claim), 'dispatch_id':str(uuid.uuid4())}

    def counts(self):
        with self.f.admin() as conn:
            return dict(conn.execute(f'''SELECT requests_reserved,pages_committed,records_committed,source_bytes,last_progress_at
                FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s''', (self.run,)).fetchone())

    def audit(self):
        with self.f.admin() as conn:
            return conn.execute(f'SELECT * FROM {self.f.schema}.backfill_relay_dispatches_v2 WHERE run_id=%s', (self.run,)).fetchall()

    def rejected(self, payload, code=None):
        result = self.f.rpc('backfill_relay_dispatch', payload, actor='worker')
        self.assertFalse(result['ok'], result)
        if code:
            self.assertEqual(result['error']['code'], code)
        return result

    def test_only_current_worker_capability_can_probe_or_dispatch(self):
        result = self.call('backfill_relay_probe', {})
        self.assertEqual(result, {'state':'AUTHORIZED','protocol':'astra-massive-relay-v2','run_id':self.run})
        for operation in ('backfill_relay_probe', 'backfill_relay_dispatch'):
            with self.subTest(operation=operation), self.assertRaises(self.f.psycopg.Error) as denied:
                self.f.rpc(operation, {}, actor='api')
            self.assertEqual(denied.exception.sqlstate, 'PT403')
        with self.assertRaises(self.f.psycopg.Error) as denied:
            self.f.rpc('backfill_relay_probe', {}, actor='worker', token='f'*64)
        self.assertEqual(denied.exception.sqlstate, 'PT401')
        with self.f.admin() as conn:
            for role in (self.f.gateway, self.f.outsider):
                acl = conn.execute("SELECT has_function_privilege(%s,%s,'EXECUTE') f,has_table_privilege(%s,%s,'SELECT') t",
                    (role,self.f.schema+'.backfill_relay_v2(text,jsonb)',role,self.f.schema+'.backfill_relay_dispatches_v2')).fetchone()
                self.assertEqual(dict(acl), {'f':False,'t':False})
            helper=conn.execute('SELECT prosecdef,proconfig FROM pg_proc WHERE oid=%s::regprocedure',
                (self.f.schema+'.backfill_relay_v2(text,jsonb)',)).fetchone()
            self.assertFalse(helper['prosecdef']);self.assertIn('search_path=""',helper['proconfig'])
            self.assertTrue(conn.execute('SELECT relrowsecurity FROM pg_class WHERE oid=%s::regclass',
                (self.f.schema+'.backfill_relay_dispatches_v2',)).fetchone()['relrowsecurity'])
            for privilege in ('UPDATE','DELETE','TRUNCATE'):
                self.assertFalse(conn.execute('SELECT has_table_privilege(%s,%s,%s) allowed',
                    (self.f.owner,self.f.schema+'.backfill_relay_dispatches_v2',privilege)).fetchone()['allowed'])
            conn.execute(f'UPDATE {self.f.schema}.runtime_credentials SET revoked_at=clock_timestamp() WHERE actor=\'worker\'')
        with self.assertRaises(self.f.psycopg.Error):
            self.call('backfill_relay_probe', {})
        self.assertEqual(self.audit(), [])

    def test_held_installer_fails_before_any_grant_or_dispatch_extension(self):
        self.assertEqual(len(self.gate_rejections),10)
        self.assertTrue(self.applied_approval['candidate_applied'])
        self.assertEqual(self.applied_approval['applied_migration_sha256'],sha256(self.migration.encode()).hexdigest())
        self.assertEqual(self.install_audits,1)
        with self.assertRaises(self.f.psycopg.Error),self.f.admin() as conn:conn.execute(self.migration)
        scope=json.loads((ROOT/'evidence/replacement-managed-relay-review-scope-v2.json').read_text())
        actual=sha256(json.dumps(scope,sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
        self.assertEqual(actual,REVIEW_HASH)
        self.assertIn(REVIEW_HASH,(ROOT/'sql/astra_backfill_massive_relay_v2.sql').read_text())

    def test_exact_supabase_transport_preserves_the_reviewed_bytes_and_rejects_extra_sql(self):
        self.assertEqual(len(self.wrapper_rejections),7)
        self.assertTrue(self.raw_preflight_passed)
        self.assertEqual(self.history_record['name'],'astra_backfill_massive_relay_v2')
        self.assertEqual(self.history_record['statements'],[self.migration])
        self.assertEqual(self.history_record['created_by'],'fixture-local-actor')
        self.assertEqual(self.applied_approval['applied_migration_sha256'],sha256(self.migration.encode()).hexdigest())

    def test_revoked_security_confirmation_denies_probe_and_fetch_without_dispatch(self):
        claim=self.owned()
        with self.f.admin() as conn:
            conn.execute(f'UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=%s::jsonb WHERE id=%s',
                (json.dumps({'massive_relay_security_confirmation':{'state':'AWAITING_ACTION_TIME_CONFIRMATION'}}),self.run))
        result=self.f.rpc('backfill_relay_probe',{},actor='worker')
        self.assertFalse(result['ok']);self.assertEqual(result['error']['code'],'conflict')
        self.rejected(self.payload(claim),'conflict');self.assertEqual(self.audit(),[])

    def test_arbitrary_task_scope_cannot_expand_members_dates_families_or_action_history(self):
        cases=[('massive_news',{'symbols':['MSFT']},None),('massive_news',{'member_ids':['member-2']},None),
            ('massive_news',{'start':'2020-01-01T00:00:00Z'},None),('massive_news',{'end':'2026-08-01T04:00:00Z'},None),
            ('massive_news',{'start':'2025-10-02T04:00:00Z'},None),('massive_news',{},'REF01'),
            ('massive_reference',{'asof':'2026-08-03'},None),('massive_reference',{'asof':'2024-02-29'},None),
            ('massive_short_volume',{'start':'2025-06-05'},None),('massive_short_interest',{'end':'2026-08-01'},None),
            ('massive_dividends',{'archive_date_filter':None},None),('massive_splits',{'retain_boundary_crossing_events':False},None),
            ('massive_dividends',{'target_start':'2020-01-01'},None)]
        for kind,scope,family in cases:
            with self.subTest(kind=kind,scope=scope,family=family):
                claim=self.owned(kind,scope_changes=scope,family_override=family)
                self.rejected(self.payload(claim),'conflict')
        self.assertEqual(self.audit(),[])

    def test_outer_authorization_and_metadata_change_only_the_two_admitted_operations(self):
        self.assertEqual(self.outer_metadata_before,self.outer_metadata_after)
        before=self.outer_before.replace("'backfill_work'", "'backfill_work','backfill_relay_probe','backfill_relay_dispatch'")
        hook=(ROOT/'sql/astra_backfill_massive_relay_v2.sql').read_text().split('$dispatch$')[1]
        hook=hook.replace('astra_ingestion_v1',self.f.schema)
        before=before.replace("    IF p_operation LIKE 'backfill_%' THEN",hook+"    IF p_operation LIKE 'backfill_%' THEN")
        self.assertEqual(before,self.outer_after)
        self.assertTrue(self.f.ok('health',actor='worker')['ready'])
        self.assertTrue(self.f.ok('health',actor='api')['ready'])

    def test_exact_current_reservation_has_one_durable_dispatch_and_no_counter_side_effect(self):
        claim = self.owned()
        payload = self.payload(claim)
        before = self.counts()
        ticket = self.call('backfill_relay_dispatch', payload)
        expected_hash = sha256(json.dumps(payload['request'],sort_keys=True,separators=(',',':'),ensure_ascii=True).encode()).hexdigest()
        self.assertEqual(ticket['state'], 'DISPATCH_AUTHORIZED')
        self.assertEqual(ticket['request_sha256'], expected_hash)
        self.assertEqual(ticket['dispatch_id'], payload['dispatch_id'])
        self.assertEqual(self.counts(), before)
        self.assertEqual(self.call('backfill_relay_dispatch', payload), {'state':'ALREADY_DISPATCHED','provider_requested':False})
        self.assertEqual(self.call('backfill_relay_dispatch', self.payload(claim))['state'], 'ALREADY_DISPATCHED')
        self.assertEqual(len(self.audit()), 1)
        row = self.audit()[0]
        self.assertEqual(row['request'], payload['request'])
        self.assertEqual(row['request_sha256'], expected_hash)
        self.assertGreater((row['not_after']-row['authorized_at']).total_seconds(), 0)
        self.assertLessEqual((row['not_after']-row['authorized_at']).total_seconds(), 25.1)
        self.assertEqual(self.counts(), before)
        for verb in ('UPDATE '+self.f.schema+'.backfill_relay_dispatches_v2 SET claim_owner=claim_owner',
                     'DELETE FROM '+self.f.schema+'.backfill_relay_dispatches_v2',
                     'TRUNCATE '+self.f.schema+'.backfill_relay_dispatches_v2'):
            with self.assertRaises(self.f.psycopg.Error), self.f.admin() as conn:
                conn.execute(verb)

    def test_every_massive_kind_uses_the_native_exact_request(self):
        kinds = ('massive_reference','massive_news','massive_dividends','massive_splits','massive_short_volume','massive_short_interest')
        for kind in kinds:
            with self.subTest(kind=kind):
                claim = self.owned(kind)
                self.assertEqual(self.call('backfill_relay_dispatch',self.payload(claim))['state'],'DISPATCH_AUTHORIZED')
        self.assertEqual(len(self.audit()), 6)
        self.assertEqual(self.counts()['requests_reserved'], 6)

    def test_stale_claim_missing_reservation_expired_attempt_and_stop_are_rejected(self):
        claim = self.owned(reserve=False)
        self.rejected(self.payload(claim), 'lease_lost')
        self.assertEqual(self.call('backfill_reserve',{'claim':self.fence(claim)})['state'],'reserved')
        for field,value in (('owner','wrong'),('generation',claim['generation']+1),('run_fence',claim['run_fence']+1),
                            ('page_no',claim['page_no']+1),('run_id','wrong-run')):
            payload = self.payload(claim);payload['claim'][field] = value
            with self.subTest(field=field): self.rejected(payload,'lease_lost')
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET attempt_deadline=clock_timestamp()-interval '1 second' WHERE id=%s",(claim['id'],))
        self.rejected(self.payload(claim),'lease_lost')
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET attempt_deadline=clock_timestamp()+interval '1 minute',lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",(claim['id'],))
        self.rejected(self.payload(claim),'lease_lost')
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET status='PAUSED',fence=fence+1 WHERE id=%s",(self.run,))
        self.rejected(self.payload(claim),'lease_lost')
        self.assertEqual(self.audit(),[])

    def test_request_and_shape_mutations_cannot_broaden_the_dispatch(self):
        claim = self.owned()
        changes = [('host','other.invalid'),('path','/v2/snapshot/locale/us/markets/stocks/tickers'),
                   ('method','POST'),('provider','Alpaca')]
        for field,value in changes:
            p=self.payload(claim);p['request'][field]=value
            with self.subTest(field=field): self.rejected(p,'conflict')
        for field,value in [('apiKey','injected'),('limit',999),('ticker','MSFT'),('published_utc.gte','2020-01-01'),('cursor','invented')]:
            p=self.payload(claim);p['request']['params'][field]=value
            with self.subTest(parameter=field): self.rejected(p,'conflict')
        p=self.payload(claim);p['claim']['unapproved']=True;self.rejected(p,'conflict')
        p=self.payload(claim);p['dispatch_id']='not-uuid';self.rejected(p,'conflict')
        p=self.payload(claim);p['extra']=True;self.rejected(p,'conflict')
        self.assertEqual(self.audit(),[])

    def test_durable_adaptive_limit_and_exact_cursor_are_bound(self):
        claim = self.owned(reserve=False)
        with self.f.admin() as conn:
            conn.execute(f'UPDATE {self.f.schema}.backfill_tasks_v2 SET page_limit=25,cursor=%s::jsonb WHERE id=%s',
                (json.dumps('opaque+token/=='),claim['id']))
        claim.update(page_limit=25,cursor='opaque+token/==')
        self.call('backfill_reserve',{'claim':self.fence(claim)})
        p=self.payload(claim);p['request']['params']['limit']=1000;self.rejected(p,'conflict')
        p=self.payload(claim);p['request']['params']['cursor']='different';self.rejected(p,'conflict')
        self.assertEqual(self.call('backfill_relay_dispatch',self.payload(claim))['state'],'DISPATCH_AUTHORIZED')

    def test_concurrent_attempts_admit_exactly_one_dispatch(self):
        claim = self.owned()
        payloads=[self.payload(claim),self.payload(claim)]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda p:self.call('backfill_relay_dispatch',p),payloads))
        self.assertEqual(sorted(result['state'] for result in results),['ALREADY_DISPATCHED','DISPATCH_AUTHORIZED'])
        self.assertEqual(len(self.audit()),1)
        self.assertEqual(self.counts()['requests_reserved'],1)

    def test_uncertain_pure_read_requires_new_generation_and_new_counted_reservation(self):
        old=self.owned();self.call('backfill_relay_dispatch',self.payload(old))
        self.call('backfill_defer',{'claim':self.fence(old),'code':'SOURCE_TRANSPORT_ERROR','message':'Fixture lost response',
            'retryable':True,'retry_after':30,'evidence':{'same_reservation_replay':False}})
        self.assertIsNone(self.claim(['massive_news']))
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET next_retry_at=clock_timestamp()-interval '1 second' WHERE id=%s",(old['id'],))
            conn.execute(f"UPDATE {self.f.schema}.source_limits SET next_request_at=0 WHERE id='massive'")
        new=self.claim(['massive_news'])
        self.assertEqual(new['id'],old['id']);self.assertGreater(new['generation'],old['generation'])
        self.rejected(self.payload(old),'lease_lost')
        self.rejected(self.payload(new),'lease_lost')
        self.assertEqual(self.call('backfill_reserve',{'claim':self.fence(new)})['state'],'reserved')
        self.assertEqual(self.call('backfill_relay_dispatch',self.payload(new))['state'],'DISPATCH_AUTHORIZED')
        self.assertEqual(len(self.audit()),2)
        self.assertEqual(self.counts()['requests_reserved'],2)

    def test_native_relay_page_commits_and_verifies_in_the_existing_durable_runtime(self):
        claim=self.owned()
        ticket=self.call('backfill_relay_dispatch',self.payload(claim))
        raw=b'{"status":"OK","results":[{"id":"retained-news-1","tickers":["AAPL"],"published_utc":"2025-09-03T12:00:00Z","title":"Fixture article"}]}'
        response=relay_fixture.envelope(claim,raw)
        response['dispatch_id']=ticket['dispatch_id'];response['request_sha256']=ticket['request_sha256']
        relay,opener=relay_fixture.ready_relay(response)
        page=relay.fetch(claim)
        result=self.call('backfill_commit',{'claim':self.fence(claim),**page.payload()})
        self.assertEqual(result['task_status'],'INGESTED')
        readback=self.call('backfill_verify',{'claim':self.fence(claim),'page_no':claim['page_no']})
        self.assertEqual(readback['raw_body'],raw.decode());self.assertEqual(readback['body_sha256'],sha256(raw).hexdigest())
        self.assertEqual(readback['readback_sha256'],sha256(raw).hexdigest())
        self.assertEqual(self.counts()['requests_reserved'],1);self.assertEqual(self.counts()['pages_committed'],1)
        self.assertEqual(self.counts()['records_committed'],1);self.assertEqual(len(self.audit()),1)
        self.assertEqual(len(opener.calls),2)

    def test_native_relay_oversize_evidence_drives_existing_durable_adaptive_recovery(self):
        claim=self.owned();self.call('backfill_relay_dispatch',self.payload(claim))
        raw=b'x'*(relay_fixture.MAX_BODY_BYTES+1)
        relay,_=relay_fixture.ready_relay(relay_fixture.envelope(claim,raw,complete=False))
        with self.assertRaises(ProviderProblem) as caught:relay.fetch(claim)
        error=caught.exception
        result=self.call('backfill_defer',{'claim':self.fence(claim),'code':error.code,'message':str(error),
            'retryable':error.retryable,'retry_after':error.retry_after,'evidence':error.evidence})
        self.assertEqual(result['state'],'RETRY_WAIT')
        with self.f.admin() as conn:
            row=conn.execute(f'SELECT page_limit,page_no,requests_reserved,cursor FROM {self.f.schema}.backfill_tasks_v2 WHERE id=%s',
                (claim['id'],)).fetchone()
        self.assertEqual(row['page_limit'],10);self.assertEqual(row['page_no'],0);self.assertIsNone(row['cursor'])
        self.assertEqual(row['requests_reserved'],1);self.assertEqual(self.counts()['pages_committed'],0)
        self.assertEqual(len(self.audit()),1)


if __name__=='__main__': unittest.main()
