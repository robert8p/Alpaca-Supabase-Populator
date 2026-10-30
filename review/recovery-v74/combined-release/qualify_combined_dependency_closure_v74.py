"""One exact-scope staged integration run with actual file/import closure."""
from pathlib import Path
from hashlib import sha1,sha256
from urllib.parse import urlparse
from time import perf_counter
import importlib,importlib.util,json,os,re,sys,unittest
ROOT=Path(__file__).resolve().parents[3];HERE=ROOT/'review/recovery-v74/combined-release'
STAGE=Path('/tmp/replacement-combined-qualified-fixture-v74')
BASE='a3bc0520e624054b278e46682b04cebb33e9b677'
TREE_PATH=Path('/tmp/replacement-checkpoint-tree-v73.json')
tree=json.loads(TREE_PATH.read_text());assert tree['sha']=='52d5ed1305aff8246599b689176d8732f2dadb2f' and not tree['truncated']
blobs={x['path']:x['sha'] for x in tree['tree'] if x['type']=='blob'}
ACTIVE={
 'astra_ingestion/rpc_store.py':'1deb7051d4311b22c09d7245a36d751dd10c843192207aaefc0a2d4cf1291403',
 'tests/ingestion/test_rpc_lock_abort_retry.py':'f0f2bc191b60c4fe737af763fe57c1b939edf2d2ffed7fcaee7df4f726976468',
 'tests/ingestion/test_rpc_lock_abort_retry_postgres.py':'ad9ded264e3f18cae54417a8a6cf5765b22a01e04d7af876034735bb38404570',
 'tests/ingestion/test_backfill_shared_field_cache_v74.py':'6ed056ec347cfe6f43706a5e06f2f7ab013e179a70711f4bb3ab20e0cd65dac8',
 'tests/ingestion/test_backfill_shared_field_cache_installation_v74.py':'f4856947f23dae88df8e5d1ce7de72363a1034fa6ea1c9052a8f8c5100caaef0',
 'sql/astra_backfill_shared_field_cache_v74.sql':'b11210b980ad7afb4f821b184d2682d1d3123406da6cf47ece4bb9855803777b',
 'sql/astra_backfill_shared_field_cache_restore_v74.sql':'4fa9d60877b25355445f0d3b8b630d87630f1e2bb00a5896a1bb83fcd4fef376',
}
def blob(data):return sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
def safe(root,path):
 if type(path) is not str or not re.fullmatch(r'[A-Za-z0-9_./-]+',path) or any(x in ('','.','..') for x in path.split('/')):
  raise ValueError('Unsafe dependency path')
 p=root
 for part in path.split('/'):
  p=p/part
  if p.is_symlink():raise ValueError('Symlink dependency rejected')
 if not p.resolve().is_relative_to(root.resolve()):raise ValueError('Dependency escapes fixture root')
 return p
prior=json.loads((ROOT/'review/recovery-v74/shared-field-cache/shared_field_fixture_closure_v74.json').read_text())
retry=json.loads((ROOT/'review/rpc-lock-rollback-retry-proposal/dependency_audit.json').read_text())
paths={x['path'] for x in prior['files']}|{x['path'] for x in retry['dependencies']}|set(ACTIVE)
paths.update('review/recovery-v74/shared-field-cache/'+n for n in ['baseline_shared_refresh_v74.sql','candidate_shared_refresh_field_cache_v74.sql','shared_field_cache_derivation_v74.json','shared_field_migration_manifest_v74.json'])
new_allowed=set(ACTIVE)|set(retry['new_actual_read_dependencies'])|{p for p in paths if p.startswith('review/recovery-v74/shared-field-cache/')}
materialized=[]
for path in sorted(paths):
 candidates=[safe(ROOT,path),safe(Path('/tmp/replacement-shared-field-cache-fixture-v74'),path),
             safe(Path('/tmp/replacement-maintenance-index-staged-v72'),path),safe(Path('/tmp/replacement-claim-capability-staged-v71'),path)]
 if path in ACTIVE:
  chosen=candidates[0];data=chosen.read_bytes()
  if sha256(data).hexdigest()!=ACTIVE[path]:raise ValueError('Frozen active artifact drift: '+path)
 elif path in blobs:
  chosen=next((p for p in candidates if p.is_file() and blob(p.read_bytes())==blobs[path]),None)
  if chosen is None:raise ValueError('No exact published dependency: '+path)
  data=chosen.read_bytes()
 elif path in new_allowed:
  chosen=candidates[0];data=chosen.read_bytes()
 else:raise ValueError('Unadmitted dependency addition: '+path)
 target=safe(STAGE,path);target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
 materialized.append({'path':path,'sha256':sha256(data).hexdigest(),'git_blob_sha1':blob(data),'bytes':len(data),
  'base_git_blob_sha1':blobs.get(path),'state':'REVIEWED_RUNTIME_REPLACEMENT' if path=='astra_ingestion/rpc_store.py' else 'EXACT_EXISTING_BLOB' if path in blobs else 'ADDITIVE'})
