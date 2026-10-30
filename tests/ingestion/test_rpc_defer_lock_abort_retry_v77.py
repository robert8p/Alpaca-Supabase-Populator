"""Defer-only retry: actual isolated PostgreSQL, explicitly simulated HTTP.

The opener never contacts the configured RPC URL or a provider. Native 55P03
comes from disposable PostgreSQL transaction lock waits; lost ACK is injected
only after the real transaction commits. No installed application source is
instrumented except a test-only late-fault trigger in the disposable schema.
"""
from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
import io
import json
import os
from pathlib import Path
import re
import unittest
from unittest.mock import patch

from astra_ingestion import rpc_store as rpc
from astra_ingestion.backfill_provider_v2 import ProviderProblem
from astra_ingestion.backfill_worker_v2 import BackfillWorker
import test_backfill_adaptive_pages_v2 as adaptive
import test_rpc_lock_abort_retry as unit
import test_rpc_lock_abort_retry_postgres as live
from test_rpc_store import Opener, PUBLIC_KEY, Reply, TOKEN

ROOT = Path(__file__).resolve().parents[2]
BUNDLE_PATH = 'review/recovery-v77/defer-native-lock-retry/defer_source_bundle_v77.json'
BUNDLE_SHA = '24e6c46d90e03442607eef934501577bd53ae45a43ec7e30fba31bf2b5f008a7'
BASE_RUNTIME_SHA = '1deb7051d4311b22c09d7245a36d751dd10c843192207aaefc0a2d4cf1291403'
LATE_GATE = 706314020277077
RESULT = {'layers': {'postgresql': 'ACTUAL_DISPOSABLE', 'http': 'SIMULATED_DOCUMENTED_POSTGREST_ENVELOPE',
                     'postgrest_server': 'NOT_RUN', 'production': 'NOT_RUN', 'provider': 'SYNTHETIC_NO_NETWORK'}, 'cases': {}}


def bundle():
    raw = (ROOT / BUNDLE_PATH).read_bytes()
    if sha256(raw).hexdigest() != BUNDLE_SHA:
        raise AssertionError('Exact current defer source capture changed')
    value = json.loads(raw)
    for row in value['functions'] + value['protected_context_functions']:
        if sha256(row['definition'].encode()).hexdigest() != row['source_sha256']:
            raise AssertionError('Exact captured definition does not match source pin')
    return value


