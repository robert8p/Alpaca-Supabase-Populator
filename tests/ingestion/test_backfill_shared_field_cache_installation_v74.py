"""Exact guarded shared-field forward/restore and atomic failure qualification."""
from hashlib import sha256
import json,os,re,unittest
from pathlib import Path
import test_backfill_claim_capability_filter_v2 as base
ROOT=Path(__file__).resolve().parents[2];HERE=ROOT/'review/recovery-v74/shared-field-cache'
MANIFEST=json.loads((HERE/'shared_field_migration_manifest_v74.json').read_text())
BASE=(HERE/'baseline_shared_refresh_v74.sql').read_text();CAND=(HERE/'candidate_shared_refresh_field_cache_v74.sql').read_text()
FORWARD=(ROOT/'sql/astra_backfill_shared_field_cache_v74.sql').read_text()
RESTORE=(ROOT/'sql/astra_backfill_shared_field_cache_restore_v74.sql').read_text()
RESULT={'schema':'astra.shared-field-migration-qualification/1','production_calls':0}
def digest(s):return sha256(s.encode()).hexdigest()
class SourceTests(unittest.TestCase):
 def test_guarded_migration_scope_and_lock_order(self):
  for op,sql in [('forward',FORWARD),('restore',RESTORE)]:
   with self.subTest(operation=op):
    expected=next(x for x in MANIFEST['files'] if x['operation']==op)
    self.assertEqual(digest(sql),expected['sha256'])
    gate=sql.index(' PERFORM pg_catalog.pg_advisory_xact_lock(706314020261028);')
    run_lock=sql.index(' PERFORM 1 FROM astra_ingestion_v1.backfill_runs_v2')
    self.assertLess(gate,run_lock);self.assertIn('FOR SHARE;',sql[run_lock:run_lock+220])
    self.assertEqual(sql.count('EXECUTE v_replacement;'),1)
    self.assertEqual(sql.count('FOR v_pin IN SELECT value'),2)
    self.assertEqual(sql.count('implementation_lease_until'),2)
    self.assertEqual(sql.count("current_setting('statement_timeout')<>'8s'"),1)
    self.assertNotRegex(sql,r'(?im)^\s*(GRANT|REVOKE|ALTER|CREATE\s+(TABLE|INDEX|ROLE))\b')
  self.assertIn("AND status='ACTIVE'",FORWARD);self.assertNotIn("AND status='ACTIVE'",RESTORE)

