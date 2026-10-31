"""Focused actual-PostgreSQL equivalence and scaled read qualification only."""
from hashlib import sha256
from pathlib import Path
import json,os,re,sys,unittest
from time import perf_counter
from urllib.parse import urlparse
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[2]
STAGE=Path('/tmp/replacement-shared-field-cache-fixture-v74')
sys.path[:0]=[str(STAGE/'tests/ingestion'),str(STAGE)]
import test_backfill_shared_refresh_performance_v2 as existing
BASE=(HERE/'baseline_shared_refresh_v74.sql').read_text()
CAND=(HERE/'candidate_shared_refresh_field_cache_v74.sql').read_text()
DER=json.loads((HERE/'shared_field_cache_derivation_v74.json').read_text())
RESULT={'schema':'astra.shared-field-cache-local-qualification/1','production_calls':0,'selected_for_activation':False}

def digest(value):return sha256(value.encode()).hexdigest()
def nodes(p):
 yield p
 for child in p.get('Plans',[]):yield from nodes(child)
def first_read(source):
 q=source[source.index(' WITH keys AS'):source.index('\n DELETE FROM')]
 q,n=re.subn(r' INSERT INTO [A-Za-z0-9_]+\.backfill_shared_records_v2\n','\n',q,count=1)
 assert n==1
 q=q[:q.index('\n ON CONFLICT(')].strip()
 assert not re.search(r'\b(INSERT|UPDATE|DELETE)\b',q,re.I)
 return q

class Source(unittest.TestCase):
 def test_exact_three_local_changes_and_complete_inverse(self):
  self.assertEqual(digest(BASE),DER['baseline_sha256']);self.assertEqual(digest(CAND),DER['candidate_sha256'])
  inserted=' chosen_fields AS MATERIALIZED(SELECT c.record_key,f.key field,f.value field_state FROM chosen c CROSS JOIN LATERAL jsonb_each(c.field_states) f),\n'
  reverted=CAND.replace(inserted,'',1).replace('COALESCE(cf.field_state,','COALESCE(c.field_states->v.field,',1)
  reverted=reverted.replace('\n  LEFT JOIN chosen_fields cf ON cf.record_key=c.record_key AND cf.field=v.field','',1)
  self.assertEqual(reverted,BASE)
  self.assertEqual(CAND[CAND.index('\n DELETE FROM'):],BASE[BASE.index('\n DELETE FROM'):])
  self.assertEqual(CAND.count('jsonb_each(c.field_states) f'),2)
  self.assertEqual(CAND.count('ORDER BY v.field'),1)
  self.assertNotRegex(CAND,r'(?im)^\s*(GRANT|REVOKE|ALTER|CREATE\s+(TABLE|ROLE|INDEX))\b')
  RESULT['source_inverse_and_link_statement_preservation']=True

