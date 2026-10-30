"""Build the explicitly reviewed defer-only release on the complete a71 tree."""
from __future__ import annotations
import hashlib, importlib.util, json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
BASE_COMMIT='a71e9df014a4f0b66818ff47b2f85f1adbf6623e'
BASE_TREE='cc1c8702b0f9b43c52952736ed47566d8189e155'
MANIFEST='evidence/replacement-defer-native-lock-retry-publication-manifest-v77.json'
spec=importlib.util.spec_from_file_location('git_objects',ROOT/'review/recovery-v76/build_independent_claim_publication_v76.py')
go=importlib.util.module_from_spec(spec);spec.loader.exec_module(go)
sha=lambda b:hashlib.sha256(b).hexdigest()
def read_json(path):return json.loads((ROOT/path).read_text())
scope=read_json('review/recovery-v77/defer-native-lock-retry/selected_publication_paths_v77.json')
archive=read_json(scope['active_payload_archive'])
base=json.loads(Path('/tmp/replacement-a71-tree-v77.json').read_text())
assert base['sha']==BASE_TREE and not base['truncated']
leaves={x['path']:x for x in base['tree'] if x['type']!='tree'}
assert len(leaves)==1095 and go.root_sha(leaves)[0]==BASE_TREE
assert archive['parent_commit']==BASE_COMMIT and archive['parent_tree']==BASE_TREE
assert sha((ROOT/scope['active_payload_archive']).read_bytes())=='cc14634c7a0593bf4824e9a35ea678f1255a92a7799471e5df083343a2576cc4'
final_path='review/recovery-v77/defer-native-lock-retry-independent-review/independent_defer_retry_release_review_final_v77.json'
assert sha((ROOT/final_path).read_bytes())=='99021f8f4fd5ee674df2560fd8106066752373e379be90b494d8cb5cdb7b27f7'
review=read_json('review/recovery-v77/defer-native-lock-retry-independent-review/independent_defer_retry_release_review_v77.json')
assert review['passed'] and not review['blocking_findings']
entries=[];selected=[]
for item in archive['files']:
 path=item['target_path'];data=item['content'].encode('utf-8')
 assert len(data)==item['bytes'] and sha(data)==item['sha256']
 assert go.object_sha('blob',data)==item['git_blob']
 assert (leaves.get(path) or {}).get('sha')==item['parent_blob']
 if item['parent_blob']:
  old=item['baseline']['content'].encode('utf-8')
  assert go.object_sha('blob',old)==item['parent_blob']
 entries.append({'path':path,'mode':'100644','type':'blob','content':data.decode()})
 selected.append({'path':path,'bytes':len(data),'sha256':sha(data),'git_blob_sha1':item['git_blob'],'parent_blob':item['parent_blob'],'source':'REVIEWED_ARCHIVE'})
assert {x['path'] for x in selected if x['parent_blob']}==set(scope['expected_changed_existing_paths'])
runtime=next(x for x in archive['files'] if x['target_path']=='astra_ingestion/rpc_store.py')
assert runtime['content'].replace(', "backfill_defer",',',',1)==runtime['baseline']['content']
paths=[x['path'] for x in scope['review_artifacts']]
paths += [
'review/recovery-v77/defer-native-lock-retry/selected_publication_paths_v77.json',
'review/recovery-v77/defer-native-lock-retry/installed_source_reconciliation_v77.json',
'review/recovery-v77/defer-native-lock-retry/additional_fixture_imports_v77.json',
'review/recovery-v77/defer-native-lock-retry-independent-review/independent_defer_retry_release_review_v77.json',
final_path,
'review/recovery-v77/defer-native-lock-retry-independent-review/independent_boundary_qualification_v77.json',
'review/recovery-v77/defer-native-lock-retry-independent-review/qualify_independent_boundary_v77.py',
'review/recovery-v76/defer-retry-independent-review/source_effect_preliminary_v76.json',
'evidence/replacement-claim-cursor-release-gates-v76.json',
'evidence/replacement-claim-postinstall-source-acquisition-proof-v76.json',
'evidence/replacement-current-monitor-gate-holder-confirmed-v76.json',
'evidence/replacement-fresh-defer-recurrence-and-qualified-recovery-assignment-v76.json',
'review/recovery-v77/build_defer_publication_v77.py',
]
assert len(paths)==len(set(paths))
held=json.loads(Path('/tmp/replacement-checkpoint-publication-packet-v75.json').read_text())
assert not set(paths)&{x['path'] for x in held['tree_entries']}
for x in scope['review_artifacts']:
 data=(ROOT/x['path']).read_bytes();assert len(data)==x['bytes'] and sha(data)==x['sha256']
