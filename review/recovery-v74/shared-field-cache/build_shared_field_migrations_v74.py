"""Exact source-only forward/restore preparation; no connection or activation."""
from pathlib import Path
from hashlib import sha256
import importlib.util,json
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
spec=importlib.util.spec_from_file_location('prior_phase_installer',ROOT/'review/recovery-v73/installation/build_phase_observation_installation_v73.py')
prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
D=json.loads((HERE/'shared_field_cache_derivation_v74.json').read_text())
P=json.loads((ROOT/'review/recovery-v74/shared-read-profile/shared_read_profile_derivation_v74.json').read_text())
TARGET='astra_ingestion_v1.backfill_shared_refresh_v2(text,jsonb)'
BASE=(HERE/'baseline_shared_refresh_v74.sql').read_text();CAND=(HERE/'candidate_shared_refresh_field_cache_v74.sql').read_text()
assert sha256(BASE.encode()).hexdigest()==D['baseline_sha256'] and sha256(CAND.encode()).hexdigest()==D['candidate_sha256']
PINS=[x for x in P['source_pins'] if x['signature']!=TARGET];assert len(PINS)==14
CAT=prior.CATALOG_QUERY.replace('astra_ingestion_v1.backfill_maintain_v2(integer)',TARGET)
def js(x,tag):
 t=json.dumps(x,separators=(',',':'));assert '$'+tag+'$' not in t
 return '$'+tag+'$'+t+'$'+tag+'$::jsonb'
def owner(active):
 return """IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2
 WHERE id='fixed3000-20250901-20260731-v1-20261030'__STATUS__ AND fence=1
  AND cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
  AND cohort_manifest_sha256='4134b415e2c26fcde9fced749c0d54ef51376e23f0d2f8c6ce9ef562f9fab99f'
  AND metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
  AND (metadata->>'implementation_lease_until')::timestamptz>clock_timestamp())
 OR (SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2
  WHERE run_id='fixed3000-20250901-20260731-v1-20261030')<>3000 THEN
 RAISE EXCEPTION 'Shared field cache owner, lease, status, fence, cohort or members changed';
 END IF;""".replace('__STATUS__'," AND status='ACTIVE'" if active else '')
CHECK="""FOR v_pin IN SELECT value FROM jsonb_array_elements(v_pins) LOOP
 SELECT pg_get_functiondef(p.oid),CASE WHEN v_pin->>'metadata_kind'='full' THEN to_jsonb(p)-'prosrc'
  ELSE jsonb_build_object('acl',p.proacl,'owner',p.proowner::text,'config',p.proconfig,'security_definer',p.prosecdef) END
 INTO STRICT v_pin_source,v_pin_metadata FROM pg_proc p WHERE p.oid=(v_pin->>'signature')::regprocedure;
 IF encode(sha256(convert_to(v_pin_source,'UTF8')),'hex') IS DISTINCT FROM v_pin->>'sha256'
  OR v_pin_metadata IS DISTINCT FROM v_pin->'metadata' THEN
  RAISE EXCEPTION 'Shared field cache immutable source or metadata pin differs';
 END IF;
 END LOOP;"""
