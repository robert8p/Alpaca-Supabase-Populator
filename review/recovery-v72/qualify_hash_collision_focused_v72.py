"""Focused real hash-collision recheck; no 700k task-fixture rebuild."""
from hashlib import sha256
import json
import os
from pathlib import Path
from time import monotonic
import uuid
import psycopg
from psycopg.rows import dict_row

HERE=Path(__file__).resolve().parent
EXPECTED='postgresql://postgres@127.0.0.1:55432/astra_ingestion_qualification'
if os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL')!=EXPECTED:
    raise SystemExit('Only the explicit disposable loopback PostgreSQL fixture is permitted')

def nodes(plan):
    yield plan
    for p in plan.get('Plans',[]):yield from nodes(p)

started=monotonic()
out={'schema':'astra.hash-collision-focused-qualification/1','production_calls':0,
    'fixture_only':True,'unchanged_primary_key_retained':True,'join_and_index_enable_settings_forced':False,
    'prior_scale_receipt':'maintenance_task_hash_sensitivity_qualification_v72.json',
    'prior_full_positive_run':'maintenance_task_hash_collision_initial_qualification_v72.json',
    'prior_failure':'The final large-table collision search reached its8-second local statement bound after positive/generic assertions; the unsuccessful result is preserved.'}
schema='maintenance_collision_'+uuid.uuid4().hex[:12]
try:
    with psycopg.connect(EXPECTED,row_factory=dict_row) as conn:
        conn.execute("SET LOCAL statement_timeout='8s'")
        conn.execute("SET LOCAL lock_timeout='3s'")
        conn.execute("SET LOCAL random_page_cost=1.1")
        conn.execute("SET LOCAL jit=off")
        pair=conn.execute('''SELECT min(id) eligible_id,max(id) excluded_id,h FROM(
          SELECT 'backfill-plan-'||lpad(g::text,64,'0') id,hashtext('backfill-plan-'||lpad(g::text,64,'0')) h
          FROM generate_series(1,200000) g) generated GROUP BY h HAVING count(*)>1 LIMIT 1''').fetchone()
        assert pair and pair['eligible_id']!=pair['excluded_id']
        conn.execute('CREATE SCHEMA '+schema)
        conn.execute(f'CREATE TABLE {schema}.tasks(id text PRIMARY KEY,family text NOT NULL,provider text NOT NULL,scope jsonb NOT NULL)')
        conn.execute(f'''INSERT INTO {schema}.tasks SELECT 'filler-'||md5(g::text),'D01','DERIVED',
          jsonb_build_object('padding',repeat('x',600)) FROM generate_series(1,100000) g''')
        conn.execute(f'INSERT INTO {schema}.tasks VALUES(%s,\'D03\',\'DERIVED\',\'{{}}\'),(%s,\'D01\',\'DERIVED\',\'{{}}\')',
            (pair['eligible_id'],pair['excluded_id']))
        conn.execute(f"CREATE INDEX probe_eligibility_hash ON {schema}.tasks USING hash(id) WHERE family='D03' AND lower(provider)='derived'")
        conn.execute('ANALYZE '+schema+'.tasks')
        query=f"SELECT id FROM {schema}.tasks WHERE family='D03' AND lower(provider)='derived' AND id=%s"
        assert conn.execute(query,(pair['eligible_id'],)).fetchall()==[{'id':pair['eligible_id']}]
        assert conn.execute(query,(pair['excluded_id'],)).fetchall()==[]
        plan=conn.execute('EXPLAIN (ANALYZE TRUE,BUFFERS TRUE,TIMING FALSE,FORMAT JSON) '+query,(pair['excluded_id'],)).fetchone()['QUERY PLAN'][0]
        assert any(x.get('Index Name')=='probe_eligibility_hash' for x in nodes(plan['Plan'])),plan
        assert any(x.get('Rows Removed by Index Recheck',0)>=1 for x in nodes(plan['Plan'])),plan
        pkey=conn.execute("SELECT indisvalid FROM pg_index WHERE indexrelid=%s::regclass",(schema+'.tasks_pkey',)).fetchone()
        assert pkey['indisvalid']
        out.update(passed=True,collision_pair=pair,plan=plan,eligible_result_count=1,excluded_result_count=0,
            actual_hash_recheck_removed_false_match=True,primary_key_valid=True,
            local_version=conn.execute('SHOW server_version').fetchone()['server_version'])
        conn.rollback()
except Exception as error:
    out.update(passed=False,error_type=type(error).__name__,reason=str(error))
out.update(elapsed_seconds=monotonic()-started,runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
    all_fixture_changes_rolled_back=True,
    interpretation='Focused PostgreSQL16 index-collision correctness with the primary key retained. Normal planner chose the exact-predicate hash index; this is not a production timing claim.')
path=HERE/'maintenance_hash_collision_focused_qualification_v72.json'
path.write_text(json.dumps(out,indent=2,default=str)+'\n')
print(json.dumps({'passed':out['passed'],'receipt':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}))
raise SystemExit(0 if out['passed'] else 1)
