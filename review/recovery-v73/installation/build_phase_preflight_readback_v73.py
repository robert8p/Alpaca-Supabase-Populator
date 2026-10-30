"""Generate one read-only catalog/ownership preflight and postchange readback."""
from hashlib import sha256
import importlib.util
import json
from pathlib import Path
import re

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
spec = importlib.util.spec_from_file_location('phase_install_builder', HERE / 'build_phase_observation_installation_v73.py')
b = importlib.util.module_from_spec(spec)
spec.loader.exec_module(b)
manifest = json.loads((HERE / 'installation_manifest_v73.json').read_text())
forward = (ROOT / 'sql/astra_backfill_maintenance_phase_observation_v73.sql').read_text()
assert sha256(forward.encode()).hexdigest() == manifest['artifacts']['forward_maintenance_phase_observation_v73.sql']['sha256']


def constant(tag):
    return json.loads(re.search(r'\$' + tag + r'\$(.*?)\$' + tag + r'\$::jsonb', forward, re.S).group(1))


pins = {}
for signature, digest, full, metadata in re.findall(
        r"\('([^']+)','([0-9a-f]{64})',(true|false),\$pin_metadata\$(.*?)\$pin_metadata\$::jsonb\)", forward, re.S):
    item = {'sha256': digest, 'full_metadata': full == 'true', 'metadata': json.loads(metadata)}
    assert signature not in pins or pins[signature] == item
    pins[signature] = item
assert len(pins) == 13