TEMPLATE="""-- PREPARATION ONLY: exact-head publication/CI and root selection precede activation.
-- __OPERATION__ only the shared-refresh function body; no provider/helper call, grant, table or index change.
-- Existing global gate -> run FOR SHARE; strict before/after source, full metadata and catalog checks.
BEGIN;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $shared_field_cache___OPERATION__$
DECLARE
 v_pins constant jsonb := __PINS__;
 v_expected_metadata constant jsonb := __METADATA__;
 v_replacement constant text := $shared_field_replacement$__REPLACEMENT__$shared_field_replacement$;
 v_before text;v_before_metadata jsonb;v_after_metadata jsonb;
 v_pin jsonb;v_pin_source text;v_pin_metadata jsonb;
 v_catalog_before jsonb;v_catalog_after jsonb;
BEGIN
 IF current_setting('statement_timeout')<>'8s' OR current_setting('lock_timeout')<>'3s'
  OR current_setting('transaction_read_only')<>'off' OR current_setting('transaction_isolation')<>'read committed' THEN
  RAISE EXCEPTION 'Shared field cache replacement requires reviewed writable RC 8s/3s bounds';
 END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(706314020261028);
 PERFORM 1 FROM astra_ingestion_v1.backfill_runs_v2
 WHERE id='fixed3000-20250901-20260731-v1-20261030' FOR SHARE;
 __OWNER_CHECK__
 SELECT pg_get_functiondef(p.oid),to_jsonb(p)-'prosrc' INTO STRICT v_before,v_before_metadata
 FROM pg_proc p WHERE p.oid='astra_ingestion_v1.backfill_shared_refresh_v2(text,jsonb)'::regprocedure;
 IF encode(sha256(convert_to(v_before,'UTF8')),'hex')<>'__EXPECTED_HASH__'
  OR v_before_metadata IS DISTINCT FROM v_expected_metadata THEN
  RAISE EXCEPTION 'Shared field cache exact source or metadata differs; reconcile before replay';
 END IF;
 __PINS_CHECK__
 IF encode(sha256(convert_to(v_replacement,'UTF8')),'hex')<>'__AFTER_HASH__' THEN
  RAISE EXCEPTION 'Shared field cache reviewed replacement bytes differ';
 END IF;
 -- SHARED_FIELD_CACHE_BEFORE_CATALOG_SNAPSHOT
 __CATALOG_BEFORE__
 EXECUTE v_replacement;
 -- SHARED_FIELD_CACHE_AFTER_REPLACEMENT
 SELECT to_jsonb(p)-'prosrc' INTO STRICT v_after_metadata FROM pg_proc p
 WHERE p.oid='astra_ingestion_v1.backfill_shared_refresh_v2(text,jsonb)'::regprocedure;
 __CATALOG_AFTER__
 IF v_after_metadata IS DISTINCT FROM v_before_metadata OR v_after_metadata IS DISTINCT FROM v_expected_metadata
  OR v_catalog_after IS DISTINCT FROM v_catalog_before
  OR pg_get_functiondef('astra_ingestion_v1.backfill_shared_refresh_v2(text,jsonb)'::regprocedure) IS DISTINCT FROM v_replacement THEN
  RAISE EXCEPTION 'Shared field cache changed unexpected source, metadata, OID, ACL or catalog';
 END IF;
 __PINS_CHECK__
 __OWNER_CHECK__
END $shared_field_cache___OPERATION__$;
COMMIT;
"""
files=[]
for op,before,after in [('forward',BASE,CAND),('restore',CAND,BASE)]:
 sql=TEMPLATE
 replacements={'__OPERATION__':op,'__PINS__':js(PINS,'shared_pins'),'__METADATA__':js(D['unchanged_metadata'],'shared_metadata'),
  '__REPLACEMENT__':after,'__EXPECTED_HASH__':sha256(before.encode()).hexdigest(),'__AFTER_HASH__':sha256(after.encode()).hexdigest(),
  '__OWNER_CHECK__':owner(op=='forward'),'__PINS_CHECK__':CHECK,
  '__CATALOG_BEFORE__':CAT.replace('@@VARIABLE@@','v_catalog_before'),
  '__CATALOG_AFTER__':CAT.replace('@@VARIABLE@@','v_catalog_after')}
 for old,new in replacements.items():sql=sql.replace(old,new)
 assert '__' not in sql.replace('implementation_owner','').replace('implementation_lease_until','') or not any(k in sql for k in replacements)
 path=HERE/(op+'_shared_field_cache_v74.sql');path.write_text(sql)
 active=ROOT/'sql'/('astra_backfill_shared_field_cache'+('_restore' if op=='restore' else '')+'_v74.sql')
 active.write_text(sql)
 files.append({'operation':op,'path':path.relative_to(ROOT).as_posix(),'active_path':active.relative_to(ROOT).as_posix(),
  'sha256':sha256(sql.encode()).hexdigest(),'bytes':len(sql.encode()),'expected_source_sha256':sha256(before.encode()).hexdigest(),'result_source_sha256':sha256(after.encode()).hexdigest()})
manifest={'schema':'astra.shared-field-cache-migration-preparation/1','state':'PREPARED_NOT_QUALIFIED_OR_SELECTED',
 'target':TARGET,'unchanged_source_metadata_pins':PINS,'target_metadata':D['unchanged_metadata'],'files':files,
 'lock_order':['existing_global_advisory_gate','existing_run_FOR_SHARE'],
 'forward_requires_active':True,'restore_permits_existing_nonactive_status_without_changing_it':True,
 'strict_replay_rejection':True,'source_only_atomic_transaction':True,'catalog_snapshot_excludes_volatile_statistics':True,
 'full_target_metadata_and_all_other_functions_relations_indexes_constraints_triggers_policies_roles_preserved':True,
 'exact_source_pins_rechecked_after_catalog_snapshot_and_replacement':True,'final_owner_lease_fence_cohort_3000_rechecked':True,
 'no_new_privileges_credentials_tables_indexes_operations_settings_or_schedule':True,'production_calls':0}
(HERE/'shared_field_migration_manifest_v74.json').write_text(json.dumps(manifest,indent=2)+'\n')
print(json.dumps({'files':files,'production_calls':0}))