class PostgreSQLTests(unittest.TestCase):
 @classmethod
 def setUpClass(cls):
  if not os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'):
   if os.environ.get('GITHUB_WORKFLOW')=='ASTRA ingestion qualification':
    raise RuntimeError('ASTRA_INGESTION_POSTGRES_TEST_URL is required by ASTRA ingestion qualification')
   raise unittest.SkipTest('Disposable PostgreSQL is exercised by the dedicated ASTRA ingestion qualification gate')
  base.CapabilityFilterPostgreSQLTests.setUpClass.__func__(cls)
  f=cls.fixture('runTest')
  monitor=next(x['definition'] for x in json.loads((ROOT/'review/recovery-v71/live_cron_functions_1331.json').read_text()) if x['proname']=='monitor_tick_v1')
  with f.admin() as conn:conn.execute(monitor.replace('astra_ingestion_v1',f.schema))
 rewrite=classmethod(base.CapabilityFilterPostgreSQLTests.rewrite.__func__)
 full_query=staticmethod(base.CapabilityFilterPostgreSQLTests.full_query)
 task=base.CapabilityFilterPostgreSQLTests.task
 snapshot=base.CapabilityFilterPostgreSQLTests.snapshot
 def setUp(self):
  base.CapabilityFilterPostgreSQLTests.setUp(self)
  self.before=BASE.replace('astra_ingestion_v1',self.f.schema)
  self.after=CAND.replace('astra_ingestion_v1',self.f.schema)
  with self.f.admin() as conn:conn.execute(self.before)
 def source(self,operation):
  sql=self.rewrite(FORWARD if operation=='forward' else RESTORE).replace(base.LIVE_RUN,self.run)
  pins=[]
  with self.f.admin() as conn:
   for original in MANIFEST['unchanged_source_metadata_pins']:
    sig=original['signature'].replace('astra_ingestion_v1',self.f.schema)
    row=conn.execute("SELECT pg_get_functiondef(p.oid) d,to_jsonb(p)-'prosrc' full,jsonb_build_object('acl',p.proacl,'owner',p.proowner::text,'config',p.proconfig,'security_definer',p.prosecdef) compact FROM pg_proc p WHERE oid=%s::regprocedure",(sig,)).fetchone()
    pins.append({**original,'signature':sig,'sha256':digest(row['d']),'metadata':row[original['metadata_kind']]})
   metadata=conn.execute("SELECT to_jsonb(p)-'prosrc' m FROM pg_proc p WHERE oid=%s::regprocedure",(self.f.schema+'.backfill_shared_refresh_v2(text,jsonb)',)).fetchone()['m']
  sql=re.sub(r'\$shared_pins\$.*?\$shared_pins\$',lambda m:'$shared_pins$'+json.dumps(pins,separators=(',',':'))+'$shared_pins$',sql,flags=re.S)
  sql=re.sub(r'\$shared_metadata\$.*?\$shared_metadata\$',lambda m:'$shared_metadata$'+json.dumps(metadata,separators=(',',':'))+'$shared_metadata$',sql,flags=re.S)
  return sql.replace(digest(BASE),digest(self.before)).replace(digest(CAND),digest(self.after))
 def definition(self,conn):
  return conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',(self.f.schema+'.backfill_shared_refresh_v2(text,jsonb)',)).fetchone()['d']
 def metadata(self,conn):
  return conn.execute("SELECT to_jsonb(p)-'prosrc' m FROM pg_proc p WHERE oid=%s::regprocedure",(self.f.schema+'.backfill_shared_refresh_v2(text,jsonb)',)).fetchone()['m']
 def execute(self,sql):
  with self.f.admin() as conn:conn.execute(sql)
 def reject(self,sql,expected_fragment=None):
  with self.f.admin() as conn:
   before=self.snapshot(conn);source=self.definition(conn);metadata=self.metadata(conn);conn.commit()
   with self.assertRaises(self.f.psycopg.Error) as caught:conn.execute(sql)
   if expected_fragment:self.assertIn(expected_fragment,caught.exception.diag.message_primary)
   conn.rollback()
   self.assertEqual(source,self.definition(conn));self.assertEqual(metadata,self.metadata(conn));self.assertEqual(before,self.snapshot(conn))
 def test_success_exact_oid_acl_data_preservation_and_strict_replay(self):
  self.task();forward=self.source('forward');restore=self.source('restore')
  with self.f.admin() as conn:before=self.snapshot(conn);metadata=self.metadata(conn)
  self.execute(forward)
  with self.f.admin() as conn:
   self.assertEqual(self.definition(conn),self.after);self.assertEqual(metadata,self.metadata(conn));self.assertEqual(before,self.snapshot(conn))
  self.reject(forward,'reconcile before replay')
  self.execute(restore)
  with self.f.admin() as conn:
   self.assertEqual(self.definition(conn),self.before);self.assertEqual(metadata,self.metadata(conn));self.assertEqual(before,self.snapshot(conn))
  self.reject(restore,'reconcile before replay')
  RESULT['success_restore_replay']={'same_oid_acl_owner_config':True,'run_member_task_provider_worker_turn_page_readback_snapshot_identical':True,'both_strict_replays_rejected':True}
 def test_preconditions_and_atomic_postreplacement_failures(self):
  forward=self.source('forward')
  wrong_metadata=re.sub(r'\$shared_metadata\$(.*?)\$shared_metadata\$',lambda m:'$shared_metadata$'+json.dumps({**json.loads(m.group(1)),'unexpected_property':True},separators=(',',':'))+'$shared_metadata$',forward,flags=re.S)
  for label,sql in [('wrong_source',forward.replace("'"+digest(self.before)+"'","'"+'0'*64+"'",1)),('wrong_metadata',wrong_metadata),
   ('wrong_owner',forward.replace("'root-replacement-20261030T042603Z'","'another-owner'")),
   ('wrong_fence',forward.replace(' AND fence=1',' AND fence=2')),
   ('wrong_cohort',forward.replace("cohort_sha256='2dc0f766befed6de6b052221c3c87482d507ba1bad931cbb98654eb3af899bec'","cohort_sha256='"+'0'*64+"'")),
   ('wrong_count',forward.replace(')<>3000 THEN',')<>2999 THEN'))]:
   with self.subTest(case=label):self.reject(sql)
  with self.f.admin() as conn:
   run_metadata=conn.execute(f'SELECT metadata FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s',(self.run,)).fetchone()['metadata']
   conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=jsonb_set(metadata,'{{implementation_lease_until}}','\"2000-01-01T00:00:00Z\"') WHERE id=%s",(self.run,))
  self.reject(forward,'owner, lease')
  with self.f.admin() as conn:conn.execute(f'UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=%s WHERE id=%s',(json.dumps(run_metadata),self.run))
  marker=' -- SHARED_FIELD_CACHE_AFTER_REPLACEMENT'
  injections={
   'postreplacement_exception':"RAISE EXCEPTION 'fixture after replacement';",
   'postreplacement_metadata':f"ALTER FUNCTION {self.f.schema}.backfill_shared_refresh_v2(text,jsonb) SET statement_timeout='123ms';",
   'postreplacement_expiry':f"UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=jsonb_set(metadata,'{{implementation_lease_until}}','\"2000-01-01T00:00:00Z\"') WHERE id='{self.run}';"}
  for label,code in injections.items():
   with self.subTest(case=label):self.reject(forward.replace(marker,marker+'\n '+code,1))
  # The drift occurs after initial pins but before the preservation snapshot,
  # so only the repeated fixed pin check can catch this exact interval.
  with self.f.admin() as conn:
   original_date=conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',(self.f.schema+'.backfill_date_v2(text)',)).fetchone()['d']
  drifted=original_date.replace('AS $function$','AS $function$\n-- FIXTURE PRE-SNAPSHOT SOURCE DRIFT\n',1)
  sql=forward.replace(' -- SHARED_FIELD_CACHE_BEFORE_CATALOG_SNAPSHOT',' EXECUTE $fixture_drift$'+drifted+'$fixture_drift$;\n -- SHARED_FIELD_CACHE_BEFORE_CATALOG_SNAPSHOT',1)
  self.reject(sql,'immutable source or metadata pin')
  with self.f.admin() as conn:self.assertEqual(original_date,conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',(self.f.schema+'.backfill_date_v2(text)',)).fetchone()['d'])
  RESULT['fail_closed']=['source','full_metadata','owner','fence','cohort','member_count','expired_lease','postreplacement_exception','postreplacement_metadata','postreplacement_expiry','presnapshot_pinned_source_drift']
 def test_paused_restore_without_reactivation_and_restore_guards(self):
  forward=self.source('forward');restore=self.source('restore');self.execute(forward)
  with self.f.admin() as conn:conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET status='PAUSED' WHERE id=%s",(self.run,))
  self.reject(restore.replace("'root-replacement-20261030T042603Z'","'another-owner'"),'owner, lease')
  self.reject(restore.replace("'"+digest(self.after)+"'","'"+'0'*64+"'",1),'reconcile before replay')
  with self.f.admin() as conn:before=self.snapshot(conn)
  self.execute(restore)
  with self.f.admin() as conn:
   self.assertEqual(self.definition(conn),self.before);self.assertEqual(before,self.snapshot(conn))
   self.assertEqual(conn.execute(f'SELECT status FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s',(self.run,)).fetchone()['status'],'PAUSED')
  RESULT['paused_cleanup_preserves_status_and_data']=True
if __name__=='__main__':unittest.main()
