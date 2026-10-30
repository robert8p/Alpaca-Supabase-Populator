"""Build a fixed read-only profile from the retained live maintenance sources."""
from pathlib import Path
import json
from hashlib import sha256

HERE = Path(__file__).resolve().parent
helpers = json.loads((HERE / 'live_maintenance_helpers_1335.json').read_text())[0]['evidence']['definitions']
defs = {x['proname']: x for x in helpers}
maintain = json.loads((HERE / 'live_backfill_maintain_1332.json').read_text())[0]
monitor = next(x for x in json.loads((HERE / 'live_cron_functions_1331.json').read_text()) if x['proname'] == 'monitor_tick_v1')


def loop_selector(name, marker, end=' LOOP'):
    text = defs[name]['definition']
    start = text.index(marker) + len(marker)
    stop = text.index(end, start)
    sql = text[start:stop].strip().replace('p_limit', '2')
    return sql


queries = []
queries.append(('BREADTH_PENDING', loop_selector('backfill_breadth_project_pending_v2', ' FOR p IN ', '\n LOOP')))
queries.append(('MINUTE_ACCOUNT_PENDING', loop_selector('backfill_minute_account_pending_v2', ' FOR x IN ', '\n LOOP')))
text = defs['backfill_identity_discover_pending_v2']['definition']
sql = text[text.index(' SELECT d.run_id'):text.index(';\n IF NOT FOUND')].strip().replace(' INTO x ', ' ')
queries.append(('IDENTITY_DISCOVERY_PENDING', sql))
text = defs['backfill_identity_refresh_pending_v2']['definition']
sql = text[text.index(' SELECT x.* INTO q'):text.index(';\n IF NOT FOUND')].strip().replace(' INTO q ', ' ').replace(' FOR UPDATE OF x', '')
queries.append(('IDENTITY_REFRESH_QUEUE', sql))
for label, name, table in [
    ('NONMINUTE_CURSOR', 'backfill_nonminute_project_pending_v2', 'backfill_nonminute_projection_cursor_v2'),
    ('S02_CURSOR', 'backfill_s02_maintain_v2', 'backfill_s02_projection_cursor_v2'),
    ('SHARED_CURSOR', 'backfill_shared_maintain_v2', 'backfill_shared_cursor_v2'),
    ('CONTRACT_CURSOR', 'backfill_contract_maintain_v2', 'backfill_contract_readback_cursor_v2'),
]:
    text = defs[name]['definition']
    marker = ' FOR x IN SELECT b.verified_at' if label == 'CONTRACT_CURSOR' else ' FOR x IN SELECT verified_at'
    start = text.index(marker) + len(' FOR x IN ')
    end = text.index(' LOOP', start)
    sql = text[start:end].strip().replace('p_limit', '4' if label == 'SHARED_CURSOR' else '2')
    sql = sql.replace('(c.verified_at,c.task_id,c.page_no)', '(SELECT c.verified_at,c.task_id,c.page_no FROM astra_ingestion_v1.' + table + ' c WHERE singleton)')
    queries.append((label, sql))
text = defs['backfill_contract_maintain_v2']['definition']
start = text.index(' FOR x IN SELECT e.task_id') + len(' FOR x IN ')
end = text.index(' LOOP', start)
sql = text[start:end].strip().replace('e.run_id=r.id', "e.run_id=(SELECT id FROM astra_ingestion_v1.backfill_runs_v2 WHERE status='ACTIVE' ORDER BY created_at LIMIT 1)")
queries.append(('CONTRACT_ENUM_PENDING', sql))
text = maintain['definition']
start = text.index(' FOR p IN SELECT pg.task_id') + len(' FOR p IN ')
end = text.index('\n LOOP', start)
queries.append(('MISSING_READBACK', text[start:end].strip().replace('p_limit', '2')))

pins = [
    ('backfill_dispatch_v2(text,jsonb)', '28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44'),
    ('rpc_dispatch(text,jsonb)', 'a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520'),
    ('backfill_maintain_v2(integer)', maintain['sha256']),
    ('monitor_tick_v1()', monitor['sha256']),
]
for item in helpers:
    types = ','.join(part.strip().split()[-1] for part in item['args'].split(',') if part.strip())
    pins.append((item['proname'] + '(' + types + ')', item['sha256']))
