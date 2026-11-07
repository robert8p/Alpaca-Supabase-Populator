"""Public synthetic smoke test; contains no application data or SQL."""
import json
import os
from pathlib import Path
import psycopg

assert os.getuid() != 0
assert sorted(p.name for p in Path('/sys/class/net').iterdir()) == ['lo']
output = Path(os.environ['OUTPUT_DIR'])
dsn = f"host={output / 'socket'} user=fixture_bootstrap dbname=postgres"
with psycopg.connect(dsn, autocommit=True) as conn:
    version = conn.execute('show server_version').fetchone()[0]
    version_num = int(conn.execute('show server_version_num').fetchone()[0])
    assert 170000 <= version_num < 180000
    assert conn.execute('show listen_addresses').fetchone()[0] == ''
    conn.execute('create role installer login nosuperuser createdb createrole bypassrls')
    conn.execute('create role verifier nologin nosuperuser nobypassrls')
    conn.execute('create database synthetic owner installer')
with psycopg.connect(f"host={output / 'socket'} user=installer dbname=synthetic", autocommit=True) as conn:
    assert conn.execute("select rolsuper from pg_roles where rolname=current_user").fetchone()[0] is False
    conn.execute('create table synthetic_values (key integer primary key, value text not null)')
    conn.execute("insert into synthetic_values values (1,'sample')")
    assert conn.execute('select * from synthetic_values').fetchall() == [(1, 'sample')]
    try:
        with conn.transaction():
            conn.execute("insert into synthetic_values values (2,'rollback')")
            raise RuntimeError('synthetic rollback')
    except RuntimeError:
        pass
    assert conn.execute('select count(*) from synthetic_values').fetchone()[0] == 1
report = dict(status='passed', postgres_version=version, postgres_version_num=version_num,
              psycopg_version=psycopg.__version__, actual_guest_uid=os.getuid(),
              network_interfaces=['lo'], listen_addresses='', synthetic_rows=1,
              rollback_verified=True, non_superuser_installer_verified=True)
(output / 'smoke.json').write_text(json.dumps(report, indent=2) + '\n')
print(json.dumps(report, sort_keys=True))
