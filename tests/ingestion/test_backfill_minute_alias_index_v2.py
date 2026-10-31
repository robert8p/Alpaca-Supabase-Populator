"""Exact minute-alias predicate, covering plans, and bounded transactional build."""
from hashlib import sha256
import json
import os
from pathlib import Path
from time import perf_counter
import unittest

import test_backfill_status_index_counts_v2 as current
import test_backfill_runtime_v2 as runtime

ROOT = Path(__file__).resolve().parents[2]
PERFORMANCE = {}
INDEX = 'backfill_tasks_minute_alias_status_v2'
PREDICATE = "family='P01' AND kind IN('alpaca_stock_bars','retained_reuse') AND COALESCE(scope->>'timeframe','1Min')='1Min'"


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'), 'Explicit disposable PostgreSQL required')
class MinuteAliasIndexTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        current.StatusIndexCountsTests.setUpClass.__func__(cls)
        cls.index_sql = cls.rewrite((ROOT / 'sql/astra_backfill_minute_alias_index_v2.sql').read_text())

    rewrite = classmethod(current.StatusIndexCountsTests.rewrite.__func__)
    task = runtime.BackfillRuntimeTests.task

    def setUp(self):
        f = self.fixture('runTest')
        with f.admin() as conn:
            conn.execute(f'DROP INDEX IF EXISTS {f.schema}.{INDEX}')
        runtime.BackfillRuntimeTests.setUp(self)

    def status(self, conn):
        result = conn.execute(self.status_sql.replace('p_run_id', '%(run)s::text'), {'run':self.run}).fetchone()
        body = next(iter(result.values()))
        body.pop('observed_at')
        return body

    def metadata(self, conn):
        return {
            'relations':conn.execute('''SELECT oid,relname,relowner,relacl,reloptions FROM pg_class
                WHERE oid=ANY(%s::regclass[]) ORDER BY relname''', ([self.f.schema + '.' + name for name in
                ('backfill_tasks_v2', 'backfill_family_receipt_status_v2', 'backfill_family_status_v2')],)).fetchall(),
            'views':conn.execute('''SELECT pg_get_viewdef(%s::regclass,true) receipt,
                pg_get_viewdef(%s::regclass,true) family''',
                (self.f.schema + '.backfill_family_receipt_status_v2', self.f.schema + '.backfill_family_status_v2')).fetchone(),
            'rpc':conn.execute('SELECT pg_get_functiondef(%s::regprocedure) definition',
                (self.f.schema + '.rpc_dispatch(text,jsonb)',)).fetchone(),
        }

    def test_exact_predicate_full_status_permissions_and_status_updates(self):
        cases = [
            ('P01','alpaca_stock_bars','Alpaca',{'timeframe':'1Min'},True),
            ('P01','alpaca_stock_bars','Alpaca',{},True),
            ('P01','retained_reuse','REUSE',{'timeframe':None},True),
            ('P01','retained_reuse','REUSE',{'timeframe':'1Min'},True),
            ('P01','alpaca_stock_bars','Alpaca',{'timeframe':'1Day'},False),
            ('P01','derive_intraday','DERIVED',{'timeframe':'1Min'},False),
            ('P01','alpaca_stock_bars','Alpaca',{'timeframe':''},False),
            ('P01','alpaca_stock_bars','Alpaca',{'timeframe':'1MIN'},False),
            ('P02','alpaca_stock_bars','Alpaca',{'timeframe':'1Min'},False),
            ('N01','alpaca_news','Alpaca',{},False),
        ]
        keys=[]
        for family,kind,provider,extra,_ in cases:
            keys.append(self.task(family=family,kind=kind,provider=provider,
                scope={'symbols':['AAPL'],'member_ids':['member-1'],**extra}))
        with self.f.admin() as conn:
            before=self.status(conn)
            metadata=self.metadata(conn)
            rows=conn.execute(f'SELECT to_jsonb(t) value FROM {self.f.schema}.backfill_tasks_v2 t WHERE run_id=%s ORDER BY id', (self.run,)).fetchall()
            conn.execute(self.index_sql)
            self.assertEqual(before,self.status(conn))
            self.assertEqual(metadata,self.metadata(conn))
            self.assertEqual(rows,conn.execute(f'SELECT to_jsonb(t) value FROM {self.f.schema}.backfill_tasks_v2 t WHERE run_id=%s ORDER BY id', (self.run,)).fetchall())
            record=conn.execute('''SELECT i.indisunique,i.indisvalid,i.indisready,i.indnkeyatts,
                pg_get_indexdef(i.indexrelid) definition FROM pg_index i WHERE indexrelid=%s::regclass''',
                (self.f.schema+'.'+INDEX,)).fetchone()
            self.assertFalse(record['indisunique']);self.assertTrue(record['indisvalid']);self.assertTrue(record['indisready'])
            self.assertEqual(record['indnkeyatts'],3)
            self.assertIn('(run_id, status, next_retry_at)',record['definition'])
            count=conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_tasks_v2 WHERE run_id=%s AND {PREDICATE}',(self.run,)).fetchone()['n']
            self.assertEqual(count,4)
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET status='RETRY_WAIT',next_retry_at='2026-10-30T12:00Z' WHERE id=%s",(keys[0],))
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET status='RETRY_WAIT',next_retry_at='2026-10-30T11:00Z' WHERE id=%s",(keys[2],))
            retries=conn.execute(f'''SELECT count(*) n,min(next_retry_at)::text deadline FROM {self.f.schema}.backfill_tasks_v2
                WHERE run_id=%s AND status='RETRY_WAIT' AND {PREDICATE}''',(self.run,)).fetchone()
            self.assertEqual(retries['n'],2);self.assertTrue(retries['deadline'].startswith('2026-10-30 11:00'))
            conn.execute(f"UPDATE {self.f.schema}.backfill_tasks_v2 SET status='NO_DATA_RETURNED' WHERE id=ANY(%s)",(keys[:4],))
            self.assertEqual(conn.execute(f'''SELECT count(*) n FROM {self.f.schema}.backfill_tasks_v2
                WHERE run_id=%s AND status='NO_DATA_RETURNED' AND {PREDICATE}''',(self.run,)).fetchone()['n'],4)
            for role in (self.f.gateway,self.f.outsider):
                self.assertFalse(conn.execute("SELECT has_table_privilege(%s,%s,'SELECT') allowed",
                    (role,self.f.schema+'.backfill_tasks_v2')).fetchone()['allowed'])

    def test_replay_conflicting_name_and_schema_drift_fail_before_creation(self):
        with self.f.admin() as conn:
            conn.execute(f'CREATE INDEX {INDEX} ON {self.f.schema}.backfill_tasks_v2(id)')
        with self.assertRaises(self.f.psycopg.Error) as conflict, self.f.admin() as conn:
            conn.execute(self.index_sql)
        self.assertIn('already exists',str(conflict.exception))
        with self.f.admin() as conn:
            self.assertIn('btree (id)',conn.execute('SELECT pg_get_indexdef(%s::regclass) d',(self.f.schema+'.'+INDEX,)).fetchone()['d'])
            conn.execute(f'DROP INDEX {self.f.schema}.{INDEX}')
            conn.execute(f'ALTER TABLE {self.f.schema}.backfill_tasks_v2 ALTER COLUMN next_retry_at DROP NOT NULL')
        try:
            with self.assertRaises(self.f.psycopg.Error) as drift, self.f.admin() as conn:
                conn.execute(self.index_sql)
            self.assertIn('column types',str(drift.exception))
            with self.f.admin() as conn:
                self.assertIsNone(conn.execute('SELECT to_regclass(%s) index',(self.f.schema+'.'+INDEX,)).fetchone()['index'])
        finally:
            with self.f.admin() as conn:
                conn.execute(f'ALTER TABLE {self.f.schema}.backfill_tasks_v2 ALTER COLUMN next_retry_at SET NOT NULL')
        with self.f.admin() as conn:
            conn.execute(self.index_sql)
        with self.assertRaises(self.f.psycopg.Error) as replay, self.f.admin() as conn:
            conn.execute(self.index_sql)
        self.assertIn('reconcile',str(replay.exception))

    def test_transactional_build_has_bounded_lock_failure_and_blocks_only_writes(self):
        key=self.task(family='P01',kind='alpaca_stock_bars')
        started=perf_counter()
        with self.f.admin() as holder:
            holder.execute(f'LOCK TABLE {self.f.schema}.backfill_tasks_v2 IN ROW EXCLUSIVE MODE')
            with self.assertRaises(self.f.psycopg.errors.LockNotAvailable), self.f.admin() as builder:
                builder.execute(self.index_sql)
        elapsed=perf_counter()-started
        self.assertTrue(2.5<elapsed<5.5,elapsed)
        with self.f.admin() as conn:
            self.assertIsNone(conn.execute('SELECT to_regclass(%s) index',(self.f.schema+'.'+INDEX,)).fetchone()['index'])
        # Emulate a delayed acknowledgement/history statement before COMMIT.
        # The exact eight-second deadline must roll back even a completed index.
        delayed=self.index_sql.rsplit('COMMIT;',1)[0]+"SELECT pg_sleep(9);\nCOMMIT;"
        timeout_started=perf_counter()
        with self.assertRaises(self.f.psycopg.errors.QueryCanceled), self.f.admin() as builder:
            builder.execute(delayed)
        timeout_seconds=perf_counter()-timeout_started
        self.assertTrue(7.5<timeout_seconds<10,timeout_seconds)
        with self.f.admin() as conn:
            self.assertIsNone(conn.execute('SELECT to_regclass(%s) index',(self.f.schema+'.'+INDEX,)).fetchone()['index'])
        with self.f.admin() as builder:
            # Same DDL and timeout configuration, holding only the final COMMIT
            # to observe the actual normal-index write lock in another session.
            builder.execute(self.index_sql.rsplit('COMMIT;',1)[0])
            with self.f.admin() as reader:
                self.assertEqual(reader.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_tasks_v2 WHERE id=%s',(key,)).fetchone()['n'],1)
            with self.assertRaises(self.f.psycopg.errors.LockNotAvailable), self.f.admin() as writer:
                writer.execute("SET LOCAL lock_timeout='250ms'")
                writer.execute(f'UPDATE {self.f.schema}.backfill_tasks_v2 SET priority=priority+1 WHERE id=%s',(key,))
            builder.commit()
        with self.f.admin() as writer:
            writer.execute(f'UPDATE {self.f.schema}.backfill_tasks_v2 SET priority=priority+1 WHERE id=%s',(key,))
        PERFORMANCE['lock_failure_seconds']=elapsed
        PERFORMANCE['timeout_rollback_seconds']=timeout_seconds
        PERFORMANCE['ordinary_reads_continue_and_task_writes_wait_until_commit']=True

    def test_wide_scale_build_and_covering_count_retry_plans_preserve_full_status(self):
        scale=int(os.environ.get('ASTRA_MINUTE_ALIAS_SCALE','30000'))
        self.assertTrue(10000<=scale<=600000)
        split=scale*4//5
        def seed(start,end):
            with self.f.admin() as conn:
                conn.execute(f'''INSERT INTO {self.f.schema}.backfill_tasks_v2
                    (id,run_id,family,provider,kind,scope,status,next_retry_at)
                    SELECT %s||'-alias-scale-'||g,%s,
                      CASE WHEN g%%20=0 THEN 'P01' WHEN g%%10=0 THEN 'N01' ELSE 'D01' END,
                      CASE WHEN g%%20=0 THEN 'Alpaca' WHEN g%%10=0 THEN 'Massive' ELSE 'DERIVED' END,
                      CASE WHEN g%%20=0 THEN 'alpaca_stock_bars' WHEN g%%10=0 THEN 'massive_news' ELSE 'derive_intraday' END,
                      jsonb_build_object('symbols',jsonb_build_array(CASE WHEN (g-1)%%3000=0 THEN 'AAPL' ELSE 'T'||(1+(g-1)%%3000) END),
                        'member_ids',jsonb_build_array('member-'||(1+(g-1)%%3000)),
                        'timeframe',CASE WHEN g%%100=0 THEN '1Day' ELSE '1Min' END,'padding',repeat(md5(g::text),30)),
                      CASE WHEN g%%140=0 THEN 'RETRY_WAIT' ELSE 'PENDING' END,'2026-10-30T12:00Z'
                    FROM generate_series(%s::integer,%s::integer)g''',(self.run,self.run,start,end))
        seed(1,split)
        with self.f.admin() as conn:
            conn.autocommit=True
            conn.execute(f'VACUUM(ANALYZE) {self.f.schema}.backfill_tasks_v2')
        seed(split+1,scale)
        query=self.status_sql.replace('p_run_id','%(run)s::text')
        with self.f.admin() as conn:
            conn.execute(f'ANALYZE {self.f.schema}.backfill_tasks_v2')
            before=self.status(conn)
            old_plan=conn.execute('EXPLAIN(ANALYZE,BUFFERS,FORMAT JSON) '+query,{'run':self.run}).fetchone()['QUERY PLAN'][0]
            started=perf_counter();conn.execute(self.index_sql);build_seconds=perf_counter()-started
            self.assertLess(build_seconds,8)
            self.assertEqual(before,self.status(conn))
            new_plan=conn.execute('EXPLAIN(ANALYZE,BUFFERS,FORMAT JSON) '+query,{'run':self.run}).fetchone()['QUERY PLAN'][0]
            indexed=[n for n in current.nodes(new_plan['Plan']) if n.get('Index Name')==INDEX and n.get('Node Type')=='Index Only Scan']
            self.assertTrue(indexed)
            alias_count=scale//20-scale//100
            count_scans=[n for n in indexed if n.get('Actual Rows')==alias_count]
            self.assertEqual(len(count_scans),1)
            self.assertEqual(count_scans[0]['Actual Loops'],1)
            self.assertLess(count_scans[0].get('Heap Fetches',scale),alias_count*0.3)
            plans={}
            count=f'SELECT status,count(*) FROM {self.f.schema}.backfill_tasks_v2 WHERE run_id=$1 AND {PREDICATE} GROUP BY status'
            retry=f"SELECT min(next_retry_at) FROM {self.f.schema}.backfill_tasks_v2 WHERE run_id=$1 AND status='RETRY_WAIT' AND {PREDICATE}"
            conn.execute('PREPARE alias_count(text) AS '+count)
            conn.execute('PREPARE alias_retry(text) AS '+retry)
            for mode in ('force_generic_plan','force_custom_plan'):
                conn.execute('SET plan_cache_mode='+mode);plans[mode]={}
                for label in ('count','retry'):
                    plan=conn.execute('EXPLAIN(ANALYZE,BUFFERS,FORMAT JSON) EXECUTE alias_'+label+"('"+self.run+"')").fetchone()['QUERY PLAN'][0]
                    scans=[n for n in current.nodes(plan['Plan']) if n.get('Relation Name')=='backfill_tasks_v2']
                    self.assertTrue(scans)
                    self.assertTrue(all(n.get('Node Type')=='Index Only Scan' and n.get('Index Name')==INDEX for n in scans),scans)
                    self.assertTrue(all('Filter' not in n for n in scans))
                    plans[mode][label]=plan
            size=conn.execute('SELECT pg_relation_size(%s::regclass) n',(self.f.schema+'.'+INDEX,)).fetchone()['n']
            self.assertLess(new_plan['Execution Time'],8000)
            PERFORMANCE.update(scale=scale,older_visible_tasks=split,recent_tasks=scale-split,
                qualifying_alias_tasks=alias_count,build_seconds=build_seconds,index_bytes=size,
                complete_status_equal=True,status_sha256=sha256(json.dumps(before,sort_keys=True).encode()).hexdigest(),
                count_heap_fetches=count_scans[0].get('Heap Fetches'),
                baseline_ms=old_plan['Execution Time'],candidate_ms=new_plan['Execution Time'],
                baseline_plan=old_plan,candidate_plan=new_plan,prepared_plans=plans)


if __name__=='__main__':
    unittest.main()
