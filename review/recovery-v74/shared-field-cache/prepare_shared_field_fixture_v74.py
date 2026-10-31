"""Materialize an exact published dependency closure; no database calls."""
from pathlib import Path
from hashlib import sha1,sha256
import json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
OUT=Path('/tmp/replacement-shared-field-cache-fixture-v74')
TREE=Path('/tmp/replacement-phase-observation-tree-v73.json')
tree=json.loads(TREE.read_text());assert tree['sha']=='bd41e2f106d412ebebf3e72f854c2665ae616aa8' and not tree['truncated']
blobs={x['path']:x['sha'] for x in tree['tree'] if x['type']=='blob'}
paths={x['path'] for x in json.loads((ROOT/'review/recovery-v73/maintenance_phase_active_qualification_v73.json').read_text())['files']}
paths.update(['tests/ingestion/test_backfill_shared_records_v2.py','tests/ingestion/test_backfill_shared_refresh_performance_v2.py'])
def blob(data):return sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
retained=[]
for path in sorted(paths):
    expected=blobs[path]
    options=[ROOT/path,Path('/tmp/replacement-maintenance-index-staged-v72')/path,
             Path('/tmp/replacement-claim-capability-staged-v71')/path]
    if path.startswith('astra_ingestion/'):
        options.append(ROOT/'review/rpc-lock-rollback-retry-proposal/baseline'/Path(path).name)
    source=next((p for p in options if p.is_file() and blob(p.read_bytes())==expected),None)
    if source is None:raise RuntimeError('No exact published dependency available: '+path)
    data=source.read_bytes();target=OUT/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    retained.append({'path':path,'sha256':sha256(data).hexdigest(),'git_blob_sha1':expected,'bytes':len(data)})
receipt={'schema':'astra.shared-field-fixture-closure/1','base_commit':'3fddb6cf196e289e79eb9bfaef45d56965b64eca','base_tree':tree['sha'],
 'base_tree_complete':True,'fixture_root':str(OUT),'files':retained,'all_dependencies_exact_published_bytes':True,
 'production_calls':0,'database_calls':0,'existing_workspace_files_overwritten':False}
(HERE/'shared_field_fixture_closure_v74.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'fixture_root':str(OUT),'verified_files':len(retained),'production_calls':0}))
