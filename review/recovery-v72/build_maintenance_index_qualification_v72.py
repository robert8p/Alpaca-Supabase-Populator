"""Freeze truthful producer evidence for the additive maintenance hash pair."""
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path

ROOT=Path(__file__).resolve().parents[2]
HERE=ROOT/'review/recovery-v72'
PATHS=[
'sql/astra_backfill_breadth_pending_hash_index_v2.sql',
'sql/astra_backfill_minute_pending_hash_index_v2.sql',
'tests/ingestion/test_backfill_maintenance_task_indexes_v2.py',
'review/recovery-v72/maintenance_index_forward_derivation_v72.json',
'review/recovery-v72/maintenance_index_active_qualification_v72.json',
'review/recovery-v72/maintenance_index_active_initial_qualification_v72.json',
'review/recovery-v72/maintenance_task_btree_initial_qualification_v72.json',
'review/recovery-v72/maintenance_task_hash_sensitivity_qualification_v72.json',
'review/recovery-v72/maintenance_task_hash_collision_initial_qualification_v72.json',
'review/recovery-v72/maintenance_hash_collision_focused_qualification_v72.json',
'review/recovery-v72/maintenance_hash_positive_generic_qualification_v72.json',
'review/recovery-v72/qualify_maintenance_task_btree_initial_v72.py',
'review/recovery-v72/qualify_maintenance_task_hash_sensitivity_v72.py',
'review/recovery-v72/qualify_maintenance_task_indexes_v72.py',
'review/recovery-v72/qualify_hash_collision_focused_v72.py',
'review/recovery-v72/qualify_hash_positive_generic_focused_v72.py',
'review/recovery-v72/build_maintenance_index_forwards_v72.py',
'review/recovery-v72/audit_maintenance_index_dependencies_v72.py',
'review/recovery-v71/live_ingestion_cron_registry_1330.json',
'review/recovery-v71/live_ingestion_cron_run_pid_proof_1331.json',
'review/recovery-v71/live_monitor_second_holder_correlation_1326.json',
'review/recovery-v71/live_monitor_gate_failures_1346_1350.json',
'review/recovery-v71/live_worker_errors_1346_1350.json',
'review/recovery-v71/live_monitor_runs_1344_1354.json',
'review/recovery-v71/live_maintenance_selector_profile_1341.json',
'review/recovery-v71/live_maintenance_candidate_metadata_1342.json',
'review/recovery-v71/live_contract_admission_reads_1349.json',
'review/recovery-v71/live_task_index_inventory_1351.json',
'review/recovery-v71/live_maintenance_helpers_1335.json',
'review/recovery-v71/live_backfill_maintain_1332.json',
'review/recovery-v71/live_cron_functions_1331.json',
'review/recovery-v71/maintenance_selectors_readonly_v71.sql',
'review/recovery-v72/live_task_visibility_stats_1359.json',
'review/recovery-v72/live_database_size_version_1404.json',
]
def load(name):return json.loads((HERE/name).read_text())
def ref(path):
 data=(ROOT/path).read_bytes()
 return {'path':path,'bytes':len(data),'sha256':sha256(data).hexdigest()}
