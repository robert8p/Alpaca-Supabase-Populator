"""Verify compact candidate metadata transport and read-only boundaries locally."""
from hashlib import sha256
import json
from pathlib import Path
from time import monotonic
import unittest
import qualify_maintenance_selectors_v71 as profile

HERE=Path(__file__).resolve().parent
profile.SQL=HERE/'maintenance_candidate_metadata_readonly_v71.sql'
profile.MARKER='ASTRA_MAINTENANCE_CANDIDATES_V71:'
RESULT={}


class Qualification(profile.Qualification):
    def test_metadata_for_real_unread_page_without_mutation(self):
        task=self.task()
        claim=self.claim()
        self.call('backfill_reserve',{'claim':self.fence(claim)})
        self.call('backfill_commit',self.page(claim))
        sql=self.source()
        with self.f.admin() as conn:
            before=self.snapshot(conn)
            conn.commit()
            started=monotonic()
            with self.assertRaises(self.f.psycopg.Error) as caught:
                conn.execute(sql)
            elapsed=monotonic()-started
            self.assertEqual(caught.exception.sqlstate,'P0001',caught.exception.diag.message_primary)
            message=caught.exception.diag.message_primary
            self.assertTrue(message.startswith(profile.MARKER),message[:250])
            result=json.loads(message[len(profile.MARKER):])
            conn.rollback()
            self.assertEqual(before,self.snapshot(conn))
            self.assertEqual(conn.execute("SELECT count(*) n FROM pg_locks WHERE pid=pg_backend_pid() AND locktype='advisory'").fetchone()['n'],0)
        self.assertTrue(result['complete'])
        self.assertEqual(result['selector_count'],10)
        self.assertEqual(result['transaction_read_only'],'on')
        self.assertEqual(result['transaction_isolation'],'repeatable read')
        candidates=[x for x in result['page_candidates'] if x['component']=='MISSING_READBACK']
        self.assertEqual(len(candidates),1)
        row=candidates[0]
        self.assertEqual(row['task_id'],task)
        self.assertEqual(row['page_no'],0)
        self.assertEqual(row['kind'],'alpaca_reference')
        self.assertEqual(row['archived_pages'],1)
        self.assertEqual(row['verified_pages'],0)
        self.assertEqual(row['source_records'],1)
        self.assertGreater(row['raw_bytes'],0)
        self.assertNotIn('asset-apple',message)
        self.assertNotIn('fixture-request',message)
        self.assertLess(elapsed,8)
        self.assertLess(len(message.encode()),60000)
        RESULT['metadata']={'passed':True,'elapsed_seconds':elapsed,'real_unread_page_metadata_correct':True,
            'source_bodies_and_request_ids_absent':True,'tables_unchanged':True,'no_advisory_lock':True,
            'result_bytes':len(message.encode())}
        (HERE/'maintenance_candidate_metadata_synthetic_result_v71.json').write_text(json.dumps(result,indent=2)+'\n')


if __name__=='__main__':
    started=monotonic()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.TestSuite(Qualification(name) for name in [
        'test_source_drift_fails_closed','test_missing_readonly_fails_closed','test_metadata_for_real_unread_page_without_mutation']))
    RESULT.update(schema='astra.maintenance-candidate-metadata-qualification/1',passed=result.wasSuccessful(),
        tests=result.testsRun,errors=len(result.errors),failures=len(result.failures),skipped=len(result.skipped),
        elapsed_seconds=monotonic()-started,production_calls=0,sql_sha256=sha256(profile.SQL.read_bytes()).hexdigest(),
        test_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
        fixture_adaptation='Same local schema/run/source-pin adaptation as maintenance selector qualification; monitor definition guarded but never invoked.')
    path=HERE/'maintenance_candidate_metadata_qualification_v71.json'
    path.write_text(json.dumps(RESULT,indent=2)+'\n')
    print(json.dumps({'passed':result.wasSuccessful(),'receipt':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}))
    raise SystemExit(0 if result.wasSuccessful() else 1)
