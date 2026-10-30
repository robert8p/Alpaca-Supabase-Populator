"""Run bounded disposable-PG tests; retain every attempt as a distinct receipt."""
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
from time import perf_counter
import unittest

HERE=Path(__file__).resolve().parent
STAGE=Path('/tmp/replacement-maintenance-index-staged-v72')
EXPECTED='postgresql://postgres@127.0.0.1:55432/astra_ingestion_qualification'
if os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL')!=EXPECTED:
    raise SystemExit('Only the established disposable loopback PostgreSQL target is allowed')
sys.path[:0]=[str(STAGE/'tests/ingestion'),str(STAGE)]
import test_backfill_maintenance_phase_observation_v73 as target
suite=unittest.defaultTestLoader.loadTestsFromModule(target)
started=perf_counter();result=unittest.TextTestRunner(verbosity=2).run(suite)
target.RESULT.update(tests=result.testsRun,failures=len(result.failures),errors=len(result.errors),
    skipped=len(result.skipped),passed=result.wasSuccessful(),elapsed_seconds=perf_counter()-started,
    candidate_sha256=sha256(target.CANDIDATE.encode()).hexdigest(),
    test_sha256=sha256(Path(target.__file__).read_bytes()).hexdigest(),
    errors_detail=[{'test':str(test),'trace':trace} for test,trace in result.errors],
    failures_detail=[{'test':str(test),'trace':trace} for test,trace in result.failures])
attempt=1
while (HERE/f'maintenance_phase_observation_qualification_attempt_{attempt}_v73.json').exists():attempt+=1
p=HERE/f'maintenance_phase_observation_qualification_attempt_{attempt}_v73.json'
p.write_text(json.dumps(target.RESULT,indent=2,default=str)+'\n')
print(json.dumps({'path':str(p),'sha256':sha256(p.read_bytes()).hexdigest(),'passed':result.wasSuccessful(),
                  'tests':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'skips':len(result.skipped)}))
raise SystemExit(0 if result.wasSuccessful() else 1)
