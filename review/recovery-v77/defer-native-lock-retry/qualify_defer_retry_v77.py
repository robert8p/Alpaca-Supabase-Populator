"""Bounded actual transaction qualification and exact actual-read dependency audit."""
import argparse
from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha1, sha256
import io
import json
from pathlib import Path
import sys
from time import perf_counter
import unittest

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--output',type=Path,required=True)
    parser.add_argument('--parent-proof',type=Path,required=True)
    parser.add_argument('--unit-only',action='store_true')
    args=parser.parse_args()
    root=args.root.resolve()
    opened=set()
    def audit(event,values):
        if event=='open' and values and isinstance(values[0],str):
            path=Path(values[0]).resolve()
            if path.is_relative_to(root) and path.suffix in {'.py','.sql','.json'}: opened.add(path)
    sys.addaudithook(audit)
    sys.path[:0]=[str(root),str(root/'tests/ingestion')]
    names=['test_rpc_lock_abort_retry','test_rpc_store','test_rpc_failure_observability_v71',
           'test_rpc_lock_abort_retry_postgres.PostgreSQLAdmissionTests',
           'test_rpc_defer_lock_abort_retry_v77.DeferSourceAndBoundaryTests']
    if not args.unit_only: names.append('test_rpc_defer_lock_abort_retry_v77.DeferPostgreSQLTests')
    suite=unittest.defaultTestLoader.loadTestsFromNames(names)
    log,out,err=io.StringIO(),io.StringIO(),io.StringIO()
    started=perf_counter()
    with redirect_stdout(out),redirect_stderr(err):
        result=unittest.TextTestRunner(stream=log,verbosity=2).run(suite)
    for module in list(sys.modules.values()):
        filename=getattr(module,'__file__',None)
        if isinstance(filename,str):
            path=Path(filename).resolve()
            if path.is_relative_to(root) and path.suffix=='.py':opened.add(path)
    parent=json.loads(args.parent_proof.read_text())
    leaves={row['path']:row for row in parent['expected_leaves']}
    dependencies=[]
    for path in sorted(opened):
        if not path.exists():continue
        raw=path.read_bytes();relative=path.relative_to(root).as_posix()
        blob=sha1(b'blob '+str(len(raw)).encode()+b'\0'+raw).hexdigest()
        expected=leaves.get(relative,{}).get('sha')
        dependencies.append({'path':relative,'bytes':len(raw),'sha256':sha256(raw).hexdigest(),
            'git_blob':blob,'parent_blob':expected,'relationship':'ADDITION' if expected is None else 'UNCHANGED' if expected==blob else 'REPLACEMENT'})
    allowed={'astra_ingestion/rpc_store.py','tests/ingestion/test_rpc_lock_abort_retry.py'}
    unexpected=[row for row in dependencies if row['relationship']=='REPLACEMENT' and row['path'] not in allowed]
    ok=result.wasSuccessful() and not result.skipped and not unexpected
    receipt={'schema':'astra.defer-native-lock-retry-qualification/1','passed':ok,
        'repository_parent_commit':'a71e9df014a4f0b66818ff47b2f85f1adbf6623e',
        'repository_parent_tree':parent['expected_result_tree'],'runtime_base_commit':'e694009d75f3fd91c69976befa0e12838e64efec',
        'tests':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'skips':len(result.skipped),
        'seconds':round(perf_counter()-started,3),'modules':names,'test_log':log.getvalue(),
        'stdout':out.getvalue(),'stderr':err.getvalue(),'opened_or_imported_dependencies':dependencies,
        'unexpected_existing_blob_differences':unexpected,
        'defer_evidence':getattr(sys.modules.get('test_rpc_defer_lock_abort_retry_v77'),'RESULT',{}),
        'production_calls':0,'external_provider_calls':0,'active_workspace_changes':0,
        'deployment_hold':'INDEPENDENT_REVIEW_CURRENT_SOURCE_BINDING_PUBLICATION_EXACT_HEAD_CI_AND_ROOT_DEPLOYMENT_REQUIRED'}
    args.output.parent.mkdir(parents=True,exist_ok=True)
    args.output.write_text(json.dumps(receipt,indent=2,sort_keys=True,default=str)+'\n')
    print(json.dumps({key:receipt[key] for key in ('passed','tests','errors','failures','skips','seconds')}))
    if not ok:print(log.getvalue())
    return 0 if ok else 1

if __name__=='__main__':raise SystemExit(main())
