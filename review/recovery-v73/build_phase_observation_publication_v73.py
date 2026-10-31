"""Build the explicit additive v73 packet only after frozen qualification/review."""
from datetime import datetime,timezone
from hashlib import sha1,sha256
import gzip
import io
import json
from pathlib import Path,PurePosixPath
import re
import tarfile

ROOT=Path(__file__).resolve().parents[2]
HERE=ROOT/'review/recovery-v73'
BASE='1f1f423e4dd1db87eff92e8687b2d9c49ba63c01'
TREE='45c5b7d6410f4fba1d154d50debdb3b574c9e86d'
INPUTS='review/recovery-v73/phase_publication_review_pins_v73.json'
AUDIT='review/recovery-v73/maintenance_phase_active_qualification_v73.json'
ACTIVE={
 'tests/ingestion/test_backfill_maintenance_phase_observation_v73.py',
 'tests/ingestion/test_backfill_maintenance_phase_installation_v73.py',
 'sql/astra_backfill_maintenance_phase_observation_v73.sql',
 'sql/astra_backfill_maintenance_phase_observation_restore_v73.sql',
}
EXTRA={
 'evidence/replacement-maintenance-phase-observation-qualification-v73.json',
 'evidence/replacement-published-checkpoint-v72.json',
 'evidence/replacement-existing-successor-update-v72.json',
 'evidence/replacement-checkpoint-ci-v72.json',
 'evidence/replacement-owner-phase-observation-cleanup-lease-v73.json',
}


def safe_path(value):
 if type(value) is not str or not re.fullmatch(r'[A-Za-z0-9_./-]+',value):raise ValueError('Noncanonical publication path')
 p=PurePosixPath(value)
 if p.is_absolute() or str(p)!=value or any(x in ('.','..') for x in value.split('/')):
  raise ValueError('Noncanonical publication path')
 q=ROOT
 for part in p.parts:
  q=q/part
  if q.is_symlink():raise ValueError('Symlink publication input is forbidden')
 if not q.resolve().is_relative_to(ROOT.resolve()):raise ValueError('Publication path escaped repository')
 return q


def blob(data):return sha1(b'blob '+str(len(data)).encode()+b'\0'+data).hexdigest()
def record(path,data):return {'path':path,'bytes':len(data),'sha256':sha256(data).hexdigest(),'git_blob_sha1':blob(data)}
def read(path):return safe_path(path).read_bytes()
def document(path):return json.loads(read(path))


