"""Run the active v76 module and retain its actual local read/import closure."""
import argparse
from datetime import datetime, timezone
import hashlib
import importlib
import importlib.util
import io
import json
from pathlib import Path
import sys
import time
import unittest


def blob(data):
    return hashlib.sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--stage', required=True)
    parser.add_argument('--tree', required=True)
    parser.add_argument('--output', required=True)
    args = parser.parse_args()
    stage = Path(args.stage).resolve()
    tree = json.loads(Path(args.tree).read_text())
    assert tree['sha']=='3599d2822a30b658666ab219e8eeca728f3917df' and not tree['truncated']
    base = {x['path']:x for x in tree['tree'] if x['type']=='blob'}
    opened = set()
    def audit(event, arguments):
        if event!='open' or not arguments or not isinstance(arguments[0],(str,bytes)):
            return
        try:
            path = Path(arguments[0]).resolve()
            path.relative_to(stage)
        except (ValueError, OSError, TypeError):
            return
        if path.suffix=='.pyc':
            try: path=Path(importlib.util.source_from_cache(str(path)))
            except ValueError: return
        opened.add(path)
    sys.addaudithook(audit)
    sys.dont_write_bytecode=True
    sys.path[:0]=[str(stage/'tests/ingestion'),str(stage)]
    started = datetime.now(timezone.utc).isoformat()
    module = importlib.import_module('test_backfill_claim_provider_cursor_v76')
    stream=io.StringIO()
    then=time.monotonic()
    result=unittest.TextTestRunner(stream=stream,verbosity=2).run(unittest.defaultTestLoader.loadTestsFromModule(module))
    elapsed=time.monotonic()-then
    # Include imported modules even when their source was cached before audit.
    for value in list(sys.modules.values()):
        filename=getattr(value,'__file__',None)
        if not filename: continue
        path=Path(filename).resolve()
        try: path.relative_to(stage)
        except ValueError: continue
        if path.suffix=='.py': opened.add(path)
    dependencies=[]
    for path in sorted(opened):
        if not path.is_file(): continue
        relative=path.relative_to(stage).as_posix()
        data=path.read_bytes()
        old=base.get(relative)
        dependencies.append(dict(path=relative,bytes=len(data),sha256=hashlib.sha256(data).hexdigest(),git_blob_sha=blob(data),
            base_git_blob_sha=None if old is None else old['sha'],base_status='ADDITIVE' if old is None else 'EXACT' if old['sha']==blob(data) else 'UNEXPECTED_DIFFERENCE'))
    receipt=dict(schema='claim-cursor-qualification-v76',base_commit='e694009d75f3fd91c69976befa0e12838e64efec',base_tree=tree['sha'],
        started_at=started,finished_at=datetime.now(timezone.utc).isoformat(),seconds=elapsed,tests_run=result.testsRun,
        failures=len(result.failures),errors=len(result.errors),skips=len(result.skipped),
        passed=result.wasSuccessful() and not result.skipped and not any(r['base_status']=='UNEXPECTED_DIFFERENCE' for r in dependencies),
        log=stream.getvalue(),actual_dependencies=dependencies,evidence=module.RESULT,
        active_artifact_pins={p:hashlib.sha256((stage/p).read_bytes()).hexdigest() for p in
            ('sql/astra_backfill_claim_provider_cursor_v76.sql','sql/astra_backfill_claim_provider_cursor_restore_v76.sql','tests/ingestion/test_backfill_claim_provider_cursor_v76.py')})
    Path(args.output).write_text(json.dumps(receipt,indent=2,sort_keys=True,default=str)+'\n')
    print(stream.getvalue())
    print(json.dumps({k:receipt[k] for k in ('passed','tests_run','errors','failures','skips','seconds')}))
    raise SystemExit(0 if receipt['passed'] else 1)


if __name__=='__main__':
    main()