sql = """-- Read-only/RR preflight or independent readback; no helper, gate, provider or DDL invocation.
-- Named P0001 JSON is the intentional bounded result; the transaction rolls back.
BEGIN;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
DO $phase_preflight_readback$
DECLARE
 v_definition text; v_source_sha256 text; v_metadata jsonb; v_audit jsonb; v_indexes jsonb;
 v_catalog jsonb; v_run jsonb; v_member_count bigint; v_state text; v_report jsonb;
 v_pin_source text; v_pin_metadata jsonb; v_pin_partial jsonb; g record;
 v_expected_metadata constant jsonb := @@METADATA@@;
 v_expected_audit constant jsonb := @@AUDIT@@;
 v_expected_indexes constant jsonb := @@INDEXES@@;
 v_expected_role constant jsonb := @@ROLE@@;
BEGIN
 IF current_setting('statement_timeout')<>'8s' OR current_setting('lock_timeout')<>'3s'
  OR current_setting('transaction_read_only')<>'on' OR current_setting('transaction_isolation')<>'repeatable read' THEN
  RAISE EXCEPTION 'Phase preflight requires read-only repeatable-read 8s/3s bounds';
 END IF;
 SELECT pg_get_functiondef(p.oid),to_jsonb(p)-'prosrc' INTO STRICT v_definition,v_metadata
  FROM pg_proc p WHERE p.oid='astra_ingestion_v1.backfill_maintain_v2(integer)'::regprocedure;
 v_source_sha256:=encode(sha256(convert_to(v_definition,'UTF8')),'hex');
 IF v_source_sha256 NOT IN (@@BASELINE@@,@@CANDIDATE@@) OR v_metadata IS DISTINCT FROM v_expected_metadata THEN
  RAISE EXCEPTION 'Phase preflight maintenance source or exact metadata differs';
 END IF;
 IF (SELECT jsonb_build_object('oid',r.oid::text,'rolname',r.rolname,'rolsuper',r.rolsuper,
  'rolcanlogin',r.rolcanlogin,'rolbypassrls',r.rolbypassrls) FROM pg_roles r
  WHERE r.oid=(v_expected_metadata->>'proowner')::oid) IS DISTINCT FROM v_expected_role THEN
  RAISE EXCEPTION 'Phase preflight maintenance owner role differs';
 END IF;
 @@PINS@@
 @@AUDIT_QUERY@@
 @@INDEX_QUERY@@
 IF v_audit IS DISTINCT FROM v_expected_audit OR v_indexes IS DISTINCT FROM v_expected_indexes THEN
  RAISE EXCEPTION 'Phase preflight exact audit permissions/catalog or installed hash pair differs';
 END IF;
 SELECT jsonb_build_object('id',id,'status',status,'fence',fence,'cohort_sha256',cohort_sha256,
  'owner',metadata->>'implementation_owner','lease_until',metadata->>'implementation_lease_until')
  INTO STRICT v_run FROM astra_ingestion_v1.backfill_runs_v2 WHERE id=@@RUN@@;
 SELECT count(*) INTO v_member_count FROM astra_ingestion_v1.backfill_members_v2 WHERE run_id=@@RUN@@;
 IF v_run->>'owner' IS DISTINCT FROM @@OWNER@@
  OR COALESCE((v_run->>'lease_until')::timestamptz>clock_timestamp(),false) IS NOT TRUE
  OR (v_run->>'fence')::bigint IS DISTINCT FROM 1
  OR v_run->>'cohort_sha256' IS DISTINCT FROM @@COHORT@@ OR v_member_count<>3000 THEN
  RAISE EXCEPTION 'Phase preflight run owner, unexpired lease, fence, cohort or 3000 members differs';
 END IF;
 @@CATALOG_QUERY@@
 v_state:=CASE WHEN v_source_sha256=@@BASELINE@@ THEN 'INSTALLED_BASELINE_6C880' ELSE 'OBSERVATION_CANDIDATE_12E05' END;
 v_report:=jsonb_build_object(
  'schema','astra.maintenance-phase-preflight-readback/1','observed_at',clock_timestamp(),
  'complete',true,'source_state',v_state,'maintain_sha256',v_source_sha256,'maintain_oid',v_metadata->>'oid',
  'unchanged_function_pins_verified',@@PIN_MAP@@,'unchanged_function_count',13,
  'all_metadata_permission_index_guards_match',true,
  'maintain_metadata_sha256',encode(sha256(convert_to(v_metadata::text,'UTF8')),'hex'),
  'audit_catalog_sha256',encode(sha256(convert_to(v_audit::text,'UTF8')),'hex'),
  'hash_index_catalog_sha256',encode(sha256(convert_to(v_indexes::text,'UTF8')),'hex'),
  'other_schema_catalog_sha256',encode(sha256(convert_to(v_catalog::text,'UTF8')),'hex'),
  'run',v_run,'member_count',v_member_count,'observation_deadline',@@DEADLINE@@,
  'observation_window_open',clock_timestamp()<@@DEADLINE@@::timestamptz,
  'install_ready',v_source_sha256=@@BASELINE@@ AND v_run->>'status'='ACTIVE' AND clock_timestamp()<@@DEADLINE@@::timestamptz,
  'restore_ready',v_source_sha256=@@CANDIDATE@@,
  'transaction_read_only',current_setting('transaction_read_only'),
  'transaction_isolation',current_setting('transaction_isolation'),
  'statement_timeout',current_setting('statement_timeout'),'lock_timeout',current_setting('lock_timeout'),
  'interpretation','Snapshot catalog/ownership check only; no execution, elapsed-phase, recovery or coverage proof.');
 IF octet_length(v_report::text)>12000 THEN RAISE EXCEPTION 'Phase preflight result exceeded bounded output'; END IF;
 RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='MAINTENANCE_PHASE_PREFLIGHT_READBACK_V73 '||v_report::text;
END $phase_preflight_readback$;
ROLLBACK;
"""
substitutions = {
    'METADATA': b.json_sql(constant('maintain_metadata'),'maintain_metadata'),
    'AUDIT': b.json_sql(constant('audit_metadata'),'audit_metadata'),
    'INDEXES': b.json_sql(constant('index_metadata'),'index_metadata'),
    'ROLE': b.json_sql(constant('owner_metadata'),'owner_metadata'),
    'BASELINE': b.quote(manifest['baseline_sha256']), 'CANDIDATE': b.quote(manifest['candidate_sha256']),
    'PINS': b.pin_check(pins), 'RUN': b.quote(b.RUN), 'OWNER': b.quote(b.OWNER),
    'COHORT': b.quote(b.COHORT), 'DEADLINE': b.quote(b.DEADLINE),
    'PIN_MAP': b.json_sql({k:v['sha256'] for k,v in pins.items()},'verified_pin_map'),
    'AUDIT_QUERY': b.AUDIT_QUERY.replace('@@VARIABLE@@','v_audit'),
    'INDEX_QUERY': b.INDEX_QUERY.replace('@@VARIABLE@@','v_indexes'),
    'CATALOG_QUERY': b.CATALOG_QUERY.replace('@@VARIABLE@@','v_catalog'),
}
for key, value in substitutions.items(): sql=sql.replace('@@'+key+'@@', value)
assert '@@' not in sql
assert 'pg_advisory_xact_lock(' not in sql and 'FOR SHARE' not in sql
assert not re.search(r'(?im)^\s*(GRANT|REVOKE|INSERT|UPDATE|DELETE|CREATE|ALTER|DROP|EXECUTE|PERFORM)\b', sql)
path=HERE/'maintenance_phase_preflight_readback_readonly_v73.sql'
path.write_text(sql)
receipt={'schema':'astra.maintenance-phase-readonly-derivation/1','status':'PREPARED_LOCAL_ONLY',
 'sql_sha256':sha256(sql.encode()).hexdigest(),'sql_bytes':len(sql.encode()),
 'baseline_sha256':manifest['baseline_sha256'],'candidate_sha256':manifest['candidate_sha256'],
 'unchanged_function_pins':{k:v['sha256'] for k,v in pins.items()},
 'source_installation_manifest_sha256':sha256((HERE/'installation_manifest_v73.json').read_bytes()).hexdigest(),
 'output_bound_bytes':12000,'intentional_result_prefix':'MAINTENANCE_PHASE_PREFLIGHT_READBACK_V73 ',
 'read_only':True,'isolation':'repeatable read','statement_timeout':'8s','lock_timeout':'3s',
 'explicit_gate_or_row_lock':False,'helper_or_provider_invocation':False,'DDL_or_DML':False,'production_calls':0,
 'interpretation':'Compare other-schema/audit/index fingerprints across the separately guarded install or restore; this is not timing/recovery proof.'}
out=HERE/'preflight_readback_derivation_v73.json';out.write_text(json.dumps(receipt,indent=2)+'\n')
print(json.dumps({'sql':str(path),'sha256':receipt['sql_sha256'],'bytes':receipt['sql_bytes'],
                  'derivation_sha256':sha256(out.read_bytes()).hexdigest()}))