def main():
 active=load('maintenance_index_active_qualification_v72.json')
 scale=load('maintenance_task_hash_sensitivity_qualification_v72.json')
 positive=load('maintenance_hash_positive_generic_qualification_v72.json')
 collision=load('maintenance_hash_collision_focused_qualification_v72.json')
 manifest=load('maintenance_index_forward_derivation_v72.json')
 for result in (active,scale,positive,collision):
  if result.get('passed') is not True:raise ValueError('A required final qualification did not pass')
 assert active['tests']==9 and active['errors']==active['failures']==active['skipped']==0
 assert not active['different_paths']
 assert scale['tests']==1 and positive['tests']==1
 assert all(x['sha256']==sha256((ROOT/x['path']).read_bytes()).hexdigest() for x in manifest['forwards'])
 metrics={}
 for label in ('BREADTH_PENDING','MINUTE_ACCOUNT_PENDING'):
  def visits(record):return sum((x.get('Shared Hit Blocks') or 0)+(x.get('Shared Read Blocks') or 0) for x in record['task_nodes'])
  metrics[label]={'baseline_task_buffer_visits':visits(scale['before'][label]),
    'hash_states':{state:{'task_buffer_visits':visits(data[label]),'execution_ms':data[label]['plan']['Execution Time'],
      'task_nodes':data[label]['task_nodes']} for state,data in scale['hash_states'].items()}}
 receipt={
 'schema':'astra.maintenance-hash-index.qualification/1',
 'created_at':datetime.now(timezone.utc).isoformat(),
 'state':'PREPARED_LOCAL_NOT_APPLIED','production_calls_by_producer':0,'root_only_production_authority':True,
 'base_commit':'536bb850cf5c5653b4865e63db3f20f50a6769a1','base_tree':'60ba98872222e1c7f285296fc48300e326ee6fda',
 'problem':{
  'proven_blocker':'The existing monitor cron602 transaction held the exact global advisory gate while worker claim/reserve operations exhausted the unchanged3-second gate wait.',
  'exact_correlations':[
   {'at':'2026-10-30T13:16:03.335Z','holder_pid':1242938,'cron_run':4068588,'cron_elapsed_seconds':3.914112},
   {'at':'2026-10-30T13:26:03.224Z','holder_pid':1244016,'cron_run':4068598,'cron_elapsed_seconds':4.040049},
   {'at':'2026-10-30T13:46:03Z','holder_pid':1246301,'cron_run':4068618,'cron_elapsed_seconds':4.126863},
   {'at':'2026-10-30T13:48:03Z','holder_pid':1246448,'cron_run':4068620,'cron_elapsed_seconds':3.829729},
   {'at':'2026-10-30T13:50:03Z','holder_pid':1246544,'cron_run':4068622,'cron_elapsed_seconds':3.771201}],
  'correlation_limits':['The last three timestamps identify the minute/second window; retained safe log files contain the exact fractional times.',
    'Cron elapsed time includes possible initial gate wait and is not a measured per-helper or exclusive lock-hold duration.',
    'Other35-byte health request failures are not counted as worker failures.'],
  'demonstrated_selector_work':{'observed_at':'2026-10-30T13:41:02.985638Z','total10_readonly_selector_profile_ms':733,
   'breadth':{'execution_ms':445.102,'candidate_rows':0,'rejected_task_pk_probes':4240,'task_heap_physical_reads':501},
   'minute':{'execution_ms':181.387,'candidate_rows':0,'rejected_task_pk_probes':4170,'task_heap_physical_reads':211}},
  'causal_limit':'These selectors demonstrate avoidable work under the proven blocker. Their direct-role733ms total does not establish the entire3-to5-second monitor cost or guarantee that this pair eliminates all contention.'},
 'change':{'only_two_additive_partial_indexes':manifest['expected_index_definitions'],
   'unchanged_existing_indexes':manifest['baseline_index_names'],'unchanged_function_source_pins':manifest['source_pins'],
   'no_function_or_query_rewrite':True,'no_row_data_change':True,'primary_unique_id_index_retained':True,
   'no_worker_deployment':True,'no_authentication_grant_credential_schedule_gate_or_runtime_timeout_change':True},
 'security_diff':{'persistent_access_expansion':False,'new_roles_or_grants':False,'new_trust_or_credentials':False,
   'persistent_changes':['Two nonunique partial hash indexes on existing task id, owned by the existing table owner, with no index ACL.'],
   'preserved':['global advisory gate706314020261028','post-lock live credential recheck','worker/API authentication and scopes',
    'fixed3000 cohort and owner/fence/lease','page and readback integrity','all runtime function sources and metadata','table owner/ACL/RLS',
    'existing15 indexes','task/status/count/reservation semantics','original selector text and cursor behavior']},
 'qualification':{'active_exact_forward_tests':{'tests':9,'errors':0,'failures':0,'skipped':0,'elapsed_seconds':active['elapsed_seconds'],
   'proof':active['qualification'],'actual_open_import_dependency_audit':True,'base_fixture_overwrites':False},
  'scale':{'tests':1,'errors':0,'failures':0,'skipped':0,'elapsed_seconds':scale['elapsed_seconds'],
   'fixture':scale['fixture'],'synthetic_d03_eligible':scale['synthetic_d03_eligible'],
   'synthetic_minute_eligible_upper_bound':scale['synthetic_minute_eligible_upper_bound'],
   'visibility':scale['visibility'],'metrics':metrics,'growth':scale['growth'],
   'minute_predicate_cases':len(scale['minute_predicate_cases']),'breadth_predicate_cases':len(scale['breadth_predicate_cases'])},
  'positive_generic':{'tests':1,'errors':0,'failures':0,'skipped':0,'elapsed_seconds':positive['elapsed_seconds'],
   'fixture':positive['fixture'],'proof':positive['positive_and_generic'],
   'interpretation':'One positive candidate per family; minute DISTINCT/LIMIT has no ORDER BY. Equality of the selected identities is proved for this fixture, not a new ordering guarantee across multiple eligible minute tasks.'},
  'hash_collision':{'passed':True,'elapsed_seconds':collision['elapsed_seconds'],'positive_count':1,'excluded_count':0,
   'actual_hash_recheck_removed_false_match':True,'normal_planner_selected_hash':True,'primary_key_retained':True},
  'local_version':'PostgreSQL16.15','live_version':'PostgreSQL17.6','live_plan_and_readback_still_required':True},
 'retained_unsuccessful_experiments':[
  {'receipt':'review/recovery-v72/maintenance_task_btree_initial_qualification_v72.json',
   'outcome':'Index selection assertions passed but B-tree pair failed the performance objective: whole-eligible scans and visibility-sensitive heap fetches; minute was slower. B-tree pair is not proposed.'},
  {'receipt':'review/recovery-v72/maintenance_task_hash_collision_initial_qualification_v72.json',
   'outcome':'Full positive/generic attempt reached the final large-table collision-search query, which hit8s; one error, no successful overall qualification. A focused collision case and reduced positive/generic case subsequently passed independently.'},
  {'receipt':'review/recovery-v72/maintenance_index_active_initial_qualification_v72.json',
   'outcome':'Nine active cases executed with one fixture setup error: the incomplete-cohort run violated the existing one-ACTIVE-run constraint. The fixture now pauses its original synthetic run before creating a separate2999-member run; production admission guards remain unchanged.'}],
 'resource_and_installation_limits':{
  'production_task_heap_bytes_at_inventory':859889664,'production_task_estimated_rows_at_inventory':712899,
  'local_pair_bytes_after50000_eligible_growth':sum(x['bytes'] for x in scale['new_indexes']),
  'actual_live_index_bytes_required':True,'database_total_bytes_is_not_free_capacity_proof':True,
  'builds':{'transactions':2,'order':['breadth','minute'],'ordinary_not_concurrent':True,
   'statement_budget_seconds':8,'lock_budget_seconds':3,'lock_order':manifest['lock_order'],
   'writer_impact':'Each ordinary build scans the task heap and can temporarily block writers while holding the existing global gate and task-table SHARE lock.',
   'no_live_build_duration_guarantee':True,'no_silent_timeout_extension':True,
   'failure_or_uncertain_outcome':'Reconcile exact index definition/validity and migration history before any retry. An exact valid installed target is a guarded no-op; drift aborts.'},
  'hash_tradeoffs':['Persistent crash-recoverable equality-only single-column indexes; original unique primary key remains.',
   'Lossy hash collisions require exact equality recheck, proved in the focused case.',
   'Foreground bucket growth and added insert/update storage work remain costs;50000 eligible inserts and2000 status transitions were measured locally.'],
  'evidence_limits':['Local scale tables copied real shapes, defaults, checks and15 index definitions but not foreign keys/triggers; actual active-forward tests used the full application fixture.',
   'Warm/fresh local cache and bloat differ from production; no uncontrolled live speed ratio is claimed.',
   'Synthetic26466 minute tasks are the live family/kind upper bound, not a measured exact timeframe-eligible production count.',
   'Local scale used normal index/join enablement with serial planner and disclosed jit/random_page/work_mem/cache settings; the live direct minute probe used parallelism.',
   'Visibility map tests are local sensitivity evidence; no production VACUUM or planner setting change is proposed.']},
 'activation_order_if_combined':['Reconcile same owner/lease/fence/cohort, exact runtime source pins and uncertain writes.',
  'Require independently reviewed artifacts and exact publication CI gates.',
  'Apply breadth hash forward once, then independently read back definition/validity/metadata/size.',
  'Apply minute hash forward once, then independently read back definition/validity/metadata/size.',
  'Only then consider the separately reviewed readback transaction-race forward, because hash admission pins the unchanged maintaincd100 definition.',
  'Measure current unchanged selector plans and successful cron durations/error correlations; count actual newly committed and read-back pages.'],
 'official_postgresql_references':['https://www.postgresql.org/docs/17/hash-index.html',
   'https://www.postgresql.org/docs/17/indexes-partial.html','https://www.postgresql.org/docs/17/sql-createindex.html'],
 'artifacts':[ref(path) for path in PATHS]}
 out=ROOT/'evidence/replacement-maintenance-task-hash-index-qualification-v72.json'
 out.write_text(json.dumps(receipt,indent=2,default=str)+'\n')
 print(json.dumps(ref(out.relative_to(ROOT).as_posix())))
if __name__=='__main__':main()
