"""Worker reuse, repair-page exhaustion and durable planner interleaving."""
from copy import deepcopy
from hashlib import sha256
import json
import os
import unittest

from astra_ingestion.backfill_provider_v2 import canonical
from astra_ingestion.backfill_worker_v2 import BackfillWorker
from astra_ingestion.rpc_store import RpcPersistenceError

import test_backfill_worker_v2 as worker_fixture
import test_backfill_reuse_commit_v2 as reuse_fixture


class NoExternalProvider:
    def supported_kinds(self):
        return ()

    def require_credentials(self, _claim):
        raise AssertionError('Retained/derived work must not require provider credentials')

    def fetch(self, _claim):
        raise AssertionError('Retained/derived work must not fetch provider data')


def material_fixture(*, exhausted):
    calendar=[{'date':'2025-09-02','open':'09:30','close':'09:32'}]
    source=worker_fixture.synthetic_claim(calendar)
    old_page=worker_fixture.synthetic_bar_page(source,2)
    retained=[{**row,'provenance_qualified':True,'valid_ohlcv':True} for row in old_page.records]
    retained.append({**retained[0],'provenance_qualified':False})
    source_parent={**source,'id':'retained-parent','kind':'retained_reuse','provider':'REUSE'}
    pointer=canonical({'rows':[{'source_digest':'b'*64}]})
    pointer_page={'task':source_parent,'page_no':0,'record_count':1,'raw_body':pointer,
                  'body_sha256':sha256(pointer.encode()).hexdigest(),'request':{'provider':'REUSE'}}
    count=2 if exhausted else 1
    repair_bars=deepcopy(json.loads(old_page.raw_body)['bars']['AAPL'][:count])
    for row in repair_bars:
        for key in ('o','h','l','c','vw'):
            row[key]+=10
    repair=canonical({'bars':{'AAPL':repair_bars},'next_page_token':None if exhausted else 'unresolved-next-page'})
    source_repair={**source,'id':'provider-repair','scope':{**source['scope'],'reuse_parent':'retained-parent'}}
    repair_page={'task':source_repair,'page_no':0,'record_count':count,'raw_body':repair,
                 'body_sha256':sha256(repair.encode()).hexdigest(),'request':old_page.request}
    claim={**source,'id':'calculation-task','kind':'derive_intraday','family':'D01','provider':'DERIVED',
           'scope':{**source['scope'],'input_start':'2025-09-02','target_start':'2025-09-02','target_end':'2025-09-02'}}
    class MaterialStore(worker_fixture.ScriptedStore):
        def _call(self,operation,payload):
            if operation=='backfill_material':
                self.calls.append((operation,payload))
                # Reverse lexical order deliberately: no order-dependent repair.
                return {'pages':[repair_page,pointer_page],'complete':True,'next_after':None}
            if operation=='backfill_reuse_read':
                self.calls.append((operation,payload))
                return {'rows':retained,'has_more':False,'next_after':None}
            return super()._call(operation,payload)
    return MaterialStore(claim),old_page,repair_bars


