"""Real queue fairness with retained-gap and complete-cohort breadth guards."""
import json
import os
from pathlib import Path
import unittest

import test_backfill_reuse_commit_v2 as reuse

ROOT=Path(__file__).resolve().parents[2]


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'),'Explicit disposable PostgreSQL required')
class FamilyFairnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reuse.RetainedReuseCommitTests.setUpClass.__func__(cls)
        f=cls.fixture('runTest')
        for name in ('astra_backfill_delivery_v2.sql','astra_backfill_breadth_material_v2.sql',
                     'astra_backfill_delivery_performance_v2.sql','astra_backfill_provider_pacing_v2.sql',
                     'astra_backfill_family_fairness_v2.sql'):
            sql=(ROOT/'sql'/name).read_text().replace('astra_ingestion_v1',f.schema).replace('astra_ingestion_rpc_owner_v1',f.owner)
            with f.admin() as conn:
                conn.execute(sql)

    setUp=reuse.RetainedReuseCommitTests.setUp
    task=reuse.RetainedReuseCommitTests.task
    call=reuse.RetainedReuseCommitTests.call
    claim=reuse.RetainedReuseCommitTests.claim
    fence=staticmethod(reuse.RetainedReuseCommitTests.fence)
    owned=reuse.RetainedReuseCommitTests.owned
    commit=reuse.RetainedReuseCommitTests.commit
    children=reuse.RetainedReuseCommitTests.children
    complete_empty_provider_page=reuse.RetainedReuseCommitTests.complete_empty_provider_page

    def test_backlog_of_reference_and_prices_cannot_starve_other_source_families(self):
        for _ in range(30):
            self.task(family='REF01',kind='alpaca_reference',priority=1)
            self.task(family='P01',kind='alpaca_stock_bars',priority=1)
        kinds={'REF01':'alpaca_reference','P01':'alpaca_stock_bars','N01':'alpaca_news','N02':'alpaca_actions',
               'N03':'massive_splits','S01':'massive_short_volume','S02':'massive_short_interest','CTX02':'alpaca_option_contracts'}
        ids={}
        for family in ('N01','N02','N03','S01','S02','CTX02'):
            kind=kinds[family]
            ids[family]=self.task(family=family,kind=kind,provider='Massive' if kind.startswith('massive') else 'Alpaca',priority=200)
        claims=[self.claim(list(kinds.values()),worker='fair-worker-'+str(i)) for i in range(8)]
        self.assertEqual([c['family'] for c in claims],['REF01','P01','N01','N02','N03','S01','S02','CTX02'])
        self.assertEqual({c['family']:c['id'] for c in claims[2:]},ids)
        with self.f.admin() as conn:
            counts=conn.execute(f'SELECT requests_reserved,pages_committed,records_committed FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s',(self.run,)).fetchone()
            self.assertEqual(dict(counts),{'requests_reserved':0,'pages_committed':0,'records_committed':0})
            turn=conn.execute(f'SELECT next_family_index,claim_turns,last_family FROM {self.f.schema}.backfill_family_turn_v2 WHERE run_id=%s',(self.run,)).fetchone()
            self.assertEqual((turn['next_family_index'],turn['claim_turns'],turn['last_family']),(16,8,'CTX02'))

    def test_cursor_survives_worker_replacement_and_priority_remains_within_family(self):
        slow=self.task(family='REF01',kind='alpaca_reference',priority=50)
        first=self.task(family='REF01',kind='alpaca_reference',priority=1)
        news=self.task(family='N01',kind='alpaca_news',priority=999)
        kinds=['alpaca_reference','alpaca_news']
        self.assertEqual(self.claim(kinds,worker='before-restart')['id'],first)
        self.assertEqual(self.claim(kinds,worker='after-restart')['id'],news)
        self.assertEqual(self.claim(kinds,worker='after-restart')['id'],slow)

    def test_actual_candidate_query_uses_family_priority_index_without_backlog_sort(self):
        template=self.task(family='REF01',kind='alpaca_reference',priority=1)
        with self.f.admin() as conn:
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_tasks_v2(id,run_id,family,provider,kind,scope,priority)
                SELECT 'fairness-load-'||i,run_id,family,provider,kind,scope,1+mod(i,20)
                FROM {self.f.schema}.backfill_tasks_v2 CROSS JOIN generate_series(1,6000) i WHERE id=%s''',(template,))
            conn.execute(f'ANALYZE {self.f.schema}.backfill_tasks_v2')
            definition=conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (self.f.schema+'.backfill_dispatch_v2(text,jsonb)',)).fetchone()['d']
            start=definition.index('SELECT q.* INTO t FROM '+self.f.schema+'.backfill_tasks_v2 q JOIN')
            end=definition.index('LIMIT 1 FOR UPDATE OF q;',start)+len('LIMIT 1 FOR UPDATE OF q;')
            query=definition[start:end].replace('SELECT q.* INTO t FROM','SELECT q.* FROM')
            for old,new in (('v_fair_run','%(run)s'),('v_fair_pick.family','%(family)s'),
                            ('v_supported','%(supported)s::jsonb'),('v_now','clock_timestamp()')):
                query=query.replace(old,new)
            plan=conn.execute('EXPLAIN (ANALYZE,FORMAT JSON) '+query,
                {'run':self.run,'family':'REF01','supported':json.dumps(['alpaca_reference'])}).fetchone()['QUERY PLAN'][0]
        def descendants(node):
            yield node
            for child in node.get('Plans',[]):
                yield from descendants(child)
        nodes=list(descendants(plan['Plan']))
        task_scans=[node for node in nodes if node.get('Alias')=='q']
        self.assertEqual(len(task_scans),1)
        self.assertEqual(task_scans[0].get('Index Name'),'backfill_tasks_family_turn_v2')
        self.assertEqual(task_scans[0]['Actual Rows'],1)
        self.assertEqual(task_scans[0].get('Rows Removed by Filter',0),0)
        self.assertFalse(any(node['Node Type'] in ('Sort','Incremental Sort') for node in nodes))

    def test_retained_gap_dependency_still_blocks_only_affected_calculation(self):
        parent=self.owned();self.commit(parent)
        derived_id=self.task(kind='derive_intraday',provider='DERIVED',family='D01',dependencies=[parent['id']],
            scope={'symbols':['AAPL'],'member_ids':['member-1'],'input_start':'2025-09-01','target_end':'2025-09-30'},priority=0)
        self.assertIsNone(self.claim(['derive_intraday']))
        news=self.task(kind='alpaca_news',family='N01',priority=999)
        self.assertEqual(self.claim(['derive_intraday','alpaca_news'])['id'],news)
        gap=self.claim(['alpaca_stock_bars'])
        self.assertEqual(gap['scope']['reuse_parent'],parent['id'])
        self.assertEqual(self.complete_empty_provider_page(gap)['task_status'],'NO_DATA_RETURNED')
        self.assertEqual(self.claim(['derive_intraday'])['id'],derived_id)

    def test_breadth_and_missing_provider_do_not_block_configured_source_family(self):
        self.task(kind='derive_breadth',provider='DERIVED',family='CTX06',scope={
            'target_start':'2025-09-02','target_end':'2025-09-02','source_month':'2025-09-01',
            'representative_security':{'member-1':{'symbol':'AAPL','eligible':None}}},priority=0)
        massive=self.task(kind='massive_short_volume',provider='Massive',family='S01',priority=0)
        news=self.task(kind='alpaca_news',family='N01',priority=500)
        claim=self.claim(['derive_breadth','alpaca_news'])
        self.assertEqual(claim['id'],news)
        self.assertIsNone(self.claim(['derive_breadth','alpaca_news']))
        with self.f.admin() as conn:
            row=conn.execute(f'SELECT attempts,requests_reserved FROM {self.f.schema}.backfill_tasks_v2 WHERE id=%s',(massive,)).fetchone()
            self.assertEqual(dict(row),{'attempts':0,'requests_reserved':0})

    def test_retry_lease_and_stop_guards_remain_in_the_rotated_selection(self):
        future=self.task(kind='alpaca_news',family='N01',priority=0)
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET status='RETRY_WAIT',next_retry_at=clock_timestamp()+interval '2 hours' WHERE id=%s",(future,))
        now=self.task(kind='alpaca_reference',family='REF01',priority=1)
        first=self.claim(['alpaca_news','alpaca_reference'])
        self.assertEqual(first['id'],now)
        self.assertIsNone(self.claim(['alpaca_news','alpaca_reference']))
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",(now,))
        resumed=self.claim(['alpaca_news','alpaca_reference'])
        self.assertEqual(resumed['id'],now)
        self.assertGreater(resumed['generation'],first['generation'])
        with self.f.admin() as conn:
            before=conn.execute(f'SELECT claim_turns FROM {self.f.schema}.backfill_family_turn_v2 WHERE run_id=%s',(self.run,)).fetchone()['claim_turns']
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET status='PAUSED',fence=fence+1 WHERE id=%s",(self.run,))
        self.assertIsNone(self.claim(['alpaca_news','alpaca_reference']))
        rejected=self.f.rpc('backfill_reserve',{'claim':self.fence(resumed)},actor='worker')
        self.assertFalse(rejected['ok']);self.assertEqual(rejected['error']['code'],'lease_lost')
        with self.f.admin() as conn:
            after=conn.execute(f'SELECT claim_turns FROM {self.f.schema}.backfill_family_turn_v2 WHERE run_id=%s',(self.run,)).fetchone()['claim_turns']
            self.assertEqual(after,before)
            public=conn.execute('SELECT has_table_privilege(%s,%s,\'SELECT\') allowed',
                (self.f.gateway,self.f.schema+'.backfill_family_turn_v2')).fetchone()['allowed']
            outsider=conn.execute('SELECT has_table_privilege(%s,%s,\'SELECT\') allowed',
                (self.f.outsider,self.f.schema+'.backfill_family_turn_v2')).fetchone()['allowed']
            self.assertFalse(public);self.assertFalse(outsider)


if __name__=='__main__':unittest.main()
