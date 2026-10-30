"""Derive two exact original selector reads for the fully installed v72 state."""
from hashlib import sha256
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
SOURCE = ROOT / 'review/recovery-v71/live_maintenance_helpers_1335.json'
helpers = {x['proname']: x for x in json.loads(SOURCE.read_text())[0]['evidence']['definitions']}
specs = [
    ('BREADTH_PENDING', 'backfill_breadth_project_pending_v2', ' FOR p IN '),
    ('MINUTE_ACCOUNT_PENDING', 'backfill_minute_account_pending_v2', ' FOR x IN '),
]
queries = []
for component, name, marker in specs:
    source = helpers[name]['definition']
    assert sha256(source.encode()).hexdigest() == helpers[name]['sha256']
    start = source.index(marker) + len(marker)
    end = source.index('\n LOOP', start)
    original = source[start:end].strip()
    assert original.startswith('SELECT ') and original.count('p_limit') == 1
    query = original.replace('p_limit', '2')
    assert query.replace('LEAST(2,8)', 'LEAST(p_limit,8)') == original
    queries.append((component, query))

pins = {
    'backfill_dispatch_v2(text,jsonb)': '28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44',
    'rpc_dispatch(text,jsonb)': 'a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520',
    'backfill_maintain_v2(integer)': '6c880114a645c8a9167d5260c4aeabf58a10617c4244cf0340be1d6cf4bf0ce7',
    'backfill_breadth_project_pending_v2(integer)': helpers['backfill_breadth_project_pending_v2']['sha256'],
    'backfill_minute_account_pending_v2(integer)': helpers['backfill_minute_account_pending_v2']['sha256'],
}
indexes = json.loads((HERE / 'maintenance_index_forward_derivation_v72.json').read_text())['expected_index_definitions']
pin_rows = ',\n'.join("  ('astra_ingestion_v1.%s','%s')" % x for x in pins.items())
index_rows = ',\n'.join("  ('%s',$definition$%s$definition$)" % x for x in indexes.items())
query_rows = ',\n'.join("  ('%s',$query$%s$query$)" % x for x in queries)
sql = """-- Read-only post-install profile of two exact original maintenance selectors.
-- Requires both reviewed hash indexes and the one-predicate maintain6c880 state.
-- Only the installed p_limit=2 is substituted; selector semantics are unchanged.
-- Direct read plans depend on current state/cache and do not prove cron latency.
-- No helper, provider, verifier, finalizer, gate or data mutation is invoked.
-- Named P0001 carries bounded plan evidence and intentionally aborts the wrapper.
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL transaction_read_only=on;
SET LOCAL transaction_isolation='repeatable read';
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $postinstall_profile$
DECLARE
 source_guard record;
 index_guard record;
 selector record;
 task_table oid;
 task_owner oid;
 index_oid oid;
 plan jsonb;
 results jsonb:='[]';
 started timestamptz:=clock_timestamp();
BEGIN
 IF current_setting('transaction_read_only')<>'on'
  OR current_setting('transaction_isolation')<>'repeatable read'
  OR current_setting('statement_timeout')<>'8s'
  OR current_setting('lock_timeout')<>'3s' THEN
  RAISE EXCEPTION 'Post-install selector profile requires explicit bounded read-only repeatable-read settings';
 END IF;
 FOR source_guard IN SELECT * FROM (VALUES
__PIN_ROWS__
 ) s(signature,expected_sha256) LOOP
  IF encode(sha256(convert_to(pg_get_functiondef(source_guard.signature::regprocedure),'UTF8')),'hex')<>source_guard.expected_sha256 THEN
   RAISE EXCEPTION 'Post-install selector source changed or final repair state is absent';
  END IF;
 END LOOP;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2
  WHERE id='fixed3000-20250901-20260731-v1-20261030' AND status='ACTIVE' AND fence=1
   AND cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
   AND metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
   AND (metadata->>'implementation_lease_until')::timestamptz>clock_timestamp())
  OR (SELECT count(*) FROM astra_ingestion_v1.backfill_members_v2
   WHERE run_id='fixed3000-20250901-20260731-v1-20261030')<>3000 THEN
  RAISE EXCEPTION 'Post-install selector run, owner, lease, fence or fixed cohort changed';
 END IF;
 task_table:='astra_ingestion_v1.backfill_tasks_v2'::regclass;
 SELECT relowner INTO STRICT task_owner FROM pg_class
  WHERE oid=task_table AND relkind='r' AND relpersistence='p';
 FOR index_guard IN SELECT * FROM (VALUES
__INDEX_ROWS__
 ) d(index_name,expected_definition) LOOP
  index_oid:=to_regclass(format('%I.%I','astra_ingestion_v1',index_guard.index_name));
  IF index_oid IS NULL OR NOT EXISTS(SELECT 1 FROM pg_index i JOIN pg_class c ON c.oid=i.indexrelid
    JOIN pg_am a ON a.oid=c.relam
   WHERE c.oid=index_oid AND i.indrelid=task_table AND c.relowner=task_owner AND c.relacl IS NULL
    AND c.relkind='i' AND c.relpersistence='p' AND a.amname='hash'
    AND i.indisvalid AND i.indisready AND i.indislive AND NOT i.indisunique AND NOT i.indisprimary
    AND NOT i.indisexclusion AND i.indnkeyatts=1 AND i.indnatts=1 AND i.indexprs IS NULL
    AND pg_get_indexdef(c.oid)=index_guard.expected_definition) THEN
   RAISE EXCEPTION 'Post-install selector exact reviewed hash index is absent or differs';
  END IF;
 END LOOP;
 FOR selector IN SELECT * FROM (VALUES
__QUERY_ROWS__
 ) q(component,read_query) LOOP
  EXECUTE 'EXPLAIN (ANALYZE TRUE,BUFFERS TRUE,TIMING FALSE,SETTINGS TRUE,FORMAT JSON) '||selector.read_query INTO plan;
  results:=results||jsonb_build_array(jsonb_build_object('component',selector.component,'plan',plan));
  IF octet_length(results::text)>60000 THEN RAISE EXCEPTION 'Post-install selector profile exceeds bounded result size'; END IF;
 END LOOP;
 IF jsonb_array_length(results)<>2 THEN RAISE EXCEPTION 'Post-install selector profile is incomplete'; END IF;
 RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='ASTRA_MAINTENANCE_INDEX_POSTINSTALL_V72:'||jsonb_build_object(
  'schema','astra.maintenance-index-postinstall-selectors/1','started_at',started,'observed_at',clock_timestamp(),
  'transaction_read_only',current_setting('transaction_read_only'),'transaction_isolation',current_setting('transaction_isolation'),
  'statement_timeout',current_setting('statement_timeout'),'lock_timeout',current_setting('lock_timeout'),
  'source_pins_verified',5,'exact_hash_indexes_verified',2,'selector_count',2,'complete',true,
  'maintenance_functions_invoked',false,'advisory_lock_acquired',false,'raw_page_bodies_returned',false,
  'interpretation','Current direct SELECT plans; cache/state-dependent; not whole-cron or gate-hold timing.',
  'results',results)::text;
END $postinstall_profile$;
ROLLBACK;
""".replace('__PIN_ROWS__', pin_rows).replace('__INDEX_ROWS__', index_rows).replace('__QUERY_ROWS__', query_rows)
path = HERE / 'maintenance_index_postinstall_selectors_readonly_v72.sql'
path.write_text(sql)
derivation = {
    'schema': 'astra.maintenance-index-postinstall-selector-derivation/1',
    'source_receipt': str(SOURCE.relative_to(ROOT)),
    'source_receipt_sha256': sha256(SOURCE.read_bytes()).hexdigest(),
    'source_pins': pins,
    'expected_index_definitions': indexes,
    'component_names': [x[0] for x in queries],
    'query_sha256': {name: sha256(query.encode()).hexdigest() for name, query in queries},
    'rewrites': ['The single original p_limit token in each selector becomes the installed literal2; nothing else changes.'],
    'forbidden_actions_absent': ['Helper invocation', 'Provider request', 'Explicit row/table/advisory lock acquisition', 'Data or schema writes', 'Global task count'],
    'interpretation': 'Direct-role current-snapshot read plans. Not original cached cron plans, production whole-helper latency, gate wait time or cross-cache speed ratios.',
    'sql_sha256': sha256(path.read_bytes()).hexdigest(),
    'sql_bytes': path.stat().st_size,
}
(HERE / 'maintenance_index_postinstall_selector_derivation_v72.json').write_text(json.dumps(derivation, indent=2) + '\n')
print(json.dumps({'path': str(path), 'sha256': derivation['sql_sha256'], 'bytes': derivation['sql_bytes']}))
