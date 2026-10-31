"""Build the additive, source-pinned v76 claim cursor replacement and exact restore.

This builder reads only retained e694 inputs and writes local preparation files.
It does not connect to a database, publish, or invoke a runtime helper.
"""
from hashlib import sha256
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
BASE_COMMIT = 'e694009d75f3fd91c69976befa0e12838e64efec'
BASE = '28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44'
AFTER = 'dbe8eb5a563eaf9e8e00678045f8a28da65c8c4b83b4a3295c4eb32c05f50fbf'
TARGET = 'astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'
RUN = 'fixed3000-20250901-20260731-v1-20261030'
OWNER = 'root-replacement-20261030T042603Z'
COHORT = '2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
MANIFEST = '4134b415e2c26fcde9fced749c0d54ef51376e23f0d2f8c6ce9ef562f9fab99f'
ROOT_CAPTURE = 'review/recovery-v74/retry_closure_root_definitions_v74.json'
CALLEE_CAPTURE = 'review/recovery-v74/retry_closure_callees_and_catalog_v74.json'
INPUT_PINS = {
 ROOT_CAPTURE: '2703407b0831de5ee13a96406964a44e8dd54b809b56b47cae1f958c2f976e61',
 CALLEE_CAPTURE: '74d74e5384fbb136ecebecee81583b45dec706ec9668da2fc7645ddfc851420f',
}
INDEX = 'CREATE INDEX backfill_tasks_provider_v2 ON astra_ingestion_v1.backfill_tasks_v2 USING btree (run_id, provider, status, kind)'


def digest(value):
 return sha256(value.encode()).hexdigest()


def compact(value):
 return json.dumps(value, separators=(',', ':'), sort_keys=True)


def sources():
 rows = []
 for path, key in ((ROOT_CAPTURE, 'functions'), (CALLEE_CAPTURE, 'selected_functions')):
  raw = (ROOT / path).read_bytes()
  assert sha256(raw).hexdigest() == INPUT_PINS[path]
  rows.extend(json.loads(raw)[0][key])
 by_name = {row['signature']: row for row in rows}
 baseline = by_name[TARGET]['definition']
 assert digest(baseline) == BASE
 candidate = (HERE / 'candidate_private_claim_cursor_v76.sql').read_text()
 assert digest(candidate) == AFTER
 old = re.search(r'(  FOR v_dependency IN\n)(.*?)(\n  LOOP\n)', baseline, re.S).group(2)
 new = re.search(r'(  FOR v_dependency IN\n)(.*?)(\n  LOOP\n)', candidate, re.S).group(2)
 assert candidate.replace(new, old, 1) == baseline
 pins = [dict(signature=name, sha256=by_name[name]['source_sha256'], metadata=by_name[name]['metadata'])
  for name in ('public.astra_ingestion_rpc_v1(text,jsonb)', 'astra_ingestion_v1.rpc_dispatch(text,jsonb)',
   'astra_ingestion_v1.backfill_identity_discover_pending_v2()',
   'astra_ingestion_v1.backfill_identity_refresh_pending_v2(integer)')]
 # The already-published/installed shared repair is retained, not reverted.
 shared_sql = (ROOT / 'sql/astra_backfill_shared_field_cache_v74.sql').read_text()
 shared_metadata = json.loads(re.search(r'\$shared_metadata\$(.*?)\$shared_metadata\$', shared_sql, re.S).group(1))
 shared = (ROOT / 'review/recovery-v74/shared-field-cache/candidate_shared_refresh_field_cache_v74.sql').read_text()
 assert digest(shared) == '7f538bf47cb5e74050c20266e01cbe9d6521c1a65663aaf2e0fe38d62041f1a4'
 pins.append(dict(signature='astra_ingestion_v1.backfill_shared_refresh_v2(text,jsonb)', sha256=digest(shared), metadata=shared_metadata))
 catalog = json.loads((ROOT / CALLEE_CAPTURE).read_text())[0]['all_function_catalog']
 for name in ('astra_ingestion_v1.backfill_maintain_v2(integer)', 'astra_ingestion_v1.backfill_recheck_page_v2(text,integer)'):
  row = next(r for r in catalog if r['signature'] == name)
  pins.append(dict(signature=name, sha256=row['source_sha256'], oid=row['oid'], metadata_sha256=row['metadata_sha256']))
 return baseline, candidate, by_name[TARGET]['metadata'], pins


