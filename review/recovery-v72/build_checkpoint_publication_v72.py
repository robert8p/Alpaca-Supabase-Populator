"""Prepare a closed-scope v72 checkpoint packet; root alone publishes it.

Default mode inventories retained evidence and preserves both canonical v71
files. Finalization requires root-supplied, hash-bound final draft QA inputs.
No connector, database, git ref or automation operation is performed.
"""
import argparse
from datetime import datetime, timezone
from hashlib import sha1, sha256
import gzip
import io
import json
from pathlib import Path
import re
import tarfile

ROOT=Path(__file__).resolve().parents[2]
HERE=ROOT/'review/recovery-v72'
BASE='d06c13f30a0bed8da6366f124101b59d21a450fa'
TREE='3dc2c6d5541d1e911ab12192cea3d10de7eddfef'
TREE_FILE=Path('/tmp/replacement-maintenance-tree-v72.json')
CANONICAL={
 'docs/INGESTION_COMPLETION_STATE.md':'docs/history/INGESTION_COMPLETION_STATE_v71.md',
 'docs/REPLACEMENT_IMPLEMENTATION_AUTOMATION_PROMPT.md':'docs/history/REPLACEMENT_IMPLEMENTATION_AUTOMATION_PROMPT_v71.md',
}
HISTORY_SHA={
 'docs/history/INGESTION_COMPLETION_STATE_v71.md':'02b60feb1010d293e7bf608a4127927c933837ebb76c725d92570d97d2dd5026',
 'docs/history/REPLACEMENT_IMPLEMENTATION_AUTOMATION_PROMPT_v71.md':'b75ab27ebcb619719a2b5c33c9e3b880f7d08a98fbc2f6a99282ded2f303b3fb',
}
MISSION='docs/REPLACEMENT_BACKFILL_MISSION_20261030.md'
MISSION_SHA='62dd1a15c5c6cf46a42340917701816c6c3b86c49e4b4fb462f8b111bcaadc45'
EXTRA_V71=[
 'evidence/replacement-checkpoint-ci-v71.json',
 'evidence/replacement-published-checkpoint-v71.json',
 'evidence/replacement-existing-successor-update-v71.json',
 'evidence/replacement-existing-successor-readback-v71.json',
 'review/recovery-v71/contract_admission_reads_readonly_v71.sql',
 'review/recovery-v71/contract_admission_reads_qualification_v71.json',
 'review/recovery-v71/contract_admission_reads_synthetic_result_v71.json',
 'review/recovery-v71/contract_admission_read_derivation_v71.json',
 'review/recovery-v71/build_contract_admission_reads_v71.py',
 'review/recovery-v71/qualify_contract_admission_reads_v71.py',
 'review/recovery-v71/independent_contract_admission_baseline_v71.json',
 'review/recovery-v71/independent_contract_admission_baseline_v71.py',
 'review/recovery-v71/eligible_task_count_diagnostic_limits_1353.json',
 'review/recovery-v71/live_contract_admission_reads_1349.json',
 'review/recovery-v71/live_contract_seed_state_helpers_1344.json',
 'review/recovery-v71/live_contract_date_stamp_helpers_1346.json',
 'review/recovery-v71/live_maintenance_page_seed_helpers_1339.json',
]
OUTPUTS={
 'review/recovery-v72/checkpoint_publication_inventory_v72.json',
 'evidence/replacement-checkpoint-publication-manifest-v72.json',
}
REFERENCE=re.compile(r'(?<![A-Za-z0-9_])((?:docs|evidence|review|sql|tests|astra_ingestion)/[A-Za-z0-9_./-]+\.(?:json|md|sql|py|diff|log|txt))')

def blob(data):return sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
def ref(path,data):return {'path':path,'bytes':len(data),'sha256':sha256(data).hexdigest(),'git_blob_sha1':blob(data)}
def safe_path(path):
 if type(path) is not str or not re.fullmatch(r'[A-Za-z0-9_./-]+',path):
  raise ValueError('Noncanonical repository path rejected')
 parts=path.split('/')
 if any(part in ('','.','..') for part in parts):raise ValueError('Noncanonical Git path rejected: '+path)
 candidate=ROOT
 for part in parts:
  candidate=candidate/part
  if candidate.is_symlink():raise ValueError('Symlink path rejected: '+path)
 if not candidate.resolve().is_relative_to(ROOT.resolve()):raise ValueError('External artifact path rejected: '+path)
 return candidate
