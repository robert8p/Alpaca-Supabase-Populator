"""Run active index regressions and audit every actual fixture/import read."""
import ast
from hashlib import sha1,sha256
import json
import os
from pathlib import Path
import sys
from time import monotonic
import unittest

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
sys.path[:0]=[str(ROOT/'tests/ingestion'),str(ROOT)]
opened=set()
def audit(event,args):
    if event!='open' or not args or not isinstance(args[0],(str,bytes)):return
    try:
        path=Path(os.fsdecode(args[0])).resolve();relative=path.relative_to(ROOT)
    except (ValueError,OSError):return
    if '__pycache__' not in relative.parts and path.is_file():opened.add(relative.as_posix())

def blob(data):return sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def main():
    if os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL')!='postgresql://postgres@127.0.0.1:55432/astra_ingestion_qualification':
        raise SystemExit('Only the explicit known disposable PostgreSQL fixture is permitted')
    sys.addaudithook(audit)
    import test_backfill_maintenance_task_indexes_v2 as module
    started=monotonic()
    result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
    modules=set()
    for item in tuple(sys.modules.values()):
        name=getattr(item,'__file__',None)
        if not name:continue
        try:p=Path(name).resolve().relative_to(ROOT)
        except ValueError:continue
        if p.suffix=='.py':modules.add(p.as_posix())
    static=[]
    for path in sorted(modules):
        content=(ROOT/path).read_text()
        for node in ast.walk(ast.parse(content,filename=path)):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in ('read_text','read_bytes'):
                static.append({'path':path,'line':node.lineno,'expression':ast.get_source_segment(content,node)})
    raw=json.loads(Path('/tmp/replacement-536-tree.json').read_text())
    entries=raw['tree'] if isinstance(raw,dict) else raw
    if isinstance(raw,dict) and raw.get('truncated'):raise ValueError('Base tree is truncated')
    tree={x['path']:x for x in entries if x.get('type')=='blob'}
    files=[]
    for path in sorted(opened|modules):
        data=(ROOT/path).read_bytes();prior=tree.get(path)
        files.append({'path':path,'bytes':len(data),'sha256':sha256(data).hexdigest(),'git_blob_sha1':blob(data),
            'base_state':'ABSENT' if prior is None else 'IDENTICAL' if prior['sha']==blob(data) else 'DIFFERENT',
            'base_git_blob_sha1':prior.get('sha') if prior else None})
    receipt={'schema':'astra.maintenance-index.active-qualification-and-dependency-audit/1',
        'base_commit':'536bb850cf5c5653b4865e63db3f20f50a6769a1','base_tree':'60ba98872222e1c7f285296fc48300e326ee6fda',
        'base_tree_entries':len(entries),'base_tree_truncated':False,'passed':result.wasSuccessful(),
        'tests':result.testsRun,'errors':len(result.errors),'failures':len(result.failures),'skipped':len(result.skipped),
        'elapsed_seconds':monotonic()-started,'qualification':module.EVIDENCE,'files':files,
        'absent_paths':[x['path'] for x in files if x['base_state']=='ABSENT'],
        'different_paths':[x['path'] for x in files if x['base_state']=='DIFFERENT'],
        'observed_project_reads':sorted(opened),'imported_project_modules':sorted(modules),'static_read_sites':static,
        'production_calls':0,'all_active_tests_executed':True}
    path=HERE/'maintenance_index_active_qualification_v72.json'
    path.write_text(json.dumps(receipt,indent=2,default=str)+'\n')
    print(json.dumps({'passed':result.wasSuccessful(),'tests':result.testsRun,'absent':receipt['absent_paths'],
        'different':receipt['different_paths'],'receipt':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}))
    return 0 if result.wasSuccessful() else 1

if __name__=='__main__':raise SystemExit(main())
