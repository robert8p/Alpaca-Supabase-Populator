"""Independent bounded classifier/source checks; no PostgreSQL or provider use."""
from contextlib import redirect_stdout, redirect_stderr
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
from time import perf_counter
import unittest

STAGE=Path('/tmp/replacement-defer-retry-fixture-v77')
HERE=Path(__file__).resolve().parent
EXPECTED={
 'astra_ingestion/rpc_store.py':'7614f7bf1094afbb552e657683726b7549c0b84d45cd3756ced79617042d3e11',
 'tests/ingestion/test_rpc_lock_abort_retry.py':'939d655c2ae59e97d7ad62466147bb4dc7f3be320d2a6f385fc1e5fae94f42b1',
 'tests/ingestion/test_rpc_defer_lock_abort_retry_v77.py':'7a9f8b76091187812b3439617eb936c224947ddf0b52d5e93937579eb0392e07',
 'review/recovery-v77/defer-native-lock-retry/defer_source_bundle_v77.json':'24e6c46d90e03442607eef934501577bd53ae45a43ec7e30fba31bf2b5f008a7'}
network_events=[]
def audit(event,args):
 if event in ('socket.connect','socket.bind','socket.getaddrinfo'):
  network_events.append(event)
  raise AssertionError('Network access is outside this independent unit qualification')
sys.addaudithook(audit)
for name,digest in EXPECTED.items():
 if sha256((STAGE/name).read_bytes()).hexdigest()!=digest:raise AssertionError(name)
sys.path[:0]=[str(STAGE),str(STAGE/'tests/ingestion')]
names=['test_rpc_lock_abort_retry.LockAbortRetryTests','test_rpc_defer_lock_abort_retry_v77.DeferSourceAndBoundaryTests']
suite=unittest.defaultTestLoader.loadTestsFromNames(names)
log,out,err=io.StringIO(),io.StringIO(),io.StringIO()
t0=perf_counter()
with redirect_stdout(out),redirect_stderr(err):result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
for name,digest in EXPECTED.items():
 if sha256((STAGE/name).read_bytes()).hexdigest()!=digest:raise AssertionError('Input changed during qualification: '+name)
passed=result.wasSuccessful() and result.testsRun==19 and not result.skipped and not network_events
receipt={'schema':'astra.independent-defer-boundary-qualification/1','passed':passed,'tests':result.testsRun,
 'errors':len(result.errors),'failures':len(result.failures),'skips':len(result.skipped),'seconds':round(perf_counter()-t0,6),
 'candidate_pins':EXPECTED,'selected_test_classes':names,'network_events':network_events,
 'postgresql_execution':False,'provider_calls':0,'production_calls':0,'native_transactional_evidence_source':'Producer51-case actual-PostgreSQL receipt is independently inspected, not rerun here.',
 'test_log':log.getvalue(),'stdout':out.getvalue(),'stderr':err.getvalue(),
 'runner_sha256':sha256(Path(__file__).read_bytes()).hexdigest()}
p=HERE/'independent_boundary_qualification_v77.json'
if p.exists():raise AssertionError('Refuse to overwrite frozen independent receipt')
b=(json.dumps(receipt,indent=2,sort_keys=True)+'\n').encode();p.write_bytes(b)
print(json.dumps({'path':str(p),'sha256':sha256(b).hexdigest(),'bytes':len(b),**{k:receipt[k] for k in ['passed','tests','errors','failures','skips','seconds']}}))
if not passed:print(log.getvalue())
raise SystemExit(0 if passed else 1)