def excluded(path):
 parts=Path(path).parts
 return ('__pycache__' in parts or path.endswith('.pyc') or 'maintenance-timing-contingency' in parts
  or 'prototype' in path.lower() or 'checkpoint-draft' in parts or path in OUTPUTS)
def allowed_new(path):
 return (path.startswith('evidence/') or path.startswith('review/recovery-v71/') or path.startswith('review/recovery-v72/')
  or path in HISTORY_SHA) and not excluded(path)
def load_base():
 raw=json.loads(TREE_FILE.read_text())
 if raw['sha']!=TREE or raw.get('truncated'):raise ValueError('Wrong or truncated exact base tree')
 return raw,{x['path']:x for x in raw['tree'] if x.get('type')=='blob'}
def read_checked(item):
 path=item['path'];p=safe_path(path)
 data=p.read_bytes()
 if sha256(data).hexdigest()!=item['sha256']:raise ValueError('Hash-bound input changed: '+path)
 return data

def collect(tree,inputs=None):
 seeds=set(EXTRA_V71)|set(HISTORY_SHA)
 seeds.update(p.relative_to(ROOT).as_posix() for p in (ROOT/'evidence').glob('*-v72.json') if p.is_file())
 seeds.update(p.relative_to(ROOT).as_posix() for p in HERE.rglob('*') if p.is_file() and not excluded(p.relative_to(ROOT).as_posix()))
 seeds.difference_update(OUTPUTS)
 source_docs={};qa=None
 explicit_evidence=set()
 deferred=set()
 if inputs:
  if inputs.get('state')!='ROOT_FINAL_DRAFT_QA_PASSED':raise ValueError('Root final draft QA has not been supplied')
  if set(inputs.get('approved_documents',{}))!=set(CANONICAL):raise ValueError('Exactly two canonical replacements required')
  qa_data=read_checked(inputs['qa_receipt']);qa=json.loads(qa_data)
  if qa.get('passed') is not True:raise ValueError('Final QA receipt does not pass')
  if qa.get('base_commit')!=BASE or qa.get('base_tree')!=TREE:raise ValueError('Final QA base binding differs')
  if qa.get('reviewed_documents')!=inputs['approved_documents']:
   raise ValueError('Final QA does not bind these exact approved document paths and hashes')
  if not inputs.get('progress_receipt') or qa.get('reviewed_progress_receipt')!=inputs['progress_receipt']:
   raise ValueError('Final QA must bind the mandatory final progress receipt')
  seeds.add(inputs['qa_receipt']['path'])
  explicit_evidence.add(inputs['qa_receipt']['path'])
  read_checked(inputs['progress_receipt']);seeds.add(inputs['progress_receipt']['path'])
  explicit_evidence.add(inputs['progress_receipt']['path'])
  deferred=set(inputs.get('deferred_postpublication_paths',[]))
  for target,item in inputs['approved_documents'].items():source_docs[target]=read_checked(item)
 else:
  for target in CANONICAL:source_docs[target]=safe_path(target).read_bytes()
 for source in source_docs.values():seeds.update(REFERENCE.findall(source.decode('utf-8')))
 required=set(seeds);queue=list(seeds);scanned=set();new={};refs={};missing=[];excluded_refs=[]
 while queue:
  path=queue.pop()
  try:checked_path=safe_path(path)
  except ValueError:
   # A QA receipt can legitimately quote rejected traversal/path examples.
   # They are never opened. Explicitly selected input paths still fail closed.
   if path in required:raise
   excluded_refs.append(path)
   continue
  if path in scanned or path in CANONICAL or path in OUTPUTS:continue
  scanned.add(path)
  if path in tree:
   local=checked_path
   matches=blob(local.read_bytes())==tree[path]['sha'] if local.is_file() else None
   refs[path]={'path':path,'base_git_blob_sha1':tree[path]['sha'],'preserved_existing_blob':True,
    'local_copy_matches_base':matches}
   if inputs and matches is False and path.startswith(('evidence/','review/')):
    raise ValueError('Referenced evidence changed an existing base blob; preserve it under a new name: '+path)
   continue
  if path in deferred:
   continue
  admitted_explicit=(path in explicit_evidence and path.endswith('.json')
    and path.startswith(('evidence/','review/recovery-v72/'))
    and 'prototype' not in path.lower() and 'maintenance-timing-contingency' not in Path(path).parts)
  if excluded(path) and not admitted_explicit:
   excluded_refs.append(path);continue
  if not allowed_new(path) and not admitted_explicit:
   missing.append({'path':path,'reason':'Absent base reference is outside the additive checkpoint scope'});continue
  p=checked_path
  if not p.is_file():
   missing.append({'path':path,'reason':'Referenced retained artifact is unavailable locally'});continue
  data=p.read_bytes();new[path]=data
  try:mentions=REFERENCE.findall(data.decode('utf-8'))
  except UnicodeDecodeError:raise ValueError('Non-text artifact excluded from checkpoint: '+path)
  queue.extend(p for p in mentions if p not in scanned)
 for target,archive in CANONICAL.items():
  data=safe_path(archive).read_bytes()
  if sha256(data).hexdigest()!=HISTORY_SHA[archive] or blob(data)!=tree[target]['sha']:
   raise ValueError('v71 history is not the exact current remote canonical blob')
  if archive in tree and tree[archive]['sha']!=blob(data):raise ValueError('Immutable v71 history differs')
  if archive not in tree:new[archive]=data
 mission=safe_path(MISSION).read_bytes()
 if sha256(mission).hexdigest()!=MISSION_SHA or blob(mission)!=tree[MISSION]['sha']:raise ValueError('Original mission drift')
 if inputs:
  prompt=source_docs['docs/REPLACEMENT_IMPLEMENTATION_AUTOMATION_PROMPT.md']
  if prompt.count(mission)!=1 or not prompt.endswith(mission):raise ValueError('Task prompt must carry exactly one byte-identical mission at EOF')
  for target,data in source_docs.items():
   if data==safe_path(CANONICAL[target]).read_bytes():raise ValueError('Final canonical v72 document did not advance')
   new[target]=data
 return new,refs,missing,excluded_refs,source_docs,qa

