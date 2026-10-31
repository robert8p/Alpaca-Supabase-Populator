"""Independent unchanged contract admission baseline in disposable PostgreSQL only."""
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from time import perf_counter
import unittest

STAGED = Path('/tmp/replacement-claim-capability-staged-v71')
REPO = Path('/workspace/scratch/a1eb25e9f187/replacement-run')
sys.path[:0] = [str(STAGED / 'tests/ingestion'), str(STAGED), str(REPO / 'tests/ingestion')]
import test_backfill_claim_capability_filter_v2 as base
import test_backfill_shared_records_v2 as shared
import test_backfill_contract_registry_v2 as registry

RESULT = {'schema': 'astra.independent-contract-admission-baseline/1',
          'production_calls': 0, 'fixture_only': True, 'repair_applied': False,
          'initial_harness_attempt': 'Import failed before any test or database connection because the staged fixture omits test_backfill_shared_records_v2; added repository tests as a fallback import path without modifying fixture or production source.'}
PINNED_NAMES = {
    'backfill_contract_admit_page_v2': 'text,integer',
    'backfill_contract_register_child_v2': 'text',
    'backfill_contract_child_trigger_v2': '',
    'backfill_contract_enqueue_v2': 'text,integer',
    'backfill_contract_key_v2': 'text,timestamp with time zone,timestamp with time zone,text,text',
    'backfill_page_rows_v2': 'text,integer',
}


