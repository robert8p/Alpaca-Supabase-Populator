"""Local qualification of the immutable-page contract read diagnostic."""
from hashlib import sha256
import json
from pathlib import Path
import sys
from time import monotonic
import unittest
import qualify_maintenance_selectors_v71 as profile

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
sys.path.append(str(ROOT/'tests/ingestion'))
import test_backfill_shared_records_v2 as shared
import test_backfill_contract_registry_v2 as registry

profile.SQL=HERE/'contract_admission_reads_readonly_v71.sql'
profile.MARKER='ASTRA_CONTRACT_READS_V71:'
extra=json.loads((HERE/'contract_admission_read_derivation_v71.json').read_text())['additional_pins']
profile.DERIVATION['source_pins'].update({k.removeprefix('astra_ingestion_v1.'):v for k,v in extra.items()})
TASK='backfill-plan-0a93df963fd7ef5a5c67e7534302d55c4fc5db535c9ff5bb8f7238d78af181e8'
SENTINEL='PRIVATE_FIXTURE_FIELD_MUST_NOT_LEAVE_DATABASE_8c4223'
RESULT={}


class Qualification(profile.Qualification):
    new=shared.SharedRecordsTests.new
    commit=shared.SharedRecordsTests.commit
    verify=shared.SharedRecordsTests.verify
    contract=staticmethod(registry.ContractRegistryTests.contract)

    def source(self):
        source=super().source()
        if hasattr(self,'probe_task'):
            source=source.replace(TASK,self.probe_task).replace('2026-10-30T07:14:07.869655+00:00',self.probe_committed_at)
        return source

    def contract_snapshot(self,conn):
        return {table:conn.execute(f'''SELECT count(*) n,encode(sha256(convert_to(COALESCE(
            string_agg(to_jsonb(x)::text,E'\n' ORDER BY to_jsonb(x)::text),''),'UTF8')),'hex') digest
            FROM {self.f.schema}.{table} x''').fetchone() for table in (
                'backfill_contract_state_v2','backfill_contract_work_v2','backfill_contract_enumeration_v2',
                'backfill_contract_parent_links_v2','backfill_contract_registered_children_v2')}

    def test_actual_read_phases_sanitized_and_no_mutation(self):
        with self.f.admin() as conn:
            conn.execute(f'INSERT INTO {self.f.schema}.backfill_contract_state_v2(run_id,seed_complete) VALUES(%s,false)',(self.run,))
        claim=self.new(kind='alpaca_option_contracts',family='CTX02',status='inactive')
        rows=[{**self.contract(i),'fixture_padding':''} for i in range(1000)]
        rows[0]['fixture_private_marker']=SENTINEL
        size=lambda:len(json.dumps({'option_contracts':rows,'next_page_token':None}).encode())
        remaining=705542-size()
        each,rest=divmod(remaining,1000)
        for i,row in enumerate(rows):row['fixture_padding']='x'*(each+(i<rest))
        self.assertEqual(size(),705542)
        self.commit(claim,rows)
        self.probe_task=claim['id']
        with self.f.admin() as conn:
            self.probe_committed_at=conn.execute(f'SELECT committed_at FROM {self.f.schema}.backfill_pages_v2 WHERE task_id=%s AND page_no=0',(claim['id'],)).fetchone()['committed_at'].isoformat()
            conn.execute(f'UPDATE {self.f.schema}.backfill_contract_state_v2 SET seed_complete=true WHERE run_id=%s',(self.run,))
        sql=self.source()
        with self.f.admin() as conn:
            before=self.snapshot(conn)
            contract_before=self.contract_snapshot(conn)
            conn.commit()
            started=monotonic()
            with self.assertRaises(self.f.psycopg.Error) as caught:conn.execute(sql)
            elapsed=monotonic()-started
            self.assertEqual(caught.exception.sqlstate,'P0001',caught.exception.diag.message_primary)
            message=caught.exception.diag.message_primary
            self.assertTrue(message.startswith(profile.MARKER),message[:250])
            result=json.loads(message[len(profile.MARKER):])
            conn.rollback()
            self.assertEqual(before,self.snapshot(conn))
            self.assertEqual(contract_before,self.contract_snapshot(conn))
            self.assertEqual(conn.execute("SELECT count(*) n FROM pg_locks WHERE pid=pg_backend_pid() AND locktype='advisory'").fetchone()['n'],0)
        self.assertTrue(result['complete'])
        self.assertTrue(result['admission_currently_pending'])
        self.assertEqual((result['parsed_records'],result['eligible_rows']),(1000,1000))
        self.assertEqual(result['transaction_read_only'],'on')
        self.assertFalse(result['raw_source_or_parsed_rows_returned'])
        self.assertFalse(result['admission_or_registration_invoked'])
        self.assertNotIn(SENTINEL,message)
        self.assertNotIn(self.contract()['symbol'],message)
        self.assertLess(elapsed,8)
        self.assertLess(len(message.encode()),60000)
        self.assertEqual([x['component'] for x in result['results']],['UNREGISTERED_SYMBOL_BATCHES','EXISTING_PARENT_LINKS'])
        self.assertEqual(result['results'][0]['nodes'][0]['actual_rows'],10)
        self.assertEqual(result['results'][1]['nodes'][0]['actual_rows'],0)
        allowed={'path','node_type','parent_relationship','join_type','relation','index','actual_rows','actual_loops',
            'rows_removed_filter','rows_removed_join_filter','shared_hits','shared_reads','temp_reads','temp_writes'}
        for phase in result['results']:
            for node in phase['nodes']:self.assertEqual(set(node),allowed)
        RESULT['probe']={'passed':True,'elapsed_seconds':elapsed,'synthetic_records':1000,'synthetic_raw_bytes':705542,
            'actual_eligible_batch_count':10,'existing_parent_links':0,'source_and_contract_tables_unchanged':True,
            'raw_source_sentinel_and_parsed_symbols_absent':True,'only_allowlisted_plan_metrics':True,
            'no_advisory_lock':True,'result_bytes':len(message.encode())}
        (HERE/'contract_admission_reads_synthetic_result_v71.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    started=monotonic()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Qualification(name) for name in [
        'test_source_drift_fails_closed','test_missing_readonly_fails_closed','test_actual_read_phases_sanitized_and_no_mutation']))
    RESULT.update(schema='astra.contract-read-diagnostic-qualification/1',passed=result.wasSuccessful(),
        tests=result.testsRun,errors=len(result.errors),failures=len(result.failures),skipped=len(result.skipped),
        elapsed_seconds=monotonic()-started,production_calls=0,sql_sha256=sha256(profile.SQL.read_bytes()).hexdigest(),
        test_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        fixture_adaptation='Schema, run/task IDs, commit time and corresponding local source hashes only. Synthetic source has the exact observed1000records/705542bytes; actual current admission logic remains unchanged.')
    path=HERE/'contract_admission_reads_qualification_v71.json'
    path.write_text(json.dumps(RESULT,indent=2)+'\n')
    print(json.dumps({'passed':result.wasSuccessful(),'receipt':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
