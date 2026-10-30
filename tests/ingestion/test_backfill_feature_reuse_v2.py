"""Authenticated compact D01 reuse; source/cached hashes and physical accounting."""
from hashlib import sha256
import json
import os
from pathlib import Path
import unittest

import test_backfill_reuse_commit_v2 as pointer
from astra_ingestion.backfill_worker_v2 import BackfillWorker
from test_backfill_worker_reuse_v2 import NoExternalProvider

ROOT = Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'), 'Explicit disposable PostgreSQL required')
class CompactFeatureReuseTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pointer.RetainedReuseCommitTests.setUpClass.__func__(cls)
        f = cls.fixture('runTest')
        cls.replacements = [
            ('market_fixed_20250901_20260831.alpaca_sip_bars_1m',f.schema+'.retained_bars_fixture'),
            ('reference.alpaca_fixed_window_instruments_v1',f.schema+'.retained_instruments_fixture'),
            ('market_provenance.alpaca_populator_jobs_v1',f.schema+'.retained_jobs_fixture'),
            ('astra_shared_equity_features_20260928_v1',f.schema),
            ('astra_ingestion_v1',f.schema),('astra_ingestion_rpc_owner_v1',f.owner)]
        with f.admin() as conn:
            for name in ('astra_backfill_delivery_v2.sql','astra_backfill_delivery_performance_v2.sql',
                         'astra_backfill_source_dedup_v2.sql','astra_backfill_breadth_material_v2.sql',
                         'astra_backfill_provider_pacing_v2.sql'):
                conn.execute(cls.rewrite((ROOT/'sql'/name).read_text()))
            conn.execute(f'''CREATE TABLE {f.schema}.feature_session_cache_remediated_v1(
                instrument_key int,session_date date,regular_open timestamptz,regular_close timestamptz,
                expected_grid_rows smallint,retained_source_rows int,unaligned_source_rows int,aligned_source_rows int,
                minute_indices smallint[],validity_codes smallint[],dependency_source_observed_at timestamptz[],
                coefficient_values double precision[],invalid_ohlc_rows int,invalid_volume_rows int,
                first_source_acquisition timestamptz,latest_source_acquisition timestamptz,
                source_rows_sha256 bytea,identity_contract_sha256 bytea,output_sha256 bytea,built_at timestamptz,
                PRIMARY KEY(instrument_key,session_date))''')
            conn.execute(f'''CREATE TABLE {f.schema}.shared_identity_contract_remediated_v1(
                instrument_key int,session_date date,identity_contract_sha256 bytea,identity_anchor text,
                PRIMARY KEY(instrument_key,session_date))''')
            functions = json.loads((ROOT/'evidence/retained-feature-reuse-functions.json').read_text())
            compact = next(f['definition'] for f in functions if f['proname']=='compact_output_hash_remediated_v1')
            conn.execute(cls.rewrite(compact))
            # Source/profile/hash validation is the real new adapter. These two
            # old-estate functions are isolated fixtures; actual formulas are
            # independently checked against root's390-row live source artifact.
            conn.execute(f'''CREATE FUNCTION {f.schema}.compute_feature_sessions_remediated_v1(
                integer,integer,date,date,boolean) RETURNS SETOF {f.schema}.feature_session_cache_remediated_v1
                LANGUAGE sql STABLE AS $$SELECT * FROM {f.schema}.feature_session_cache_remediated_v1 WHERE false$$''')
            conn.execute(f'''CREATE FUNCTION {f.schema}.feature_grid_remediated_v1(integer,date,timestamptz,boolean)
                RETURNS TABLE(session_date date,provider_interval_start timestamptz,bar_present boolean,
                  quality_flags jsonb,close float8,return_1m float8,archive_value_identity_eligible boolean)
                LANGUAGE sql STABLE AS $$SELECT $2,($2+time '09:30')AT TIME ZONE 'America/New_York'+g*interval '1 minute',
                  g<2,'{{"identity_eligible":true,"exact_clock_grid":true}}'::jsonb,CASE WHEN g<2 THEN 101.0::float8 END,
                  NULL::float8,true FROM generate_series(0,389) g$$''')
            sql = cls.rewrite((ROOT/'sql/astra_backfill_feature_reuse_v2.sql').read_text())
            signatures = [
                ('019b86197174c682febb88a546a0ff956c058347e99b6dc0dbdd430e090fb552','compute_feature_sessions_remediated_v1(integer,integer,date,date,boolean)'),
                ('5f45e08dce40aa5cc138fa9b5819b25d049bacea574d50ceb2f943d8ff02b251','feature_grid_remediated_v1(integer,date,timestamptz,boolean)'),
                ('3d2af9589f2171964f77ecb2a5739e7417d12775833c0b3c884a61438689dae5','compact_output_hash_remediated_v1(bytea,bytea,smallint[],smallint[],timestamptz[],double precision[],integer,integer,integer,integer)')]
            for original, signature in signatures:
                actual = conn.execute('SELECT pg_get_functiondef(%s::regprocedure) definition',(f.schema+'.'+signature,)).fetchone()['definition']
                sql = sql.replace(original,sha256(actual.encode()).hexdigest())
            conn.execute(sql)

    @classmethod
    def rewrite(cls, sql):
        for a,b in cls.replacements: sql=sql.replace(a,b)
        return sql

    task = pointer.RetainedReuseCommitTests.task
    call = pointer.RetainedReuseCommitTests.call
    claim = pointer.RetainedReuseCommitTests.claim
    fence = staticmethod(pointer.RetainedReuseCommitTests.fence)
    owned = pointer.RetainedReuseCommitTests.owned
    commit_source = pointer.RetainedReuseCommitTests.commit

    def setUp(self):
        pointer.RetainedReuseCommitTests.setUp(self)
        with self.f.admin() as conn:
            conn.execute(f'DELETE FROM {self.f.schema}.feature_session_cache_remediated_v1')
            conn.execute(f'DELETE FROM {self.f.schema}.shared_identity_contract_remediated_v1')
            conn.execute(f'''INSERT INTO {self.f.schema}.shared_identity_contract_remediated_v1
                VALUES(41,'2025-09-02',sha256('fixture identity'::bytea),'fixture-identity-anchor')''')
            conn.execute(f'''INSERT INTO {self.f.schema}.feature_session_cache_remediated_v1
                SELECT 41,'2025-09-02','2025-09-02T13:30Z','2025-09-02T20:00Z',390,2,0,2,
                 ARRAY[0,1]::smallint[],ARRAY[55,55]::smallint[],
                 ARRAY['2026-08-05T00:00Z','2026-08-05T00:00Z']::timestamptz[],
                 array_fill(101.0::float8,ARRAY[2,17]),0,0,'2026-08-05T00:00Z','2026-08-05T00:00Z',
                 (SELECT sha256(string_agg(sha256(convert_to(jsonb_build_array(instrument_key,bar_ts,open,high,low,close,
                     volume,trade_count,vwap,source_loaded_at,loaded_by_job_id)::text,'UTF8')),''::bytea ORDER BY bar_ts))
                   FROM {self.f.schema}.retained_bars_fixture WHERE bar_ts>='2025-09-02T13:30Z' AND bar_ts<'2025-09-02T20:00Z'),
                 sha256('fixture identity'::bytea),NULL,'2026-10-08T06:00Z' ''')
            conn.execute(f'''UPDATE {self.f.schema}.feature_session_cache_remediated_v1 c SET output_sha256=
              {self.f.schema}.compact_output_hash_remediated_v1(source_rows_sha256,identity_contract_sha256,minute_indices,
               validity_codes,dependency_source_observed_at,coefficient_values,retained_source_rows,unaligned_source_rows,invalid_ohlc_rows,invalid_volume_rows)''')

    def setup_derived(self, *, claim_task=True, prefer_cache=False):
        source=self.owned();self.commit_source(source)
        key=self.task(kind='derive_intraday',family='D01',provider='DERIVED',
            scope={'member_ids':['member-1'],'symbols':['AAPL'],'target_start':'2025-09-02','target_end':'2025-09-02',
                   'input_start':'2025-09-02','calendar':[{'date':'2025-09-02','open':'09:30','close':'16:00'}],
                   'prefer_retained_formula_cache':prefer_cache},
            dependencies=[source['id']])
        # A real nonoverlapping Sep3 gap is pending; only complete it to permit
        # generic dependency admission. The Sep2 feature cache remains unchanged.
        gap=self.claim(['alpaca_stock_bars'])
        if gap: pointer.RetainedReuseCommitTests.complete_empty_provider_page(self,gap)
        if not claim_task:
            return source,key
        claimed=self.claim(['derive_intraday']);self.assertEqual(claimed['id'],key)
        return source,claimed

    def worker_store(self):
        test=self
        class Store:
            def __init__(self):self.operations=[]
            def _call(self,operation,payload):
                self.operations.append(operation)
                return test.call(operation,payload)
        return Store()

    def test_real_worker_uses_cache_and_generic_independent_proof_without_refetch(self):
        _,task_id=self.setup_derived(claim_task=False,prefer_cache=True)
        with self.f.admin() as conn:
            before=dict(conn.execute(f'SELECT requests_reserved,pages_committed,records_committed FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s',(self.run,)).fetchone())
        store=self.worker_store()
        result=BackfillWorker(store,NoExternalProvider(),worker_id='fixture-cache-worker').run_once()
        self.assertEqual(result['task_id'],task_id)
        self.assertEqual(result['reused_feature_rows'],390)
        self.assertEqual(result['source_readback'],'FEATURE_REUSE_SOURCE_VERIFIED')
        self.assertEqual(store.operations,['backfill_claim','backfill_feature_reuse_commit','backfill_verify'])
        with self.f.admin() as conn:
            page=conn.execute(f'SELECT record_count,raw_body FROM {self.f.schema}.backfill_pages_v2 WHERE task_id=%s',(task_id,)).fetchone()
            self.assertEqual(page['record_count'],1)
            self.assertEqual(json.loads(page['raw_body'])['rows'][0]['record_type'],'DERIVED_RETAINED_SOURCE_POINTER')
            proof=conn.execute(f'SELECT retained_feature_verification,reused_feature_records FROM {self.f.schema}.backfill_readbacks_v2 WHERE task_id=%s',(task_id,)).fetchone()
            self.assertTrue(proof['retained_feature_verification']['passed'])
            self.assertEqual(proof['reused_feature_records'],390)
            after=dict(conn.execute(f'SELECT requests_reserved,pages_committed,records_committed FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s',(self.run,)).fetchone())
        self.assertEqual(after['requests_reserved'],before['requests_reserved'])
        self.assertEqual(after['pages_committed'],before['pages_committed']+1)
        self.assertEqual(after['records_committed'],before['records_committed']+1)
        replacement_store=self.worker_store()
        self.assertEqual(BackfillWorker(replacement_store,NoExternalProvider(),worker_id='fixture-cache-worker-restarted').run_once()['state'],'idle')
        self.assertEqual(replacement_store.operations,['backfill_claim'])

    def test_real_worker_cache_miss_calculates_from_retained_input_automatically(self):
        _,task_id=self.setup_derived(claim_task=False,prefer_cache=True)
        with self.f.admin() as conn:
            conn.execute(f'DELETE FROM {self.f.schema}.feature_session_cache_remediated_v1')
        store=self.worker_store()
        result=BackfillWorker(store,NoExternalProvider(),worker_id='fixture-cache-fallback-worker').run_once()
        self.assertEqual(result['task_id'],task_id)
        self.assertIn('backfill_feature_reuse_commit',store.operations)
        self.assertIn('backfill_material',store.operations)
        self.assertIn('backfill_reuse_read',store.operations)
        self.assertEqual(store.operations.count('backfill_commit'),1)
        self.assertNotIn('backfill_reserve',store.operations)
        with self.f.admin() as conn:
            page=conn.execute(f'SELECT record_count,raw_body FROM {self.f.schema}.backfill_pages_v2 WHERE task_id=%s',(task_id,)).fetchone()
            raw=json.loads(page['raw_body'])
            self.assertEqual(page['record_count'],390)
            self.assertEqual(raw['formula_version'],'fixed3000-derived-v2.1')
            self.assertEqual(sum(r['values']['bar_present'] for r in raw['rows']),2)
            self.assertEqual(raw['rows'][2]['null_reasons']['close'],'SOURCE_BAR_NOT_RETURNED')
            proof=conn.execute(f'SELECT actual_records,reused_feature_records FROM {self.f.schema}.backfill_readbacks_v2 WHERE task_id=%s',(task_id,)).fetchone()
            self.assertEqual(dict(proof),{'actual_records':390,'reused_feature_records':0})

    def test_one_pointer_preserves_cache_and_counts390_logical_rows(self):
        _,claim=self.setup_derived()
        result=self.call('backfill_feature_reuse_commit',{'claim':self.fence(claim)})
        self.assertEqual(result['record_count'],1)
        self.assertEqual(result['reused_feature_rows'],390)
        self.assertEqual(result['qualifying_feature_rows'],2)
        self.assertEqual(result['formula_version'],'compact_intraday_float64_v1')
        verified=self.call('backfill_feature_reuse_verify',{'task_id':claim['id'],'page_no':0})
        self.assertTrue(verified['passed'],verified)
        readback=self.call('backfill_verify',{'claim':self.fence(claim),'page_no':0,'include_raw':False})
        self.assertEqual(readback['verification']['actual_records'],1)
        self.assertEqual(readback['verification']['target_records'],390)
        self.assertEqual(readback['verification']['reused_feature_records'],390)
        report=self.call('backfill_delivery_status',{'run_id':self.run},actor='api')['runs'][0]
        d01=next(r for r in report['families'] if r['family']=='D01')
        self.assertEqual(d01['committed_records'],390)
        self.assertEqual(d01['referenced_existing_records'],390)
        self.assertEqual(d01['referenced_usable_records'],2)
        again=self.call('backfill_feature_reuse_commit',{'claim':self.fence(claim)})
        self.assertEqual(again['state'],'already_committed')
        self.assertEqual(again['body_sha256'],result['body_sha256'])
        with self.f.admin() as conn:
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.retained_bars_fixture').fetchone()['n'],5)
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.feature_session_cache_remediated_v1').fetchone()['n'],1)
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_family_d01_v2 WHERE run_id=%s',(self.run,)).fetchone()['n'],390)
            row=conn.execute(f'SELECT source_row FROM {self.f.schema}.backfill_family_d01_v2 WHERE run_id=%s ORDER BY record_ordinal LIMIT 1',(self.run,)).fetchone()['source_row']
            self.assertEqual(row['formula_version'],'compact_intraday_float64_v1')
            self.assertNotIn('identity_eligible',row['quality_flags'])
            self.assertNotIn('archive_value_identity_eligible',row['values'])
            self.assertIsNone(row['values']['micro_quote_count'])
            self.assertIn('return_1m',row['null_reasons'])

    def test_miss_never_completes_task_or_adds_pointer(self):
        _,claim=self.setup_derived()
        with self.f.admin() as conn:
            conn.execute(f'DELETE FROM {self.f.schema}.feature_session_cache_remediated_v1')
        result=self.call('backfill_feature_reuse_commit',{'claim':self.fence(claim)})
        self.assertEqual(result['state'],'CACHE_NOT_REUSABLE')
        self.assertEqual(result['reason'],'CACHE_ROW_ABSENT')
        with self.f.admin() as conn:
            row=conn.execute(f'SELECT status,records_committed FROM {self.f.schema}.backfill_tasks_v2 WHERE id=%s',(claim['id'],)).fetchone()
            self.assertEqual(dict(row),{'status':'RUNNING','records_committed':0})
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_pages_v2 WHERE task_id=%s',(claim['id'],)).fetchone()['n'],0)

    def test_source_or_output_tamper_refuses_independent_readback(self):
        _,claim=self.setup_derived()
        self.call('backfill_feature_reuse_commit',{'claim':self.fence(claim)})
        with self.f.admin() as conn:
            conn.execute(f'UPDATE {self.f.schema}.feature_session_cache_remediated_v1 SET coefficient_values[1][1]=999')
        verified=self.call('backfill_feature_reuse_verify',{'task_id':claim['id'],'page_no':0})
        self.assertFalse(verified['passed'])
        self.assertEqual(verified['reason'],'CACHE_OUTPUT_HASH_MISMATCH')
        bad=self.f.rpc('backfill_verify',{'claim':self.fence(claim),'page_no':0,'include_raw':False},actor='worker')
        self.assertFalse(bad['ok'])
        with self.f.admin() as conn:
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_readbacks_v2 WHERE task_id=%s',(claim['id'],)).fetchone()['n'],0)

    def test_profile_and_identity_changes_decline_cache(self):
        _,claim=self.setup_derived()
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.retained_jobs_fixture SET config=jsonb_set(config,'{{feed}}','\"iex\"')")
        result=self.call('backfill_feature_reuse_commit',{'claim':self.fence(claim)})
        self.assertEqual(result['reason'],'RETAINED_SOURCE_PROFILE_NOT_FULLY_QUALIFIED')
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.shared_identity_contract_remediated_v1 SET identity_contract_sha256=sha256('changed'::bytea)")
        result=self.call('backfill_feature_reuse_commit',{'claim':self.fence(claim)})
        self.assertEqual(result['reason'],'IDENTITY_CONTRACT_HASH_MISMATCH')

    def test_changed_raw_source_and_missing_array_are_never_reused(self):
        _,claim=self.setup_derived()
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.retained_bars_fixture SET close=100.75 WHERE bar_ts='2025-09-02T13:30Z'")
        result=self.call('backfill_feature_reuse_commit',{'claim':self.fence(claim)})
        self.assertEqual(result['reason'],'RAW_SOURCE_HASH_OR_GRID_MISMATCH')
        with self.f.admin() as conn:
            conn.execute(f'UPDATE {self.f.schema}.feature_session_cache_remediated_v1 SET validity_codes=NULL')
        result=self.call('backfill_feature_reuse_commit',{'claim':self.fence(claim)})
        self.assertEqual(result['reason'],'CACHE_ARRAY_OR_SESSION_SHAPE_MISMATCH')

    def test_existing_gap_on_same_session_declines_old_cache(self):
        source,claim=self.setup_derived()
        self.task(kind='alpaca_stock_bars',family='P01',provider='Alpaca',
            scope={'symbols':['AAPL'],'member_ids':['member-1'],'reuse_parent':source['id'],
                   'calendar':[{'date':'2025-09-02','open':'09:30','close':'16:00'}]})
        result=self.call('backfill_feature_reuse_commit',{'claim':self.fence(claim)})
        self.assertEqual(result['reason'],'SESSION_HAS_PROVIDER_REPAIR_CHILD')

    def test_api_and_direct_private_access_denied(self):
        _,claim=self.setup_derived()
        with self.assertRaises(self.f.psycopg.Error) as denied:
            self.f.rpc('backfill_feature_reuse_commit',{'claim':self.fence(claim)},actor='api')
        self.assertEqual(denied.exception.sqlstate,'PT403')
        with self.f.admin() as conn:
            row=conn.execute("SELECT has_function_privilege(%s,%s,'EXECUTE') ok",(self.f.gateway,self.f.schema+'.backfill_feature_reuse_summary_v2(text)')).fetchone()
            self.assertFalse(row['ok'])
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",(claim['id'],))
        refused=self.f.rpc('backfill_feature_reuse_commit',{'claim':self.fence(claim)},actor='worker')
        self.assertFalse(refused['ok'])
        self.assertEqual(refused['error']['code'],'lease_lost')


if __name__=='__main__':
    unittest.main()
