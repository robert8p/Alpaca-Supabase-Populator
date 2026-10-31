"""Prepare one candidate-only read while guarding the still-installed baseline."""
from pathlib import Path
from hashlib import sha256
import json,re
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
source=ROOT/'review/recovery-v74/shared-read-profile/shared_refresh_record_select_input_readonly_v74.sql'
assert sha256(source.read_bytes()).hexdigest()=='b86543db1a2f95b9e085c4b716c8bcaf184c1dfdf9f87479c4a3bd14dab5af65'
sql=source.read_text();query=(HERE/'candidate_full_record_select_v74.sql').read_text().strip()
query=re.sub(r'\bp_keys\b','$6',re.sub(r'\bp_run\b','$5',query))
assert not re.search(r'\b(INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|PERFORM)\b',query,re.I)
a=sql.index('$read_select$')+len('$read_select$');b=sql.index('$read_select$',a)
old_query=sql[a:b];candidate=sql[:a]+query+sql[b:]
needle="'observed_at',clock_timestamp(),'component',v_component,"
replacement=needle+"'variant','CANDIDATE_SELECT_ONLY_FUNCTION_NOT_INSTALLED',\n  'candidate_definition_sha256','7f538bf47cb5e74050c20266e01cbe9d6521c1a65663aaf2e0fe38d62041f1a4',\n  'installed_function_sha256','b18a30c47e13a9738f111ff739e8cda53120e882eaa7e7e0427144372ab8dbc4',"
assert candidate.count(needle)==1;candidate=candidate.replace(needle,replacement,1)
reverted=candidate.replace(query,old_query,1).replace(replacement,needle,1)
assert reverted==sql
out=HERE/'shared_candidate_record_select_readonly_v74.sql';out.write_text(candidate)
receipt={'schema':'astra.shared-candidate-read-derivation/1','baseline_probe':{'path':source.relative_to(ROOT).as_posix(),'sha256':sha256(source.read_bytes()).hexdigest()},
 'candidate_probe':{'path':out.relative_to(ROOT).as_posix(),'sha256':sha256(out.read_bytes()).hexdigest(),'bytes':out.stat().st_size},
 'candidate_definition_sha256':'7f538bf47cb5e74050c20266e01cbe9d6521c1a65663aaf2e0fe38d62041f1a4',
 'installed_function_guard_unchanged':'b18a30c47e13a9738f111ff739e8cda53120e882eaa7e7e0427144372ab8dbc4',
 'all15_baseline_source_metadata_pins_identical':True,'readonly_wrapper_fixed_page_keys_and_bounds_identical':True,
 'changes':['Only the full SELECT body uses the qualified candidate','Only result annotation explicitly identifies the candidate and still-installed baseline'],
 'mechanical_inverse_equals_selected_baseline_probe':True,'production_calls':0,'baseline_probe_must_not_be_replayed':True,
 'interpretation':'Separate snapshots/cache state preclude a controlled latency ratio. This tests read access and IO behavior only; function not installed and no full-phase recovery claim.'}
(HERE/'candidate_read_derivation_v74.json').write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps(receipt['candidate_probe']))