for path in sorted(paths):
 assert path not in leaves and path not in {x['path'] for x in entries}
 assert not (path.startswith('review/') and Path(path).name.startswith('test_') and path.endswith('.py'))
 data=(ROOT/path).read_bytes();blob=go.object_sha('blob',data)
 entries.append({'path':path,'mode':'100644','type':'blob','content':data.decode('utf-8')})
 selected.append({'path':path,'bytes':len(data),'sha256':sha(data),'git_blob_sha1':blob,'parent_blob':None,'source':'EXPLICIT_EVIDENCE'})
manifest={
 'schema':'astra.defer-only-publication-manifest/1','base_commit':BASE_COMMIT,'base_tree':BASE_TREE,
 'base_blob_count':1095,'changed_existing_paths':scope['expected_changed_existing_paths'],
 'retained_existing_blobs':1093,'selected_files_excluding_manifest':selected,
 'runtime_diff':'Add only backfill_defer to existing strict complete nativeHTTP500/55P03 retry allowlist. All parser/endpoint/auth/serialization/deadline/backoff/ambiguous-result behavior unchanged.',
 'local_qualification':{'producer_tests':51,'independent_boundary_tests':19,'failures':0,'errors':0,'skips':0,'actual_postgresql':'16.15','http':'SIMULATED','production_or_provider_calls':0},
 'review_scope_path_resolution':{'provisional':'independent_final_release_review_v77.json','actual_final':final_path,'sha256':'99021f8f4fd5ee674df2560fd8106066752373e379be90b494d8cb5cdb7b27f7'},
 'installed_database_context':{'private':'dbe8eb5a563eaf9e8e00678045f8a28da65c8c4b83b4a3295c4eb32c05f50fbf','claim_migration':'20261030195049','shared':'7f538bf47cb5e74050c20266e01cbe9d6521c1a65663aaf2e0fe38d62041f1a4'},
 'no_database_ddl_or_permissions_or_credentials_or_source_or_cost_change':True,
 'historical_defer_request_outcomes':'UNKNOWN_NOT_REPLAYED',
 'held_checkpoint':{'state':'RECOVERY_HOST_REJECTED_NO_RETRY_HOLD','packet_sha256':'8806ef636f5be4220562b0ee52d64426f620461d8ad99adef5f9edd1f9724da3','expected_tree':'e56dc140deeb00eb2a0aae4e7d572519d773ccd0','unchanged':True},
 'held_identity':'Original archive retained, not activated. Future rebind must preserve installed dbe8 and any later admitted defer runtime; never overwrite newer repair with old package.',
 'activation_gate':'All exact published-head CI, fresh source/OID/metadata/effect catalog/owner/finite lease/fixed scope and existing Render service checks; one separately selected pinned worker deploy, independent deployment/readback and actual subsequent source pages. No blind restart or installed-SQL replay.',
 'reporting':'DOT_CONSOLIDATED_CHECKPOINTS_ONLY'
}
data=(json.dumps(manifest,indent=2,ensure_ascii=False)+'\n').encode()
(ROOT/MANIFEST).write_bytes(data)
entries.append({'path':MANIFEST,'mode':'100644','type':'blob','content':data.decode()})
result=dict(leaves)
for e in entries:result[e['path']]={'path':e['path'],'mode':e['mode'],'type':'blob','sha':go.object_sha('blob',e['content'].encode())}
changed=[p for p in leaves if result[p]['sha']!=leaves[p]['sha']]
assert set(changed)==set(scope['expected_changed_existing_paths'])
expected,trees=go.root_sha(result)
packet={'schema':'astra.defer-only-publication-packet/1','repository_full_name':'robert8p/Alpaca-Supabase-Populator','branch':'feat/astra-ingestion-service','base_commit':BASE_COMMIT,'base_tree':BASE_TREE,'expected_result_tree':expected,'base_blobs':1095,'retained_blobs':1093,'changed_existing_paths':changed,'result_blob_count':len(result),'manifest_sha256':sha(data),'tree_entries':entries}
raw=(json.dumps(packet,indent=2,ensure_ascii=False)+'\n').encode()
Path('/tmp/replacement-defer-publication-packet-v77.json').write_bytes(raw)
proof={'schema':'astra.defer-publication-local-proof/1','base_commit':BASE_COMMIT,'base_tree':BASE_TREE,'expected_tree':expected,'entry_count':len(entries),'changed_existing_paths':changed,'retained_blobs':1093,'additions':len(result)-1095,'result_blob_count':len(result),'packet_sha256':sha(raw),'packet_bytes':len(raw),'manifest_sha256':sha(data),'expected_leaves':sorted(result.values(),key=lambda x:x['path'])}
(ROOT/'review/recovery-v77/defer_publication_local_proof_v77.json').write_text(json.dumps(proof,indent=2)+'\n')
print(json.dumps({k:v for k,v in proof.items() if k!='expected_leaves'}))
