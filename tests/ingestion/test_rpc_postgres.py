"""Fixed-operation RPC integration tests on an explicitly admitted loopback PG.

No production DSN is accepted. Every object and role is generated per test class;
cleanup and mutations are restricted to those exact owned test identifiers.
"""
from __future__ import annotations

import copy
import hashlib
import json
import os
from pathlib import Path
import re
import unittest
from urllib.parse import unquote, urlsplit
import uuid

from astra_ingestion.models import IngestionSpec
from astra_ingestion.source import FetchResult, parse_page
from astra_ingestion.store import Store
from astra_ingestion.worker import verify_receipts

TEST_URL = os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL', '')
BASE = {'name':'RPC qualification','symbols':['AAPL'],'start':'2025-09-02T13:30:00Z',
        'end':'2025-09-02T14:00:00Z','timeframe':'5Min'}
ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(TEST_URL, 'RPC PostgreSQL qualification NOT_RUN: explicit loopback DSN absent')
class RPCPostgreSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        target = urlsplit(TEST_URL)
        if (target.scheme not in {'postgresql','postgres'} or target.hostname not in {'localhost','127.0.0.1','::1'}
                or unquote(target.path) != '/astra_ingestion_qualification' or target.query or target.fragment):
            raise RuntimeError('RPC tests require loopback astra_ingestion_qualification without overrides')
        import psycopg
        from psycopg.rows import dict_row
        cls.psycopg, cls.dict_row = psycopg, dict_row
        suffix = uuid.uuid4().hex[:12]
        cls.schema = 'astra_rpc_test_' + suffix
        cls.auth_schema = 'astra_rpc_auth_' + suffix
        cls.owner = 'astra_rpc_owner_' + suffix
        cls.gateway = 'astra_rpc_anon_' + suffix
        cls.outsider = 'astra_rpc_outsider_' + suffix
        cls.endpoint = 'astra_rpc_endpoint_' + suffix
        cls.identifiers = [cls.schema, cls.auth_schema, cls.owner, cls.gateway, cls.endpoint,cls.outsider]
        assert all(re.fullmatch(r'astra_rpc_[a-z]+_[0-9a-f]{12}', v) for v in cls.identifiers)
        cls.store = Store(TEST_URL, test_mode=True, schema=cls.schema)
        cls.addClassCleanup(cls.cleanup)
        cls.store.migrate()
        with cls.admin() as conn:
            conn.execute(f'CREATE ROLE {cls.gateway} NOLOGIN NOINHERIT')
            conn.execute(f'CREATE ROLE {cls.outsider} NOLOGIN NOINHERIT')
            conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {cls.schema} GRANT EXECUTE ON FUNCTIONS TO {cls.outsider}')
            conn.execute(f'ALTER DEFAULT PRIVILEGES IN SCHEMA {cls.schema} GRANT SELECT ON TABLES TO {cls.outsider}')
            conn.execute(f'CREATE SCHEMA {cls.auth_schema}')
            conn.execute(f'''CREATE FUNCTION {cls.auth_schema}.uid() RETURNS uuid LANGUAGE sql STABLE
                SET search_path='' AS $$ SELECT (NULLIF(pg_catalog.current_setting('request.jwt.claims',true),'')::jsonb->>'sub')::uuid $$''')
            conn.execute(f'GRANT USAGE ON SCHEMA public TO {cls.gateway}')
        migration = (ROOT/'sql/astra_ingestion_rpc_v1.sql').read_text()
        migration = migration.replace('astra_ingestion_rpc_owner_v1',cls.owner).replace('astra_ingestion_rpc_v1',cls.endpoint)
        migration = migration.replace('astra_ingestion_v1',cls.schema).replace('auth.uid()',cls.auth_schema+'.uid()')
        migration = migration.replace(','+'auth TO',','+cls.auth_schema+' TO')
        migration = re.sub(r'\banon\b',cls.gateway,migration)
        cls.migration = migration
        with cls.admin() as conn:
            conn.execute(migration)
            # Reproduce Supabase's provider-owned auth-schema restriction.
            conn.execute(f'REVOKE USAGE ON SCHEMA {cls.auth_schema} FROM {cls.owner}')
        cls.tokens = {'api':'a'*64,'worker':'b'*64}
        # The historical installed dispatcher must exhibit the real permission
        # failure before applying its independent, forward-only repair.
        try:
            with cls.admin() as conn:
                conn.execute(f'SET LOCAL ROLE {cls.gateway}')
                conn.execute("SELECT set_config('request.headers',%s,true),set_config('request.jwt.claims',%s,true),set_config('request.method','POST',true)",
                             (json.dumps({'x-astra-ingestion-token':cls.tokens['api']}),json.dumps({'role':cls.gateway})))
                conn.execute(f"SELECT public.{cls.endpoint}('health','{{}}'::jsonb)")
        except cls.psycopg.Error as error:
            if error.sqlstate != '42501':
                raise
        else:
            raise AssertionError('Fixture did not reproduce the provider auth-schema denial')
        original = (ROOT/'sql/astra_ingestion_rpc_v1.sql').read_text()
        pattern = r'CREATE FUNCTION [a-z0-9_]+\.rpc_dispatch\(p_operation text,p_payload jsonb\)\nRETURNS jsonb .*? AS \$fn\$(.*?)\$fn\$;'
        original_body = re.search(pattern,original,re.S).group(1)
        fixture_body = re.search(pattern,migration,re.S).group(1)
        old_check = "OR v_claims->>'role' IS DISTINCT FROM 'anon' OR auth.uid() IS NOT NULL"
        new_check = "OR v_claims->>'role' IS DISTINCT FROM 'anon'\n     OR (v_claims->>'sub') IS NOT NULL\n     OR NULLIF(pg_catalog.current_setting('request.jwt.claim.sub',true),'') IS NOT NULL"
        fixture_old_check = old_check.replace('anon',cls.gateway).replace('auth.uid()',cls.auth_schema+'.uid()')
        fixture_new_check = new_check.replace('anon',cls.gateway)
        forward = (ROOT/'sql/astra_ingestion_rpc_auth_context_v1.sql').read_text()
        for before,after in [(original_body,fixture_body),
                             (original_body.replace(old_check,new_check),fixture_body.replace(fixture_old_check,fixture_new_check))]:
            expected = hashlib.sha256(before.encode()).hexdigest()
            assert expected in forward, 'Forward migration is not pinned to its historical source'
            forward = forward.replace(expected,hashlib.sha256(after.encode()).hexdigest())
        forward = forward.replace('astra_ingestion_rpc_owner_v1',cls.owner).replace('astra_ingestion_v1',cls.schema)
        forward = forward.replace('auth.uid()',cls.auth_schema+'.uid()')
        forward = re.sub(r'\banon\b',cls.gateway,forward)
        cls.forward_migration = forward
        with cls.admin() as conn:
            cls.dispatch_metadata_before = conn.execute("SELECT to_jsonb(p)-'prosrc' AS metadata FROM pg_proc p WHERE oid=%s::regprocedure",
                                                        (cls.schema+'.rpc_dispatch(text,jsonb)',)).fetchone()['metadata']
            conn.execute(forward)
            cls.dispatch_metadata_after = conn.execute("SELECT to_jsonb(p)-'prosrc' AS metadata FROM pg_proc p WHERE oid=%s::regprocedure",
                                                       (cls.schema+'.rpc_dispatch(text,jsonb)',)).fetchone()['metadata']

    @classmethod
    def admin(cls):
        return cls.psycopg.connect(TEST_URL, row_factory=cls.dict_row, connect_timeout=5)

    @classmethod
    def cleanup(cls):
        if not hasattr(cls,'identifiers'):
            return
        if not all(re.fullmatch(r'astra_rpc_[a-z]+_[0-9a-f]{12}',v) for v in cls.identifiers):
            raise AssertionError('Refusing cleanup of unowned identifiers')
        with cls.admin() as conn:
            conn.execute(f'DROP FUNCTION IF EXISTS public.{cls.endpoint}(text,jsonb)')
            conn.execute(f'DROP SCHEMA IF EXISTS {cls.schema} CASCADE')
            conn.execute(f'DROP SCHEMA IF EXISTS {cls.auth_schema} CASCADE')
            for role in (cls.owner,cls.gateway,cls.outsider):
                if conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(role,)).fetchone():
                    conn.execute(f'DROP OWNED BY {role}')
                    conn.execute(f'DROP ROLE {role}')

    def setUp(self):
        with self.admin() as conn:
            conn.execute(f'TRUNCATE {self.schema}.jobs CASCADE')
            conn.execute(f'TRUNCATE {self.schema}.runtime_credentials')
            conn.execute(f"UPDATE {self.schema}.source_limits SET next_request_at=0 WHERE id='alpaca'")
            for actor,token in self.tokens.items():
                conn.execute(f'''INSERT INTO {self.schema}.runtime_credentials(token_sha256,actor,expires_at)
                    VALUES(%s,%s,clock_timestamp()+interval '1 hour')''',(hashlib.sha256(token.encode()).hexdigest(),actor))

    def rpc(self, operation, payload=None, *, actor='api', token=None, claims=None, headers=None, method='POST', private=False, legacy_subject=''):
        payload = {} if payload is None else payload
        token = self.tokens[actor] if token is None else token
        claims = {'role':self.gateway} if claims is None else claims
        headers = {'x-astra-ingestion-token':token} if headers is None else headers
        endpoint = f'{self.schema}.rpc_dispatch' if private else f'public.{self.endpoint}'
        with self.admin() as conn:
            conn.execute(f'SET LOCAL ROLE {self.gateway}')
            conn.execute("SELECT set_config('request.headers',%s,true),set_config('request.jwt.claims',%s,true),set_config('request.method',%s,true),set_config('request.jwt.claim.sub',%s,true)",
                         (json.dumps(headers),json.dumps(claims),method,legacy_subject))
            return conn.execute(f'SELECT {endpoint}(%s,%s::jsonb) AS value',(operation,json.dumps(payload))).fetchone()['value']

    def ok(self, operation, payload=None, **kwargs):
        result = self.rpc(operation,payload,**kwargs)
        self.assertTrue(result['ok'],result)
        return result['result']

    def submit(self, request_key='rpc-qualification-001', **changes):
        spec = IngestionSpec.from_dict({**BASE,**changes})
        return self.ok('submit_job',{'spec':spec.to_dict(),'request_key':request_key})

    def claim(self, worker='worker-a'):
        return self.ok('claim_next',{'worker_id':worker,'lease_seconds':90},actor='worker')

    @staticmethod
    def fence(claim):
        return {key:claim[key] for key in ('id','owner','generation','next_page_token')}

    def page(self, claim, *, close=100.5, token=None):
        raw = json.dumps({'bars':{'AAPL':[{'t':BASE['start'],'o':100,'h':101,'l':99,'c':close,'v':100,'n':4,'vw':100.25}]},'next_page_token':token})
        parsed = parse_page(raw,symbol='AAPL',start=claim['start'],end=claim['end'],timeframe='5Min')
        return {'claim':self.fence(claim),'raw_body':raw,'request_id':'rpc-test','records':list(parsed.records),
                'next_page_token':parsed.next_page_token,'response_sha256':parsed.response_sha256}

    def loaded(self):
        job=self.submit();claim=self.claim()
        self.ok('reserve_request',{'claim':self.fence(claim)},actor='worker')
        self.ok('commit_page',self.page(claim),actor='worker')
        return job,claim

    def rows(self, table):
        self.assertIn(table,{'jobs','partitions','receipts','records','verifications','events','runtime_credentials','source_limits'})
        with self.admin() as conn:
            return conn.execute(f'SELECT * FROM {self.schema}.{table}').fetchall()

    def test_forward_auth_context_preserves_metadata_and_needs_no_auth_schema_access(self):
        self.assertEqual(self.dispatch_metadata_before,self.dispatch_metadata_after)
        with self.admin() as conn:
            allowed=conn.execute("SELECT has_schema_privilege(%s,%s,'USAGE') AS allowed",(self.owner,self.auth_schema)).fetchone()['allowed']
            self.assertFalse(allowed)
        self.assertTrue(self.ok('health')['ready'])
        self.assertTrue(self.ok('health',actor='worker')['ready'])
        self.assertTrue(self.ok('health',claims={'role':self.gateway,'sub':None})['ready'])
        for subject in ('',str(uuid.uuid4()),'not-a-uuid',' ',0,{},[]):
            with self.subTest(subject=subject),self.assertRaises(self.psycopg.Error) as error:
                self.rpc('health',claims={'role':self.gateway,'sub':subject})
            self.assertEqual(error.exception.sqlstate,'PT401')
        for legacy in (str(uuid.uuid4()),'not-a-uuid',' '):
            with self.subTest(legacy=legacy),self.assertRaises(self.psycopg.Error) as error:
                self.rpc('health',legacy_subject=legacy)
            self.assertEqual(error.exception.sqlstate,'PT401')

    def test_forward_migration_refuses_changed_source_without_touching_metadata(self):
        with self.admin() as conn:
            before=conn.execute('SELECT to_jsonb(p) AS definition FROM pg_proc p WHERE oid=%s::regprocedure',
                                (self.schema+'.rpc_dispatch(text,jsonb)',)).fetchone()['definition']
        with self.assertRaises(self.psycopg.Error) as error:
            with self.admin() as conn:
                conn.execute(self.forward_migration)
        self.assertIn('reviewed baseline',str(error.exception))
        with self.admin() as conn:
            after=conn.execute('SELECT to_jsonb(p) AS definition FROM pg_proc p WHERE oid=%s::regprocedure',
                               (self.schema+'.rpc_dispatch(text,jsonb)',)).fetchone()['definition']
        self.assertEqual(before,after)

    def test_independent_monitor_role_and_synthetic_stalls(self):
        """An isolated transaction qualifies the observer with zero production/provider effects."""
        suffix=self.schema.rsplit('_',1)[-1]
        monitor_role='astra_rpc_monitor_'+suffix
        migration=(ROOT/'sql/astra_ingestion_observer_v1.sql').read_text()
        migration=migration.replace('astra_ingestion_v1',self.schema)
        migration=migration.replace('astra_ingestion_monitor_owner_v1',monitor_role)
        self.assertNotIn('cron.schedule',migration.split('-- pg_cron scheduling')[0])
        with self.admin() as conn:
            # Everything including CREATE ROLE is rolled back after this test.
            try:
                original=conn.execute(
                    "SELECT prosrc,proowner,proacl FROM pg_proc WHERE oid=%s::regprocedure",
                    (self.schema+'.rpc_dispatch(text,jsonb)',)).fetchone()
                conn.execute(migration)
                unchanged=conn.execute(
                    "SELECT prosrc,proowner,proacl FROM pg_proc WHERE oid=%s::regprocedure",
                    (self.schema+'.rpc_dispatch(text,jsonb)',)).fetchone()
                self.assertEqual(original,unchanged)
                perms=conn.execute(
                    """SELECT has_table_privilege(%s,%s,'SELECT') AS can_read,
                           has_table_privilege(%s,%s,'UPDATE') AS can_change_job,
                           has_table_privilege(%s,%s,'INSERT') AS can_write_incident,
                           has_table_privilege(%s,%s,'SELECT') AS can_read_incident,
                           has_function_privilege(%s,%s,'EXECUTE') AS gateway_cannot_call""",
                    (monitor_role,self.schema+'.jobs',monitor_role,self.schema+'.jobs',
                     monitor_role,self.schema+'.monitor_incidents',monitor_role,
                     self.schema+'.monitor_incidents',self.gateway,
                     self.schema+'.monitor_tick_v1()')).fetchone()
                self.assertEqual(dict(perms),dict(can_read=True,can_change_job=False,
                    can_write_incident=True,can_read_incident=False,gateway_cannot_call=False))
                fn='SELECT '+self.schema+'.monitor_tick_v1() AS value'
                self.assertEqual(conn.execute(fn).fetchone()['value']['active_jobs'],0)
                # Place only synthetic bounded ledger rows, never a provider request.
                spec=IngestionSpec.from_dict(BASE)
                conn.execute(
                    f"""INSERT INTO {self.schema}.jobs
                      (id,request_key,scope_hash,name,spec,status,created_at,
                       updated_at,last_progress_at,deadline_at,request_count,record_count)
                      VALUES ('observer-synthetic','observer-synthetic-01',%s,%s,%s,
                              'running',extract(epoch from clock_timestamp())-500,
                              extract(epoch from clock_timestamp())-500,
                              extract(epoch from clock_timestamp())-500,
                              extract(epoch from clock_timestamp())+1800,0,0)""",
                    (spec.scope_hash,spec.name,json.dumps(spec.to_dict())))
                conn.execute(
                    f"""INSERT INTO {self.schema}.partitions
                      (id,job_id,symbol,start_at,end_at,status,generation,lease_until,
                       next_attempt_at,last_progress_at,request_count,record_count,page_count)
                      VALUES ('observer-part','observer-synthetic','AAPL',%s,%s,
                              'pending',0,NULL,
                              extract(epoch from clock_timestamp())-500,
                              extract(epoch from clock_timestamp())-500,0,0,0)""",
                    (BASE['start'],BASE['end']))
                # Provider not-before means a legitimate wait: no false stall.
                conn.execute(f"""UPDATE {self.schema}.source_limits SET
                     next_request_at=extract(epoch from clock_timestamp())+300 WHERE id='alpaca'""")
                self.assertEqual(conn.execute(fn).fetchone()['value']['new_incidents'],0)
                conn.execute(f"UPDATE {self.schema}.source_limits SET next_request_at=0 WHERE id='alpaca'")
                self.assertEqual(conn.execute(fn).fetchone()['value']['new_incidents'],1)
                self.assertEqual(conn.execute(fn).fetchone()['value']['new_incidents'],0)
                # A valid claim is not a stall; expired claim is, without takeover.
                conn.execute(f"""UPDATE {self.schema}.partitions SET status='running',owner='synthetic-worker',
                    generation=2,lease_until=extract(epoch from clock_timestamp())+120
                    WHERE id='observer-part'""")
                self.assertEqual(conn.execute(fn).fetchone()['value']['new_incidents'],0)
                conn.execute(f"""UPDATE {self.schema}.partitions SET
                    lease_until=extract(epoch from clock_timestamp())-75
                    WHERE id='observer-part'""")
                self.assertEqual(conn.execute(fn).fetchone()['value']['new_incidents'],1)
                self.assertEqual(conn.execute(fn).fetchone()['value']['new_incidents'],0)
                # Paused jobs must not be diagnosed as stalled.
                conn.execute(f"UPDATE {self.schema}.jobs SET status='paused' WHERE id='observer-synthetic'")
                self.assertEqual(conn.execute(fn).fetchone()['value']['new_incidents'],0)
                # A deadline beyond its 60-second grace gets one durable incident.
                conn.execute(f"""UPDATE {self.schema}.jobs SET status='running',
                    deadline_at=extract(epoch from clock_timestamp())-80 WHERE id='observer-synthetic'""")
                self.assertEqual(conn.execute(fn).fetchone()['value']['new_incidents'],1)
                self.assertEqual(conn.execute(fn).fetchone()['value']['new_incidents'],0)
                incidents=conn.execute(f"""SELECT reason,disposition,partition_id,
                      generation FROM {self.schema}.monitor_incidents
                      WHERE job_id='observer-synthetic' ORDER BY reason""").fetchall()
                self.assertEqual(len(incidents),3)
                self.assertEqual({v['reason'] for v in incidents},
                    {'eligible_unclaimed','lease_expired','deadline_overdue'})
                self.assertTrue(all(v['disposition']=='FAIL_CLOSED_MANUAL_REVIEW' for v in incidents))
                # The observer has no permission to mutate an ingestion job.
                conn.execute('SAVEPOINT monitor_role_access_check')
                try:
                    conn.execute(f'SET LOCAL ROLE {monitor_role}')
                    with self.assertRaises(self.psycopg.errors.InsufficientPrivilege):
                        conn.execute(f"UPDATE {self.schema}.jobs SET status='cancelled' WHERE id='observer-synthetic'")
                finally:
                    conn.execute('ROLLBACK TO SAVEPOINT monitor_role_access_check')
                # Tick records are independent observer outputs, never provider heartbeats.
                self.assertEqual(conn.execute(
                    f'SELECT count(*) AS n FROM {self.schema}.monitor_ticks').fetchone()['n'],10)
            finally:
                conn.rollback()

    def test_empty_health_and_capability_permissions(self):
        self.assertEqual(self.ok('health'),{'ready':True,'schema_version':1,'rpc_version':1})
        self.assertEqual(self.ok('health',actor='worker')['rpc_version'],1)
        for operation,actor in [('claim_next','api'),('list_jobs','worker'),('execute_sql','worker')]:
            with self.assertRaises(self.psycopg.Error) as error:
                self.rpc(operation,{},actor=actor)
            self.assertEqual(error.exception.sqlstate,'PT403')
        with self.admin() as conn:
            role=conn.execute('SELECT rolcanlogin,rolsuper,rolbypassrls FROM pg_roles WHERE rolname=%s',(self.owner,)).fetchone()
            self.assertEqual(role,{'rolcanlogin':False,'rolsuper':False,'rolbypassrls':False})
            self.assertFalse(conn.execute('SELECT has_table_privilege(%s,%s,\'SELECT\') AS x',(self.gateway,self.schema+'.records')).fetchone()['x'])
            self.assertFalse(conn.execute('SELECT has_table_privilege(%s,%s,\'INSERT,UPDATE,DELETE\') AS x',(self.owner,self.schema+'.runtime_credentials')).fetchone()['x'])
            self.assertFalse(conn.execute('SELECT has_schema_privilege(%s,%s,\'CREATE\') AS x',(self.owner,self.schema)).fetchone()['x'])
            self.assertFalse(conn.execute('SELECT has_function_privilege(%s,%s,\'EXECUTE\') AS x',(self.gateway,self.schema+'.rpc_owned(jsonb,boolean)')).fetchone()['x'])
            self.assertFalse(conn.execute('SELECT has_function_privilege(%s,%s,\'EXECUTE\') AS x',(self.outsider,self.schema+'.rpc_dispatch(text,jsonb)')).fetchone()['x'])
            self.assertFalse(conn.execute('SELECT has_table_privilege(%s,%s,\'SELECT\') AS x',(self.outsider,self.schema+'.runtime_credentials')).fetchone()['x'])
            self.assertFalse(conn.execute('SELECT c.relowner=r.oid AS x FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace CROSS JOIN pg_roles r WHERE n.nspname=%s AND c.relname=\'jobs\' AND r.rolname=%s',(self.schema,self.owner)).fetchone()['x'])

    def test_missing_malformed_revoked_and_end_user_credentials_denied(self):
        attempts=[{'headers':{}},{'token':'a'*63},{'token':'a'*64+', '+ 'a'*64},{'token':'c'*64},
                  {'claims':{'role':self.gateway,'sub':str(uuid.uuid4())}},{'claims':{'role':'authenticated'}},{'method':'GET'}]
        for kwargs in attempts:
            with self.subTest(kwargs=kwargs),self.assertRaises(self.psycopg.Error) as error:
                self.rpc('health',**kwargs)
            self.assertEqual(error.exception.sqlstate,'PT401')
        with self.admin() as conn:
            conn.execute(f"UPDATE {self.schema}.runtime_credentials SET revoked_at=clock_timestamp() WHERE actor='api'")
        with self.assertRaises(self.psycopg.Error) as error:
            self.rpc('health',private=True)
        self.assertEqual(error.exception.sqlstate,'PT401')

    def test_scope_hash_unicode_idempotency_and_server_bounds(self):
        spec=IngestionSpec.from_dict({**BASE,'name':'Prüfung 🦉 \"test\"'})
        first=self.ok('submit_job',{'spec':spec.to_dict(),'request_key':'unicode-scope-001'})
        self.assertEqual(first['scope_hash'],spec.scope_hash)
        self.assertEqual(self.ok('submit_job',{'spec':spec.to_dict(),'request_key':'unicode-scope-001'})['id'],first['id'])
        changed={**spec.to_dict(),'symbols':['MSFT']}
        self.assertEqual(self.rpc('submit_job',{'spec':changed,'request_key':'unicode-scope-001'})['error']['code'],'conflict')
        for key,value in [('max_requests',201),('max_records',100001),('deadline_seconds',7201),('symbols',['AAPL','AAPL']),('feed','iex'),('max_requests',True),('start','2025-09-02T13:30:00.0000001Z')]:
            with self.subTest(key=key,value=value):
                invalid={**spec.to_dict(),key:value}
                self.assertFalse(self.rpc('submit_job',{'spec':invalid,'request_key':'invalid-spec-'+str(len(str(value)))})['ok'])
        self.assertEqual(len(self.rows('jobs')),1)

    def test_rpc_store_worker_full_workflow_against_real_sql(self):
        from astra_ingestion.rpc_store import RpcStore, PROJECT_URL
        from astra_ingestion.worker import Worker
        from astra_ingestion.source import SourceError
        test=self
        class SQLReply:
            status=200
            def __init__(self, value,url):
                self.content=json.dumps(value).encode();self.position=0;self.url=url
                self.headers={'Content-Type':'application/json','Content-Length':str(len(self.content))}
            def geturl(self): return self.url
            def read1(self,size):
                value=self.content[self.position:self.position+size];self.position+=len(value);return value
            def __enter__(self): return self
            def __exit__(self,*args): pass
        class SQLBridge:
            def __init__(self): self.operations=[]
            def open(self,request,timeout):
                test.assertEqual(request.get_method(),'POST')
                test.assertLessEqual(timeout,15)
                message=json.loads(request.data);headers={k.lower():v for k,v in request.header_items()}
                test.assertEqual(set(message),{'operation','payload'})
                self.operations.append(message['operation'])
                result=test.rpc(message['operation'],message['payload'],token=headers['x-astra-ingestion-token'])
                return SQLReply(result,request.full_url)
        bridge=SQLBridge();key='sb_publishable_'+'p'*32
        api=RpcStore(PROJECT_URL,key,self.tokens['api'],opener=bridge)
        worker_store=RpcStore(PROJECT_URL,key,self.tokens['worker'],opener=bridge)
        self.assertTrue(api.health()['ready']);self.assertTrue(worker_store.health()['ready'])
        job=api.submit_job(IngestionSpec.from_dict(BASE),'rpc-client-workflow-001')
        self.assertEqual(len(api.list_jobs()),1)
        api.control_job(job['id'],'pause')
        self.assertIsNone(worker_store.claim_next('while-paused'))
        api.control_job(job['id'],'resume')
        class FixtureSource:
            calls=0
            def fetch_page(self,spec,claim,page_token):
                self.calls+=1
                return FetchResult(test.page(claim)['raw_body'],'wire-fixture')
        source=FixtureSource();worker=Worker(worker_store,source,worker_id='wire-worker')
        self.assertEqual(worker.run_once()['state'],'page_committed')
        self.assertEqual(worker.run_once()['state'],'verified')
        self.assertEqual(worker.run_once()['state'],'idle')
        self.assertEqual(source.calls,1)
        final=api.get_job(job['id']);self.assertEqual(final['status'],'completed')
        self.assertEqual(final['coverage_certification'],'NOT_CERTIFIED')
        second=api.submit_job(IngestionSpec.from_dict(BASE),'rpc-client-workflow-002')
        with self.admin() as conn:
            conn.execute(f'UPDATE {self.schema}.source_limits SET next_request_at=0')
        class RejectedSource:
            def fetch_page(self,*args): raise SourceError('invalid_source','Synthetic invalid source')
        self.assertEqual(Worker(worker_store,RejectedSource(),worker_id='reject-worker').run_once()['state'],'retry_or_hold')
        self.assertEqual(api.get_job(second['id'])['status'],'blocked')
        self.assertTrue({'health','submit_job','list_jobs','get_job','control_job','claim_next','reserve_request','commit_page',
                         'verification_material','finish_verification','fail_claim'}<=set(bridge.operations))

    def test_complete_atomic_page_and_fresh_verification(self):
        job,fetch_claim=self.loaded()
        self.assertEqual(len(self.rows('receipts')),1)
        self.assertEqual(len(self.rows('records')),1)
        verify_claim=self.claim('verifier-b')
        self.assertEqual(verify_claim['phase'],'verify')
        material=self.ok('verification_material',{'claim':self.fence(verify_claim)},actor='worker')
        proof=verify_receipts(verify_claim,material['receipts'],[r['payload'] for r in material['records']])
        self.ok('finish_verification',{'claim':self.fence(verify_claim),'result':proof},actor='worker')
        final=self.ok('get_job',{'job_id':job['id']})
        self.assertEqual((final['status'],final['verification_status']),('completed','passed'))
        self.assertEqual(final['coverage_certification'],'NOT_CERTIFIED')
        self.assertEqual(final['partitions'][0]['verification']['result']['scope_hash'],job['scope_hash'])
        self.assertFalse(self.rpc('commit_page',self.page(fetch_claim),actor='worker')['ok'])
        self.assertEqual(len(self.rows('records')),1)

    def test_incomplete_or_relabelled_verification_cannot_mark_success(self):
        self.loaded();claim=self.claim('verifier')
        material=self.ok('verification_material',{'claim':self.fence(claim)},actor='worker')
        proof=verify_receipts(claim,material['receipts'],[r['payload'] for r in material['records']])
        attempts=[]
        for key in ('expected_hash','actual_hash','missing_count','changed_count','scope_hash'):
            incomplete=dict(proof);incomplete.pop(key);attempts.append(incomplete)
        attempts.append({**proof,'coverage_certification':'CERTIFIED'})
        attempts.append({**proof,'actual_hash':'0'*64,'expected_hash':'0'*64})
        attempts.append({**proof,'actual_count':True})
        attempts.append({**proof,'missing_keys':['AAPL|2025-09-02T13:30:00Z']})
        for invalid in attempts:
            result=self.rpc('finish_verification',{'claim':self.fence(claim),'result':invalid},actor='worker')
            self.assertEqual(result['error']['code'],'quality_hold')
        self.assertEqual(self.rows('verifications'),[])
        self.assertEqual(self.rows('partitions')[0]['status'],'verifying')
        self.ok('finish_verification',{'claim':self.fence(claim),'result':proof},actor='worker')

    def test_deferred_pacing_transition_commits(self):
        self.submit();claim=self.claim()
        with self.admin() as conn:
            conn.execute(f"UPDATE {self.schema}.source_limits SET next_request_at=extract(epoch from clock_timestamp())+20")
        result=self.rpc('reserve_request',{'claim':self.fence(claim)},actor='worker')
        self.assertEqual(result['error']['code'],'request_deferred')
        p=self.rows('partitions')[0]
        self.assertEqual(p['status'],'pending');self.assertIsNone(p['owner']);self.assertGreater(p['next_attempt_at'],0)
        self.assertEqual(self.rows('jobs')[0]['request_count'],0)
        self.assertIsNone(self.claim('not-yet'))

    def test_pause_cancel_and_replaced_owner_fence_effects(self):
        job=self.submit();claim=self.claim()
        self.ok('control_job',{'job_id':job['id'],'action':'pause'})
        self.assertEqual(self.rpc('commit_page',self.page(claim),actor='worker')['error']['code'],'lease_lost')
        self.assertIsNone(self.claim('paused'))
        self.ok('control_job',{'job_id':job['id'],'action':'resume'})
        replacement=self.claim('replacement')
        self.assertGreater(replacement['generation'],claim['generation'])
        self.ok('control_job',{'job_id':job['id'],'action':'cancel'})
        self.assertEqual(self.rpc('reserve_request',{'claim':self.fence(replacement)},actor='worker')['error']['code'],'lease_lost')
        self.assertEqual(self.rows('receipts'),[])

    def test_rejects_forged_records_and_rolls_back_budget_exhaustion(self):
        self.submit(max_records=1);claim=self.claim();self.ok('reserve_request',{'claim':self.fence(claim)},actor='worker')
        forged=self.page(claim);forged['records'][0]['close']='100.75'
        self.assertEqual(self.rpc('commit_page',forged,actor='worker')['error']['code'],'quality_hold')
        self.assertEqual(self.rows('records'),[]);self.assertEqual(self.rows('receipts'),[])
        page=self.page(claim);body=json.loads(page['raw_body']);second=copy.deepcopy(body['bars']['AAPL'][0]);second['t']='2025-09-02T13:35:00Z';body['bars']['AAPL'].append(second)
        raw=json.dumps(body);parsed=parse_page(raw,symbol='AAPL',start=claim['start'],end=claim['end'],timeframe='5Min')
        page.update(raw_body=raw,records=list(parsed.records),response_sha256=parsed.response_sha256)
        self.assertEqual(self.rpc('commit_page',page,actor='worker')['error']['code'],'quality_hold')
        self.assertEqual(self.rows('records'),[]);self.assertEqual(self.rows('receipts'),[])
        self.assertEqual(self.rows('jobs')[0]['request_count'],1)

    def test_post_write_deadline_recheck_rolls_back_records_and_receipt(self):
        self.submit();claim=self.claim();self.ok('reserve_request',{'claim':self.fence(claim)},actor='worker')
        # Owned fixture-only trigger simulates time/fence loss during the write.
        with self.admin() as conn:
            conn.execute(f'''CREATE FUNCTION {self.schema}.expire_test_claim() RETURNS trigger LANGUAGE plpgsql SECURITY DEFINER SET search_path='' AS $$
              BEGIN UPDATE {self.schema}.partitions SET lease_until=0 WHERE id=NEW.partition_id; RETURN NEW; END $$''')
            conn.execute(f'CREATE TRIGGER expire_test_claim AFTER INSERT ON {self.schema}.records FOR EACH ROW EXECUTE FUNCTION {self.schema}.expire_test_claim()')
        try:
            result=self.rpc('commit_page',self.page(claim),actor='worker')
            self.assertEqual(result['error']['code'],'lease_lost')
            self.assertEqual(self.rows('records'),[]);self.assertEqual(self.rows('receipts'),[])
            self.assertEqual(self.rows('partitions')[0]['page_count'],0)
            self.assertGreater(self.rows('partitions')[0]['lease_until'],0)
        finally:
            with self.admin() as conn:
                conn.execute(f'DROP TRIGGER expire_test_claim ON {self.schema}.records')
                conn.execute(f'DROP FUNCTION {self.schema}.expire_test_claim()')

    def test_failure_retry_budget_and_quality_hold(self):
        self.submit();claim=self.claim()
        self.ok('fail_claim',{'claim':self.fence(claim),'code':'provider_http','message':'Provider returned HTTP 429','retryable':True,'retry_after':60,'raw_response':None},actor='worker')
        part=self.rows('partitions')[0];self.assertEqual((part['status'],part['retry_count']),('pending',1))
        with self.admin() as conn:
            conn.execute(f'UPDATE {self.schema}.partitions SET next_attempt_at=0')
        claim=self.claim('second')
        self.ok('fail_claim',{'claim':self.fence(claim),'code':'provider_http','message':'Provider returned HTTP 429','retryable':True,'retry_after':60,'raw_response':None},actor='worker')
        self.assertEqual(self.rows('partitions')[0]['status'],'failed')
        self.assertFalse(self.rpc('control_job',{'job_id':claim['job_id'],'action':'resume'})['ok'])

    def test_source_offsets_and_zero_nanoseconds_match_python(self):
        self.submit();claim=self.claim();self.ok('reserve_request',{'claim':self.fence(claim)},actor='worker')
        page=self.page(claim);body=json.loads(page['raw_body']);body['bars']['AAPL'][0]['t']='2025-09-02T14:30:00.000000000+01:00'
        raw=json.dumps(body);parsed=parse_page(raw,symbol='AAPL',start=claim['start'],end=claim['end'],timeframe='5Min')
        page.update(raw_body=raw,records=list(parsed.records),response_sha256=parsed.response_sha256)
        self.ok('commit_page',page,actor='worker')
        self.assertEqual(json.loads(self.rows('records')[0]['payload'])['timestamp'],BASE['start'])

    def test_raw_duplicate_json_and_scope_injection_rejected(self):
        self.submit();claim=self.claim();self.ok('reserve_request',{'claim':self.fence(claim)},actor='worker')
        page=self.page(claim);page['raw_body']=page['raw_body'].replace('"o": 100','"o": 100, "o": 101')
        page['response_sha256']=hashlib.sha256(page['raw_body'].encode()).hexdigest()
        self.assertEqual(self.rpc('commit_page',page,actor='worker')['error']['code'],'quality_hold')
        page=self.page(claim);page['raw_body']=page['raw_body'].replace('"AAPL"','"MSFT"');page['response_sha256']=hashlib.sha256(page['raw_body'].encode()).hexdigest()
        self.assertEqual(self.rpc('commit_page',page,actor='worker')['error']['code'],'quality_hold')
        self.assertEqual(self.rows('records'),[])

    def test_preexisting_public_overload_is_preserved(self):
        suffix=uuid.uuid4().hex[:12]
        schema='astra_rpc_test_'+suffix;owner='astra_rpc_owner_'+suffix;endpoint='astra_rpc_endpoint_'+suffix
        fixture=Store(TEST_URL,test_mode=True,schema=schema)
        fixture.migrate()
        try:
            with self.admin() as conn:
                conn.execute(f'CREATE FUNCTION public.{endpoint}(integer) RETURNS integer LANGUAGE sql IMMUTABLE AS $$ SELECT $1 $$')
                conn.execute(f'GRANT EXECUTE ON FUNCTION public.{endpoint}(integer) TO {self.outsider}')
                before=conn.execute('SELECT proacl::text AS acl FROM pg_proc WHERE oid=%s::regprocedure',(f'public.{endpoint}(integer)',)).fetchone()['acl']
            migration=(ROOT/'sql/astra_ingestion_rpc_v1.sql').read_text()
            migration=migration.replace('astra_ingestion_rpc_owner_v1',owner).replace('astra_ingestion_rpc_v1',endpoint).replace('astra_ingestion_v1',schema)
            migration=migration.replace('auth.uid()',self.auth_schema+'.uid()').replace(',auth TO',','+self.auth_schema+' TO')
            migration=re.sub(r'\banon\b',self.gateway,migration)
            with self.assertRaises(self.psycopg.Error):
                with self.admin() as conn:
                    conn.execute(migration)
            with self.admin() as conn:
                after=conn.execute('SELECT proacl::text AS acl FROM pg_proc WHERE oid=%s::regprocedure',(f'public.{endpoint}(integer)',)).fetchone()['acl']
                self.assertEqual(before,after)
                self.assertIsNone(conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(owner,)).fetchone())
        finally:
            with self.admin() as conn:
                conn.execute(f'DROP FUNCTION IF EXISTS public.{endpoint}(text,jsonb)')
                conn.execute(f'DROP FUNCTION IF EXISTS public.{endpoint}(integer)')
                conn.execute(f'DROP SCHEMA {schema} CASCADE')
                if conn.execute('SELECT 1 FROM pg_roles WHERE rolname=%s',(owner,)).fetchone():
                    conn.execute(f'DROP OWNED BY {owner}')
                    conn.execute(f'DROP ROLE {owner}')

    def test_expired_token_denied_and_collision_does_not_modify_existing_role(self):
        with self.admin() as conn:
            conn.execute(f"UPDATE {self.schema}.runtime_credentials SET created_at=clock_timestamp()-interval '2 hours',expires_at=clock_timestamp()-interval '1 hour' WHERE actor='api'")
        with self.assertRaises(self.psycopg.Error) as error:
            self.rpc('health')
        self.assertEqual(error.exception.sqlstate,'PT401')
        with self.assertRaises(self.psycopg.Error):
            with self.admin() as conn:
                conn.execute(self.migration)
        with self.admin() as conn:
            self.assertFalse(conn.execute('SELECT rolcanlogin FROM pg_roles WHERE rolname=%s',(self.owner,)).fetchone()['rolcanlogin'])


if __name__=='__main__':
    unittest.main()