class PostgreSQL(existing.SharedRefreshPerformanceTests):
 @classmethod
 def setUpClass(cls):
  parsed=urlparse(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL',''))
  if parsed.hostname not in ('127.0.0.1','localhost') or parsed.port!=55432 or parsed.path!='/astra_ingestion_qualification':
   raise RuntimeError('Explicit existing loopback disposable PostgreSQL required')
  super().setUpClass()
  old_admin=cls.fixture.admin
  def local_admin(_cls):
   conn=old_admin();conn.execute("SET track_functions='none'");return conn
  cls.fixture.admin=classmethod(local_admin)
  f=cls.fixture('runTest')
  expected=BASE.replace('astra_ingestion_v1',f.schema)
  if cls.candidate!=expected:raise AssertionError('Published fixture does not reproduce actual installed b18a30 after schema mapping')
  with f.admin() as conn:
   RESULT['environment']=conn.execute("SELECT current_setting('server_version') server_version,current_setting('jit') jit,current_setting('work_mem') work_mem,current_setting('plan_cache_mode') plan_cache_mode,current_setting('track_functions') track_functions").fetchone()

 def setUp(self):
  super().setUp()
  self.original=BASE.replace('astra_ingestion_v1',self.f.schema)
  self.proposed=CAND.replace('astra_ingestion_v1',self.f.schema)
  with self.f.admin() as conn:conn.execute(self.original)

 def install(self,source):
  with self.f.admin() as conn:conn.execute(source)

 def refresh(self,keys=None):
  with self.f.admin() as conn:conn.execute(f'SELECT {self.f.schema}.backfill_shared_refresh_v2(%s,%s::jsonb)',(self.run,json.dumps(self.keys() if keys is None else keys)))

 def test_missing_and_jsonnull_field_value_equivalence(self):
  # Isolated field aggregation cases exercise states admitted by the JSONB
  # storage shape, including present JSON null that the current producer does
  # not normally emit as an entire field-state object.
  prefix="WITH chosen AS MATERIALIZED(SELECT 'r'::text record_key,%s::jsonb field_states),votes AS MATERIALIZED(SELECT 'r'::text record_key,* FROM jsonb_to_recordset(%s::jsonb) AS v(field text,n bigint,\"values\" bigint,nonnull boolean,datatype text)),candidate_counts AS MATERIALIZED(SELECT 'r'::text record_key,%s::bigint n),\n"
  old=BASE[BASE.index(' fields AS MATERIALIZED('):BASE.index('\n clean AS MATERIALIZED(')].strip().removesuffix(',')
  new=CAND[CAND.index(' chosen_fields AS MATERIALIZED('):CAND.index('\n clean AS MATERIALIZED(')].strip().removesuffix(',')
  cases=[({},['x'],1,1,2),({'x':None},['x'],1,1,1),({'x':{'nonnull':True,'datatype':'text','value_sha256':'a'}},['x'],2,2,2),
    ({'y':{'nonnull':False,'datatype':'text','value_sha256':'b'}},['x','y'],1,1,2),
    ({'x':None,'z':{'nonnull':False,'datatype':'number','value_sha256':'c'}},['z','x','a'],1,2,2),({},[],0,0,2)]
  comparisons=[]
  with self.f.admin() as conn:
   for states,fields,n,values,total in cases:
    votes=[{'field':f,'n':n,'values':values,'nonnull':True,'datatype':'text'} for f in fields]
    args=(json.dumps(states),json.dumps(votes),total)
    a=conn.execute(prefix+old+' SELECT to_jsonb(fields) r FROM fields',args).fetchall()
    b=conn.execute(prefix+new+' SELECT to_jsonb(fields) r FROM fields',args).fetchall()
    self.assertEqual(a,b);comparisons.append({'chosen_fields':list(states),'voted_fields':fields,'rows':len(a),'equal':True})
  RESULT['field_state_edge_cases']=comparisons

 def test_whole_refresh_equivalence_versions_conflicts_and_real_followon(self):
  missing=self.article(id='missing-chosen',title='same')
  present={**missing,'rare_field':'present'}
  with self.f.admin() as conn:
   def choose(row,order):
    return conn.execute("SELECT r FROM (SELECT %s::jsonb||jsonb_build_object('test_nonce',g) r FROM generate_series(0,31) g) q ORDER BY encode(sha256(convert_to(r::text,'UTF8')),'hex') "+order+' LIMIT 1',(json.dumps(row),)).fetchone()['r']
   missing,present=choose(missing,'ASC'),choose(present,'DESC')
   order=conn.execute("SELECT encode(sha256(convert_to((%s::jsonb)::text,'UTF8')),'hex') < encode(sha256(convert_to((%s::jsonb)::text,'UTF8')),'hex') ok",(json.dumps(missing),json.dumps(present))).fetchone()['ok']
   self.assertTrue(order)
  rows=[self.article(id='single',updated_utc='2026-07-31T12:00:00Z'),
   self.article(id='all-null',title='first'),self.article(id='all-null',title='second'),
   self.article(id='partial-null',title='first',updated_utc='2026-07-31T12:00:00Z'),self.article(id='partial-null',title='second'),
   self.article(id='ordered',title='old',updated_utc='2026-07-31T12:00:00Z'),self.article(id='ordered',title='new',updated_utc='2026-07-31T13:00:00Z'),
   self.article(id='tie-latest',title='first',updated_utc='2026-07-31T13:00:00Z'),self.article(id='tie-latest',title='second',updated_utc='2026-07-31T13:00:00Z'),
   missing,present,self.article(id='null-value',extra=None),self.article(id='null-value',extra='known')]
  self.commit(self.new(),rows)
  before=self.snapshot();keys=self.keys()
  with self.f.admin() as conn:
   metadata=conn.execute("SELECT to_jsonb(p)-'prosrc' m FROM pg_proc p WHERE oid=%s::regprocedure",(self.f.schema+'.backfill_shared_refresh_v2(text,jsonb)',)).fetchone()['m']
  self.install(self.proposed);self.refresh(keys)
  self.assertEqual(self.snapshot(),before)
  with self.f.admin() as conn:
   self.assertEqual(metadata,conn.execute("SELECT to_jsonb(p)-'prosrc' m FROM pg_proc p WHERE oid=%s::regprocedure",(self.f.schema+'.backfill_shared_refresh_v2(text,jsonb)',)).fetchone()['m'])
   rows=conn.execute(f'SELECT provider_record_id,ordered_versions,current_candidate_versions,conflict_fields,field_states FROM {self.f.schema}.backfill_shared_records_v2 WHERE run_id=%s',(self.run,)).fetchall()
  by_id={r['provider_record_id']:r for r in rows}
  self.assertFalse(by_id['all-null']['ordered_versions']);self.assertFalse(by_id['partial-null']['ordered_versions'])
  self.assertEqual(by_id['ordered']['current_candidate_versions'],1);self.assertEqual(by_id['tie-latest']['current_candidate_versions'],2)
  self.assertIn('title',by_id['tie-latest']['conflict_fields'])
  self.assertNotIn('value_sha256',by_id['missing-chosen']['field_states']['rare_field'])
  self.assertEqual(by_id['missing-chosen']['field_states']['rare_field']['reason'],'CONFLICTING_PROVIDER_RECORD_VERSIONS')
  self.commit(self.new(symbol='T2',member='member-2'),[self.article(id='ordered',title='newest',updated_utc='2026-07-31T14:00:00Z')])
  after_followon=self.snapshot();self.install(self.original);self.refresh()
  self.assertEqual(after_followon,self.snapshot())
  RESULT['whole_function_equivalence']={'single_multiple_null_partial_and_tied_versions':True,'chosen_missing_other_candidate_field':True,
   'present_source_jsonnull':True,'conflict_order_identical':True,'all_shared_sources_records_links_counters_and_receipts_identical':True,
   'real_successor_page_after_candidate_verified':True,'metadata_oid_acl_owner_config_identical':True}

 def test_scaled_full_output_and_normal_generic_plan_cost(self):
  rows=[]
  for i in range(1000):
   row={'id':'contract-'+str(i),'symbol':'AAPL260117C'+str(100000+i).zfill(8),'underlying_symbol':'AAPL',
    'expiration_date':'2026-01-17','strike_price':str(100+i),'type':'call','status':'inactive'}
   row.update({'field'+str(j).zfill(2):digest(str(i)+'-'+str(j))[:8] for j in range(12)})
   row['fixture_padding']='';rows.append(row)
  size=lambda:len(json.dumps({'option_contracts':rows,'next_page_token':None}).encode())
  remaining=711481-size();self.assertGreaterEqual(remaining,0)
  each,rest=divmod(remaining,1000)
  for i,row in enumerate(rows):row['fixture_padding']='x'*(each+(i<rest))
  self.assertEqual(size(),711481);self.assertTrue(all(len(row)==20 for row in rows))
  self.commit(self.new(kind='alpaca_option_contracts',family='CTX02',status='inactive'),rows)
  before=self.snapshot();keys=self.keys();self.assertEqual(len(keys),1000)
  metrics=[]
  with self.f.admin() as conn:
   conn.execute(f'ANALYZE {self.f.schema}.backfill_shared_versions_v2');conn.execute(f'ANALYZE {self.f.schema}.backfill_shared_occurrences_v2')
   toast=conn.execute("SELECT pg_relation_size(c.reltoastrelid) bytes FROM pg_class c WHERE c.oid=%s::regclass",(self.f.schema+'.backfill_shared_versions_v2',)).fetchone()['bytes']
   fields=conn.execute(f'SELECT min(jsonb_object_length_dummy) lo,max(jsonb_object_length_dummy) hi FROM (SELECT (SELECT count(*) FROM jsonb_object_keys(field_states)) jsonb_object_length_dummy FROM {self.f.schema}.backfill_shared_versions_v2 WHERE run_id=%s) x',(self.run,)).fetchone()
   self.assertEqual(fields,{'lo':20,'hi':20});self.assertGreater(toast,0)
   commands={}
   for label,source in [('before',self.original),('after',self.proposed)]:
    query=re.sub(r'\bp_keys\b','$2',re.sub(r'\bp_run\b','$1',first_read(source)))
    name='field_cache_'+label
    conn.execute(f'PREPARE {name}(text,jsonb) AS '+query)
    commands[label]=self.f.psycopg.sql.SQL('EXECUTE {} ({},{})').format(self.f.psycopg.sql.Identifier(name),self.f.psycopg.sql.Literal(self.run),self.f.psycopg.sql.Literal(json.dumps(keys)))
   full={}
   for label,command in commands.items():
    with conn.cursor(row_factory=self.f.psycopg.rows.tuple_row) as cur:
     cur.execute(command);full[label]=sorted(cur.fetchall(),key=lambda x:x[1])
   self.assertEqual(len(full['before']),1000);self.assertEqual(full['before'],full['after'])
   output_hash=digest(json.dumps(full['before'],default=str,separators=(',',':')))
   for mode in ('auto','force_generic_plan'):
    conn.execute('SET LOCAL plan_cache_mode='+mode)
    for label in ('before','after','after','before'):
     p=conn.execute(self.f.psycopg.sql.SQL('EXPLAIN(ANALYZE,BUFFERS,TIMING FALSE,FORMAT JSON) ')+commands[label]).fetchone()['QUERY PLAN'][0]
     flat=list(nodes(p['Plan']));field_node=next(n for n in flat if n.get('Subplan Name')=='CTE fields')
     child_hits=sum(c.get('Shared Hit Blocks',0) for c in field_node.get('Plans',[]))
     metrics.append({'mode':mode,'variant':label,'execution_ms':p['Execution Time'],'planning_ms':p['Planning Time'],
      'actual_rows':p['Plan']['Actual Rows'],'shared_hits':p['Plan'].get('Shared Hit Blocks',0),'shared_reads':p['Plan'].get('Shared Read Blocks',0),
      'temp_reads':p['Plan'].get('Temp Read Blocks',0),'temp_writes':p['Plan'].get('Temp Written Blocks',0),
      'fields_aggregate_extra_shared_hits':field_node.get('Shared Hit Blocks',0)-child_hits,
      'chosen_fields_rows':next((n.get('Actual Rows') for n in flat if n.get('Subplan Name')=='CTE chosen_fields'),None)})
     self.assertEqual(p['Plan']['Actual Rows'],1000)
  self.install(self.proposed);started=perf_counter();self.refresh(keys);whole_ms=(perf_counter()-started)*1000
  self.assertEqual(before,self.snapshot())
  for mode in ('auto','force_generic_plan'):
   old=[x for x in metrics if x['mode']==mode and x['variant']=='before'];new=[x for x in metrics if x['mode']==mode and x['variant']=='after']
   self.assertTrue(all(x['fields_aggregate_extra_shared_hits']>50000 for x in old),old)
   self.assertTrue(all(x['fields_aggregate_extra_shared_hits']<100 for x in new),new)
   self.assertLess(sum(x['execution_ms'] for x in new),sum(x['execution_ms'] for x in old))
  RESULT['scaled']={'records':1000,'fields_per_record':20,'raw_bytes':711481,'retained_versions_toast_bytes':toast,
   'full_tuple_output_sha256':output_hash,'full_output_equivalent':True,'normal_and_generic_measurements':metrics,
   'candidate_whole_refresh_ms':whole_ms,'whole_function_snapshot_identical':True,
   'limits':'Warm local PostgreSQL16.15 with synthetic values; no production cold-cache or whole-cron improvement claim. Temporary spill and storage geometry remain explicit.'}

if __name__=='__main__':
 started=perf_counter();suite=unittest.TestSuite([Source('test_exact_three_local_changes_and_complete_inverse'),
  PostgreSQL('test_missing_and_jsonnull_field_value_equivalence'),PostgreSQL('test_whole_refresh_equivalence_versions_conflicts_and_real_followon'),
  PostgreSQL('test_scaled_full_output_and_normal_generic_plan_cost')])
 result=unittest.TextTestRunner(verbosity=2).run(suite)
 RESULT.update(passed=result.wasSuccessful(),tests=result.testsRun,errors=len(result.errors),failures=len(result.failures),skipped=len(result.skipped),
  elapsed_seconds=perf_counter()-started,baseline_sha256=digest(BASE),candidate_sha256=digest(CAND),test_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
  error_details=[{'test':str(t),'traceback':e} for t,e in result.errors],failure_details=[{'test':str(t),'traceback':e} for t,e in result.failures])
 path=HERE/'shared_field_cache_qualification_v74.json';path.write_text(json.dumps(RESULT,indent=2,default=str)+'\n')
 print(json.dumps({'passed':result.wasSuccessful(),'receipt':str(path),'sha256':sha256(path.read_bytes()).hexdigest()}))
 raise SystemExit(0 if result.wasSuccessful() else 1)
