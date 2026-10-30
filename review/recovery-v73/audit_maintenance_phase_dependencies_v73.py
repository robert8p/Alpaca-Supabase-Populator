"""Run final active v73 regressions while auditing actual project reads/imports."""
import ast
from hashlib import sha1,sha256
import importlib
import json
import os
from pathlib import Path
import sys
from time import monotonic
import unittest

ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
BASE='1f1f423e4dd1db87eff92e8687b2d9c49ba63c01'
TREE='45c5b7d6410f4fba1d154d50debdb3b574c9e86d'
sys.path[:0]=[str(ROOT/'tests/ingestion'),str(ROOT)]
opened=set()

def audit(event,args):
    if event!='open' or not args or type(args[0]) not in (str,bytes):return
    try:
        p=Path(os.fsdecode(args[0])).resolve();rel=p.relative_to(ROOT)
    except (ValueError,OSError):return
    if '__pycache__' not in rel.parts and p.is_file():opened.add(rel.as_posix())

def blob(data):return sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()

def main():
    if os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL')!='postgresql://postgres@127.0.0.1:55432/astra_ingestion_qualification':
        raise SystemExit('Only the existing disposable loopback PostgreSQL fixture is allowed')
    if os.environ.get('GITHUB_WORKFLOW')!='ASTRA ingestion qualification':
        raise SystemExit('Run under the dedicated qualification context')
    raw=json.loads(Path('/tmp/replacement-checkpoint-tree-v72.json').read_text())
    if raw.get('sha')!=TREE or raw.get('truncated'):raise ValueError('Unexpected or truncated exact1f1f tree')
    tree={x['path']:x for x in raw['tree'] if x.get('type')=='blob'}
    sys.addaudithook(audit)
    modules=[importlib.import_module(x) for x in (
        'test_backfill_maintenance_phase_observation_v73',
        'test_backfill_maintenance_phase_installation_v73')]
    started=monotonic()
    outcomes=[]
    for module in modules:
        result=unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
        outcomes.append({'module':module.__name__,'tests':result.testsRun,'errors':len(result.errors),
            'failures':len(result.failures),'skipped':len(result.skipped),'passed':result.wasSuccessful(),
            'qualification':getattr(module,'RESULT',{}),
            'errors_detail':[{'test':str(t),'trace':s} for t,s in result.errors],
            'failures_detail':[{'test':str(t),'trace':s} for t,s in result.failures]})
    imported=set()
    for module in tuple(sys.modules.values()):
        name=getattr(module,'__file__',None)
        if not name:continue
        try:p=Path(name).resolve().relative_to(ROOT)
        except ValueError:continue
        if p.suffix=='.py':imported.add(p.as_posix())
    static=[]
    for rel in sorted(imported):
        content=(ROOT/rel).read_text()
        for node in ast.walk(ast.parse(content,filename=rel)):
            if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in ('read_text','read_bytes'):
                static.append({'path':rel,'line':node.lineno,'expression':ast.get_source_segment(content,node)})
    files=[]
    for rel in sorted(opened|imported):
        data=(ROOT/rel).read_bytes();prior=tree.get(rel)
        files.append({'path':rel,'bytes':len(data),'sha256':sha256(data).hexdigest(),'git_blob_sha1':blob(data),
            'base_state':'ABSENT' if prior is None else 'IDENTICAL' if prior['sha']==blob(data) else 'DIFFERENT',
            'base_git_blob_sha1':prior.get('sha') if prior else None})
    receipt={'schema':'astra.maintenance-phase.active-qualification-and-dependency-audit/1',
        'base_commit':BASE,'base_tree':TREE,'base_tree_entries':len(raw['tree']),'base_tree_truncated':False,
        'passed':all(x['passed'] and not x['skipped'] for x in outcomes),
        'tests':sum(x['tests'] for x in outcomes),'errors':sum(x['errors'] for x in outcomes),
        'failures':sum(x['failures'] for x in outcomes),'skipped':sum(x['skipped'] for x in outcomes),
        'outcomes':outcomes,'elapsed_seconds':monotonic()-started,'files':files,
        'absent_paths':[x['path'] for x in files if x['base_state']=='ABSENT'],
        'different_paths':[x['path'] for x in files if x['base_state']=='DIFFERENT'],
        'observed_project_reads':sorted(opened),'imported_project_modules':sorted(imported),
        'static_read_sites':static,'production_calls':0,'all_active_tests_executed':True}
    if receipt['different_paths']:receipt['passed']=False
    p=HERE/'maintenance_phase_active_qualification_v73.json'
    if p.exists():raise RuntimeError('Retain existing result; use a separately versioned attempt path')
    p.write_text(json.dumps(receipt,indent=2,default=str)+'\n')
    print(json.dumps({'passed':receipt['passed'],'tests':receipt['tests'],'errors':receipt['errors'],
        'failures':receipt['failures'],'skips':receipt['skipped'],'different':receipt['different_paths'],
        'path':str(p),'sha256':sha256(p.read_bytes()).hexdigest()}))
    return 0 if receipt['passed'] else 1

if __name__=='__main__':raise SystemExit(main())
