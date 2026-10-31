import hashlib
import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from astra_ingestion.models import IngestionSpec
from astra_ingestion.source import FetchResult, SourceError, parse_page
from astra_ingestion.store import LeaseLost, Store
from astra_ingestion.worker import Worker

BASE = {"name":"Qualification", "symbols":["AAPL"], "start":"2025-09-02T13:30:00Z",
        "end":"2025-09-02T14:00:00Z", "timeframe":"5Min"}
def body(token=None, symbol="AAPL", timestamp="2025-09-02T13:30:00Z"):
    return json.dumps({"bars":{symbol:[{"t":timestamp,"o":100,"h":101,"l":99,"c":100.5,"v":100,"n":4,"vw":100.25}]},
                       "next_page_token":token})
class FixtureSource:
    def __init__(self, *responses):
        self.responses=list(responses) or [body()]
        self.calls=0
    def fetch_page(self, spec, partition, page_token=None):
        self.calls+=1
        value=self.responses.pop(0)
        if isinstance(value, Exception):
            raise value
        return FetchResult(value,"fixture-request")

class StoreWorkerTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.url="sqlite:///"+str(Path(self.tmp.name)/"ledger.db")
        self.store=Store(self.url, test_mode=True)
        self.store.migrate()
    def tearDown(self):
        self.tmp.cleanup()
    def submit(self, **changes):
        return self.store.submit_job(IngestionSpec.from_dict({**BASE,**changes}), "qualification-001")
    def sql(self, query,args=()):
        with self.store.transaction() as c:
            return self.store.execute(c,query,args).fetchall()
    def unpace(self):
        self.sql("UPDATE {s}source_limits SET next_request_at=0")
        self.sql("UPDATE {s}partitions SET next_attempt_at=0")
    def claim(self):
        return self.store.claim_next("original")
    def parsed(self):
        return parse_page(body(),symbol="AAPL",start=BASE["start"],end=BASE["end"],timeframe="5Min")

    def test_end_to_end_requires_a_separate_verification_step(self):
        job=self.submit(); source=FixtureSource();worker=Worker(self.store,source)
        self.assertEqual(worker.run_once()["state"],"page_committed")
        pending=self.store.get_job(job["id"])
        self.assertEqual(pending["verification_status"],"pending")
        self.assertNotEqual(pending["status"],"completed")
        self.assertEqual(worker.run_once()["state"],"verified")
        complete=self.store.get_job(job["id"])
        self.assertEqual((complete["status"],complete["verification_status"]),("completed","passed"))
        self.assertEqual(complete["record_count"],1)
        self.assertEqual(complete["partitions"][0]["verification"]["result"]["status"],"passed")
        self.assertEqual(complete["coverage_certification"],"NOT_CERTIFIED")
        self.assertEqual(source.calls,1)

    def test_duplicate_submission_is_idempotent_and_changed_scope_is_rejected(self):
        a=self.submit(); b=self.submit()
        self.assertEqual(a["id"],b["id"])
        self.assertEqual(len(self.store.list_jobs()),1)
        with self.assertRaises(ValueError):self.submit(symbols=["MSFT"])
        self.assertEqual(len(self.sql("SELECT * FROM {s}partitions")),1)

    def test_database_rejects_mutating_the_original_job_scope(self):
        self.submit()
        with self.assertRaises(sqlite3.IntegrityError):
            self.sql("UPDATE {s}jobs SET spec='{}'")

    def test_stale_owner_cannot_commit_or_report_failure_after_takeover(self):
        self.submit(); old=self.claim()
        self.sql("UPDATE {s}partitions SET lease_until=0")
        new=self.store.claim_next("replacement")
        self.assertGreater(new["generation"],old["generation"])
        with self.assertRaises(LeaseLost):self.store.commit_page(old,FetchResult(body(),"fixture"),self.parsed())
        with self.assertRaises(LeaseLost):self.store.fail_claim(old,code="late",message="obsolete")
        self.assertEqual(len(self.sql("SELECT * FROM {s}receipts")),0)
        self.assertEqual(len(self.sql("SELECT * FROM {s}records")),0)

    def test_pause_and_cancel_fence_inflight_work_and_resume_preserves_scope(self):
        job=self.submit(); old=self.claim()
        self.store.control_job(job["id"],"pause")
        with self.assertRaises(LeaseLost):self.store.commit_page(old,FetchResult(body(),"fixture"),self.parsed())
        self.assertIsNone(self.store.claim_next("other"))
        self.store.control_job(job["id"],"resume")
        new=self.store.claim_next("other")
        self.assertEqual(new["spec"]["symbols"],["AAPL"])
        self.store.control_job(job["id"],"cancel")
        with self.assertRaises(LeaseLost):self.store.commit_page(new,FetchResult(body(),"fixture"),self.parsed())
        self.assertEqual(self.store.get_job(job["id"])["status"],"cancelled")

    def test_empty_source_is_a_visible_hold_and_symbol_remains_expected(self):
        job=self.submit(); worker=Worker(self.store,FixtureSource('{"bars":{},"next_page_token":null}'))
        worker.run_once()
        blocked=self.store.get_job(job["id"])
        self.assertEqual(blocked["status"],"blocked")
        self.assertEqual(blocked["spec"]["symbols"],["AAPL"])
        self.assertEqual(blocked["partitions"][0]["symbol"],"AAPL")
        self.assertIn("No source records",blocked["partitions"][0]["error"])
        self.assertEqual(len(self.sql("SELECT * FROM {s}rejections")),1)
        with self.assertRaises(ValueError):self.store.control_job(job["id"],"resume")

    def test_an_invalid_partition_does_not_discard_independent_work(self):
        job=self.submit(symbols=["AAPL","MSFT"])
        source=FixtureSource('{"bars":{},"next_page_token":null}', body(symbol="MSFT"))
        worker=Worker(self.store,source)
        worker.run_once();self.unpace();worker.run_once();worker.run_once()
        final=self.store.get_job(job["id"])
        self.assertEqual(final["status"],"blocked")
        self.assertEqual([p["status"] for p in final["partitions"]],["blocked","verified"])
        self.assertEqual(final["record_count"],1)

    def test_target_value_tampering_is_detected_despite_equal_counts(self):
        job=self.submit();worker=Worker(self.store,FixtureSource());worker.run_once()
        row=self.sql("SELECT payload FROM {s}records")[0]
        value=json.loads(row["payload"]);value["close"]="100.75"
        self.sql("UPDATE {s}records SET payload=?",(json.dumps(value),))
        self.assertEqual(worker.run_once()["state"],"blocked")
        result=json.loads(self.sql("SELECT result FROM {s}verifications")[0]["result"])
        self.assertEqual(result["changed_count"],1)
        self.assertEqual(self.store.get_job(job["id"])["verification_status"],"blocked")

    def test_stored_primary_key_tampering_is_detected(self):
        job=self.submit();worker=Worker(self.store,FixtureSource());worker.run_once()
        self.sql("UPDATE {s}records SET record_key='wrong-key'")
        worker.run_once()
        self.assertEqual(self.store.get_job(job["id"])["status"],"blocked")
        self.assertIn("key does not match",self.store.get_job(job["id"])["partitions"][0]["error"])

    def test_missing_target_and_corrupt_source_receipt_are_detected(self):
        job=self.submit();worker=Worker(self.store,FixtureSource());worker.run_once()
        self.sql("DELETE FROM {s}records")
        worker.run_once()
        result=json.loads(self.sql("SELECT result FROM {s}verifications")[0]["result"])
        self.assertEqual(result["missing_count"],1)
        # Source integrity is independently covered by a fresh database/job below.
        other=Store("sqlite:///"+str(Path(self.tmp.name)/"other.db"),test_mode=True);other.migrate()
        j=other.submit_job(IngestionSpec.from_dict(BASE),"other-key-001");w=Worker(other,FixtureSource());w.run_once()
        with other.transaction() as c:other.execute(c,"UPDATE {s}receipts SET body_sha256='broken'")
        w.run_once()
        self.assertEqual(other.get_job(j["id"])["status"],"blocked")

    def test_repeated_page_token_holds_without_partial_second_page(self):
        job=self.submit();worker=Worker(self.store,FixtureSource(body("repeat"),body("repeat",timestamp="2025-09-02T13:35:00Z")))
        worker.run_once();self.unpace();worker.run_once()
        final=self.store.get_job(job["id"])
        self.assertEqual(final["status"],"blocked")
        self.assertEqual(final["record_count"],1)
        self.assertEqual(len(self.sql("SELECT * FROM {s}receipts")),1)
        self.assertIn("pagination token",final["partitions"][0]["error"])

    def test_rate_limit_wait_is_durable_and_no_retry_storm_occurs(self):
        job=self.submit();source=FixtureSource(SourceError("provider_http","Provider returned HTTP 429",True,60))
        worker=Worker(self.store,source);worker.run_once()
        with self.store.snapshot() as c:
            now=self.store.now(c);p=self.store.execute(c,"SELECT * FROM {s}partitions").fetchone()
            self.assertGreaterEqual(p["next_attempt_at"]-now,59)
        self.assertEqual(worker.run_once()["state"],"idle")
        self.assertEqual(source.calls,1)
        self.assertEqual(self.store.get_job(job["id"])["request_count"],1)

    def test_extreme_retry_after_is_persisted_as_terminal_outcome(self):
        job=self.submit()
        worker=Worker(self.store,FixtureSource(SourceError("provider_http","Provider returned HTTP 429",True,1e100)))
        worker.run_once()
        final=self.store.get_job(job["id"])
        self.assertEqual(final["status"],"failed")
        self.assertIn("exceeds the original job deadline",final["partitions"][0]["error"])
        self.assertEqual(final["partitions"][0]["retry_count"],1)

    def test_second_transient_failure_exhausts_preserved_attempt_budget(self):
        job=self.submit();error=SourceError("provider_transport","timeout",True,1)
        source=FixtureSource(error,error);worker=Worker(self.store,source)
        worker.run_once();self.unpace();worker.run_once()
        self.assertEqual(self.store.get_job(job["id"])["status"],"failed")
        self.assertEqual(self.store.get_job(job["id"])["partitions"][0]["retry_count"],2)
        self.assertEqual(worker.run_once()["state"],"idle")
        self.assertEqual(source.calls,2)

    def test_request_budget_is_reserved_before_network_dispatch(self):
        job=self.submit(max_requests=1);source=FixtureSource(body("next"));worker=Worker(self.store,source)
        worker.run_once();self.unpace();worker.run_once()
        self.assertEqual(source.calls,1)
        self.assertEqual(self.store.get_job(job["id"])["status"],"blocked")
        self.assertIn("request budget",self.store.get_job(job["id"])["partitions"][0]["error"])

    def test_deadline_prevents_dispatch_and_does_not_reset_on_restart(self):
        job=self.submit();self.sql("UPDATE {s}jobs SET deadline_at=0")
        source=FixtureSource();worker=Worker(self.store,source)
        self.assertEqual(worker.run_once()["state"],"idle")
        self.assertEqual(source.calls,0)
        self.assertEqual(self.store.get_job(job["id"])["status"],"failed")

    def test_expiry_during_write_rolls_back_receipt_records_and_progress(self):
        self.submit();claim=self.claim()
        with self.store.snapshot() as c:now=self.store.now(c)
        with patch.object(self.store,"now",side_effect=[now,now+200]):
            with self.assertRaises(LeaseLost):self.store.commit_page(claim,FetchResult(body(),"fixture"),self.parsed())
        self.assertEqual(len(self.sql("SELECT * FROM {s}records")),0)
        self.assertEqual(len(self.sql("SELECT * FROM {s}receipts")),0)
        self.assertEqual(self.store.list_jobs()[0]["record_count"],0)

    def test_process_crash_after_commit_resumes_verification_without_refetch(self):
        job=self.submit()
        program = """
import os,sys
from astra_ingestion.store import Store
from astra_ingestion.worker import Worker
from astra_ingestion.source import FetchResult
class Source:
 def fetch_page(self,*args): return FetchResult(sys.argv[2],'crash-fixture')
Worker(Store(sys.argv[1],test_mode=True),Source(),after_commit=lambda _:os._exit(23)).run_once()
"""
        result=subprocess.run([sys.executable,"-c",program,self.url,body()],capture_output=True,text=True,timeout=10)
        self.assertEqual(result.returncode,23,result.stderr)
        source=FixtureSource()
        outcome=Worker(Store(self.url,test_mode=True),source).run_once()
        self.assertEqual(outcome["state"],"verified")
        self.assertEqual(source.calls,0)
        self.assertEqual(self.store.get_job(job["id"])["record_count"],1)
        self.assertEqual(len(self.sql("SELECT * FROM {s}receipts")),1)
        self.assertEqual(self.store.get_job(job["id"])["status"],"completed")

if __name__=="__main__":unittest.main()