class BackfillReuseWorkerTests(unittest.TestCase):
    def test_exhausted_repair_replaces_retained_day_without_duplicate_inputs(self):
        store,old,repair=material_fixture(exhausted=True)
        BackfillWorker(store,NoExternalProvider()).run_once()
        rows=store.payload['records']
        self.assertEqual(len(rows),2)
        self.assertEqual([row['values']['close'] for row in rows],[bar['c'] for bar in repair])
        self.assertTrue(all(row['values']['bar_present'] for row in rows))
        receipt=json.loads(store.payload['raw_body'])
        original=next(x for x in receipt['input_lineage'] if x['task_id']=='retained-parent')
        self.assertEqual(original['material_records'],2)
        self.assertEqual(original['unusable_inputs_excluded'],1)
        self.assertNotIn('backfill_reserve',[op for op,_ in store.calls])

    def test_unfinished_repair_page_cannot_erase_unreplaced_retained_minute(self):
        store,old,_=material_fixture(exhausted=False)
        BackfillWorker(store,NoExternalProvider()).run_once()
        rows=store.payload['records']
        self.assertEqual(len(rows),2)
        # The changed first minute remains a conflict. The original second
        # minute must survive an unexhausted repair response.
        self.assertIsNone(rows[0]['values']['close'])
        self.assertEqual(rows[1]['values']['close'],old.records[1]['source']['c'])
        self.assertTrue(rows[1]['values']['bar_present'])

    def test_planning_interleaves_with_claims_and_stops_only_after_seal(self):
        class PlanningStore:
            def __init__(self):
                self.calls=[];self.plans=0

            def _call(self,operation,payload):
                self.calls.append((operation,payload))
                if operation=='backfill_plan_next':
                    self.plans+=1
                    return {'state':'FULL_PLAN_SEALED' if self.plans==2 else 'PLAN_ADVANCED',
                            'plan_complete':self.plans==2,'next_selection_order':self.plans+1}
                if operation=='backfill_claim':return None
                raise AssertionError(operation)
        store=PlanningStore();worker=BackfillWorker(store,NoExternalProvider(),planning_enabled=True)
        for _ in range(12):self.assertEqual(worker.run_once()['state'],'idle')
        self.assertEqual(store.plans,2)
        self.assertEqual([i for i,(op,_) in enumerate(store.calls) if op=='backfill_plan_next'],[0,6])
        self.assertEqual(sum(op=='backfill_claim' for op,_ in store.calls),12)
        args=store.calls[0][1]
        self.assertEqual(args['member_limit'],1)
        self.assertIn('retained_reuse',args['supported_kinds'])
        self.assertEqual(args['capability_revision'],worker.capability_revision)
        self.assertTrue(worker.plan_complete)

    def test_retained_source_readback_mismatch_is_fatal_without_refetch(self):
        claim=worker_fixture.synthetic_claim(kind='retained_reuse')
        class MismatchStore:
            def __init__(self):self.calls=[]
            def _call(self,operation,payload):
                self.calls.append(operation)
                if operation=='backfill_claim':return claim
                if operation=='backfill_reuse_commit':return {'body_sha256':'a'*64,'record_count':1}
                if operation=='backfill_verify':return {'state':'committed','body_sha256':'a'*64,'readback_sha256':'a'*64,'record_count':1}
                if operation=='backfill_reuse_verify':return {'passed':False,'state':'SOURCE_MISMATCH'}
                raise AssertionError(operation)
        store=MismatchStore()
        with self.assertRaises(RpcPersistenceError):BackfillWorker(store,NoExternalProvider()).run_once()
        self.assertEqual(store.calls,['backfill_claim','backfill_reuse_commit','backfill_verify','backfill_reuse_verify'])


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'),'Explicit disposable PostgreSQL required')
class BackfillReuseWorkerPostgreSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        reuse_fixture.RetainedReuseCommitTests.setUpClass.__func__(cls)

    setUp=reuse_fixture.RetainedReuseCommitTests.setUp
    task=reuse_fixture.RetainedReuseCommitTests.task
    call=reuse_fixture.RetainedReuseCommitTests.call

    def test_real_worker_commits_pointer_verifies_source_and_preserves_gap_successor(self):
        task_id=self.task(kind='retained_reuse',provider='REUSE',family='P01',scope=self.scope)
        test=self
        class DirectStore:
            def __init__(self):self.operations=[]
            def _call(self,operation,payload):
                self.operations.append(operation)
                return test.call(operation,payload)
        store=DirectStore();result=BackfillWorker(store,NoExternalProvider()).run_once()
        self.assertEqual(result['task_id'],task_id)
        self.assertEqual(result['reused_records'],5)
        self.assertEqual(result['new_market_rows_written'],0)
        self.assertIn('source_readback',result)
        self.assertEqual(store.operations,['backfill_claim','backfill_reuse_commit','backfill_verify','backfill_reuse_verify'])
        with self.f.admin() as conn:
            self.assertEqual(conn.execute(f'SELECT count(*) n FROM {self.f.schema}.retained_bars_fixture').fetchone()['n'],5)
            counters=dict(conn.execute(f'SELECT requests_reserved,pages_committed,records_committed FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s',(self.run,)).fetchone())
            children=conn.execute(f"SELECT kind,status,scope FROM {self.f.schema}.backfill_tasks_v2 WHERE run_id=%s AND scope->>'reuse_parent'=%s",(self.run,task_id)).fetchall()
        self.assertEqual(counters,{'requests_reserved':0,'pages_committed':1,'records_committed':1})
        self.assertEqual(len(children),1)
        self.assertEqual(children[0]['kind'],'alpaca_stock_bars')
        self.assertEqual(children[0]['status'],'PENDING')
        self.assertEqual(children[0]['scope']['calendar'][0]['date'],'2025-09-03')


if __name__=='__main__':unittest.main()