pin_rows = ',\n'.join("  ('astra_ingestion_v1.%s','%s')" % item for item in pins)
query_rows = ',\n'.join("  ('%s',$query$%s$query$)" % item for item in queries)
sql = """-- Read-only selector costs from the exact retained maintenance source.
-- No maintenance, projector, verifier, finalizer or provider function is invoked.
-- The four cursor parameter reads become uncorrelated singleton InitPlans;
-- this is a current read-path probe, not the cron's original cached plan.
-- Only FOR UPDATE/INTO targets are omitted and fixed installed limits substituted.
-- The named P0001 result intentionally rolls back the transaction.
BEGIN ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL transaction_read_only=on;
SET LOCAL transaction_isolation='repeatable read';
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='3s';
DO $profile$
DECLARE x record; p jsonb; results jsonb:='[]'; started timestamptz:=clock_timestamp();
BEGIN
 IF current_setting('transaction_read_only')<>'on'
  OR current_setting('transaction_isolation')<>'repeatable read'
  OR current_setting('statement_timeout')<>'8s' OR current_setting('lock_timeout')<>'3s' THEN
  RAISE EXCEPTION 'Maintenance selector profile requires explicit bounded read-only repeatable-read settings';
 END IF;
 FOR x IN SELECT * FROM (VALUES
__PIN_ROWS__
 ) s(signature,expected_sha256) LOOP
  IF encode(sha256(convert_to(pg_get_functiondef(x.signature::regprocedure),'UTF8')),'hex')<>x.expected_sha256 THEN
   RAISE EXCEPTION 'Maintenance selector source changed; reconcile before diagnosis';
  END IF;
 END LOOP;
 IF NOT EXISTS(SELECT 1 FROM astra_ingestion_v1.backfill_runs_v2
  WHERE id='fixed3000-20250901-20260731-v1-20261030' AND status='ACTIVE' AND fence=1
   AND cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'
   AND metadata->>'implementation_owner'='root-replacement-20261030T042603Z'
   AND (metadata->>'implementation_lease_until')::timestamptz>clock_timestamp()) THEN
  RAISE EXCEPTION 'Maintenance selector run, owner, lease, fence or fixed cohort changed';
 END IF;
 FOR x IN SELECT * FROM (VALUES
__QUERY_ROWS__
 ) s(component,read_query) LOOP
  EXECUTE 'EXPLAIN (ANALYZE TRUE,BUFFERS TRUE,TIMING FALSE,SETTINGS TRUE,FORMAT JSON) '||x.read_query INTO p;
  results:=results||jsonb_build_array(jsonb_build_object('component',x.component,'plan',p));
  IF octet_length(results::text)>120000 THEN RAISE EXCEPTION 'Maintenance selector profile exceeds bounded result size'; END IF;
 END LOOP;
 RAISE EXCEPTION USING ERRCODE='P0001',MESSAGE='ASTRA_MAINTENANCE_SELECTORS_V71:'||jsonb_build_object(
  'schema','astra.maintenance-selectors/1','observed_at',clock_timestamp(),'started_at',started,
  'transaction_read_only',current_setting('transaction_read_only'),'transaction_isolation',current_setting('transaction_isolation'),
  'statement_timeout',current_setting('statement_timeout'),'lock_timeout',current_setting('lock_timeout'),
  'selector_count',jsonb_array_length(results),'complete',true,'maintenance_functions_invoked',false,
  'advisory_lock_acquired',false,'raw_page_bodies_returned',false,'results',results)::text;
END $profile$;
ROLLBACK;
""".replace('__PIN_ROWS__', pin_rows).replace('__QUERY_ROWS__', query_rows)
path = HERE / 'maintenance_selectors_readonly_v71.sql'
path.write_text(sql)
(HERE / 'maintenance_selector_derivation_v71.json').write_text(json.dumps({
    'source_receipts':['live_backfill_maintain_1332.json','live_cron_functions_1331.json','live_maintenance_helpers_1335.json'],
    'component_names':[q[0] for q in queries], 'source_pins':dict(pins),
    'sql_sha256':sha256(path.read_bytes()).hexdigest(),
    'interpretation':'Selector-only timing; not mutation-body duration, cached cron plan, or gate-wait timing.',
    'rewrites':['PL/pgSQL INTO and row-lock clause removed','fixed installed p_limit substituted',
                'cursor values read from the same singleton via scalar subquery','oldest active run read via scalar subquery']
},indent=2)+'\n')
print(json.dumps({'path':str(path),'sha256':sha256(path.read_bytes()).hexdigest(),'selectors':len(queries)}))
