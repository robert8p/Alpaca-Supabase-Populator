"""Independent PostgreSQL checks for truthful non-minute observation accounting."""
import hashlib
import json
import os
from pathlib import Path
import unittest

from astra_ingestion.backfill_provider_v2 import request_for
import test_backfill_runtime_v2 as runtime
import test_backfill_feature_reuse_v2 as feature

ROOT=Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'),'Explicit disposable PostgreSQL required')
class NonminuteCoverageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        feature.CompactFeatureReuseTests.setUpClass.__func__(cls)
        f=cls.fixture('runTest')
        # Interface fixture for the independently delivered progressive-identity
        # layer. Coverage must respond to its invalidation signal, not mutate it.
        with f.admin() as conn:
            conn.execute(f'''CREATE TABLE {f.schema}.coverage_identity_fixture(
                task_id text PRIMARY KEY,identity_material_current boolean,identity_invalidated boolean NOT NULL DEFAULT false,invalidation_reason text)''')
            conn.execute(f'''CREATE VIEW {f.schema}.backfill_identity_output_validity_v2 WITH(security_invoker=true) AS
                SELECT t.id task_id,i.identity_material_current,COALESCE(i.identity_invalidated,false) identity_invalidated,i.invalidation_reason
                FROM {f.schema}.backfill_tasks_v2 t LEFT JOIN {f.schema}.coverage_identity_fixture i ON i.task_id=t.id
                WHERE t.kind IN('derive_daily','derive_intraday','derive_breadth')''')
            conn.execute(f'GRANT SELECT ON {f.schema}.coverage_identity_fixture,{f.schema}.backfill_identity_output_validity_v2 TO {f.owner}')
            sql=(ROOT/'sql/astra_backfill_nonminute_coverage_v2.sql').read_text().replace('astra_ingestion_v1',f.schema).replace('astra_ingestion_rpc_owner_v1',f.owner)
            conn.execute(sql)

    rewrite=classmethod(feature.CompactFeatureReuseTests.rewrite.__func__)
    setUp=feature.CompactFeatureReuseTests.setUp
    owned=feature.CompactFeatureReuseTests.owned
    commit_source=feature.CompactFeatureReuseTests.commit_source
    task=runtime.BackfillRuntimeTests.task
    call=runtime.BackfillRuntimeTests.call
    claim=runtime.BackfillRuntimeTests.claim
    fence=staticmethod(runtime.BackfillRuntimeTests.fence)

    def task_for(self,family='D02',kind='derive_daily',provider='DERIVED',**extra):
        scope={'symbols':['AAPL'],'member_ids':['member-1'],'start':'2025-08-01T00:00:00Z','end':'2026-08-31T23:59:59Z',
               'target_start':'2025-09-01','target_end':'2026-07-31','timeframe':'1Day','adjustment':'raw',**extra}
        key=self.task(family=family,kind=kind,provider=provider,scope=scope)
        c=self.claim([kind]);self.assertEqual(c['id'],key)
        return c

    def commit_rows(self,c,rows,*,next_cursor=None,verify=True,quality=None):
        if c['provider'] in ('Alpaca','Massive'):
            with self.f.admin() as conn:conn.execute(f'UPDATE {self.f.schema}.source_limits SET next_request_at=0')
            self.call('backfill_reserve',{'claim':self.fence(c)})
            request=request_for(c)
            if c['kind']=='alpaca_stock_bars':body={'bars':{'AAPL':rows},'next_page_token':next_cursor}
            elif c['kind']=='alpaca_news':body={'news':rows,'next_page_token':next_cursor}
            elif c['provider']=='Massive':body={'status':'OK','results':rows}
            else:raise AssertionError('Unsupported synthetic source fixture')
            records=[{'symbol':'AAPL','source':r} for r in rows]
        else:
            body={'rows':rows,'formula_version':'fixture-v2','input_lineage':[],'limitations':quality or []}
            records=rows;request={'provider':'DERIVED','kind':c['kind']}
        raw=json.dumps(body)
        payload={'claim':self.fence(c),'raw_body':raw,'body_sha256':hashlib.sha256(raw.encode()).hexdigest(),'http_status':200,
                 'request':request,'records':records,'next_cursor':next_cursor,'quality':quality or [],'headers':{},
                 'fetched_at':'2026-10-30T07:00:00Z','adapter_version':'coverage-fixture-v2'}
        self.call('backfill_commit',payload)
        if verify:self.verify(c)
        return payload

    def verify(self,c):
        return self.call('backfill_verify',{'claim':self.fence(c),'page_no':c['page_no'],'include_raw':False})

    def report(self):
        return {r['family']:r for r in self.call('backfill_delivery_status',{'run_id':self.run},actor='api')['runs'][0]['families']}

    @staticmethod
    def daily(day='2025-09-02',close=100,reason=None):
        return {'symbol':'AAPL','member_id':'member-1','market_date':day,
                'values':{'raw_close':close,'raw_volume':10,'dollar_volume':1000,'adjusted_close':100,'adjusted_volume':10,
                          'source_code':'ALPACA_SIP_1DAY_PROVIDER_DEFINITION','daily_basis':'PROVIDER_DAILY_NOT_ASSERTED_RTH',
                          'adjustment_basis':'PROVIDER_SPLIT_SERIES','availability':'ARCHIVED_PROVIDER_VALUES_NOT_ORIGINAL_RECEIPT_CERTIFIED'},
                'null_reasons':{'raw_close':reason} if reason else {},'quality_flags':{'historical_identity_qualified':False}}

    @staticmethod
    def bar(day):
        return {'t':day+'T04:00:00Z','o':100,'h':101,'l':99,'c':100,'v':10,'n':2,'vw':100}

    def test_d02_raw_split_and_derived_counts_are_separate_and_unknown_denominator_stays_null(self):
        raw=self.task_for(kind='alpaca_stock_bars',provider='Alpaca')
        payload=self.commit_rows(raw,[self.bar(d) for d in ('2025-08-29','2025-09-02','2026-08-03')])
        split=self.task_for(kind='alpaca_stock_bars',provider='Alpaca',adjustment='split')
        self.commit_rows(split,[self.bar('2025-08-29'),self.bar('2025-09-02')])
        derived=self.task_for()
        self.commit_rows(derived,[self.daily(),self.daily('2025-09-03',None,'SOURCE_DAILY_BAR_NOT_RETURNED')],
                         quality=[{'state':'IDENTITY_OR_QUALITY_UNRESOLVED','field':'raw_close','reason':'SOURCE_DAILY_BAR_NOT_RETURNED','affected_records':1}])
        families=self.report();self.assertEqual(len(families),16)
        d=families['D02'];cov=d['nonminute_coverage']
        self.assertEqual(d['committed_records'],2)
        self.assertEqual(cov['physical_receipt_records'],7)
        self.assertEqual((cov['source_observation_records'],cov['raw_daily_source_records'],cov['split_daily_source_records'],cov['selected_derived_records']),(5,3,2,2))
        self.assertIsNone(cov['expected_applicable_records']);self.assertIsNone(cov['coverage_fraction'])
        raw_variant=next(v for v in cov['variants'] if v['source_variant']=='ALPACA_1DAY_RAW')
        self.assertEqual((raw_variant['target_records'],raw_variant['support_records'],raw_variant['after_target_records']),(1,1,1))
        f=next(v for v in cov['fields'] if v['observation_role']=='DERIVED' and v['field']=='raw_close')
        self.assertEqual((f['observed_field_slots'],f['usable_values'],f['missing_values']),(2,1,1))
        self.assertEqual(f['null_or_unusable_reasons'],{'SOURCE_DAILY_BAR_NOT_RETURNED':1})
        with self.f.admin() as conn:
            p=conn.execute(f'SELECT raw_body,body_sha256 FROM {self.f.schema}.backfill_pages_v2 WHERE task_id=%s',(raw['id'],)).fetchone()
            b=conn.execute(f'SELECT body_sha256,readback_sha256,actual_records FROM {self.f.schema}.backfill_readbacks_v2 WHERE task_id=%s',(raw['id'],)).fetchone()
            self.assertEqual(p['raw_body'],payload['raw_body']);self.assertEqual(p['body_sha256'],b['readback_sha256']);self.assertEqual(b['actual_records'],3)
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_nonminute_selected_records_v2 WHERE run_id=%s AND family=\'D02\'',(self.run,)).fetchone()['n'],2)

    def test_partial_revision_cannot_displace_old_and_identity_revocation_blocks_usable_values(self):
        original=self.task_for();self.commit_rows(original,[self.daily(),self.daily('2025-09-03')])
        child=self.task_for(identity_refresh_of=original['id'],identity_material_sha256='a'*64)
        self.commit_rows(child,[self.daily(close=200)],next_cursor='derived-continuation')
        self.assertEqual(self.report()['D02']['committed_records'],2)
        with self.f.admin() as conn:
            conn.execute(f'INSERT INTO {self.f.schema}.coverage_identity_fixture VALUES(%s,false,true,%s)',
                (original['id'],'CURRENT_IDENTITY_EVIDENCE_CHANGED_RECOMPUTE_PENDING'))
        cov=self.report()['D02']['nonminute_coverage']
        self.assertEqual(cov['identity_invalidated_output_records'],2)
        close=next(v for v in cov['fields'] if v['field']=='raw_close')
        self.assertEqual((close['nonnull_values'],close['usable_values'],close['unusable_present_values']),(2,0,2))
        self.assertEqual(close['null_or_unusable_reasons'],{'CURRENT_IDENTITY_EVIDENCE_CHANGED_RECOMPUTE_PENDING':2})
        again=self.claim(['derive_daily']);self.assertEqual(again['id'],child['id'])
        self.commit_rows(again,[self.daily('2025-09-03',200)])
        cov=self.report()['D02']['nonminute_coverage']
        self.assertEqual((cov['all_derived_version_records'],cov['selected_derived_records'],cov['superseded_or_incomplete_revision_records']),(4,2,2))
        close=next(v for v in cov['fields'] if v['field']=='raw_close')
        self.assertEqual(close['usable_values'],2)

    def test_missing_publication_and_invalid_numbers_do_not_become_usable(self):
        c=self.task_for(family='S02',kind='massive_short_interest',provider='Massive')
        self.commit_rows(c,[{'ticker':'AAPL','settlement_date':'2026-07-15','short_interest':10,'avg_daily_volume':2,'days_to_cover':5},
                            {'ticker':'AAPL','settlement_date':'2026-07-31','short_interest':-1,'avg_daily_volume':0,'days_to_cover':None}])
        cov=self.report()['S02']['nonminute_coverage']
        f={x['field']:x for x in cov['fields']}
        self.assertEqual(f['publication_time']['usable_values'],0)
        self.assertEqual(f['publication_time']['null_or_unusable_reasons'],{'PUBLICATION_TIMESTAMP_NOT_SUPPLIED':2})
        self.assertEqual((f['short_interest']['usable_values'],f['short_interest']['unusable_present_values']),(1,1))
        self.assertEqual(f['avg_daily_volume']['usable_values'],2)
        self.assertIsNone(f['short_interest']['expected_applicable_field_slots'])

    def test_existing_verified_pages_are_caught_up_in_bounded_monotonic_batches(self):
        claims=[]
        with self.f.admin() as conn:conn.execute(f'ALTER TABLE {self.f.schema}.backfill_readbacks_v2 DISABLE TRIGGER backfill_nonminute_readback_v2')
        try:
            for _ in range(3):
                c=self.task_for();self.commit_rows(c,[self.daily()]);claims.append(c)
        finally:
            with self.f.admin() as conn:conn.execute(f'ALTER TABLE {self.f.schema}.backfill_readbacks_v2 ENABLE TRIGGER backfill_nonminute_readback_v2')
        with self.f.admin() as conn:
            # Advance through other test fixtures, then prove exactly one of
            # these previously verified pages is projected per bounded call.
            oldest=conn.execute(f'SELECT verified_at FROM {self.f.schema}.backfill_readbacks_v2 WHERE task_id=%s',(claims[0]['id'],)).fetchone()['verified_at']
            conn.execute(f'UPDATE {self.f.schema}.backfill_nonminute_projection_cursor_v2 SET verified_at=%s,task_id=\'\',page_no=-1',(oldest,))
            self.assertEqual(conn.execute(f'SELECT {self.f.schema}.backfill_nonminute_project_pending_v2(1) n').fetchone()['n'],1)
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_nonminute_pages_v2 WHERE run_id=%s',(self.run,)).fetchone()['n'],1)
        self.call('backfill_maintain',{'limit':1})
        self.assertEqual(self.report()['D02']['nonminute_coverage']['projection_pending_verified_pages'],0)
        with self.f.admin() as conn:
            self.assertEqual(conn.execute(f'SELECT {self.f.schema}.backfill_nonminute_project_pending_v2(8) n').fetchone()['n'],0)
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_nonminute_pages_v2 WHERE run_id=%s',(self.run,)).fetchone()['n'],3)

    def test_pointer_and_unknown_dates_stay_separate_from_native_observations(self):
        pointer=self.task_for(family='REF01')
        self.commit_rows(pointer,[{'record_type':'RETAINED_REFERENCE_SOURCE_POINTER','original_source_id':'synthetic-reference',
                                  'original_source_sha256':'f'*64,'referenced_reference_records':3000}])
        c=self.task_for(family='N01',kind='alpaca_news',provider='Alpaca')
        self.commit_rows(c,[{'id':1,'headline':'Fixture','created_at':None,'symbols':['AAPL']}])
        report=self.report()
        self.assertEqual(report['REF01']['committed_records'],0)
        self.assertEqual(report['REF01']['nonminute_coverage']['physical_pointer_records'],1)
        self.assertEqual(report['REF01']['nonminute_coverage']['source_observation_records'],0)
        self.assertEqual(report['N01']['nonminute_coverage']['unknown_date_records'],1)
        self.assertEqual(report['N01']['nonminute_coverage']['target_records'],0)

    def test_status_uses_projection_without_reading_raw_again_and_keeps_private_acl(self):
        c=self.task_for();self.commit_rows(c,[self.daily()])
        with self.f.admin() as conn:
            original=conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',(self.f.schema+'.backfill_page_rows_v2(text,integer)',)).fetchone()['d']
            conn.execute(f'''CREATE OR REPLACE FUNCTION {self.f.schema}.backfill_page_rows_v2(p_task_id text,p_page_no integer)
                RETURNS TABLE(record_ordinal bigint,symbol text,market_date date,session text,target_window boolean,record_group text,source_row jsonb)
                LANGUAGE plpgsql STABLE SET search_path='' AS $$ BEGIN RAISE EXCEPTION 'Raw page must not be read by coverage status'; END $$''')
        try:
            self.assertEqual(self.report()['D02']['committed_records'],1)
        finally:
            with self.f.admin() as conn:conn.execute(original)
        with self.f.admin() as conn:
            denied=conn.execute('SELECT has_table_privilege(%s,%s,\'SELECT\') view,has_function_privilege(%s,%s,\'EXECUTE\') helper',
                (self.f.outsider,self.f.schema+'.backfill_nonminute_field_coverage_v2',self.f.gateway,self.f.schema+'.backfill_nonminute_project_page_v2(text,integer)')).fetchone()
            self.assertFalse(denied['view']);self.assertFalse(denied['helper'])
            with self.assertRaises(self.f.psycopg.Error):
                conn.execute(f'UPDATE {self.f.schema}.backfill_nonminute_pages_v2 SET physical_records=0 WHERE task_id=%s',(c['id'],))

    def test_minute_overlap_and_d01_cache_accounting_stay_unchanged(self):
        source,derived=feature.CompactFeatureReuseTests.setup_derived(self)
        self.verify(source)
        self.call('backfill_feature_reuse_commit',{'claim':self.fence(derived)})
        self.verify(derived)
        report=self.report()
        self.assertEqual(len(report),16)
        self.assertEqual(report['P01']['committed_records'],2)
        self.assertEqual(report['P02']['committed_records'],2)
        self.assertEqual(report['D01']['committed_records'],390)
        self.assertEqual(report['D01']['referenced_usable_records'],2)
        self.assertTrue(all(report[f]['nonminute_coverage'] is None for f in ('P01','P02','D01','REF03')))


if __name__=='__main__':unittest.main()
