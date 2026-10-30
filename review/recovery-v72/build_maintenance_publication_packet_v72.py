"""Build explicit additive publication payloads; no remote mutation or deployment."""
from datetime import datetime, timezone
from hashlib import sha1,sha256
import gzip
import io
import json
from pathlib import Path
import tarfile

ROOT=Path(__file__).resolve().parents[2]
HERE=ROOT/'review/recovery-v72'
BASE='536bb850cf5c5653b4865e63db3f20f50a6769a1'
TREE='60ba98872222e1c7f285296fc48300e326ee6fda'
REVIEWED={
 'sql/astra_backfill_breadth_pending_hash_index_v2.sql':'8ff7824557d19d6981e036acc9228d148b460de50c38ec33017b7f628037fad9',
 'sql/astra_backfill_minute_pending_hash_index_v2.sql':'1355b571ffd60602bee67e525dc687535b31e5c7c69ea3ac058551fc0c591203',
 'sql/astra_backfill_readback_transaction_race_v2.sql':'f729d5be47cb9d09d8f6db1423fcab1364592b376878bfeb782218d078a1195b',
 'tests/ingestion/test_backfill_maintenance_task_indexes_v2.py':'50108ef354e9d3c36b76e6f3b55f31306067f2c20ee4a749b4c5eded931a2145',
 'tests/ingestion/test_backfill_readback_transaction_race_v2.py':'04312d34e94331fb79981b7b0032560a3128a84aab01d1a32c9efbb53021ae83',
 'evidence/replacement-maintenance-task-hash-index-qualification-v72.json':'458f149d06bf65d09bdedadf05fa3f9337c32ff8ff206cd6a8795c8939b01071',
 'review/recovery-v72/maintenance_index_active_qualification_v72.json':'995ec6fb0a5eed6773d73d63f55cdd21b554e7381ae959047d3f6855152a0f96',
 'review/recovery-v72/maintenance_readback_active_qualification_v72.json':'e09b8fa26a9c062a88ed401bc8ac69fbc7ee0a2bf21acf7faa56fea74d1ef855',
}
# Populated only with the independently frozen review receipts, not a producer
# substitute; absent or changed receipts make packaging fail closed.
REVIEWS_PATH=HERE/'maintenance_publication_review_pins_v72.json'
EXTRA=[
 'review/recovery-v72/build_maintenance_index_qualification_v72.py',
 'review/recovery-v72/build_maintenance_publication_packet_v72.py',
 'review/recovery-v72/build_maintenance_index_forwards_v72.py',
 'review/recovery-v72/stage_maintenance_index_v72.py',
 'review/recovery-v72/audit_maintenance_index_dependencies_v72.py',
 'review/recovery-v72/audit_readback_race_dependencies_v72.py',
 'review/recovery-v72/maintenance_index_staged_source_v72.json',
 'review/recovery-v72/maintenance_index_independent_test_result_v72.json',
 'review/recovery-v72/maintenance_readback_active_initial_qualification_v72.json',
 'review/recovery-v72/readback_transaction_race_actual_reason_1410.json',
 'review/recovery-v72/reconcile_exact_readback_transaction_race_v72.sql',
 'review/recovery-v72/exact_readback_transaction_reconciliation_result_v72.json',
 'review/recovery-v72/exact_readback_transaction_reconciliation_committed_v72.json',
 'evidence/replacement-owner-lease-continuation-v72.json',
]
def blob(data):return sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
def ref(path,data):return {'path':path,'bytes':len(data),'sha256':sha256(data).hexdigest(),'git_blob_sha1':blob(data)}
def main():
 raw=json.loads(Path('/tmp/replacement-536-tree.json').read_text())
 if raw['sha']!=TREE or raw['truncated']:raise ValueError('Unexpected or truncated exact base tree')
 tree={x['path']:x for x in raw['tree'] if x.get('type')=='blob'}
 reviews=json.loads(REVIEWS_PATH.read_text())
 pins={**REVIEWED,**reviews['frozen_receipt_pins']}
 for path,pin in pins.items():
  if sha256((ROOT/path).read_bytes()).hexdigest()!=pin:raise ValueError('Frozen source or review changed: '+path)
 audits=[]
 for name,count in [('maintenance_index_active_qualification_v72.json',9),('maintenance_readback_active_qualification_v72.json',8)]:
  audit=json.loads((HERE/name).read_text())
  if not(audit['passed'] and audit['tests']==count and audit['errors']==audit['failures']==audit['skipped']==0
    and audit['all_active_tests_executed'] and audit['base_commit']==BASE and not audit['different_paths']):
   raise ValueError('Final active qualification incomplete: '+name)
  audits.append(audit)
 paths=set(pins)|set(EXTRA)|{REVIEWS_PATH.relative_to(ROOT).as_posix()}
 paths.update(reviews.get('extra_paths',[]))
 qual=json.loads((ROOT/'evidence/replacement-maintenance-task-hash-index-qualification-v72.json').read_text())
 for item in qual['artifacts']:
  path=item['path'];data=(ROOT/path).read_bytes()
  if sha256(data).hexdigest()!=item['sha256']:raise ValueError('Producer evidence artifact drift: '+path)
  paths.add(path)
 paths.update(p.relative_to(ROOT).as_posix() for p in (HERE/'readback-transaction-race').iterdir() if p.is_file())
 # Actual active fixture reads/imports are required closure, including review
 # paths. Existing ones must already be exact on the selected base tree.
 dependency_records={}
 for audit in audits:
  for item in audit['files']:
   prior=dependency_records.get(item['path'])
   if prior and prior['sha256']!=item['sha256']:raise ValueError('Test closures disagree: '+item['path'])
   dependency_records[item['path']]=item
   if item['base_state']=='ABSENT':paths.add(item['path'])
   elif item['base_state']!='IDENTICAL':raise ValueError('Unexpected existing dependency modification')
 for path,item in dependency_records.items():
  if item['base_state']=='ABSENT':
   if path not in paths or sha256((ROOT/path).read_bytes()).hexdigest()!=item['sha256']:
    raise ValueError('New active fixture dependency missing or changed: '+path)
  elif tree.get(path,{}).get('sha')!=item['git_blob_sha1']:
   raise ValueError('Base dependency blob mismatch: '+path)
 payload={};all_refs=[]
 for path in sorted(paths):
  data=(ROOT/path).read_bytes();item=ref(path,data);prior=tree.get(path)
  item['base_state']='ABSENT' if prior is None else 'IDENTICAL' if prior['sha']==item['git_blob_sha1'] else 'DIFFERENT'
  if item['base_state']=='DIFFERENT':raise ValueError('Additive packet would overwrite existing base file: '+path)
  all_refs.append(item)
  if item['base_state']=='ABSENT':payload[path]=data
 dep={'schema':'astra.maintenance-combined.publication-dependencies/1','base_commit':BASE,'base_tree':TREE,
  'base_tree_entries':len(raw['tree']),'base_tree_truncated':False,'active_test_results':[{'tests':x['tests'],
  'errors':x['errors'],'failures':x['failures'],'skipped':x['skipped'],'elapsed_seconds':x['elapsed_seconds']} for x in audits],
  'all_actual_opened_imported_dependencies_accounted_for':True,'existing_dependencies_overwritten':False,
  'new_required_paths':sorted(p for p,x in dependency_records.items() if x['base_state']=='ABSENT'),
  'files':[dependency_records[p] for p in sorted(dependency_records)],
  'static_read_sites':[r for a in audits for r in a['static_read_sites']],
  'reviewed_source_hashes':pins,'runtime_python_and_worker_files_in_packet':False}
 dep_path='review/recovery-v72/maintenance_combined_publication_dependencies_v72.json'
 dep_data=(json.dumps(dep,indent=2)+'\n').encode();(ROOT/dep_path).write_bytes(dep_data);payload[dep_path]=dep_data
 manifest={'schema':'astra.maintenance-combined.publication-manifest/1','created_at':datetime.now(timezone.utc).isoformat(),
  'repository':'robert8p/Alpaca-Supabase-Populator','base_commit':BASE,'base_tree':TREE,
  'state':'PREPARED_LOCAL_NOT_PUBLISHED','remote_mutations_by_producer':0,'application_is_separate':True,
  'scope':'Two additive partial hash indexes and the independently reviewed single readback-transaction eligibility predicate, with active qualification and retained evidence.',
  'activation_order':['sql/astra_backfill_breadth_pending_hash_index_v2.sql','sql/astra_backfill_minute_pending_hash_index_v2.sql','sql/astra_backfill_readback_transaction_race_v2.sql'],
  'application_constraints':['Root reconciles head, same owner/lease/fence, exact source pins and uncertain writes first.',
   'Exact-head required CI must pass before application.',
   'Each forward is separate and guarded; reconcile readback after any uncertain result before retry.',
   'Hash forwards pin unchanged maintaincd100; readback predicate forward follows both indexes.',
   'No worker redeploy, authentication/access expansion, credential change, telemetry or schedule change.'],
  'function_sources_after_hashes_unchanged':True,'runtime_python_files_unchanged':True,
  'preparation_only_not_a_successful_full_run':['review/recovery-v72/qualify_maintenance_task_indexes_v72.py'],
  'successful_focused_replacements':['review/recovery-v72/qualify_hash_collision_focused_v72.py','review/recovery-v72/qualify_hash_positive_generic_focused_v72.py'],
  'active_tests':{'index_tests':9,'readback_tests':8,'failures':0,'errors':0,'skipped':0,'exact_base_dependencies':True},
  'payloads_excluding_manifest':len(payload),'payload_bytes_excluding_manifest':sum(map(len,payload.values())),
  'referenced_existing_and_new_artifacts':all_refs,'dependency_audit':ref(dep_path,dep_data),
  'payload_files':[ref(p,d) for p,d in sorted(payload.items())]}
 manifest_path='evidence/replacement-maintenance-combined-publication-manifest-v72.json'
 m=(json.dumps(manifest,indent=2)+'\n').encode();(ROOT/manifest_path).write_bytes(m);payload[manifest_path]=m
 packet={'schema':'astra.maintenance-combined.publication-packet/1','base_commit':BASE,'base_tree':TREE,
  'expected_head_must_be_reconciled_before_mutation':True,'manifest':ref(manifest_path,m),
  'tree_entries':[{'path':p,'mode':'100644','type':'blob','content':d.decode('utf-8')} for p,d in sorted(payload.items())]}
 out=Path('/tmp/replacement-maintenance-publication-packet-v72.json');out.write_text(json.dumps(packet,ensure_ascii=False)+'\n')
 listing=Path('/tmp/replacement-maintenance-publication-files-v72.txt');listing.write_text('\n'.join(sorted(payload))+'\n')
 archive=Path('/tmp/replacement-maintenance-publication-packet-v72.tar.gz')
 with archive.open('wb') as output,gzip.GzipFile(fileobj=output,mode='wb',mtime=0) as compressed,tarfile.open(fileobj=compressed,mode='w') as tar:
  for p,d in sorted(payload.items()):
   info=tarfile.TarInfo(p);info.size=len(d);info.mode=0o644;info.mtime=0;tar.addfile(info,io.BytesIO(d))
 print(json.dumps({'manifest':ref(manifest_path,m),'payload_count':len(payload),
   'packet':ref(str(out),out.read_bytes()),'archive':ref(str(archive),archive.read_bytes()),'file_list':str(listing),
   'dependency_count':len(dependency_records),'new_required_dependency_count':len(dep['new_required_paths'])}))
if __name__=='__main__':main()