class AdmissionBaseline(base.CapabilityFilterPostgreSQLTests):
    new = shared.SharedRecordsTests.new
    commit = shared.SharedRecordsTests.commit
    verify = shared.SharedRecordsTests.verify
    contract = staticmethod(registry.ContractRegistryTests.contract)

    def test_unchanged_1000_contract_admission_and_insert_triggers(self):
        paths = [REPO / 'review/recovery-v71/live_maintenance_page_seed_helpers_1339.json',
                 REPO / 'review/recovery-v71/live_contract_seed_state_helpers_1344.json']
        retained = json.loads(paths[0].read_text())
        retained += json.loads(paths[1].read_text())[0]['evidence']['functions']
        definitions = {d['proname']: d for d in retained}
        source_checks = {}
        with self.f.admin() as conn:
            for name, args in PINNED_NAMES.items():
                original = definitions[name]['definition']
                self.assertEqual(sha256(original.encode()).hexdigest(), definitions[name]['sha256'])
                local = conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                    (self.f.schema + '.' + name + '(' + args + ')',)).fetchone()['d']
                expected = original.replace('astra_ingestion_v1', self.f.schema)
                self.assertTrue(local == expected, 'Retained function differs after schema-only adaptation: ' + name)
                source_checks[name] = {'retained_sha256': definitions[name]['sha256'],
                    'schema_only_adaptation': True, 'local_sha256': sha256(local.encode()).hexdigest()}
            conn.execute(f'INSERT INTO {self.f.schema}.backfill_contract_state_v2(run_id,seed_complete) VALUES(%s,false)',
                         (self.run,))

        claim = self.new(kind='alpaca_option_contracts', family='CTX02', status='inactive')
        rows = [{**self.contract(i), 'fixture_padding': ''} for i in range(1000)]
        def body_bytes():
            return len(json.dumps({'option_contracts': rows, 'next_page_token': None}).encode())
        # Match the observed page's byte count with synthetic inert padding, not real provider records.
        target = 705542
        missing = target - body_bytes()
        self.assertGreaterEqual(missing, 0)
        per_row, remainder = divmod(missing, 1000)
        for i, row in enumerate(rows):
            row['fixture_padding'] = 'x' * (per_row + (i < remainder))
        self.assertEqual(body_bytes(), target)
        payload = self.commit(claim, rows)
        setup_timings = dict(self._commit_timings)
        self.assertEqual(len(payload['raw_body'].encode()), target)

        with self.f.admin() as conn:
            gate = conn.execute(f'''SELECT s.seed_complete,e.processed_at,
                p.record_count,octet_length(p.raw_body) raw_bytes,
                p.body_sha256=b.body_sha256 AND b.body_sha256=b.readback_sha256
                 AND p.record_count=b.actual_records integrity,
                (SELECT count(*) FROM {self.f.schema}.backfill_tasks_v2 t
                  WHERE t.run_id=%s AND t.kind='alpaca_option_bars') children
                FROM {self.f.schema}.backfill_contract_state_v2 s
                JOIN {self.f.schema}.backfill_contract_enumeration_v2 e ON e.run_id=s.run_id
                JOIN {self.f.schema}.backfill_pages_v2 p USING(task_id,page_no)
                JOIN {self.f.schema}.backfill_readbacks_v2 b USING(task_id,page_no)
                WHERE s.run_id=%s AND e.task_id=%s AND e.page_no=0''',
                (self.run, self.run, claim['id'])).fetchone()
            self.assertFalse(gate['seed_complete'])
            self.assertIsNone(gate['processed_at'])
            self.assertTrue(gate['integrity'])
            self.assertEqual((gate['record_count'], gate['raw_bytes'], gate['children']), (1000, target, 0))
            triggers = conn.execute(f'''SELECT t.tgname,t.tgenabled FROM pg_trigger t
                WHERE t.tgrelid=%s::regclass AND NOT t.tgisinternal ORDER BY t.tgname''',
                (self.f.schema + '.backfill_tasks_v2',)).fetchall()
            self.assertTrue(any(t['tgname']=='backfill_contract_child_insert_v2' for t in triggers))
            self.assertTrue(all(t['tgenabled'] != 'D' for t in triggers))
            conn.execute(f'UPDATE {self.f.schema}.backfill_contract_state_v2 SET seed_complete=true WHERE run_id=%s',
                         (self.run,))

        with self.f.admin() as conn:
            profile = conn.execute("SELECT current_setting('server_version') server_version,current_setting('jit') jit,current_setting('plan_cache_mode') plan_cache_mode,current_setting('track_functions') track_functions").fetchone()
            conn.commit()
            conn.execute("SET LOCAL statement_timeout='8s'")
            conn.execute("SET LOCAL lock_timeout='3s'")
            conn.execute('SELECT pg_advisory_xact_lock(706314020261028)')
            started = perf_counter()
            answer = conn.execute(f'SELECT {self.f.schema}.backfill_contract_admit_page_v2(%s,0) result',
                                  (claim['id'],)).fetchone()['result']
            admission_seconds = perf_counter() - started
            function_profile = conn.execute('''SELECT funcname,calls,total_time,self_time
                FROM pg_stat_xact_user_functions WHERE schemaname=%s AND calls>0
                ORDER BY total_time DESC,funcname''', (self.f.schema,)).fetchall()
            self.assertEqual(answer['state'], 'CONTRACT_WORK_LINKED')
            self.assertEqual((answer['new_children'], answer['linked_source_contracts'], answer['unlinked_source_contracts']),
                             (10, 1000, 0))
            actual = conn.execute(f'''SELECT
                (SELECT count(*) FROM {self.f.schema}.backfill_tasks_v2 WHERE run_id=%s AND kind='alpaca_option_bars') children,
                (SELECT count(*) FROM {self.f.schema}.backfill_contract_work_v2 WHERE run_id=%s) registered,
                (SELECT count(*) FROM {self.f.schema}.backfill_contract_parent_links_v2 WHERE run_id=%s) links,
                (SELECT min(jsonb_array_length(scope->'symbols')) FROM {self.f.schema}.backfill_tasks_v2 WHERE run_id=%s AND kind='alpaca_option_bars') min_batch,
                (SELECT max(jsonb_array_length(scope->'symbols')) FROM {self.f.schema}.backfill_tasks_v2 WHERE run_id=%s AND kind='alpaca_option_bars') max_batch''',
                (self.run,)*5).fetchone()
            self.assertEqual(dict(actual), {'children':10, 'registered':1000, 'links':1000, 'min_batch':100, 'max_batch':100})
            same_page = conn.execute(f'SELECT body_sha256,record_count FROM {self.f.schema}.backfill_pages_v2 WHERE task_id=%s AND page_no=0',
                                    (claim['id'],)).fetchone()
            self.assertEqual((same_page['body_sha256'],same_page['record_count']), (payload['body_sha256'],1000))
            conn.commit()
        RESULT.update(source_checks=source_checks, setup_commit_verify_seconds=setup_timings,
            synthetic_page={'records':1000,'raw_bytes':target,'inert_padding':True,
                'source_page_and_independent_readback_immutable':True},
            admission_seconds=admission_seconds, actual_result=answer,
            postconditions=dict(actual), task_triggers=[dict(t) for t in triggers],
            enabled_trigger_chain=True, seed_false_during_commit_and_readback=True,
            seed_true_before_measured_admission=True, local_profile=dict(profile),
            local_function_profile=[dict(x) for x in function_profile],
            interpretation='One synthetic fresh-registry local PostgreSQL admission including unchanged real child triggers; warm fixture and instrumentation. Not production timing or the prior failed monitor snapshot. Global gate held locally without contention; no production settings changed.')


if __name__ == '__main__':
    expected = 'postgresql://postgres@127.0.0.1:55432/astra_ingestion_qualification'
    if os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL') != expected:
        raise SystemExit('Only the known disposable loopback PostgreSQL fixture is permitted')
    started = perf_counter()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite([
        AdmissionBaseline('test_unchanged_1000_contract_admission_and_insert_triggers')]))
    RESULT.update(passed=result.wasSuccessful(), tests=result.testsRun, errors=len(result.errors),
        failures=len(result.failures), skips=len(result.skipped), total_seconds=perf_counter()-started,
        runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest())
    path=Path('/tmp/replacement-contract-admission-baseline-v71.json')
    path.write_text(json.dumps(RESULT,indent=2,default=str)+'\n')
    print(json.dumps({'receipt':str(path),'sha256':sha256(path.read_bytes()).hexdigest(),
        'passed':result.wasSuccessful(),'admission_seconds':RESULT.get('admission_seconds')}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
