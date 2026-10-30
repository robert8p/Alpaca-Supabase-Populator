"""Prepare exact-source install/restore SQL. Never connect to a database or activate it.

The candidate hash is an explicit build input because the producer owns its review
and qualification. Generated SQL remains subject to independent review, publication,
exact-published-head CI, and root's separate bounded installation/readback.
"""
from __future__ import annotations

import argparse
from hashlib import sha256
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
BASE_SHA = "6c880114a645c8a9167d5260c4aeabf58a10617c4244cf0340be1d6cf4bf0ce7"
BASE_PATH = "review/recovery-v72/readback-transaction-race/candidate_maintain_readback_transaction_v72.sql"
INVENTORY_PATH = "review/recovery-v73/live_phase_observation_permission_inventory_v73.json"
HELPERS_PATH = "review/recovery-v71/live_maintenance_helpers_1335.json"
READBACK_PATH = "review/recovery-v72/readback_transaction_race_installation_readback_v72.json"
INSTALLATION_PATH = "evidence/replacement-maintenance-combined-live-installation-v72.json"
RUN = "fixed3000-20250901-20260731-v1-20261030"
OWNER = "root-replacement-20261030T042603Z"
COHORT = "2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec"
DEADLINE = "2026-10-30 15:45:00+00"


def read_json(path: str):
    return json.loads((ROOT / path).read_text())


def digest(value: str | bytes) -> str:
    return sha256(value.encode() if isinstance(value, str) else value).hexdigest()


