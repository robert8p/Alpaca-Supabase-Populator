"""Local-only runner for the portable source and installation suites."""
from pathlib import Path
from hashlib import sha256
from urllib.parse import urlparse
from time import perf_counter
import importlib,json,os,sys,unittest
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
STAGE=Path('/tmp/replacement-shared-field-cache-fixture-v74')
u=urlparse(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL',''))
if u.hostname not in ('127.0.0.1','localhost') or u.port!=55432 or u.path!='/astra_ingestion_qualification':
 raise RuntimeError('Only the existing explicit loopback disposable PostgreSQL is admitted')
if os.environ.get('GITHUB_WORKFLOW')!='ASTRA ingestion qualification':raise RuntimeError('Explicit dedicated workflow context required')
sys.path[:0]=[str(STAGE/'tests/ingestion'),str(STAGE)]
started=perf_counter();suite=unittest.TestSuite();modules=[]
for name in ['test_backfill_shared_field_cache_v74','test_backfill_shared_field_cache_installation_v74']:
 m=importlib.import_module(name);modules.append(m);cases=unittest.defaultTestLoader.loadTestsFromModule(m)
 if cases.countTestCases()!=4:raise AssertionError('Unexpected inherited or missing cases in '+name)
 suite.addTests(cases)
result=unittest.TextTestRunner(verbosity=2).run(suite)
paths=['tests/ingestion/test_backfill_shared_field_cache_v74.py','tests/ingestion/test_backfill_shared_field_cache_installation_v74.py','sql/astra_backfill_shared_field_cache_v74.sql','sql/astra_backfill_shared_field_cache_restore_v74.sql']
for path in paths:
 if (ROOT/path).read_bytes()!=(STAGE/path).read_bytes():raise AssertionError('Staged active bytes differ: '+path)
d={'schema':'astra.shared-field-active-qualification/1','passed':result.wasSuccessful(),'tests':result.testsRun,
 'errors':len(result.errors),'failures':len(result.failures),'skipped':len(result.skipped),'elapsed_seconds':perf_counter()-started,
 'modules':{m.__name__:m.RESULT for m in modules},'active_paths':[{'path':p,'sha256':sha256((ROOT/p).read_bytes()).hexdigest()} for p in paths],
 'production_calls':0,'no_inherited_duplicate_cases':True,'hosted_ci_wallclock_speedup_assertions':False,
 'error_details':[{'test':str(t),'traceback':e} for t,e in result.errors],
 'failure_details':[{'test':str(t),'traceback':e} for t,e in result.failures]}
p=HERE/'shared_field_active_qualification_v74.json';p.write_text(json.dumps(d,indent=2,default=str)+'\n')
print(json.dumps({'passed':result.wasSuccessful(),'tests':result.testsRun,'receipt':str(p),'sha256':sha256(p.read_bytes()).hexdigest()}))
raise SystemExit(0 if result.wasSuccessful() else 1)
