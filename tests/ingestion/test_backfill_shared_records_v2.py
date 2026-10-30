"""Real PostgreSQL shared records, versions, links and bounded report counters."""
import hashlib
import json
import os
from pathlib import Path
from time import perf_counter
import unittest

from astra_ingestion.backfill_provider_v2 import parse_response, request_for
import test_backfill_retained_s02_v2 as s02
import test_backfill_runtime_v2 as runtime

ROOT=Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'),'Explicit disposable PostgreSQL required')
class SharedRecordsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s02.RetainedS02Tests.setUpClass.__func__(cls)
        f=cls.fixture('runTest')
        with f.admin() as conn:conn.execute(cls.rewrite((ROOT/'sql/astra_backfill_shared_records_v2.sql').read_text()))

    rewrite=classmethod(s02.RetainedS02Tests.rewrite.__func__)
    task=runtime.BackfillRuntimeTests.task
    call=runtime.BackfillRuntimeTests.call
    claim=runtime.BackfillRuntimeTests.claim
    fence=staticmethod(runtime.BackfillRuntimeTests.fence)
    setUp=runtime.BackfillRuntimeTests.setUp

    def new(self,kind='massive_news',family='N01',symbol='AAPL',member='member-1',**scope):
        provider='Massive' if kind.startswith('massive_') else 'Alpaca'
        key=self.task(kind=kind,family=family,provider=provider,scope={'symbols':[symbol],'member_ids':[member],
            'start':'2025-09-01T04:00:00Z','end':'2026-08-01T03:59:59.999999Z','target_start':'2025-09-01',
            'target_end':'2026-07-31','market_timezone':'America/New_York',**scope})
        claim=self.claim([kind]);self.assertEqual(claim['id'],key)
        return claim

    def commit(self,c,rows,*,verify=True,next_cursor=None):
        if c['kind']=='alpaca_news':body={'news':rows,'next_page_token':next_cursor}
        elif c['kind']=='alpaca_actions':body={'corporate_actions':rows,'next_page_token':next_cursor}
        elif c['kind']=='alpaca_option_contracts':body={'option_contracts':rows,'next_page_token':next_cursor}
        elif c['kind']=='alpaca_option_bars':body={'bars':rows,'next_page_token':next_cursor}
        else:
            body={'status':'OK','results':rows}
            if next_cursor:body['next_url']='https://api.massive.com'+request_for(c)['path']+'?cursor='+next_cursor
        raw=json.dumps(body);request=request_for(c);records,cursor,quality=parse_response(c,request,raw.encode())
        with self.f.admin() as conn:conn.execute(f'UPDATE {self.f.schema}.source_limits SET next_request_at=0')
        self.call('backfill_reserve',{'claim':self.fence(c)})
        payload={'claim':self.fence(c),'raw_body':raw,'body_sha256':hashlib.sha256(raw.encode()).hexdigest(),
            'http_status':200,'request':request,'records':list(records),'next_cursor':cursor,'quality':list(quality),
            'headers':{},'fetched_at':'2026-10-30T10:00:00Z','adapter_version':'shared-record-fixture-v2'}
        self.call('backfill_commit',payload)
        if verify:self.verify(c)
        return payload

    def verify(self,c):
        return self.call('backfill_verify',{'claim':self.fence(c),'page_no':c['page_no'],'include_raw':False})

    def report(self):
        return {f['family']:f for f in self.call('backfill_delivery_status',{'run_id':self.run},actor='api')['runs'][0]['families']}

    def rows(self,family):
        with self.f.admin() as conn:return conn.execute(f'SELECT * FROM {self.f.schema}.backfill_family_{family.lower()}_v2 WHERE run_id=%s',(self.run,)).fetchall()

    @staticmethod
    def article(**change):
        return {'id':'article-1','title':'Original title','published_utc':'2026-07-31T14:00:00Z',
            'tickers':['AAPL','T2'],'description':'Retained source text','article_url':'https://example.test/article/1','author':'Fixture',**change}

    def field(self,family,name,kind=None):
        rows=self.report()[family]['nonminute_coverage']['fields']
        return next(x for x in rows if x['field']==name and (kind is None or x['source_variant']==kind))

    def test_repeated_article_is_one_record_with_distinct_security_links_and_all_receipts(self):
        body=self.article(tickers=['AAPL','T2','T2'])
        c1=self.new();first=self.commit(c1,[body]);c2=self.new(symbol='T2',member='member-2');self.commit(c2,[body])
        r=self.report();self.assertEqual(len(r),16)
        cov=r['N01']['nonminute_coverage'];s=cov['shared_records']
        self.assertEqual(r['N01']['committed_records'],1)
        self.assertEqual((s['unique_articles'],s['verified_source_occurrences'],s['source_versions']),(1,2,1))
        self.assertEqual((s['article_security_links'],s['cohort_candidate_article_links']),(2,2))
        self.assertEqual(self.field('N01','title')['usable_values'],1)
        self.assertIsNone(cov['expected_applicable_records']);self.assertEqual(s['historically_attributed_article_links'],0)
        self.assertEqual(len(self.rows('N01')),1)
        with self.f.admin() as conn:
            links=conn.execute(f'SELECT security_symbol,candidate_member_ids FROM {self.f.schema}.backfill_article_security_links_v2 WHERE run_id=%s ORDER BY security_symbol',(self.run,)).fetchall()
            self.assertEqual([x['security_symbol'] for x in links],['AAPL','T2'])
            self.assertEqual([x['candidate_member_ids'] for x in links],[['member-1'],['member-2']])
            pages=conn.execute(f'SELECT raw_body FROM {self.f.schema}.backfill_pages_v2 WHERE run_id=%s',(self.run,)).fetchall()
            self.assertEqual(len(pages),2);self.assertTrue(all(x['raw_body']==first['raw_body'] for x in pages))
        self.assertEqual(self.call('backfill_commit',first)['state'],'already_committed')
        self.verify(c1);self.assertEqual(self.report()['N01']['committed_records'],1)

    def test_disjoint_version_links_are_retained_and_conflicting_fields_are_not_usable(self):
        self.commit(self.new(),[self.article(tickers=['AAPL'])])
        self.commit(self.new(symbol='T2',member='member-2'),[self.article(tickers=['T2'],title='Conflicting title')])
        s=self.report()['N01']['nonminute_coverage']['shared_records']
        self.assertEqual((s['unique_articles'],s['source_versions'],s['conflicting_records'],s['article_security_links']),(1,2,1,2))
        title=self.field('N01','title');self.assertEqual(title['usable_values'],0)
        self.assertEqual(title['null_or_unusable_reasons'],{'CONFLICTING_PROVIDER_RECORD_VERSIONS':1})
        self.assertIsNone(self.rows('N01')[0]['source_row']['title'])
        self.assertEqual(self.field('N01','description')['usable_values'],1)
        with self.f.admin() as conn:
            states=conn.execute(f'SELECT link_state FROM {self.f.schema}.backfill_article_security_links_v2 WHERE run_id=%s',(self.run,)).fetchall()
            self.assertEqual(len(states),2);self.assertTrue(all(x['link_state']=='CONFLICTING_PROVIDER_RECORD_LINK_VERSIONS' for x in states))

    def test_ordered_provider_updates_select_latest_and_provider_ids_do_not_cross_merge(self):
        self.commit(self.new(),[self.article(updated_utc='2026-07-31T15:00:00Z')])
        self.commit(self.new(),[self.article(updated_utc='2026-07-31T16:00:00Z',title='Provider correction')])
        self.assertEqual(self.rows('N01')[0]['source_row']['title'],'Provider correction')
        self.assertEqual(self.field('N01','title')['usable_values'],1)
        self.assertEqual(self.report()['N01']['nonminute_coverage']['shared_records']['conflicting_records'],0)
        self.commit(self.new(kind='alpaca_news'),[{'id':'article-1','headline':'Provider correction',
            'created_at':'2026-07-31T14:00:00Z','updated_at':'2026-07-31T16:00:00Z','symbols':['AAPL'],'content':'Text',
            'url':'https://example.test/article/1','author':'Fixture'}])
        s=self.report()['N01']['nonminute_coverage']['shared_records']
        self.assertEqual(s['unique_articles'],2);self.assertEqual(s['cross_provider_matching'],'NOT_ASSERTED')

    def test_missing_ids_use_explicit_content_fallback_without_inventing_article_identity(self):
        row=self.article();del row['id']
        self.commit(self.new(),[row,row]);self.commit(self.new(),[row])
        s=self.report()['N01']['nonminute_coverage']['shared_records']
        self.assertEqual((s['unique_articles'],s['fallback_content_keys'],s['verified_source_occurrences']),(1,1,3))
        self.assertIn('FALLBACK',self.rows('N01')[0]['source_row']['_shared_record']['identity_basis'])

    def test_alpaca_split_is_shared_by_reference_and_other_actions_stay_n02(self):
        c=self.new(kind='alpaca_actions',family='N02',start='2025-06-05',end='2026-10-30')
        self.commit(c,{'forward_splits':[{'id':'split-1','symbol':'AAPL','process_date':'2026-06-02','ex_date':'2026-06-01','old_rate':1,'new_rate':2}],
            'cash_dividends':[{'id':'cash-1','symbol':'AAPL','process_date':'2026-06-01','cash':0.5}]})
        r=self.report();self.assertEqual((r['N02']['committed_records'],r['N03']['committed_records']),(2,1))
        self.assertEqual((len(self.rows('N02')),len(self.rows('N03'))),(2,1))
        split=self.rows('N03')[0];self.assertEqual(split['task_id'],c['id']);self.assertEqual(split['source_row']['new_rate'],2)
        self.assertEqual(self.field('N03','new_rate')['usable_values'],1)
        with self.f.admin() as conn:
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_pages_v2 WHERE run_id=%s',(self.run,)).fetchone()['n'],1)
        self.assertEqual(r['N03']['archived_pages'],0)  # Shared receipt is not rewritten as a new physical N03 page.

    def test_new_york_publication_and_all_action_date_axes_include_boundary_events(self):
        self.commit(self.new(),[self.article(published_utc='2026-08-01T02:00:00Z')])
        row=self.rows('N01')[0];self.assertEqual(str(row['market_date']),'2026-07-31');self.assertTrue(row['target_window'])
        self.commit(self.new(kind='massive_dividends',family='N02'),[
            {'id':'boundary-1','ticker':'AAPL','declaration_date':'2026-07-30','ex_dividend_date':'2026-08-14','record_date':'2026-08-17','pay_date':'2026-08-21','cash_amount':1,'currency':'USD'},
            {'id':'boundary-2','ticker':'AAPL','declaration_date':'2025-08-01','ex_dividend_date':'2026-08-14','pay_date':'2026-08-21','cash_amount':1,'currency':'USD'}])
        cov=self.report()['N02']['nonminute_coverage'];s=cov['shared_records']
        self.assertEqual((cov['target_records'],cov['support_records'],cov['after_target_records']),(1,1,0))
        self.assertEqual((s['boundary_crossing_events'],s['boundary_support_events']),(2,1))
        decl=next(x for x in s['date_axes'] if x['date_axis']=='declaration_date' and x['period']=='TARGET')
        ex=next(x for x in s['date_axes'] if x['date_axis']=='ex_dividend_date' and x['period']=='AFTER_TARGET')
        self.assertEqual((decl['records'],ex['records']),(1,2))

    def test_contract_references_and_contract_session_bars_count_separately_with_conflicts(self):
        symbol='AAPL260117C00200000';contract={'id':'contract-1','symbol':symbol,'underlying_symbol':'AAPL','expiration_date':'2026-01-17',
            'strike_price':'200','type':'call','status':'inactive'}
        self.commit(self.new(kind='alpaca_option_contracts',family='CTX02',status='inactive'),[contract])
        self.commit(self.new(kind='alpaca_option_contracts',family='CTX02',status='inactive'),[contract])
        bar={'t':'2025-09-02T04:00:00Z','o':1,'h':2,'l':1,'c':2,'v':5,'n':2,'vw':1.5}
        self.commit(self.claim(['alpaca_option_bars']),{symbol:[bar]})
        self.commit(self.claim(['alpaca_option_bars']),{symbol:[{**bar,'v':6}]})
        r=self.report()['CTX02'];s=r['nonminute_coverage']['shared_records']
        self.assertEqual(r['committed_records'],1)
        self.assertEqual((s['unique_provider_record_keys'],s['unique_contract_references'],s['unique_contract_session_bars']),(2,1,1))
        self.assertEqual((s['verified_source_occurrences'],s['conflicting_records']),(4,1))
        self.assertEqual(self.field('CTX02','v',kind='alpaca_option_bars')['usable_values'],0)
        rows=self.rows('CTX02');self.assertEqual(len(rows),2)
        bar_row=next(x for x in rows if x['kind']=='alpaca_option_bars')
        self.assertIsNone(bar_row['source_row']['v']);self.assertEqual(bar_row['member_ids'],['member-1'])
        self.assertIn('PROVIDER_REPORTED_SECURITY_LINK',bar_row['lineage']['member_ids_basis'])
        with self.f.admin() as conn:
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_contract_underlying_links_v2 WHERE run_id=%s',(self.run,)).fetchone()['n'],1)
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_option_bar_underlying_links_v2 WHERE run_id=%s',(self.run,)).fetchone()['n'],1)

    def test_contract_id_omission_does_not_change_symbol_identity(self):
        contract={'id':'contract-id','symbol':'AAPL270117C00200000','underlying_symbol':'AAPL','expiration_date':'2027-01-17',
                  'strike_price':'200','type':'call','status':'inactive'}
        self.commit(self.new(kind='alpaca_option_contracts',family='CTX02',status='inactive'),[contract])
        missing_id={k:v for k,v in contract.items() if k!='id'}
        self.commit(self.new(kind='alpaca_option_contracts',family='CTX02',status='inactive'),[missing_id])
        s=self.report()['CTX02']['nonminute_coverage']['shared_records']
        self.assertEqual((s['unique_contract_references'],s['source_versions'],s['verified_source_occurrences']),(1,2,2))
        self.assertEqual(self.rows('CTX02')[0]['symbol'],contract['symbol'])
        self.assertEqual(self.field('CTX02','symbol')['usable_values'],1)
        self.assertEqual(self.field('CTX02','id')['usable_values'],0)
        with self.f.admin() as conn:
            links=conn.execute(f'SELECT contract_provider_id,candidate_member_ids FROM {self.f.schema}.backfill_contract_underlying_links_v2 WHERE run_id=%s',(self.run,)).fetchall()
            self.assertEqual(len(links),1);self.assertIsNone(links[0]['contract_provider_id']);self.assertEqual(links[0]['candidate_member_ids'],['member-1'])

    def test_undated_bars_keep_distinct_contracts_and_source_member_provenance(self):
        symbols=['AAPL270117C00200000','AAPL270117C00210000']
        bar={'t':'not-a-timestamp','o':1,'h':2,'l':1,'c':2,'v':5,'n':2,'vw':1.5}
        self.commit(self.new(kind='alpaca_option_bars',family='CTX02',symbols=symbols),{s:[bar] for s in symbols})
        s=self.report()['CTX02']['nonminute_coverage']['shared_records']
        self.assertEqual((s['unique_provider_record_keys'],s['unique_contract_session_bars'],s['non_session_option_bar_records']),(2,0,2))
        rows=self.rows('CTX02');self.assertEqual({r['symbol'] for r in rows},set(symbols))
        self.assertTrue(all(r['member_ids']==['member-1'] for r in rows))
        self.assertTrue(all(r['lineage']['member_ids_basis']=='SOURCE_QUERY_MEMBER_SCOPE_NOT_HISTORICAL_ATTRIBUTION' for r in rows))

    def test_action_security_conflict_does_not_publish_arbitrary_top_level_symbol(self):
        event={'id':'same-action','ticker':'AAPL','declaration_date':'2026-07-01','ex_dividend_date':'2026-07-02','cash_amount':1,'currency':'USD'}
        self.commit(self.new(kind='massive_dividends',family='N02'),[event])
        self.commit(self.new(kind='massive_dividends',family='N02',symbol='T2',member='member-2'),[{**event,'ticker':'T2'}])
        rows=self.rows('N02');self.assertEqual(len(rows),1)
        self.assertIsNone(rows[0]['symbol']);self.assertIsNone(rows[0]['source_row']['ticker'])
        self.assertEqual(rows[0]['member_ids'],['member-1','member-2'])
        self.assertEqual(self.field('N02','ticker')['usable_values'],0)

    def test_real_worker_verify_serializes_with_monitor_through_existing_gateway_lock(self):
        c=self.new();self.commit(c,[self.article()],verify=False)
        with self.f.admin() as worker, self.f.admin() as monitor:
            worker.execute(f'SET LOCAL ROLE {self.f.gateway}')
            worker.execute("SELECT set_config('request.headers',%s,true),set_config('request.jwt.claims',%s,true),set_config('request.method','POST',true),set_config('request.jwt.claim.sub','',true)",
                           (json.dumps({'x-astra-ingestion-token':self.f.tokens['worker']}),json.dumps({'role':self.f.gateway})))
            answer=worker.execute(f'SELECT public.{self.f.endpoint}(%s,%s::jsonb) value',
                ('backfill_verify',json.dumps({'claim':self.fence(c),'page_no':0,'include_raw':False}))).fetchone()['value']
            self.assertTrue(answer['ok'])  # Transaction still holds gateway, run-row and shared-projection locks.
            busy=monitor.execute(f'SELECT {self.f.schema}.backfill_maintain_v2(1) value').fetchone()['value']
            self.assertEqual(busy['state'],'BUSY')
            worker.commit()
            observed=monitor.execute(f'SELECT {self.f.schema}.backfill_maintain_v2(1) value').fetchone()['value']
            self.assertEqual(observed['state'],'OBSERVED')
        self.assertEqual(self.report()['N01']['committed_records'],1)

    def test_unverified_pages_are_excluded_and_catchup_is_bounded_idempotent(self):
        c=self.new();self.commit(c,[self.article()],verify=False)
        self.assertEqual(self.report()['N01']['committed_records'],0);self.assertEqual(self.rows('N01'),[])
        with self.f.admin() as conn:
            with self.assertRaises(self.f.psycopg.Error):conn.execute(f'SELECT {self.f.schema}.backfill_shared_project_v2(%s,0)',(c['id'],))
        with self.f.admin() as conn:conn.execute(f'ALTER TABLE {self.f.schema}.backfill_readbacks_v2 DISABLE TRIGGER backfill_shared_readback_v2')
        try:
            self.verify(c);second=self.new();self.commit(second,[self.article(id='article-2')])
        finally:
            with self.f.admin() as conn:conn.execute(f'ALTER TABLE {self.f.schema}.backfill_readbacks_v2 ENABLE TRIGGER backfill_shared_readback_v2')
        self.assertEqual(self.report()['N01']['nonminute_coverage']['shared_records']['projection_pending_verified_pages'],2)
        with self.f.admin() as conn:
            stamp=conn.execute(f'SELECT verified_at FROM {self.f.schema}.backfill_readbacks_v2 WHERE task_id=%s',(c['id'],)).fetchone()['verified_at']
            conn.execute(f'UPDATE {self.f.schema}.backfill_shared_cursor_v2 SET verified_at=%s,task_id=\'\',page_no=-1',(stamp,))
            self.assertEqual(conn.execute(f'SELECT {self.f.schema}.backfill_shared_maintain_v2(1) n').fetchone()['n'],1)
        self.assertEqual(self.report()['N01']['committed_records'],1)
        self.call('backfill_maintain',{'limit':1});self.assertEqual(self.report()['N01']['committed_records'],2)
        self.call('backfill_maintain',{'limit':1});self.assertEqual(self.report()['N01']['committed_records'],2)

    def test_report_uses_compact_counters_without_raw_or_canonical_record_scan_and_private_acl(self):
        c=self.new();rows=[self.article(id='article-'+str(i)) for i in range(1000)]
        start=perf_counter();self.commit(c,rows);elapsed=perf_counter()-start;self.assertLess(elapsed,12)
        with self.f.admin() as conn:
            definition=conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',(self.f.schema+'.backfill_page_rows_v2(text,integer)',)).fetchone()['d']
            conn.execute(f'''CREATE OR REPLACE FUNCTION {self.f.schema}.backfill_page_rows_v2(p_task_id text,p_page_no integer)
             RETURNS TABLE(record_ordinal bigint,symbol text,market_date date,session text,target_window boolean,record_group text,source_row jsonb)
             LANGUAGE plpgsql STABLE AS $$BEGIN RAISE EXCEPTION 'Status attempted raw reparse';END$$''')
        try:
            r=self.report()['N01'];self.assertEqual(r['committed_records'],1000)
            self.assertEqual(next(f for f in r['nonminute_coverage']['fields'] if f['field']=='title')['usable_values'],1000)
            with self.f.admin() as conn:
                plan=conn.execute(f'EXPLAIN (FORMAT JSON) SELECT * FROM {self.f.schema}.backfill_shared_family_summary_v2 WHERE run_id=%s',(self.run,)).fetchone()
                self.assertNotIn('backfill_shared_records_v2',json.dumps(plan))
                self.assertLess(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_shared_fields_v2 WHERE run_id=%s',(self.run,)).fetchone()['n'],100)
                acl=conn.execute('SELECT has_function_privilege(%s,%s,\'EXECUTE\') helper,has_table_privilege(%s,%s,\'SELECT\') raw',
                    (self.f.gateway,self.f.schema+'.backfill_shared_project_v2(text,integer)',self.f.outsider,self.f.schema+'.backfill_shared_versions_v2')).fetchone()
                self.assertFalse(acl['helper']);self.assertFalse(acl['raw'])
        finally:
            with self.f.admin() as conn:conn.execute(definition)

    def test_maximum_options_page_projects_within_the_bounded_verifier(self):
        symbols=['AAPL270117C'+str(2000000+i).zfill(8) for i in range(100)]
        dates=[e['date'] for e in json.loads((ROOT/'evidence/replacement-calendar-v1.json').read_text())['sessions']
               if '2025-09-01'<=e['date']<='2026-07-31'][:100]
        bars={symbol:[{'t':day+'T13:30:00Z','o':1,'h':2,'l':1,'c':2,'v':5,'n':2,'vw':1.5} for day in dates] for symbol in symbols}
        c=self.new(kind='alpaca_option_bars',family='CTX02',symbols=symbols)
        started=perf_counter();self.commit(c,bars);elapsed=perf_counter()-started
        self.assertLess(elapsed,15)
        summary=self.report()['CTX02']['nonminute_coverage']['shared_records']
        self.assertEqual(summary['unique_contract_session_bars'],10000)
        with self.f.admin() as conn:
            self.assertLess(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_shared_fields_v2 WHERE run_id=%s',(self.run,)).fetchone()['n'],100)


if __name__=='__main__':unittest.main()
