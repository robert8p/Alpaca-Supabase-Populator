"""Prepare one conditional, semantics-preserving shared field decomposition."""
from hashlib import sha256
from pathlib import Path
import difflib,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
source_file=ROOT/'review/recovery-v73/live_shared_nested_definitions_after_restore_v73.json'
f=next(x for x in json.loads(source_file.read_text())[0]['functions'] if x['name']=='backfill_shared_refresh_v2')
before=f['definition'];assert sha256(before.encode()).hexdigest()==f['source_sha256']
needle=' fields AS MATERIALIZED(SELECT c.record_key,jsonb_object_agg(v.field,COALESCE(c.field_states->v.field,jsonb_build_object('
replacement=' chosen_fields AS MATERIALIZED(SELECT c.record_key,f.key field,f.value field_state FROM chosen c CROSS JOIN LATERAL jsonb_each(c.field_states) f),\n fields AS MATERIALIZED(SELECT c.record_key,jsonb_object_agg(v.field,COALESCE(cf.field_state,jsonb_build_object('
old_join='  FROM chosen c JOIN votes v USING(record_key) JOIN candidate_counts n USING(record_key) GROUP BY c.record_key),'
new_join='  FROM chosen c JOIN votes v USING(record_key) JOIN candidate_counts n USING(record_key)\n  LEFT JOIN chosen_fields cf ON cf.record_key=c.record_key AND cf.field=v.field GROUP BY c.record_key),'
assert before.count(needle)==1 and before.count(old_join)==1 and before.count('c.field_states->v.field')==1
after=before.replace(needle,replacement,1).replace(old_join,new_join,1)
assert after.replace(replacement,needle,1).replace(new_join,old_join,1)==before
assert after[after.index('\n DELETE FROM'):]==before[before.index('\n DELETE FROM'):]
(HERE/'baseline_shared_refresh_v74.sql').write_text(before)
(HERE/'candidate_shared_refresh_field_cache_v74.sql').write_text(after)
(HERE/'shared_refresh_field_cache_v74.diff').write_text(''.join(difflib.unified_diff(before.splitlines(keepends=True),after.splitlines(keepends=True),fromfile='installed_b18a30',tofile='candidate_field_decomposition')))
def read_input(text):
 q=text[text.index(' WITH keys AS'):text.index('\n DELETE FROM')]
 q=q.replace(' INSERT INTO astra_ingestion_v1.backfill_shared_records_v2\n','\n',1)
 return q[:q.index('\n ON CONFLICT(')].strip()
for label,text in [('baseline',before),('candidate',after)]:
 (HERE/(label+'_full_record_select_v74.sql')).write_text(read_input(text)+'\n')
d={'schema':'astra.shared-field-cache-candidate/1','state':'CONDITIONAL_PREPARATION_NOT_SELECTED_OR_INSTALLED',
 'source_path':source_file.relative_to(ROOT).as_posix(),'source_file_sha256':sha256(source_file.read_bytes()).hexdigest(),
 'signature':f['signature'],'baseline_sha256':sha256(before.encode()).hexdigest(),'candidate_sha256':sha256(after.encode()).hexdigest(),
 'unchanged_metadata':f['metadata'],'exact_inverse_restores_baseline':True,'second_link_statement_byte_identical':True,
 'changes':['Materialize chosen JSONB fields once for each chosen record','Left join by the unique record_key/field pair','Use the joined JSONB value in the existing COALESCE fallback'],
 'preserved':['Missing key SQLNULL and present JSONnull distinctions','Existing conflict counts and deterministic conflict ordering','Version ordering and tied/unknown timestamp behavior','All link/date/identity/accounting/source/fence/lease/authentication semantics','Function owner ACL OID config and signature'],
 'live_evidence':'review/recovery-v74/shared-read-profile/live_refresh_record_select_input_v74.json',
 'causal_limit':'Additional80000sharedbufferhits in fields aggregate beyond its child are consistent with repeated detoast; node timings were disabled and this is not exclusive whole-phase attribution.',
 'production_calls':0,'active_forward_written':False}
(HERE/'shared_field_cache_derivation_v74.json').write_text(json.dumps(d,indent=2)+'\n')
print(json.dumps({'baseline_sha256':d['baseline_sha256'],'candidate_sha256':d['candidate_sha256'],'state':d['state']}))