def quote(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def json_sql(value, tag: str) -> str:
    text = json.dumps(value, sort_keys=True, separators=(",", ":"))
    assert f"${tag}$" not in text
    return f"${tag}$" + text + f"${tag}$::jsonb"


# Omit volatile statistics and physical sizes; preserve every schema function,
# index definition/catalog row, owner/ACL/RLS field, constraint, trigger and policy.
CATALOG_QUERY = """SELECT jsonb_build_object(
 'namespace',(SELECT to_jsonb(n) FROM pg_namespace n WHERE n.oid='astra_ingestion_v1'::regnamespace),
 'functions',(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.oid) FROM pg_proc p
  WHERE p.pronamespace='astra_ingestion_v1'::regnamespace
   AND p.oid<>'astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure),
 'relations',(SELECT jsonb_agg(jsonb_build_object('oid',c.oid::text,'name',c.relname,
  'namespace',c.relnamespace::text,'kind',c.relkind,'owner',c.relowner::text,'acl',c.relacl,
  'rls',c.relrowsecurity,'force_rls',c.relforcerowsecurity,'method',c.relam::text,'options',c.reloptions)
  ORDER BY c.oid) FROM pg_class c WHERE c.relnamespace='astra_ingestion_v1'::regnamespace),
 'indexes',(SELECT jsonb_agg(jsonb_build_object('catalog',to_jsonb(i),'definition',pg_get_indexdef(i.indexrelid))
  ORDER BY i.indexrelid) FROM pg_index i JOIN pg_class c ON c.oid=i.indrelid
  WHERE c.relnamespace='astra_ingestion_v1'::regnamespace),
 'constraints',(SELECT jsonb_agg(to_jsonb(c) ORDER BY c.oid) FROM pg_constraint c
  WHERE c.connamespace='astra_ingestion_v1'::regnamespace),
 'triggers',(SELECT jsonb_agg(to_jsonb(t) ORDER BY t.oid) FROM pg_trigger t JOIN pg_class c ON c.oid=t.tgrelid
  WHERE c.relnamespace='astra_ingestion_v1'::regnamespace),
 'policies',(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.oid) FROM pg_policy p JOIN pg_class c ON c.oid=p.polrelid
  WHERE c.relnamespace='astra_ingestion_v1'::regnamespace),
 'roles',(SELECT jsonb_agg(to_jsonb(r) ORDER BY r.oid) FROM pg_roles r
  WHERE r.rolname IN ('astra_ingestion_rpc_owner_v1','astra_ingestion_monitor_owner_v1')),
 'role_memberships',(SELECT jsonb_agg(to_jsonb(m) ORDER BY m.roleid,m.member,m.grantor) FROM pg_auth_members m
  WHERE m.roleid IN (SELECT oid FROM pg_roles WHERE rolname IN ('astra_ingestion_rpc_owner_v1','astra_ingestion_monitor_owner_v1'))
   OR m.member IN (SELECT oid FROM pg_roles WHERE rolname IN ('astra_ingestion_rpc_owner_v1','astra_ingestion_monitor_owner_v1')))
) INTO @@VARIABLE@@;"""


AUDIT_QUERY = """SELECT jsonb_build_object(
 'audit_table',(SELECT jsonb_build_object('acl',c.relacl,'oid',c.oid::text,'rls',c.relrowsecurity,
  'owner',c.relowner::text,'force_rls',c.relforcerowsecurity) FROM pg_class c
  WHERE c.oid='astra_ingestion_v1.backfill_audit_v2'::regclass),
 'audit_sequence',(SELECT jsonb_build_object('acl',c.relacl,'oid',c.oid::text,
  'name','astra_ingestion_v1.backfill_audit_v2_id_seq','owner',c.relowner::text) FROM pg_class c
  WHERE c.oid='astra_ingestion_v1.backfill_audit_v2_id_seq'::regclass),
 'existing_maintain_owner_privileges',jsonb_build_object(
  'run_select',has_table_privilege('astra_ingestion_rpc_owner_v1','astra_ingestion_v1.backfill_runs_v2','SELECT'),
  'run_update',has_table_privilege('astra_ingestion_rpc_owner_v1','astra_ingestion_v1.backfill_runs_v2','UPDATE'),
  'audit_delete',has_table_privilege('astra_ingestion_rpc_owner_v1','astra_ingestion_v1.backfill_audit_v2','DELETE'),
  'audit_insert',has_table_privilege('astra_ingestion_rpc_owner_v1','astra_ingestion_v1.backfill_audit_v2','INSERT'),
  'audit_select',has_table_privilege('astra_ingestion_rpc_owner_v1','astra_ingestion_v1.backfill_audit_v2','SELECT'),
  'audit_update',has_table_privilege('astra_ingestion_rpc_owner_v1','astra_ingestion_v1.backfill_audit_v2','UPDATE'),
  'sequence_usage',has_sequence_privilege('astra_ingestion_rpc_owner_v1','astra_ingestion_v1.backfill_audit_v2_id_seq','USAGE'),
  'sequence_update',has_sequence_privilege('astra_ingestion_rpc_owner_v1','astra_ingestion_v1.backfill_audit_v2_id_seq','UPDATE')),
 'constraints',(SELECT jsonb_agg(jsonb_build_object('name',c.conname,'type',c.contype,'definition',pg_get_constraintdef(c.oid))
  ORDER BY c.conname) FROM pg_constraint c WHERE c.conrelid='astra_ingestion_v1.backfill_audit_v2'::regclass),
 'triggers',(SELECT jsonb_agg(jsonb_build_object('name',t.tgname,'enabled',t.tgenabled,
  'function',t.tgfoid::regprocedure::text,'internal',t.tgisinternal,'definition',pg_get_triggerdef(t.oid))
  ORDER BY t.tgname) FROM pg_trigger t WHERE t.tgrelid='astra_ingestion_v1.backfill_audit_v2'::regclass),
 'policies',(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.polname) FROM pg_policy p
  WHERE p.polrelid='astra_ingestion_v1.backfill_audit_v2'::regclass),
 'standard_roles',(SELECT jsonb_object_agg(r,jsonb_build_object(
  'audit_insert',has_table_privilege(r,'astra_ingestion_v1.backfill_audit_v2','INSERT'),
  'audit_select',has_table_privilege(r,'astra_ingestion_v1.backfill_audit_v2','SELECT'),
  'monitor_execute',has_function_privilege(r,'astra_ingestion_v1.monitor_tick_v1()','EXECUTE'),
  'maintain_execute',has_function_privilege(r,'astra_ingestion_v1.backfill_maintain_v2(integer)','EXECUTE')))
  FROM unnest(ARRAY['anon','authenticated','service_role']::text[]) AS r)
) INTO @@VARIABLE@@;"""


INDEX_QUERY = """SELECT jsonb_agg(jsonb_build_object('acl',c.relacl,'oid',c.oid::text,
 'live',i.indislive,'name',c.relname,'owner',c.relowner::text,'ready',i.indisready,'valid',i.indisvalid,
 'method',a.amname,'definition',pg_get_indexdef(i.indexrelid)) ORDER BY c.relname)
 INTO @@VARIABLE@@ FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_am a ON a.oid=c.relam
 WHERE i.indrelid='astra_ingestion_v1.backfill_tasks_v2'::regclass
  AND c.relname IN ('backfill_tasks_breadth_pending_id_v2','backfill_tasks_minute_pending_id_v2');"""


def owner_check(*, lock: bool, require_active: bool) -> str:
    status_clause = " AND status='ACTIVE'" if require_active else ""
    predicate = f"""id={quote(RUN)}{status_clause} AND fence=1
  AND cohort_sha256={quote(COHORT)}
  AND metadata->>'implementation_owner'={quote(OWNER)}
  AND (metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()"""
    if lock:
        check = f"""PERFORM 1 FROM astra_ingestion_v1.backfill_runs_v2 WHERE {predicate} FOR SHARE;
 IF NOT FOUND THEN RAISE EXCEPTION 'Phase observation owner, lease, status, fence or cohort differs'; END IF;"""
    else:
        check = f"""IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2 WHERE {predicate}) THEN
  RAISE EXCEPTION 'Phase observation owner, lease, status, fence or cohort changed before completion';
 END IF;"""
    return check + f"""
 IF (SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id={quote(RUN)})<>3000 THEN
  RAISE EXCEPTION 'Phase observation requires the exact 3000-member cohort';
 END IF;"""


def pin_check(pins: dict) -> str:
    rows = []
    for signature, info in sorted(pins.items()):
        rows.append("  (" + quote(signature) + "," + quote(info['sha256']) + "," +
                    ("true" if info['full_metadata'] else "false") + "," +
                    json_sql(info['metadata'], "pin_metadata") + ")")
    return """FOR g IN SELECT * FROM (VALUES
""" + ",\n".join(rows) + """
 ) pinned(signature,expected_sha256,full_metadata,metadata) LOOP
  SELECT pg_get_functiondef(p.oid),to_jsonb(p)-'prosrc',
   jsonb_build_object('acl',p.proacl,'owner',p.proowner::text,'config',p.proconfig,'security_definer',p.prosecdef)
   INTO STRICT v_pin_source,v_pin_metadata,v_pin_partial FROM pg_proc p WHERE p.oid=g.signature::regprocedure;
  IF encode(sha256(convert_to(v_pin_source,'UTF8')),'hex')<>g.expected_sha256
   OR (CASE WHEN g.full_metadata THEN v_pin_metadata ELSE v_pin_partial END) IS DISTINCT FROM g.metadata THEN
   RAISE EXCEPTION 'Phase observation pinned helper, verifier, dispatch or monitor source/metadata differs';
  END IF;
 END LOOP;"""


def render(*, operation: str, expected_source_hash: str, replacement: str,
           metadata: dict, audit: dict, indexes: list, pins: dict, role: dict) -> str:
    assert operation in ('install', 'restore')
    assert '$phase_replacement$' not in replacement
    deadline = (f"IF clock_timestamp()>={quote(DEADLINE)}::timestamptz THEN\n"
                "  RAISE EXCEPTION 'Phase observation fixed installation window expired';\n END IF;"
                if operation == 'install' else
                "-- Restore remains admissible after the observation deadline, under a still-valid same-owner lease.")
    target_hash = digest(replacement)
    code = """-- LOCAL PREPARATION ONLY: independent review, publication and exact-head CI precede activation.
-- @@OPERATION@@ only backfill_maintain_v2; no helper/provider invocation or grant/configuration change.
-- Source, full maintenance metadata, 13 unchanged function pins, audit permissions,
-- the installed hash pair and all other schema catalogs are checked before/after.
BEGIN;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $phase_observation_@@OPERATION@@$
DECLARE
 v_before text; v_before_metadata jsonb; v_after_metadata jsonb;
 v_catalog_before jsonb; v_catalog_after jsonb;
 v_audit_before jsonb; v_audit_after jsonb; v_indexes_before jsonb; v_indexes_after jsonb;
 v_pin_source text; v_pin_metadata jsonb; v_pin_partial jsonb; g record;
 v_expected_metadata constant jsonb := @@METADATA@@;
 v_expected_audit constant jsonb := @@AUDIT@@;
 v_expected_indexes constant jsonb := @@INDEXES@@;
 v_expected_role constant jsonb := @@ROLE@@;
 v_replacement constant text := $phase_replacement$@@REPLACEMENT@@$phase_replacement$;
BEGIN
 IF current_setting('statement_timeout')<>'8s' OR current_setting('lock_timeout')<>'3s'
  OR current_setting('transaction_read_only')<>'off' OR current_setting('transaction_isolation')<>'read committed' THEN
  RAISE EXCEPTION 'Phase observation replacement requires reviewed writable RC 8s/3s transaction bounds';
 END IF;
 @@DEADLINE@@
 PERFORM pg_catalog.pg_advisory_xact_lock(706314020261028);
 @@OWNER_BEFORE@@
 SELECT pg_get_functiondef(p.oid),to_jsonb(p)-'prosrc' INTO STRICT v_before,v_before_metadata
  FROM pg_proc p WHERE p.oid='astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure;
 IF encode(sha256(convert_to(v_before,'UTF8')),'hex')<>@@EXPECTED_HASH@@
  OR v_before_metadata IS DISTINCT FROM v_expected_metadata THEN
  RAISE EXCEPTION 'Phase observation exact maintenance source/metadata differs; reconcile before replay';
 END IF;
 IF (SELECT jsonb_build_object('oid',r.oid::text,'rolname',r.rolname,'rolsuper',r.rolsuper,
  'rolcanlogin',r.rolcanlogin,'rolbypassrls',r.rolbypassrls) FROM pg_roles r
  WHERE r.oid=(v_expected_metadata->>'proowner')::oid) IS DISTINCT FROM v_expected_role THEN
  RAISE EXCEPTION 'Phase observation maintenance owner role differs';
 END IF;
 @@PINS@@
 @@AUDIT_BEFORE@@
 @@INDEXES_BEFORE@@
 IF v_audit_before IS DISTINCT FROM v_expected_audit OR v_indexes_before IS DISTINCT FROM v_expected_indexes THEN
  RAISE EXCEPTION 'Phase observation audit privileges/catalog or exact installed hash pair differs';
 END IF;
 IF encode(sha256(convert_to(v_replacement,'UTF8')),'hex')<>@@TARGET_HASH@@ THEN
  RAISE EXCEPTION 'Phase observation replacement bytes do not match reviewed source';
 END IF;
 @@CATALOG_BEFORE@@
 -- INSTALLATION_TEST_BOUNDARY: all mutations below remain inside this atomic DO.
 EXECUTE v_replacement;
 SELECT to_jsonb(p)-'prosrc' INTO STRICT v_after_metadata FROM pg_proc p
  WHERE p.oid='astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure;
 @@CATALOG_AFTER@@
 @@AUDIT_AFTER@@
 @@INDEXES_AFTER@@
 IF v_after_metadata IS DISTINCT FROM v_before_metadata OR v_after_metadata IS DISTINCT FROM v_expected_metadata
  OR v_catalog_after IS DISTINCT FROM v_catalog_before OR v_audit_after IS DISTINCT FROM v_expected_audit
  OR v_indexes_after IS DISTINCT FROM v_expected_indexes
  OR pg_get_functiondef('astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure) IS DISTINCT FROM v_replacement THEN
  RAISE EXCEPTION 'Phase observation changed unexpected source, OID, metadata, permissions or schema catalog';
 END IF;
 -- Fixed pins are repeated after the preservation snapshot and replacement.
 @@PINS@@
 @@OWNER_AFTER@@
 @@DEADLINE@@
END $phase_observation_@@OPERATION@@$;
COMMIT;
"""
    substitutions = {
        'OPERATION': operation, 'METADATA': json_sql(metadata, 'maintain_metadata'),
        'AUDIT': json_sql(audit, 'audit_metadata'), 'INDEXES': json_sql(indexes, 'index_metadata'),
        'ROLE': json_sql(role, 'owner_metadata'), 'REPLACEMENT': replacement,
        'EXPECTED_HASH': quote(expected_source_hash), 'TARGET_HASH': quote(target_hash),
        'DEADLINE': deadline, 'OWNER_BEFORE': owner_check(lock=True, require_active=operation == 'install'),
        'OWNER_AFTER': owner_check(lock=False, require_active=operation == 'install'),
        'PINS': pin_check(pins),
    }
    for name, query in [('CATALOG', CATALOG_QUERY), ('AUDIT', AUDIT_QUERY), ('INDEXES', INDEX_QUERY)]:
        for phase in ['BEFORE', 'AFTER']:
            substitutions[f'{name}_{phase}'] = query.replace('@@VARIABLE@@', f'v_{name.lower()}_{phase.lower()}')
    for name, value in substitutions.items():
        code = code.replace(f'@@{name}@@', value)
    assert not re.search(r'@@[A-Z_]+@@', code)
    return code


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--candidate-sha256', required=True)
    parser.add_argument('--write-active-paths', action='store_true')
    args = parser.parse_args()
    candidate_path = args.candidate.resolve()
    candidate = candidate_path.read_text()
    assert re.fullmatch(r'[0-9a-f]{64}', args.candidate_sha256)
    assert digest(candidate) == args.candidate_sha256, 'Explicit candidate pin differs'
    baseline = (ROOT / BASE_PATH).read_text()
    assert digest(baseline) == BASE_SHA
    # Only the producer's marked observation additions may differ from installed source.
    stripped = re.sub(r'^ -- PHASE_OBSERVATION_V73_BEGIN[^\n]*\n.*?^ -- PHASE_OBSERVATION_V73_END[^\n]*\n',
                      '', candidate, flags=re.MULTILINE | re.DOTALL)
    assert stripped == baseline, 'Candidate does not reverse exactly to installed 6c880 source'
    inventory = read_json(INVENTORY_PATH)[0]
    assert inventory['maintain']['source_sha256'] == BASE_SHA
    observed = inventory['maintain']['metadata']
    role_keys = ['rolname', 'rolsuper', 'rolcanlogin', 'rolbypassrls']
    metadata = {k: v for k, v in observed.items() if k not in role_keys}
    role = {'oid': metadata['proowner'], **{k: observed[k] for k in role_keys}}
    assert not role['rolsuper'] and not role['rolcanlogin'] and not role['rolbypassrls']
    audit = {k: inventory[k] for k in ['audit_table','audit_sequence','existing_maintain_owner_privileges',
                                      'constraints','triggers','policies','standard_roles']}
    pins = {}
    for item in read_json(HELPERS_PATH)[0]['evidence']['definitions']:
        argtypes = ','.join(arg.split(' ', 1)[1].strip() for arg in item['args'].split(', ') if arg)
        signature = 'astra_ingestion_v1.' + item['proname'] + '(' + argtypes + ')'
        pins[signature] = {'sha256': item['sha256'], 'full_metadata': False, 'metadata': item['metadata']}
    readback = read_json(READBACK_PATH)['verified']['readback']
    for signature, info in readback['functions'].items():
        if signature == 'astra_ingestion_v1.backfill_maintain_v2(integer)':
            assert info['source_sha256'] == BASE_SHA and info['metadata'] == metadata
            continue
        if signature in pins:
            assert pins[signature]['sha256'] == info['source_sha256']
        pins[signature] = {'sha256': info['source_sha256'], 'full_metadata': True, 'metadata': info['metadata']}
    assert len(pins) == 13
    indexes = sorted([{k: v for k, v in item.items() if k != 'bytes'}
                       for item in read_json(INSTALLATION_PATH)['final_indexes']], key=lambda x: x['name'])
    assert len(indexes) == 2 and all(x['method'] == 'hash' and x['valid'] and x['ready'] and x['live'] for x in indexes)
    outputs = {
        'forward_maintenance_phase_observation_v73.sql': render(operation='install', expected_source_hash=BASE_SHA,
             replacement=candidate, metadata=metadata, audit=audit, indexes=indexes, pins=pins, role=role),
        'restore_maintenance_phase_observation_v73.sql': render(operation='restore', expected_source_hash=args.candidate_sha256,
             replacement=baseline, metadata=metadata, audit=audit, indexes=indexes, pins=pins, role=role),
    }
    for name, text in outputs.items():
        (HERE / name).write_text(text)
    active_paths = {
        'forward_maintenance_phase_observation_v73.sql': 'sql/astra_backfill_maintenance_phase_observation_v73.sql',
        'restore_maintenance_phase_observation_v73.sql': 'sql/astra_backfill_maintenance_phase_observation_restore_v73.sql',
    }
    if args.write_active_paths:
        for name, active in active_paths.items():
            (ROOT / active).write_text(outputs[name])
    inputs = [BASE_PATH, INVENTORY_PATH, HELPERS_PATH, READBACK_PATH, INSTALLATION_PATH, str(candidate_path.relative_to(ROOT))]
    manifest = {
        'schema': 'astra.maintenance-phase-observation-installation/1',
        'status': 'LOCAL_PREPARATION_ONLY_PENDING_REVIEW_QUALIFICATION_PUBLICATION_EXACT_HEAD_CI',
        'base_commit': '1f1f423e4dd1db87eff92e8687b2d9c49ba63c01',
        'baseline_sha256': BASE_SHA, 'candidate_sha256': args.candidate_sha256,
        'exact_candidate_reverse_to_baseline': True, 'observation_deadline_utc': DEADLINE,
        'restore_allowed_after_observation_deadline': True,
        'restore_requires_same_unexpired_owner_lease': True,
        'installation_status_policy': 'ACTIVE_ONLY',
        'restore_status_policy': 'ANY_EXISTING_STATUS_WITH_ALL_OTHER_EXACT_GUARDS; NO_STATUS_OR_DATA_CHANGE',
        'run_id': RUN, 'owner': OWNER, 'fence': 1, 'cohort_sha256': COHORT, 'member_count': 3000,
        'statement_timeout': '8s', 'lock_timeout': '3s', 'installation_isolation': 'read committed',
        'lock_order': ['existing_global_advisory_gate', 'fixed_run_FOR_SHARE'],
        'unchanged_function_pins': {k: v['sha256'] for k, v in pins.items()},
        'expected_maintain_metadata': metadata, 'expected_audit_permissions_catalog': audit,
        'expected_hash_indexes': indexes,
        'preserved': ['maintenance OID and complete pg_proc metadata', 'all other schema functions',
                      'all schema index catalogs and definitions', 'schema/table/sequence owners ACLs RLS',
                      'constraints triggers policies and maintenance-owner role membership',
                      'all application rows and audit records; no helper invoked'],
        'inputs': {p: {'sha256': digest((ROOT / p).read_bytes()), 'bytes': (ROOT / p).stat().st_size} for p in inputs},
        'artifacts': {name: {'sha256': digest(text), 'bytes': len(text.encode())} for name, text in outputs.items()},
        'active_paths': {active: {'sha256': digest(outputs[name]), 'bytes': len(outputs[name].encode()),
                                 'written_by_this_build': args.write_active_paths} for name, active in active_paths.items()},
        'production_calls': 0, 'activation_selected': False, 'qualification': 'PENDING',
    }
    path = HERE / 'installation_manifest_v73.json'
    path.write_text(json.dumps(manifest, indent=2) + '\n')
    print(json.dumps({'manifest_sha256': digest(path.read_bytes()), 'artifacts': manifest['artifacts']}))


if __name__ == '__main__':
    main()