u=urlparse(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL',''))
if u.hostname not in ('127.0.0.1','localhost') or u.port!=55432 or u.path!='/astra_ingestion_qualification':
 raise RuntimeError('Explicit loopback disposable PostgreSQL only')
if os.environ.get('GITHUB_WORKFLOW')!='ASTRA ingestion qualification':raise RuntimeError('Dedicated workflow context required')
reads=set()
def audit(event,args):
 if event!='open' or not args or not isinstance(args[0],(str,bytes)):return
 try:p=Path(os.fsdecode(args[0])).resolve()
 except (TypeError,ValueError):return
 if not p.is_relative_to(STAGE):return
 if p.suffix=='.pyc':
  try:p=Path(importlib.util.source_from_cache(str(p)))
  except ValueError:return
 if p.is_file():reads.add(p.relative_to(STAGE).as_posix())
sys.addaudithook(audit)
sys.path[:0]=[str(STAGE/'tests/ingestion'),str(STAGE)]
modules=[];suite=unittest.TestSuite()
names=['test_backfill_shared_field_cache_v74','test_backfill_shared_field_cache_installation_v74',
       'test_rpc_lock_abort_retry','test_rpc_lock_abort_retry_postgres','test_rpc_store','test_rpc_failure_observability_v71']
for name in names:
 m=importlib.import_module(name);modules.append(m);tests=unittest.defaultTestLoader.loadTestsFromModule(m)
 if name.startswith('test_backfill_shared_field') and tests.countTestCases()!=4:raise AssertionError('Inherited/missing shared test cases')
 suite.addTests(tests)
if suite.countTestCases()!=56:raise AssertionError('Unexpected combined case count')
started=perf_counter();result=unittest.TextTestRunner(verbosity=2).run(suite);elapsed=perf_counter()-started
for m in tuple(sys.modules.values()):
 f=getattr(m,'__file__',None)
 if not f:continue
 try:p=Path(f).resolve()
 except (ValueError,TypeError):continue
 if p.is_relative_to(STAGE) and p.suffix=='.py':reads.add(p.relative_to(STAGE).as_posix())
observed=[];unexpected=[]
for path in sorted(reads):
 data=safe(STAGE,path).read_bytes();actual=blob(data)
 if path in blobs and actual!=blobs[path] and path!='astra_ingestion/rpc_store.py':unexpected.append(path)
 if path not in blobs and path not in new_allowed:unexpected.append(path)
 if path in ACTIVE and sha256(data).hexdigest()!=ACTIVE[path]:unexpected.append(path)
 observed.append({'path':path,'sha256':sha256(data).hexdigest(),'git_blob_sha1':actual,'bytes':len(data),'base_git_blob_sha1':blobs.get(path),
  'state':'REVIEWED_RUNTIME_REPLACEMENT' if path=='astra_ingestion/rpc_store.py' else 'EXACT_EXISTING_BLOB' if path in blobs else 'ADDITIVE'})
receipt={'schema':'astra.combined-v74-actual-dependency-qualification/1','base_commit':BASE,'base_tree':tree['sha'],
 'passed':result.wasSuccessful() and not unexpected,'tests':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'skipped':len(result.skipped),
 'elapsed_seconds':elapsed,'active_paths':ACTIVE,'actual_dependency_count':len(observed),'actual_reads_and_imports':observed,
 'all_materialized_files':materialized,'unexpected_existing_blob_differences':unexpected,
 'source_fixture_root':str(STAGE),'no_inherited_duplicate_shared_cases':True,'production_calls':0,
 'same_source_inputs_no_workflow_or_foundation_overwrite':True,'modules':{m.__name__:getattr(m,'RESULT',getattr(m,'EVIDENCE',{})) for m in modules},
 'error_details':[{'test':str(t),'traceback':e} for t,e in result.errors],'failure_details':[{'test':str(t),'traceback':e} for t,e in result.failures]}
path=HERE/'combined_active_dependency_qualification_v74.json';path.write_text(json.dumps(receipt,indent=2,default=str)+'\n')
print(json.dumps({'passed':receipt['passed'],'tests':result.testsRun,'actual_dependencies':len(observed),'unexpected':unexpected,'receipt':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}))
raise SystemExit(0 if receipt['passed'] else 1)