def main():
 args=argparse.ArgumentParser()
 args.add_argument('--finalize',action='store_true')
 args.add_argument('--inputs',default='review/recovery-v72/checkpoint_publication_inputs_v72.json')
 options=args.parse_args()
 raw,tree=load_base()
 input_path=safe_path(options.inputs)
 inputs=json.loads(input_path.read_text()) if options.finalize else None
 new,refs,missing,excluded_refs,source_docs,qa=collect(tree,inputs)
 existing_drift=[]
 for root in (ROOT/'evidence',HERE):
  for p in root.rglob('*'):
   if not p.is_file():continue
   path=p.relative_to(ROOT).as_posix()
   p=safe_path(path)
   if path in tree and not excluded(path) and blob(p.read_bytes())!=tree[path]['sha']:
    existing_drift.append({'path':path,'base_git_blob_sha1':tree[path]['sha'],'local_git_blob_sha1':blob(p.read_bytes()),'published':False})
 inventory={'schema':'astra.checkpoint-publication-inventory/1','created_at':datetime.now(timezone.utc).isoformat(),
  'state':'FINAL_QA_BOUND' if inputs else 'PREPARED_ONLY_CANONICAL_DOCUMENTS_NOT_PROMOTED',
  'base_commit':BASE,'base_tree':TREE,'base_tree_entries':len(raw['tree']),'truncated':False,
  'permitted_replacements':list(CANONICAL),'canonical_v71_archives':HISTORY_SHA,
  'new_candidate_files':[ref(p,d) for p,d in sorted(new.items()) if p not in tree],
  'existing_references_preserved':[refs[p] for p in sorted(refs)],
  'existing_local_drift_excluded':existing_drift,'unavailable_references':missing,'excluded_references':sorted(set(excluded_refs)),
  'excluded_classes':['Nine stale local runtime/foundation differences','active SQL/test changes','timing contingency and prototypes','__pycache__ and pyc','unapproved checkpoint drafts'],
  'required_final_inputs':{'state':'ROOT_FINAL_DRAFT_QA_PASSED','qa_receipt':{'path':'<actual passed QA JSON>','sha256':'<actual hash>'},
   'approved_documents':{p:{'path':'<root-approved final draft path>','sha256':'<actual final draft hash>'} for p in CANONICAL},
   'progress_receipt':{'path':'<actual final progress receipt>','sha256':'<actual hash>'}},
  'remote_or_production_calls':0,'canonical_local_files_written':False}
 inv_path='review/recovery-v72/checkpoint_publication_inventory_v72.json';inv_data=(json.dumps(inventory,indent=2)+'\n').encode()
 (ROOT/inv_path).write_bytes(inv_data)
 if not options.finalize:
  print(json.dumps({'state':inventory['state'],'new_candidates':len(inventory['new_candidate_files']),
   'existing_refs':len(refs),'unavailable_refs':missing,'inventory':ref(inv_path,inv_data)}));return
 if missing:raise ValueError('Unresolved checkpoint references: '+json.dumps(missing))
 if input_path.relative_to(ROOT).as_posix() in tree:raise ValueError('Final inputs unexpectedly overwrite a base file')
 new[input_path.relative_to(ROOT).as_posix()]=input_path.read_bytes();new[inv_path]=inv_data
 for path,data in new.items():
  if path in tree and path not in CANONICAL:raise ValueError('Forbidden existing blob replacement: '+path)
  if path.startswith(('sql/','tests/','astra_ingestion/')):raise ValueError('Checkpoint cannot modify active code, tests or SQL')
 manifest={'schema':'astra.checkpoint-publication-manifest/1','created_at':datetime.now(timezone.utc).isoformat(),
  'version':72,'state':'READY_LOCAL_NOT_PUBLISHED','repository':'robert8p/Alpaca-Supabase-Populator','base_commit':BASE,'base_tree':TREE,
  'canonical_replacements':{p:ref(p,new[p]) for p in CANONICAL},'exact_v71_archives':HISTORY_SHA,
  'canonical_bytes_equal_exact_reviewed_drafts':True,
  'reviewed_draft_sources_not_duplicated_in_publication':inputs['approved_documents'],
  'all_other_existing_blobs_preserved':True,'active_runtime_sql_tests_or_workflows_changed':False,
  'mission_sha256':MISSION_SHA,'mission_exact_once_at_task_prompt_eof':True,
  'root_final_qa_receipt':inputs['qa_receipt'],'root_final_progress_receipt':inputs.get('progress_receipt'),
  'deferred_postpublication_paths':inputs.get('deferred_postpublication_paths',[]),
  'no_automation_write_or_controller_creation':True,'no_publication_or_production_calls':True,
  'files':[dict(ref(p,d),base_state='REPLACE_CANONICAL' if p in tree else 'ADDITIVE') for p,d in sorted(new.items())]}
 mpath='evidence/replacement-checkpoint-publication-manifest-v72.json';mdata=(json.dumps(manifest,indent=2)+'\n').encode()
 (ROOT/mpath).write_bytes(mdata);new[mpath]=mdata
 packet={'schema':'astra.checkpoint-publication-packet/1','base_commit':BASE,'base_tree':TREE,
  'expected_head_must_be_reconciled_before_mutation':True,'manifest':ref(mpath,mdata),
  'tree_entries':[{'path':p,'mode':'100644','type':'blob','content':d.decode('utf-8')} for p,d in sorted(new.items())]}
 output=Path('/tmp/replacement-checkpoint-publication-packet-v72.json');output.write_text(json.dumps(packet,ensure_ascii=False)+'\n')
 listing=Path('/tmp/replacement-checkpoint-publication-files-v72.txt');listing.write_text('\n'.join(sorted(new))+'\n')
 archive=Path('/tmp/replacement-checkpoint-publication-packet-v72.tar.gz')
 with archive.open('wb') as f,gzip.GzipFile(fileobj=f,mode='wb',mtime=0) as compressed,tarfile.open(fileobj=compressed,mode='w') as tar:
  for p,d in sorted(new.items()):
   info=tarfile.TarInfo(p);info.size=len(d);info.mode=0o644;info.mtime=0;tar.addfile(info,io.BytesIO(d))
 print(json.dumps({'state':manifest['state'],'file_count':len(new),'manifest':ref(mpath,mdata),
  'packet':ref(str(output),output.read_bytes()),'archive':ref(str(archive),archive.read_bytes()),'file_list':str(listing)}))
if __name__=='__main__':main()