def main():
 raw=json.loads(Path('/tmp/replacement-checkpoint-tree-v72.json').read_text())
 if raw.get('sha')!=TREE or raw.get('truncated'):raise ValueError('Exact1f1f base tree is missing or truncated')
 tree={x['path']:x for x in raw['tree'] if x.get('type')=='blob'}
 inputs=document(INPUTS)
 if inputs.get('base_commit')!=BASE or inputs.get('base_tree')!=TREE:raise ValueError('Review inputs use a different base')
 pins=inputs['reviewed_artifact_pins']
 if not ACTIVE<=set(pins):raise ValueError('Every active SQL and test must have a frozen reviewed pin')
 for path,pin in pins.items():
  if sha256(read(path)).hexdigest()!=pin:raise ValueError('Frozen reviewed artifact drift: '+path)
 reviewed_bindings={}
 for path in inputs['independent_review_paths']:
  if path not in pins:raise ValueError('Independent receipt is not hash-bound')
  review=document(path)
  if review.get('passed') is not True:raise ValueError('Independent review is not an explicit pass')
  if review.get('base_commit')!=BASE or review.get('base_tree')!=TREE:raise ValueError('Independent review binds a different base')
  for source,pin in review.get('reviewed_artifact_pins',{}).items():
   safe_path(source)
   if source in reviewed_bindings and reviewed_bindings[source]!=pin:raise ValueError('Independent review bindings conflict')
   reviewed_bindings[source]=pin
 required=ACTIVE|{'review/recovery-v73/candidate_maintain_phase_observation_v73.sql',
                 'evidence/replacement-maintenance-phase-observation-qualification-v73.json'}
 if any(reviewed_bindings.get(path)!=pins.get(path) or path not in pins for path in required):
  raise ValueError('Independent review does not bind the exact active artifacts/candidate/producer proof')
 audit=document(AUDIT)
 if not(audit.get('passed') and audit.get('base_commit')==BASE and audit.get('base_tree')==TREE
  and audit.get('all_active_tests_executed') and audit.get('errors')==audit.get('failures')==audit.get('skipped')==0
  and not audit.get('different_paths')):raise ValueError('Final active qualification/closure is incomplete')
 expected=inputs['expected_active_tests']
 if {x['module']:x['tests'] for x in audit['outcomes']}!=expected:raise ValueError('Active test inventory differs')
 # Only the explicitly scoped v73 preparation directory, reviewed receipts,
 # four active additions and the three completed v72 continuity receipts.
 paths=set(ACTIVE)|set(EXTRA)|set(pins)|{INPUTS,AUDIT}
 for p in HERE.rglob('*'):
  if '__pycache__' in p.parts or p.suffix=='.pyc':continue
  rel=p.relative_to(ROOT).as_posix();safe_path(rel)
  if p.is_file():
   if p.suffix not in ('.json','.md','.py','.sql','.diff'):raise ValueError('Unexpected v73 artifact type')
   paths.add(rel)
 dependencies={x['path']:x for x in audit['files']}
 for path,item in dependencies.items():
  if item['base_state']=='ABSENT':
   if sha256(read(path)).hexdigest()!=item['sha256']:raise ValueError('New dependency changed: '+path)
   paths.add(path)
  elif item['base_state']=='IDENTICAL':
   if tree.get(path,{}).get('sha')!=item['git_blob_sha1']:raise ValueError('Existing dependency tree mismatch')
  else:raise ValueError('Existing dependency modification is forbidden')
 payload={};refs=[]
 for path in sorted(paths):
  if path.startswith(('astra_ingestion/','.github/','docs/')):raise ValueError('Runtime/workflow/canonical-doc change is out of scope')
  if path.startswith(('sql/','tests/')) and path not in ACTIVE:
   # A previously absent base fixture is allowed only if observed as required;
   # this does not permit an arbitrary source-file expansion.
   if path not in dependencies or dependencies[path]['base_state']!='ABSENT':raise ValueError('Unreviewed active source addition')
  data=read(path);item=record(path,data);prior=tree.get(path)
  item['base_state']='ABSENT' if prior is None else 'IDENTICAL' if prior['sha']==item['git_blob_sha1'] else 'DIFFERENT'
  if item['base_state']=='DIFFERENT':raise ValueError('Packet would overwrite an existing1f1f blob: '+path)
  refs.append(item)
  if prior is None:payload[path]=data
 manifest={
  'schema':'astra.maintenance-phase-observation.publication-manifest/1',
  'state':'PREPARED_LOCAL_NOT_PUBLISHED_NOT_ACTIVATED',
  'created_at':datetime.now(timezone.utc).isoformat(),'base_commit':BASE,'base_tree':TREE,
  'repository':'robert8p/Alpaca-Supabase-Populator','remote_mutations_by_producer':0,
  'scope':'Temporarily observe at most four global-maintenance phase samples using existing permissions; exact6c880 restoration accompanies it.',
  'observation_deadline_utc':'2026-10-30T15:45:00Z','deadline_is_not_extended_by_publication_or_receipt':True,
  'activation_status':'NOT_ACTIVATED_PENDING_ROOT_RECONCILIATION_AND_EXACT_CI',
  'database_incident_reconciliation_requirement':'Database returned57P03 around15:24; require fresh successful ownership, source, permissions and exact-head reconciliation before any activation.',
  'required_before_activation':['Root reconciles existing controller, successor, same owner/fence/cohort/lease and every uncertain write.',
   'All exact-head required CI gates must pass; complete17-case observation suite and installer suite must execute with zero dedicated-gate skips.',
   'Fresh database source/metadata/ACL/index guards must pass before fixed15:45 deadline.',
   'Root alone applies reviewed forward once and reads back exact candidate; uncertain outcomes are reconciled before retry.',
   'Observe at most four committed samples; exact restore may run after deadline under same unexpired owner lease.'],
  'no_runtime_worker_auth_grant_credential_provider_schedule_changes':True,
  'all_existing1f1f_blobs_retained':True,'active_additions':sorted(ACTIVE),
  'active_tests':expected,'dependency_count':len(dependencies),'required_new_dependencies':audit['absent_paths'],
  'failed_qualification_attempt_retained':'review/recovery-v73/maintenance_phase_observation_qualification_attempt_1_v73.json',
  'reviewed_artifact_pins':pins,'referenced_existing_and_new_artifacts':refs,
  'payload_files':[record(p,d) for p,d in sorted(payload.items())]}
 manifest_path='evidence/replacement-maintenance-phase-observation-publication-manifest-v73.json'
 data=(json.dumps(manifest,indent=2)+'\n').encode();safe_path(manifest_path).write_bytes(data);payload[manifest_path]=data
 packet={'schema':'astra.maintenance-phase-observation.publication-packet/1','base_commit':BASE,'base_tree':TREE,
  'expected_head_must_be_reconciled_before_mutation':True,'manifest':record(manifest_path,data),
  'tree_entries':[{'path':p,'mode':'100644','type':'blob','content':d.decode('utf-8')} for p,d in sorted(payload.items())]}
 output=Path('/tmp/replacement-phase-observation-publication-packet-v73.json');output.write_text(json.dumps(packet,ensure_ascii=False)+'\n')
 listing=Path('/tmp/replacement-phase-observation-publication-files-v73.txt');listing.write_text('\n'.join(sorted(payload))+'\n')
 archive=Path('/tmp/replacement-phase-observation-publication-packet-v73.tar.gz')
 with archive.open('wb') as out,gzip.GzipFile(fileobj=out,mode='wb',mtime=0) as zipped,tarfile.open(fileobj=zipped,mode='w') as tar:
  for p,d in sorted(payload.items()):
   info=tarfile.TarInfo(p);info.size=len(d);info.mode=0o644;info.mtime=0;tar.addfile(info,io.BytesIO(d))
 print(json.dumps({'files':len(payload),'manifest':record(manifest_path,data),
  'packet':record(str(output),output.read_bytes()),'archive':record(str(archive),archive.read_bytes()),
  'file_list':str(listing),'dependencies':len(dependencies)}))

if __name__=='__main__':main()