CATALOG = """SELECT jsonb_build_object(
 'namespace',(SELECT to_jsonb(n) FROM pg_namespace n WHERE n.oid='astra_ingestion_v1'::regnamespace),
 'functions',(SELECT jsonb_agg(to_jsonb(p) ORDER BY p.oid) FROM pg_proc p
  WHERE (p.pronamespace='astra_ingestion_v1'::regnamespace OR p.oid='public.astra_ingestion_rpc_v1(text,jsonb)'::regprocedure)
   AND p.oid<>'astra_ingestion_v1.backfill_dispatch_v2(text,jsonb)'::regprocedure),
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
) INTO {variable};"""


def owner_check(restore=False):
 status = '' if restore else " AND status='ACTIVE'"
 return f"""IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2
 WHERE id='{RUN}'{status} AND fence=1
  AND cohort_sha256='{COHORT}' AND cohort_manifest_sha256='{MANIFEST}'
  AND metadata->>'implementation_owner'='{OWNER}'
  AND isfinite((metadata->>'implementation_lease_until')::timestamptz)
  AND (metadata->>'implementation_lease_until')::timestamptz>clock_timestamp())
 OR (SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id='{RUN}')<>3000 THEN
 RAISE EXCEPTION 'Claim cursor owner, finite lease, status, fence, cohort or member guard differs';
 END IF;"""


PIN_CHECK = """FOR v_pin IN SELECT value FROM jsonb_array_elements(v_pins) LOOP
 SELECT pg_get_functiondef(p.oid),to_jsonb(p)-'prosrc' INTO STRICT v_pin_source,v_pin_metadata
 FROM pg_proc p WHERE p.oid=(v_pin->>'signature')::regprocedure;
 IF encode(sha256(convert_to(v_pin_source,'UTF8')),'hex') IS DISTINCT FROM v_pin->>'sha256'
  OR (v_pin ? 'metadata' AND v_pin_metadata IS DISTINCT FROM v_pin->'metadata')
  OR (v_pin ? 'metadata_sha256' AND (v_pin_metadata->>'oid' IS DISTINCT FROM v_pin->>'oid'
   OR encode(sha256(convert_to(v_pin_metadata::text,'UTF8')),'hex') IS DISTINCT FROM v_pin->>'metadata_sha256')) THEN
  RAISE EXCEPTION 'Claim cursor immutable source or full metadata differs';
 END IF;
 END LOOP;"""

INDEX_CHECK = f"""IF NOT EXISTS(SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid JOIN pg_am a ON a.oid=c.relam
  WHERE i.indexrelid='astra_ingestion_v1.backfill_tasks_provider_v2'::regclass
   AND i.indrelid='astra_ingestion_v1.backfill_tasks_v2'::regclass AND i.indisvalid AND i.indisready AND i.indislive
   AND a.amname='btree' AND pg_get_indexdef(i.indexrelid)='{INDEX}') THEN
  RAISE EXCEPTION 'Claim cursor required existing provider index differs';
 END IF;"""