class DeferSourceAndBoundaryTests(unittest.TestCase):
    def test_only_one_operation_literal_changes_runtime(self):
        source = (ROOT / 'astra_ingestion/rpc_store.py').read_text()
        addition = '"backfill_verify", "backfill_plan_next", "backfill_defer",'
        self.assertEqual(source.count(addition), 1)
        inverse = source.replace(addition, '"backfill_verify", "backfill_plan_next",')
        self.assertEqual(sha256(inverse.encode()).hexdigest(), BASE_RUNTIME_SHA)
        self.assertNotIn('backfill_identity_material', rpc.LOCK_ABORT_RETRY_OPERATIONS)
        self.assertEqual(len(rpc.LOCK_ABORT_RETRY_OPERATIONS), 7)
        selected = bundle()
        self.assertEqual(len(selected['functions']), 9)
        pins = {row['signature']: row['source_sha256'] for row in selected['functions']}
        self.assertEqual(pins['astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'],
                         'dbe8eb5a563eaf9e8e00678045f8a28da65c8c4b83b4a3295c4eb32c05f50fbf')
        self.assertEqual(pins['astra_ingestion_v1.backfill_adapt_page_v2(astra_ingestion_v1.backfill_tasks_v2,jsonb)'],
                         '10a17158429447e5734259e87b6ca45dbeb648b5234d98cbddeb35cd164c06b8')

    def test_dsn_admission_keeps_dedicated_gate_strict(self):
        for workflow, error in (('ASTRA ingestion qualification', RuntimeError), ('release-gate', unittest.SkipTest)):
            with self.subTest(workflow=workflow), patch.dict(os.environ, {'GITHUB_WORKFLOW': workflow}, clear=True):
                with self.assertRaises(error):
                    DeferPostgreSQLTests.setUpClass()

    def test_defer_rejects_ambiguous_errors_and_keeps_same_deadline_budget(self):
        cases = [unit.error_response(code='57014')[0], TimeoutError(unit.SECRET),
                 unit.error_response(status=503)[0], unit.error_response(raw=b'{"code":"55P03"}')[0],
                 unit.error_response(value={'code':'55P03','message':'x','details':None,'hint':None,'ok':False})[0]]
        for error in cases:
            with self.subTest(error=type(error).__name__):
                opener = Opener(error, Reply('must not send'))
                store = rpc.RpcStore(rpc.PROJECT_URL, PUBLIC_KEY, TOKEN, opener=opener)
                output = io.StringIO()
                with redirect_stderr(output), redirect_stdout(output), self.assertRaises(rpc.RpcPersistenceError) as caught:
                    store._call('backfill_defer', {'message':unit.SECRET})
                self.assertEqual(len(opener.calls), 1)
                self.assertEqual(output.getvalue(), '')
                self.assertNotIn(unit.SECRET, str(caught.exception))
        clock = unit.Clock()
        opener = Opener(*(unit.error_response()[0] for _ in range(3)), Reply('must not send'))
        store = rpc.RpcStore(rpc.PROJECT_URL, PUBLIC_KEY, TOKEN, opener=opener)
        with patch.object(rpc, 'monotonic', clock.monotonic), patch.object(rpc, 'sleep', clock.sleep):
            with self.assertRaises(rpc.RpcPersistenceError) as caught:
                store._call('backfill_defer', {'message':unit.SECRET})
        self.assertEqual(caught.exception.rpc_failure_reason, 'LOCK_ABORT_RETRY_EXHAUSTED')
        self.assertEqual(clock.delays, [0.25, 0.75])
        self.assertEqual([timeout for _, timeout in opener.calls], [15, 14.75, 14.0])
        self.assertEqual(len({request.data for request, _ in opener.calls}), 1)


class FailingProvider:
    def __init__(self, case, variant):
        self.case, self.variant = case, variant
        self.fetch_count = 0
        self.claim = None

    def supported_kinds(self):
        return ('alpaca_stock_bars',)

    def require_credentials(self, _claim):
        pass

    def fetch(self, claim):
        self.fetch_count += 1
        self.claim = claim
        payload = self.case.failure(claim, 120)
        if self.variant == 'rate':
            payload.update(code='SOURCE_RATE_LIMIT', message='synthetic rate response',
                           retryable=True, evidence={'http_status':429})
        elif self.variant == 'dependency':
            payload.update(code='MISSING_PROVIDER_CREDENTIAL', message='synthetic dependency', retryable=False,
                           evidence={'dependency':'ALPACA_WORKER_CREDENTIAL'})
        elif self.variant != 'adaptive':
            raise AssertionError('Unknown test variant')
        raise ProviderProblem(payload['code'], payload['message'], retryable=payload['retryable'],
                              retry_after=payload['retry_after'], evidence=payload['evidence'])


class DeferPostgreSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        live.PostgreSQLLockAbortTests.setUpClass.__func__(cls)
        f = cls.fixture('runTest')
        selected = bundle()
        with f.admin() as conn:
            for row in selected['functions'] + selected['protected_context_functions']:
                definition = cls.rewrite(row['definition'])
                definition = definition.replace('public.astra_ingestion_rpc_v1', 'public.' + f.endpoint)
                definition = re.sub(r'\banon\b', f.gateway, definition)
                conn.execute(definition)
            RESULT['postgresql_version'] = conn.execute('SHOW server_version').fetchone()['server_version']
        cls.selected = selected

    rewrite = classmethod(live.PostgreSQLLockAbortTests.rewrite.__func__)
    full_query = staticmethod(live.PostgreSQLLockAbortTests.full_query)
    task = live.PostgreSQLLockAbortTests.task
    call = live.PostgreSQLLockAbortTests.call
    claim = live.PostgreSQLLockAbortTests.claim
    page = live.PostgreSQLLockAbortTests.page
    fence = staticmethod(live.PostgreSQLLockAbortTests.fence)
    hold = live.PostgreSQLLockAbortTests.hold
    release = live.PostgreSQLLockAbortTests.release
    normalized = live.PostgreSQLLockAbortTests.normalized
    totals = live.PostgreSQLLockAbortTests.totals
    source_task = adaptive.AdaptivePostgreSQLTests.source_task
    failure = adaptive.AdaptivePostgreSQLTests.failure
    row = adaptive.AdaptivePostgreSQLTests.row

    def setUp(self):
        live.PostgreSQLLockAbortTests.setUp(self)
        with self.f.admin() as conn:
            conn.execute(f'DROP TRIGGER IF EXISTS defer_retry_late_fault ON {self.f.schema}.backfill_tasks_v2')

    def store(self, **kwargs):
        opener = live.DatabaseOpener(self, **kwargs)
        return rpc.RpcStore(rpc.PROJECT_URL, PUBLIC_KEY, self.f.tokens['worker'], opener=opener), opener

    def snapshot(self, key):
        with self.f.admin() as conn:
            out = {'task':dict(conn.execute(f'SELECT * FROM {self.f.schema}.backfill_tasks_v2 WHERE id=%s',(key,)).fetchone())}
            out['source_limits'] = [dict(row) for row in conn.execute(f'SELECT * FROM {self.f.schema}.source_limits ORDER BY id').fetchall()]
            for table in ('backfill_provider_dependencies_v2','backfill_exceptions_v2','backfill_pages_v2','backfill_readbacks_v2'):
                out[table] = [dict(row) for row in conn.execute(f'SELECT * FROM {self.f.schema}.{table} WHERE run_id=%s ORDER BY 1',(self.run,)).fetchall()]
            out['run'] = dict(conn.execute(f'SELECT * FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s',(self.run,)).fetchone())
            return out

    def final_assertions(self, key, before, variant):
        after = self.snapshot(key)
        task = after['task']
        expected = 'BLOCKED_EXTERNAL' if variant == 'dependency' else 'RETRY_WAIT'
        self.assertEqual(task['status'], expected)
        self.assertIsNone(task['owner'])
        self.assertIsNone(task['lease_until'])
        for field in ('scope','cursor','page_no','attempts','page_attempts','attempt_deadline','requests_reserved',
                      'reserved_generation','reserved_page_no','generation','run_fence'):
            self.assertEqual(task[field], before['task'][field], field)
        self.assertEqual(task['page_limit'], 1000 if variant == 'adaptive' else before['task']['page_limit'])
        self.assertEqual(len(after['backfill_exceptions_v2']), 1)
        self.assertEqual(after['backfill_pages_v2'], [])
        self.assertEqual(after['backfill_readbacks_v2'], [])
        self.assertEqual(self.totals(), {'pages_committed':0,'records_committed':0,'requests_reserved':1,'readbacks':0})
        if variant == 'rate':
            old = next(row for row in before['source_limits'] if row['id']=='alpaca')
            new = next(row for row in after['source_limits'] if row['id']=='alpaca')
            self.assertGreater(new['next_request_at'], old['next_request_at'] + 100)
        if variant == 'dependency':
            self.assertEqual(len(after['backfill_provider_dependencies_v2']), 1)
            dependency = after['backfill_provider_dependencies_v2'][0]
            self.assertEqual(dependency['state'], 'BLOCKED_EXTERNAL')
            self.assertEqual(dependency['blocked_worker'], before['task']['owner'])
            self.assertTrue(dependency['blocked_revision'])
        return expected

    def install_late_fault(self, variant, before, *, native=True):
        schema = self.f.schema
        if variant == 'rate':
            old = next(row for row in before['source_limits'] if row['id']=='alpaca')['next_request_at']
            check = f"(SELECT next_request_at FROM {schema}.source_limits WHERE id='alpaca')>{float(old)+100}"
        elif variant == 'dependency':
            check = f"EXISTS(SELECT 1 FROM {schema}.backfill_provider_dependencies_v2 WHERE run_id=NEW.run_id AND blocked_worker=OLD.owner AND blocked_revision IS NOT NULL AND state='BLOCKED_EXTERNAL')"
        else:
            check = 'NEW.page_limit=1000 AND OLD.page_limit=1000'
        statement = (f'PERFORM pg_catalog.pg_advisory_xact_lock({LATE_GATE});' if native else
                     "RAISE EXCEPTION USING ERRCODE='55P03',MESSAGE='fixture authority-transition abort';")
        with self.f.admin() as conn:
            conn.execute(f'''CREATE OR REPLACE FUNCTION {schema}.defer_retry_late_fault_fn()
              RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $test$
              BEGIN
                IF OLD.status='RUNNING' AND NEW.status IN('RETRY_WAIT','BLOCKED_EXTERNAL','OPERATIONAL_ERROR') THEN
                  IF NEW.owner IS NOT NULL OR NEW.lease_until IS NOT NULL OR NOT ({check})
                    OR (SELECT count(*) FROM {schema}.backfill_exceptions_v2 WHERE task_id=NEW.id)<>1 THEN
                    RAISE EXCEPTION 'fixture did not reach all expected real defer effects';
                  END IF;
                  INSERT INTO {schema}.retry_fault_probe(note) VALUES('verified real defer effects before abort');
                  {statement}
                END IF;
                RETURN NEW;
              END $test$''')
            conn.execute(f'''CREATE TRIGGER defer_retry_late_fault AFTER UPDATE ON {schema}.backfill_tasks_v2
                            FOR EACH ROW EXECUTE FUNCTION {schema}.defer_retry_late_fault_fn()''')

    def drop_late_fault(self):
        with self.f.admin() as conn:
            conn.execute(f'DROP TRIGGER defer_retry_late_fault ON {self.f.schema}.backfill_tasks_v2')

    def assert_same_defer_bytes(self, opener, count):
        attempts = [(raw, timeout) for operation, raw, timeout in opener.calls if operation=='backfill_defer']
        self.assertEqual(len(attempts), count)
        self.assertEqual(len({raw for raw, _ in attempts}), 1)
        self.assertTrue(all(0 < timeout <= 15 for _, timeout in attempts))
        self.assertEqual(sum(operation=='backfill_claim' for operation,_,_ in opener.calls),1)
        self.assertEqual(sum(operation=='backfill_reserve' for operation,_,_ in opener.calls),1)

    def test_current_nine_function_sources_and_security_catalog(self):
        with self.f.admin() as conn:
            pins = []
            for row in self.selected['functions']:
                signature = self.rewrite(row['signature']).replace('public.astra_ingestion_rpc_v1','public.'+self.f.endpoint)
                actual = conn.execute('SELECT pg_get_functiondef(%s::regprocedure) definition', (signature,)).fetchone()['definition']
                self.assertEqual(sha256(self.normalized(actual).encode()).hexdigest(), row['source_sha256'])
                pins.append({'signature':row['signature'],'source_sha256':row['source_sha256']})
            self.assertNotEqual(self.f.owner, self.f.gateway)
        RESULT['current_nine_function_pins'] = pins
        RESULT['fixture_identifier_adaptation'] = 'Existing disposable schema, roles, endpoint and retained source relation names only; sources normalize byte-exact.'

    def test_early_native_gate_abort_retries_only_identical_defer(self):
        key = self.source_task(cursor='same-opaque-alpaca-cursor')
        provider = FailingProvider(self, 'rate')
        state = {}
        def before(operation):
            if operation=='backfill_defer' and not state:
                state['before'] = self.snapshot(key)
                state['holder'] = self.hold()
        def aborted(operation, code):
            self.assertEqual((operation,code),('backfill_defer','55P03'))
            self.assertEqual(self.snapshot(key),state['before'])
            self.release(state['holder'])
        store, opener = self.store(before=before, after_abort=aborted)
        outcome = BackfillWorker(store,provider,worker_id='defer-early-worker').run_once()
        self.assertEqual(outcome['state'],'backfill_exception_recorded')
        self.assertEqual(provider.fetch_count,1)
        self.assert_same_defer_bytes(opener,2)
        self.assertEqual(opener.transactions,['COMMITTED','COMMITTED','ROLLED_BACK','COMMITTED'])
        self.final_assertions(key,state['before'],'rate')
        RESULT['cases']['early_native_gate_abort'] = {'sqlstate':'55P03','unchanged_aborted_business_snapshot':True,
            'defer_sends':2,'provider_fetches':1,'serialized_request_equal':True,'native_lock_wait':True}

    def test_late_native_abort_rolls_back_all_three_effect_branches(self):
        checked=[]
        for index,variant in enumerate(('rate','dependency','adaptive')):
            with self.subTest(variant=variant):
                if index: self.setUp()
                key=self.source_task(cursor='same-opaque-alpaca-cursor')
                provider=FailingProvider(self,variant)
                state={}
                def before(operation):
                    if operation=='backfill_defer' and not state:
                        state['before']=self.snapshot(key)
                        state['holder']=self.hold(LATE_GATE)
                        self.install_late_fault(variant,state['before'])
                def aborted(operation,code):
                    self.assertEqual((operation,code),('backfill_defer','55P03'))
                    self.assertEqual(self.snapshot(key),state['before'])
                    with self.f.admin() as conn:
                        self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.retry_fault_probe').fetchone()['n'],0)
                        sequence=conn.execute(f'SELECT last_value,is_called FROM {self.f.schema}.retry_fault_probe_id_seq').fetchone()
                        self.assertTrue(sequence['is_called'])
                        self.assertEqual(sequence['last_value'],1)
                    self.release(state['holder'])
                store,opener=self.store(before=before,after_abort=aborted)
                outcome=BackfillWorker(store,provider,worker_id='defer-late-worker').run_once()
                self.assertEqual(outcome['state'],'backfill_exception_recorded')
                self.assert_same_defer_bytes(opener,2)
                self.assertEqual(provider.fetch_count,1)
                self.assertEqual(opener.transactions,['COMMITTED','COMMITTED','ROLLED_BACK','COMMITTED'])
                self.final_assertions(key,state['before'],variant)
                with self.f.admin() as conn:
                    rows=conn.execute(f'SELECT id FROM {self.f.schema}.retry_fault_probe').fetchall()
                    self.assertEqual([row['id'] for row in rows],[2])
                checked.append({'variant':variant,'native_sqlstate':'55P03','real_effects_reached':True,
                    'business_rollback_exact':True,'retained_sequence_gap':True,'defer_sends':2,'provider_fetches':1})
        RESULT['cases']['late_native_effect_abort']=checked

    def test_committed_defer_lost_ack_never_retries_or_refetches(self):
        checked=[]
        for index,variant in enumerate(('rate','dependency','adaptive')):
            with self.subTest(variant=variant):
                if index: self.setUp()
                key=self.source_task(cursor='same-opaque-alpaca-cursor')
                provider=FailingProvider(self,variant)
                state={}
                def before(operation):
                    if operation=='backfill_defer': state['before']=self.snapshot(key)
                store,opener=self.store(before=before,lose_ack='backfill_defer')
                with self.assertRaises(rpc.RpcPersistenceError) as caught:
                    BackfillWorker(store,provider,worker_id='defer-lost-ack-worker').run_once()
                self.assertEqual(caught.exception.rpc_failure_reason,'TRANSPORT_ERROR')
                self.assert_same_defer_bytes(opener,1)
                self.assertEqual(provider.fetch_count,1)
                self.assertEqual(opener.transactions,['COMMITTED']*3)
                self.final_assertions(key,state['before'],variant)
                checked.append({'variant':variant,'actual_commit':True,'defer_sends':1,'provider_fetches':1,
                                'fatal_reason':'TRANSPORT_ERROR','defer_is_not_idempotent':True})
        RESULT['cases']['committed_lost_ack']=checked

    def test_retry_rechecks_all_existing_authority_without_renewal(self):
        checked=[]
        for index,condition in enumerate(('owner','generation','run_fence','lease','run_paused','credential_revoked','credential_expired')):
            with self.subTest(condition=condition):
                if index: self.setUp()
                key=self.source_task(cursor='same-opaque-alpaca-cursor')
                provider=FailingProvider(self,'adaptive')
                state={}
                def before(operation):
                    if operation=='backfill_defer' and not state:
                        state['before']=self.snapshot(key)
                        self.install_late_fault('adaptive',state['before'],native=False)
                def aborted(operation,code):
                    if code!='55P03': return
                    self.assertEqual(operation,'backfill_defer')
                    self.assertEqual(self.snapshot(key),state['before'])
                    self.drop_late_fault()
                    with self.f.admin() as conn:
                        s=self.f.schema
                        if condition=='owner': conn.execute(f"UPDATE {s}.backfill_tasks_v2 SET owner='another-worker' WHERE id=%s",(key,))
                        elif condition=='generation': conn.execute(f'UPDATE {s}.backfill_tasks_v2 SET generation=generation+1 WHERE id=%s',(key,))
                        elif condition=='run_fence': conn.execute(f'UPDATE {s}.backfill_runs_v2 SET fence=fence+1 WHERE id=%s',(self.run,))
                        elif condition=='lease': conn.execute(f"UPDATE {s}.backfill_tasks_v2 SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",(key,))
                        elif condition=='run_paused': conn.execute(f"UPDATE {s}.backfill_runs_v2 SET status='PAUSED' WHERE id=%s",(self.run,))
                        elif condition=='credential_revoked': conn.execute(f"UPDATE {s}.runtime_credentials SET revoked_at=clock_timestamp() WHERE actor='worker'")
                        else: conn.execute(f"UPDATE {s}.runtime_credentials SET created_at=clock_timestamp()-interval '2 seconds',expires_at=clock_timestamp()-interval '1 second' WHERE actor='worker'")
                store,opener=self.store(before=before,after_abort=aborted)
                if condition.startswith('credential'):
                    with self.assertRaises(rpc.RpcAuthenticationError):
                        BackfillWorker(store,provider,worker_id='defer-authority-worker').run_once()
                else:
                    outcome=BackfillWorker(store,provider,worker_id='defer-authority-worker').run_once()
                    self.assertEqual(outcome['state'],'ownership_lost')
                self.assert_same_defer_bytes(opener,2)
                self.assertEqual(provider.fetch_count,1)
                after=self.snapshot(key)
                self.assertEqual(after['backfill_exceptions_v2'],[])
                self.assertEqual(after['backfill_provider_dependencies_v2'],[])
                self.assertEqual(after['task']['page_limit'],10000)
                self.assertEqual(after['task']['requests_reserved'],1)
                checked.append(condition)
        RESULT['cases']['authority_rechecks']={'conditions':checked,'abort_layer':'ACTUAL_PG_TEST_RAISED_55P03_AFTER_EFFECTS',
            'native_lock_abort_separately_covered':True,'no_provider_refetch':True,'no_lease_renewal':True}

    def test_invalid_scoped_adaptive_receipt_stays_controlled_single_send(self):
        key=self.source_task()
        claim=self.claim(['alpaca_stock_bars'])
        self.call('backfill_reserve',{'claim':self.fence(claim)})
        payload=self.failure(claim)
        payload['evidence']['partial_body_sha256']='0'*64
        before=self.snapshot(key)
        store,opener=self.store()
        with self.assertRaises(ValueError): store._call('backfill_defer',payload)
        self.assertEqual(len(opener.calls),1)
        self.assertEqual(opener.errors,[])
        self.assertEqual(self.snapshot(key),before)
        RESULT['cases']['controlled_invalid_scope']={'native_errors':0,'sends':1,'business_unchanged':True}


if __name__=='__main__':
    unittest.main()
