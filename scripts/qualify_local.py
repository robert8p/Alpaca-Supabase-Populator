"""Produce honest local evidence; never contacts a live provider or database."""
import contextlib
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import sys
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from astra_ingestion.models import IngestionSpec
from astra_ingestion.source import FetchResult
from astra_ingestion.store import Store
from astra_ingestion.worker import Worker

def main():
    output=ROOT/"evidence"
    output.mkdir(exist_ok=True)
    log=io.StringIO()
    suite=unittest.defaultTestLoader.discover(str(ROOT/"tests"/"ingestion"),pattern="test_*.py")
    with contextlib.redirect_stderr(log):
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    report={
        "schema":"astra.ingestion.local-qualification/1",
        "observed_at":datetime.now(timezone.utc).isoformat(),
        "origin":"LOCAL_SYNTHETIC_REFERENCE",
        "backend":"SQLite reference adapter",
        "tests_discovered":result.testsRun,
        "passed":result.testsRun-len(result.failures)-len(result.errors)-len(result.skipped),
        "failed":len(result.failures),"errors":len(result.errors),
        "skipped":[{"test":str(test),"reason":reason} for test,reason in result.skipped],
        "postgres_qualification":"NOT_RUN",
        "asgi_runtime_qualification":"NOT_RUN",
        "live_provider_qualification":"NOT_RUN",
        "deployed":"NO",
    }
    (output/"local-tests.txt").write_text(log.getvalue())
    (output/"local-tests.json").write_text(json.dumps(report,indent=2)+"\n")
    if not result.wasSuccessful():
        print(json.dumps(report,indent=2));return 1

    fixture=json.dumps({"bars":{"AAPL":[{"t":"2025-09-02T13:30:00Z","o":100,"h":101,"l":99,"c":100.5,"v":100,"n":4,"vw":100.25}]},"next_page_token":None})
    class Fixture:
        calls=0
        def fetch_page(self,*_):
            self.calls+=1
            return FetchResult(fixture,"synthetic-local-canary")
    with tempfile.TemporaryDirectory(prefix="astra-local-proof-") as directory:
        store=Store("sqlite:///"+str(Path(directory)/"ledger.db"),test_mode=True);store.migrate()
        spec=IngestionSpec.from_dict({"name":"Synthetic local qualification","symbols":["AAPL"],"start":"2025-09-02T13:30:00Z","end":"2025-09-02T14:00:00Z"})
        job=store.submit_job(spec,"local-synthetic-qualification-20261028")
        source=Fixture();worker=Worker(store,source)
        before=store.get_job(job["id"])
        first=worker.run_once();after_write=store.get_job(job["id"])
        second=Worker(Store(store.database_url,test_mode=True),source).run_once()
        after_verification=store.get_job(job["id"])
        assert first["state"]=="page_committed" and after_write["verification_status"]=="pending"
        assert second["state"]=="verified" and after_verification["status"]=="completed" and source.calls==1
        proof={"origin":"SYNTHETIC_ONLY_NOT_MARKET_DATA","source_response_sha256":hashlib.sha256(fixture.encode()).hexdigest(),
               "source_calls":source.calls,"scope":spec.to_dict(),"scope_hash":spec.scope_hash,
               "transitions":[{"stage":"admitted","status":before["status"],"verification":before["verification_status"]},
                              {"stage":"committed","status":after_write["status"],"verification":after_write["verification_status"]},
                              {"stage":"fresh_readback","status":after_verification["status"],"verification":after_verification["verification_status"]}],
               "verification":after_verification["partitions"][0]["verification"]["result"],
               "production_completion_claim":False}
        (output/"synthetic-canary.json").write_text(json.dumps(proof,indent=2)+"\n")
    print(json.dumps({"passed":report["passed"],"skipped":len(report["skipped"]),"failed":report["failed"],
                      "synthetic_canary":"passed","production_qualification":"NOT_RUN"}))
    return 0
if __name__=="__main__":raise SystemExit(main())
