"""Build the index-test fixture closure at exact current536bb850 source."""
from hashlib import sha1,sha256
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
OLD=Path('/tmp/replacement-claim-capability-staged-v71')
STAGE=Path('/tmp/replacement-maintenance-index-staged-v72')
def blob(data):return sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
raw=json.loads(Path('/tmp/replacement-536-tree.json').read_text())
entries=raw['tree'] if isinstance(raw,dict) else raw
assert not isinstance(raw,dict) or not raw.get('truncated')
tree={x['path']:x for x in entries if x.get('type')=='blob'}
closure=json.loads((ROOT/'review/recovery-v71/claim_capability_staged_publication_dependencies_v71.json').read_text())['files']
paths={x['path'] for x in closure}
new={'sql/astra_backfill_breadth_pending_hash_index_v2.sql','sql/astra_backfill_minute_pending_hash_index_v2.sql',
    'tests/ingestion/test_backfill_maintenance_task_indexes_v2.py',
    'review/recovery-v72/maintenance_index_forward_derivation_v72.json',
    'review/recovery-v72/audit_maintenance_index_dependencies_v72.py',
    'review/recovery-v71/live_cron_functions_1331.json'}
new.update({'sql/astra_backfill_readback_transaction_race_v2.sql',
    'tests/ingestion/test_backfill_readback_transaction_race_v2.py',
    'review/recovery-v72/audit_readback_race_dependencies_v72.py'})
new.update(p.relative_to(ROOT).as_posix() for p in (ROOT/'review/recovery-v72/readback-transaction-race').iterdir() if p.is_file())
paths.update(new)
records=[]
for path in sorted(paths):
    prior=tree.get(path)
    if path in new:
        data=(ROOT/path).read_bytes()
        if prior and blob(data)!=prior['sha']:raise ValueError('New dependency unexpectedly changes base path: '+path)
    else:
        data=None
        for base in (OLD,ROOT,Path('/tmp/replacement-3ee4-baseline')):
            source=base/path
            if source.exists() and prior and blob(source.read_bytes())==prior['sha']:
                data=source.read_bytes();break
        if data is None:raise ValueError('No exact base dependency blob: '+path)
    target=STAGE/path;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(data)
    records.append({'path':path,'bytes':len(data),'sha256':sha256(data).hexdigest(),'git_blob_sha1':blob(data),
        'state':'IDENTICAL_BASE' if prior else 'NEW_EXPLICIT'})
result={'schema':'astra.maintenance-index.staged-source/1','base_commit':'536bb850cf5c5653b4865e63db3f20f50a6769a1',
    'base_tree':'60ba98872222e1c7f285296fc48300e326ee6fda','files':records,'stage':str(STAGE),
    'all_existing_dependencies_exact_base':True,'remote_mutations':False}
out=ROOT/'review/recovery-v72/maintenance_index_staged_source_v72.json'
out.write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'stage':str(STAGE),'files':len(records),'receipt':str(out),'sha256':sha256(out.read_bytes()).hexdigest()}))
