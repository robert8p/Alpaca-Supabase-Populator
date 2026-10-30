"""Local disposable-PostgreSQL qualification; no production or network service calls."""
from hashlib import sha256
import json
from pathlib import Path
import re
import sys
from time import monotonic

ROOT=Path.cwd()
sys.path.insert(0,str(ROOT/'tests/ingestion'))
import test_backfill_maintenance_phase_installation_v73 as fixture

SQL_PATH='review/recovery-v73/installation/maintenance_phase_preflight_readback_readonly_v73.sql'
sql=(ROOT/SQL_PATH).read_text()
started=monotonic()
T=fixture.PostgreSQLInstallationTests
T.setUpClass()
t=T('test_real_forward_and_restore_preserve_full_catalog_data_and_oid')
report={'schema':'astra.maintenance-phase-readonly-qualification/1','production_calls':0,
        'sql_sha256':sha256(sql.encode()).hexdigest(),'cases':[]}
try:
    t.setUp()
    adapted=t.identifiers(sql)
    for tag,value in [('maintain_metadata',t.expected_metadata),('audit_metadata',t.expected_audit),
                     ('index_metadata',t.expected_indexes),('owner_metadata',t.expected_role)]:
        pattern=r'\$'+tag+r'\$.*?\$'+tag+r'\$::jsonb'
        adapted,count=re.subn(pattern,lambda _:fixture.builder.json_sql(value,tag),adapted,flags=re.S)
        assert count==1
    pattern=r"\('([^']+)','[0-9a-f]{64}',(true|false),\$pin_metadata\$.*?\$pin_metadata\$::jsonb\)"
    def pin(match):
        signature,full=match.group(1),match.group(2)
        value=t.pin_info[signature]
        return '('+fixture.builder.quote(signature)+','+fixture.builder.quote(fixture.digest(value['source']))+','+full+','+fixture.builder.json_sql(
            value['metadata'] if full=='true' else value['partial'],'pin_metadata')+')'
    adapted,count=re.subn(pattern,pin,adapted,flags=re.S)
    assert count==13
    for signature,old in fixture.MANIFEST['unchanged_function_pins'].items():
        adapted=adapted.replace(old,fixture.digest(t.pin_info[signature.replace('astra_ingestion_v1',t.f.schema)]['source']))
    adapted=adapted.replace(fixture.observation.PIN,fixture.digest(t.baseline)).replace(
        fixture.observation.DERIVATION['candidate_sha256'],fixture.digest(t.candidate))
    prefix='MAINTENANCE_PHASE_PREFLIGHT_READBACK_V73 '
    def execute(text,expect_success):
        with t.f.admin() as conn:
            before=t.application_snapshot(conn)
            catalog=conn.execute(t.query(fixture.builder.CATALOG_QUERY)).fetchone()['value']
        with t.f.admin() as conn:
            try:
                conn.execute(text)
            except t.f.psycopg.Error as error:
                message=error.diag.message_primary
                assert error.sqlstate=='P0001'
                if expect_success:
                    assert message.startswith(prefix),message
                    result=json.loads(message[len(prefix):])
                    assert result['complete'] and result['transaction_read_only']=='on'
                    assert result['transaction_isolation']=='repeatable read'
                    assert result['statement_timeout']=='8s' and result['lock_timeout']=='3s'
                    assert len(message.encode())<=12000+len(prefix)
                else:
                    assert not message.startswith(prefix),message
                    result={'rejected':True,'reason':message}
                conn.rollback()
            else:
                raise AssertionError('Named P0001 result or guard failure was not raised')
        with t.f.admin() as conn:
            assert t.application_snapshot(conn)==before
            assert conn.execute(t.query(fixture.builder.CATALOG_QUERY)).fetchone()['value']==catalog
        return result
    baseline=execute(adapted,True)
    assert baseline['install_ready'] and not baseline['restore_ready']
    assert baseline['maintain_sha256']==fixture.digest(t.baseline)
    report['cases'].append({'case':'baseline_readonly','install_ready':True,'rows_and_catalog_unchanged':True})
    with t.f.admin() as conn: conn.execute(t.candidate)
    candidate=execute(adapted,True)
    assert candidate['restore_ready'] and not candidate['install_ready']
    assert baseline['other_schema_catalog_sha256']==candidate['other_schema_catalog_sha256']
    report['cases'].append({'case':'candidate_readonly','restore_ready':True,'other_schema_fingerprint_equal':True})
    for a,b in [("SET LOCAL statement_timeout='8s'","SET LOCAL statement_timeout='9s'"),
                ("SET LOCAL lock_timeout='3s'","SET LOCAL lock_timeout='4s'"),
                ('ISOLATION LEVEL REPEATABLE READ READ ONLY','ISOLATION LEVEL READ COMMITTED READ ONLY'),
                ('ISOLATION LEVEL REPEATABLE READ READ ONLY','ISOLATION LEVEL REPEATABLE READ READ WRITE')]:
        execute(adapted.replace(a,b),False)
    report['cases'].append({'case':'four_transaction_bounds_rejected','count':4,'rows_and_catalog_unchanged':True})
    with t.f.admin() as conn:
        conn.execute(f"UPDATE {t.f.schema}.backfill_runs_v2 SET metadata=metadata-'implementation_owner' WHERE id=%s",(t.run,))
    execute(adapted,False)
    report['cases'].append({'case':'null_owner_rejected','rows_and_catalog_unchanged':True})
    report.update(passed=True,errors=0,failures=0,skips=0,case_count=len(report['cases']),elapsed_seconds=round(monotonic()-started,3),
                  maximum_safe_result_bytes=max(len(json.dumps(x).encode()) for x in (baseline,candidate)))
finally:
    T.doClassCleanups()
out=Path(sys.argv[1])
out.write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps({'receipt':str(out),'sha256':sha256(out.read_bytes()).hexdigest(),'summary':report}))
