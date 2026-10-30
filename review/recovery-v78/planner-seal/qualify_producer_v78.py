"""Run only new v78 tests in a separately staged, already-qualified local fixture."""
from contextlib import redirect_stdout, redirect_stderr
from hashlib import sha256, sha1
import importlib, io, json, os
from pathlib import Path
import sys, time, unittest

ROOT=Path(__file__).resolve().parents[3]
STAGE=Path('/tmp/replacement-planner-seal-fixture-v78')
OUT=ROOT/'review/recovery-v78/planner-seal'
ATTEMPT=int(sys.argv[1])
TARGET=OUT/f'producer_qualification_attempt{ATTEMPT:02}_v78.json'
if TARGET.exists():raise RuntimeError('Attempt receipts are immutable; use the next attempt number')
if os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL')!='postgresql://postgres@127.0.0.1:55432/astra_ingestion_qualification':raise RuntimeError('Only the existing disposable loopback database is admitted by this runner')
read_files=set()
def audit(event,args):
 if event=='open' and isinstance(args[0],str):
  p=Path(args[0]).resolve()
  if p.is_relative_to(STAGE):read_files.add(p)
sys.addaudithook(audit)
sys.path[:0]=[str(STAGE/'tests/ingestion'),str(STAGE)]
stream=io.StringIO();start=time.monotonic()
with redirect_stdout(stream),redirect_stderr(stream):
 module=importlib.import_module('test_backfill_seal_dynamic_exclusions_v78')
 suite=unittest.defaultTestLoader.loadTestsFromModule(module)
 result=unittest.TextTestRunner(stream=stream,verbosity=2).run(suite)
for mod in list(sys.modules.values()):
 p=getattr(mod,'__file__',None)
 if p and Path(p).resolve().is_relative_to(STAGE):read_files.add(Path(p).resolve())
proof=json.loads((ROOT/'review/recovery-v77/defer_publication_local_proof_v77.json').read_text())
expected={r['path']:r for r in proof['expected_leaves']}
new={'tests/ingestion/test_backfill_seal_dynamic_exclusions_v78.py','sql/astra_backfill_seal_dynamic_exclusions_v78.sql','sql/astra_backfill_seal_dynamic_exclusions_restore_v78.sql','review/recovery-v78/planner-seal/candidate_archive_v78.json'}
receipts=[]
for path in sorted(read_files):
 if path.suffix=='.pyc' or not path.is_file():continue
 rel=str(path.relative_to(STAGE));raw=path.read_bytes();blob=sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
 receipts.append({'path':rel,'sha256':sha256(raw).hexdigest(),'git_blob':blob,'bytes':len(raw),'classification':'new_v78' if rel in new else 'published_08bea_dependency','published_base_blob':expected.get(rel,{}).get('sha'),'base_match':None if rel in new else blob==expected.get(rel,{}).get('sha')})
bad=[r for r in receipts if r['classification']=='published_08bea_dependency' and not r['base_match']]
cleanup=None
if hasattr(module.SealPostgreSQLTests,'fixture'):
 f=module.SealPostgreSQLTests.fixture('runTest')
 with f.admin() as conn:cleanup=conn.execute('SELECT NOT EXISTS(SELECT 1 FROM pg_namespace WHERE nspname=%s) absent',(f.schema,)).fetchone()['absent']
value={'schema':'astra.planner-seal-producer-postgresql-qualification/1','attempt':ATTEMPT,'status':'PASS' if result.wasSuccessful() and not bad and cleanup is True else 'FAIL','elapsed_seconds':round(time.monotonic()-start,3),'tests_run':result.testsRun,'failures':len(result.failures),'errors':len(result.errors),'skipped':len(result.skipped),'log':stream.getvalue(),'results':module.RESULT,'loaded_source_dependency_receipts':receipts,'base_dependency_mismatches':bad,'cleanup_schema_absent':cleanup,'production_calls':0,'provider_calls':0,'base_commit':'08bea176e39174f8c39f62caebae79d5cb50cdcf','fixture_database_route':'existing disposable loopback database; no production route'}
TARGET.write_text(json.dumps(value,indent=2,sort_keys=True,default=str)+'\n')
print(json.dumps({k:value[k] for k in ('attempt','status','elapsed_seconds','tests_run','failures','errors','skipped','cleanup_schema_absent')},sort_keys=True))
print('receipt',str(TARGET),'sha256',sha256(TARGET.read_bytes()).hexdigest())
print(stream.getvalue()[-18000:])
if bad:print('DEPENDENCY_MISMATCHES',json.dumps(bad))
sys.exit(0 if value['status']=='PASS' else 1)