def build(restore=False):
 baseline, candidate, metadata, pins = sources()
 before, after, definition = (AFTER, BASE, baseline) if restore else (BASE, AFTER, candidate)
 mode = 'restore' if restore else 'forward'
 return f"""-- v76 claim-provider cursor {mode}: exact one-query source replacement only.
-- Publish this additive repair and pass exact-head CI before root activation.
-- Existing global gate -> run FOR SHARE; 8s/3s bounds; no helper/provider/permission change.
-- Restore accepts any existing status under unchanged authority; it does not reactivate the run.
BEGIN;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $claim_cursor_{mode}$
DECLARE
 v_pins constant jsonb := $claim_pins${compact(pins)}$claim_pins$::jsonb;
 v_expected_metadata constant jsonb := $claim_metadata${compact(metadata)}$claim_metadata$::jsonb;
 v_replacement constant text := $claim_replacement${definition}$claim_replacement$;
 v_before text;v_before_metadata jsonb;v_after_metadata jsonb;
 v_pin jsonb;v_pin_source text;v_pin_metadata jsonb;
 v_catalog_before jsonb;v_catalog_after jsonb;v_run_before jsonb;v_run_after jsonb;
BEGIN
 IF current_setting('statement_timeout')<>'8s' OR current_setting('lock_timeout')<>'3s'
  OR current_setting('transaction_read_only')<>'off' OR current_setting('transaction_isolation')<>'read committed' THEN
  RAISE EXCEPTION 'Claim cursor replacement requires reviewed writable RC 8s/3s bounds';
 END IF;
 PERFORM pg_catalog.pg_advisory_xact_lock(706314020261028);
 PERFORM 1 FROM astra_ingestion_v1.backfill_runs_v2 WHERE id='{RUN}' FOR SHARE;
 {owner_check(restore)}
 SELECT to_jsonb(r) INTO STRICT v_run_before FROM astra_ingestion_v1.backfill_runs_v2 r WHERE id='{RUN}';
 SELECT pg_get_functiondef(p.oid),to_jsonb(p)-'prosrc' INTO STRICT v_before,v_before_metadata
 FROM pg_proc p WHERE p.oid='{TARGET}'::regprocedure;
 IF encode(sha256(convert_to(v_before,'UTF8')),'hex')<>'{before}'
  OR v_before_metadata IS DISTINCT FROM v_expected_metadata THEN
  RAISE EXCEPTION 'Claim cursor exact source or metadata differs; reconcile before replay';
 END IF;
 {PIN_CHECK}
 {INDEX_CHECK}
 IF encode(sha256(convert_to(v_replacement,'UTF8')),'hex')<>'{after}' THEN
  RAISE EXCEPTION 'Claim cursor reviewed replacement bytes differ';
 END IF;
 -- CLAIM_CURSOR_BEFORE_CATALOG_SNAPSHOT
 {CATALOG.format(variable='v_catalog_before')}
 EXECUTE v_replacement;
 -- CLAIM_CURSOR_AFTER_REPLACEMENT
 SELECT to_jsonb(p)-'prosrc' INTO STRICT v_after_metadata FROM pg_proc p WHERE p.oid='{TARGET}'::regprocedure;
 {CATALOG.format(variable='v_catalog_after')}
 IF v_after_metadata IS DISTINCT FROM v_before_metadata OR v_after_metadata IS DISTINCT FROM v_expected_metadata
  OR v_catalog_after IS DISTINCT FROM v_catalog_before
  OR pg_get_functiondef('{TARGET}'::regprocedure) IS DISTINCT FROM v_replacement THEN
  RAISE EXCEPTION 'Claim cursor changed unexpected source, metadata, OID, ACL or catalog';
 END IF;
 {PIN_CHECK}
 {INDEX_CHECK}
 {owner_check(restore)}
 SELECT to_jsonb(r) INTO STRICT v_run_after FROM astra_ingestion_v1.backfill_runs_v2 r WHERE id='{RUN}';
 IF v_run_after IS DISTINCT FROM v_run_before THEN
  RAISE EXCEPTION 'Claim cursor replacement changed the run row';
 END IF;
END $claim_cursor_{mode}$;
COMMIT;
"""


def main():
 baseline, candidate, metadata, pins = sources()
 outputs = {
  ROOT / 'sql/astra_backfill_claim_provider_cursor_v76.sql': build(),
  ROOT / 'sql/astra_backfill_claim_provider_cursor_restore_v76.sql': build(True),
  HERE / 'claim_cursor_guard_pins_v76.json': json.dumps(dict(base_commit=BASE_COMMIT, target=TARGET,
   baseline_sha256=BASE,candidate_sha256=AFTER,target_metadata=metadata,pins=pins), indent=2, sort_keys=True)+'\n',
 }
 for path, text in outputs.items():
  path.parent.mkdir(parents=True, exist_ok=True)
  path.write_text(text)
  print(path.relative_to(ROOT), digest(text), len(text.encode()))


if __name__ == '__main__':
 main()
