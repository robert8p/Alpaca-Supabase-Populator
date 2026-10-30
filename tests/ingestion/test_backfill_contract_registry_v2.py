"""Retained option children, verified admissions and shared contract work."""
import json
import os
from pathlib import Path
from time import perf_counter
import unittest

import test_backfill_shared_records_v2 as shared
import test_backfill_runtime_v2 as runtime

ROOT=Path(__file__).resolve().parents[2]
START='2025-09-01T00:00:00-04:00'
END='2026-07-31T23:59:59-04:00'


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'),'Explicit disposable PostgreSQL required')
class ContractRegistryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        shared.SharedRecordsTests.setUpClass.__func__(cls)
        f=cls.fixture('runTest')
        with f.admin() as conn:conn.execute(cls.rewrite((ROOT/'sql/astra_backfill_contract_registry_v2.sql').read_text()))

    rewrite=classmethod(shared.SharedRecordsTests.rewrite.__func__)
    setUp=runtime.BackfillRuntimeTests.setUp
    task=runtime.BackfillRuntimeTests.task
    call=runtime.BackfillRuntimeTests.call
    claim=runtime.BackfillRuntimeTests.claim
    fence=staticmethod(runtime.BackfillRuntimeTests.fence)
    new=shared.SharedRecordsTests.new
    commit=shared.SharedRecordsTests.commit
    verify=shared.SharedRecordsTests.verify
    report=shared.SharedRecordsTests.report

    @staticmethod
    def contract(n=0,underlying='AAPL'):
        return {'id':'option-'+str(n),'symbol':'AAPL270117C'+str(2000000+n).zfill(8),'underlying_symbol':underlying,
                'expiration_date':'2027-01-17','strike_price':str(200+n/1000),'type':'call','status':'inactive'}

    @staticmethod
    def bar():
        return {'t':'2025-09-02T13:30:00Z','o':1,'h':2,'l':1,'c':2,'v':5,'n':2,'vw':1.5}

    def seed(self,limit=8):
        with self.f.admin() as conn:return conn.execute(f'SELECT {self.f.schema}.backfill_contract_seed_v2(%s,%s) n',(self.run,limit)).fetchone()['n']

    def children(self):
        with self.f.admin() as conn:return conn.execute(f"SELECT id,scope,status,cursor,page_no,generation,records_committed,requests_reserved,owner,lease_until FROM {self.f.schema}.backfill_tasks_v2 WHERE run_id=%s AND kind='alpaca_option_bars' ORDER BY created_at,id",(self.run,)).fetchall()

    def legacy(self,symbols,*,priority=100,member='member-1',end=END):
        with self.f.admin() as conn:conn.execute(f'ALTER TABLE {self.f.schema}.backfill_tasks_v2 DISABLE TRIGGER backfill_contract_child_insert_v2')
        try:
            return self.task(kind='alpaca_option_bars',family='CTX02',scope={'symbols':symbols,'member_ids':[member],
                'start':START,'end':end,'identity_status':'PROVIDER_CONTRACT_UNDERLYING_LINK','enumeration_parent':'retained-enumeration-parent'},priority=priority)
        finally:
            with self.f.admin() as conn:conn.execute(f'ALTER TABLE {self.f.schema}.backfill_tasks_v2 ENABLE TRIGGER backfill_contract_child_insert_v2')

    def legacy_commit(self,c,rows,next_cursor=None):
        with self.f.admin() as conn:conn.execute(f'ALTER TABLE {self.f.schema}.backfill_readbacks_v2 DISABLE TRIGGER backfill_contract_readback_v2')
        try:return self.commit(c,rows,next_cursor=next_cursor)
        finally:
            with self.f.admin() as conn:conn.execute(f'ALTER TABLE {self.f.schema}.backfill_readbacks_v2 ENABLE TRIGGER backfill_contract_readback_v2')

    def contract_summary(self):
        return self.report()['CTX02']['nonminute_coverage']['shared_records']['contract_work']

    def test_new_enumeration_waits_for_readback_and_reuses_global_contract_keys(self):
        self.seed();c=self.new(kind='alpaca_option_contracts',family='CTX02',status='inactive')
        payload=self.commit(c,[self.contract(0),self.contract(1)],verify=False)
        self.assertEqual(self.children(),[])
        self.assertEqual(self.contract_summary()['pending_enumeration_pages'],1)
        self.verify(c);before=self.children();self.assertEqual(len(before),1)
        second=self.new(kind='alpaca_option_contracts',family='CTX02',status='inactive')
        self.commit(second,[self.contract(1),self.contract(2)])
        after=self.children();self.assertEqual(len(after),2)
        self.assertEqual(after[1]['scope']['symbols'],[self.contract(2)['symbol']])
        s=self.contract_summary();self.assertEqual((s['registered_contract_windows'],s['parent_contract_links'],s['new_children_created']),(3,4,2))
        with self.f.admin() as conn:
            links=conn.execute(f'SELECT * FROM {self.f.schema}.backfill_contract_parent_work_v2 WHERE run_id=%s AND contract_symbol=%s',(self.run,self.contract(1)['symbol'])).fetchall()
            self.assertEqual(len(links),2);self.assertEqual(len({x['canonical_task_id'] for x in links}),1)
            self.assertTrue(all(not x['canonical_query_complete'] for x in links))
        self.assertEqual(self.call('backfill_commit',payload)['state'],'already_committed')
        self.verify(c);self.assertEqual(len(self.children()),2)

    def test_retained_complete_child_is_preferred_and_pending_duplicate_is_unchanged(self):
        symbol=self.contract()['symbol'];pending=self.legacy([symbol],priority=100)
        complete=self.legacy([symbol],priority=1);claim=self.claim(['alpaca_option_bars']);self.assertEqual(claim['id'],complete)
        self.legacy_commit(claim,{symbol:[self.bar()]});before={x['id']:dict(x) for x in self.children()}
        self.assertEqual(self.seed(1),1)
        with self.f.admin() as conn:self.assertFalse(conn.execute(f'SELECT seed_complete FROM {self.f.schema}.backfill_contract_state_v2 WHERE run_id=%s',(self.run,)).fetchone()['seed_complete'])
        c=self.new(kind='alpaca_option_contracts',family='CTX02',status='inactive');self.commit(c,[self.contract()])
        self.assertEqual(self.contract_summary()['pending_enumeration_pages'],1)
        self.call('backfill_maintain',{'limit':1})
        after={x['id']:dict(x) for x in self.children()};self.assertEqual(before,after)
        with self.f.admin() as conn:
            link=conn.execute(f'SELECT * FROM {self.f.schema}.backfill_contract_parent_work_v2 WHERE parent_task_id=%s',(c['id'],)).fetchone()
            self.assertEqual(link['canonical_task_id'],complete);self.assertTrue(link['canonical_query_complete'])
        self.assertEqual(after[pending]['status'],'PENDING')
        self.assertEqual(self.contract_summary()['existing_overlap_contract_links'],1)
        self.assertEqual(self.claim(['alpaca_option_bars'])['id'],pending)  # No silent virtual completion or dropped unit.

    def test_retained_partial_cursor_is_referenced_as_incomplete_and_new_symbols_get_successors(self):
        old=self.legacy([self.contract()['symbol']],priority=1);c=self.claim(['alpaca_option_bars'])
        self.legacy_commit(c,{self.contract()['symbol']:[self.bar()]},next_cursor='retained-next-page')
        before=dict(self.children()[0]);self.seed()
        parent=self.new(kind='alpaca_option_contracts',family='CTX02',status='inactive')
        self.commit(parent,[self.contract(),self.contract(1)])
        rows=self.children();self.assertEqual(len(rows),2);self.assertEqual(dict(rows[0]),before)
        self.assertEqual(rows[1]['scope']['symbols'],[self.contract(1)['symbol']])
        with self.f.admin() as conn:
            link=conn.execute(f'SELECT * FROM {self.f.schema}.backfill_contract_parent_work_v2 WHERE parent_task_id=%s AND contract_symbol=%s',(parent['id'],self.contract()['symbol'])).fetchone()
            self.assertEqual(link['canonical_task_id'],old);self.assertFalse(link['canonical_query_complete'])
        self.assertEqual(rows[0]['cursor'],'retained-next-page');self.assertEqual(rows[0]['page_no'],1)

    def test_different_windows_are_not_falsely_reused_and_many_parent_member_scopes_survive(self):
        symbol=self.contract()['symbol'];old=self.legacy([symbol],end='2026-06-30T23:59:59-04:00');self.seed()
        first=self.new(kind='alpaca_option_contracts',family='CTX02',status='inactive');self.commit(first,[self.contract()])
        second=self.new(kind='alpaca_option_contracts',family='CTX02',status='inactive',symbol='T2',member='member-2')
        self.commit(second,[self.contract(underlying='T2')])
        self.assertEqual(len(self.children()),2)
        with self.f.admin() as conn:
            links=conn.execute(f'SELECT parent_member_ids,canonical_task_member_ids,canonical_task_id FROM {self.f.schema}.backfill_contract_parent_work_v2 WHERE run_id=%s ORDER BY parent_member_ids::text',(self.run,)).fetchall()
            self.assertEqual([x['parent_member_ids'] for x in links],[['member-1'],['member-2']])
            self.assertEqual(len({x['canonical_task_id'] for x in links}),1);self.assertNotEqual(links[0]['canonical_task_id'],old)
            self.assertTrue(all(x['canonical_task_member_ids']==['member-1'] for x in links))

    def test_existing_running_lease_is_not_replaced_and_stale_enumeration_fence_is_rejected(self):
        self.legacy([self.contract()['symbol']]);running=self.claim(['alpaca_option_bars'])
        before=dict(self.children()[0]);self.seed()
        p=self.new(kind='alpaca_option_contracts',family='CTX02',status='inactive')
        with self.f.admin() as conn:conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET lease_until=clock_timestamp()-interval '1 second' WHERE id=%s",(p['id'],))
        new=self.claim(['alpaca_option_contracts'],worker='restarted-contract-worker')
        # Independent receipt readback is allowed; an old generation cannot reserve or commit new source work.
        stale=self.f.rpc('backfill_reserve',{'claim':self.fence(p)},actor='worker');self.assertFalse(stale['ok'])
        payload=self.commit(new,[self.contract()])
        self.assertFalse(self.f.rpc('backfill_commit',{**payload,'claim':self.fence(p)},actor='worker')['ok'])
        self.assertEqual(dict(self.children()[0]),before)
        self.assertEqual(len(self.children()),1);self.assertEqual(self.children()[0]['id'],running['id'])

    def test_full_enumeration_page_has_finite_batches_and_private_helpers(self):
        self.seed();p=self.new(kind='alpaca_option_contracts',family='CTX02',status='inactive')
        started=perf_counter();self.commit(p,[self.contract(i) for i in range(1000)]);elapsed=perf_counter()-started
        self.assertLess(elapsed,12);children=self.children();self.assertEqual(len(children),10)
        self.assertTrue(all(len(x['scope']['symbols'])==100 for x in children))
        self.assertEqual(len({s for c in children for s in c['scope']['symbols']}),1000)
        self.assertEqual(self.contract_summary()['registered_contract_windows'],1000)
        with self.f.admin() as conn:
            acl=conn.execute('SELECT has_function_privilege(%s,%s,\'EXECUTE\') helper,has_table_privilege(%s,%s,\'SELECT\') raw',
                (self.f.gateway,self.f.schema+'.backfill_contract_admit_page_v2(text,integer)',self.f.outsider,self.f.schema+'.backfill_contract_parent_links_v2')).fetchone()
            self.assertFalse(acl['helper']);self.assertFalse(acl['raw'])

    def test_retained_enumeration_discovery_queues_then_admits_one_page_per_successor(self):
        self.legacy([self.contract()['symbol']]);self.seed();parents=[]
        with self.f.admin() as conn:conn.execute(f'ALTER TABLE {self.f.schema}.backfill_readbacks_v2 DISABLE TRIGGER backfill_contract_readback_v2')
        try:
            for _ in range(2):
                p=self.new(kind='alpaca_option_contracts',family='CTX02',status='inactive');self.commit(p,[self.contract()]);parents.append(p)
        finally:
            with self.f.admin() as conn:conn.execute(f'ALTER TABLE {self.f.schema}.backfill_readbacks_v2 ENABLE TRIGGER backfill_contract_readback_v2')
        with self.f.admin() as conn:
            # Model pre-extension receipts: original immutable pages/readbacks
            # exist, but this new derived admission queue has no entries yet.
            conn.execute(f'DELETE FROM {self.f.schema}.backfill_contract_enumeration_v2 WHERE run_id=%s',(self.run,))
            stamp=conn.execute(f'SELECT verified_at FROM {self.f.schema}.backfill_readbacks_v2 WHERE task_id=%s',(parents[0]['id'],)).fetchone()['verified_at']
            conn.execute(f'UPDATE {self.f.schema}.backfill_contract_readback_cursor_v2 SET verified_at=%s,task_id=\'\',page_no=-1',(stamp,))
        self.assertEqual(self.contract_summary()['unreconciled_verified_enumeration_pages'],2)
        self.call('backfill_maintain',{'limit':1})
        self.assertEqual(self.contract_summary()['pending_enumeration_pages'],2)
        self.assertEqual(len(self.children()),1)
        self.call('backfill_maintain',{'limit':1})
        self.assertEqual(self.contract_summary()['pending_enumeration_pages'],1)
        self.call('backfill_maintain',{'limit':1})
        summary=self.contract_summary()
        self.assertEqual((summary['pending_enumeration_pages'],summary['unreconciled_verified_enumeration_pages']),(0,0))
        self.assertEqual(summary['parent_contract_links'],2);self.assertEqual(len(self.children()),1)
        self.assertEqual(self.children()[0]['status'],'PENDING')


if __name__=='__main__':unittest.main()
