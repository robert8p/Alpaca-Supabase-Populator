"""Independent20s maintenance budget; original8s artifact stays unchanged."""
import json
import os
from pathlib import Path
from time import perf_counter
import unittest

import test_backfill_runtime_status_performance_v2 as current

ROOT=Path(__file__).resolve().parents[2]
PERFORMANCE={}


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'),'Explicit disposable PostgreSQL required')
class RuntimeSummaryMaintenanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        current.RuntimeStatusPerformanceTests.setUpClass.__func__(cls)
        cls.maintenance_sql=cls.rewrite((ROOT/'sql/astra_backfill_runtime_summary_index_maintenance_v2.sql').read_text())

    full_query=staticmethod(current.RuntimeStatusPerformanceTests.full_query)
    rewrite=classmethod(current.RuntimeStatusPerformanceTests.rewrite.__func__)
    setUp=current.RuntimeStatusPerformanceTests.setUp
    report=current.RuntimeStatusPerformanceTests.report
    task=current.RuntimeStatusPerformanceTests.task

    def test_only_maintenance_deadline_changes_and_real_index_keeps_outputs_metadata_and_runtime_limits(self):
        old=(ROOT/'sql/astra_backfill_runtime_summary_index_v2.sql').read_text().split('BEGIN;',1)[1]
        new=(ROOT/'sql/astra_backfill_runtime_summary_index_maintenance_v2.sql').read_text().split('BEGIN;',1)[1]
        self.assertEqual(old,new.replace("statement_timeout='20s'","statement_timeout='8s'",1))
        with self.f.admin() as conn:
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_tasks_v2
                (id,run_id,family,provider,kind,scope,status,records_committed,last_progress_at)
                SELECT %s||'-maintenance-'||g,%s,'D01','DERIVED','derive_intraday',
                  jsonb_build_object('symbols',jsonb_build_array(CASE WHEN (g-1)%%3000=0 THEN 'AAPL' ELSE 'T'||(1+(g-1)%%3000) END),
                    'member_ids',jsonb_build_array('member-'||(1+(g-1)%%3000)),'padding',repeat(md5(g::text),30)),
                  CASE WHEN g%%2=0 THEN 'PENDING' ELSE 'NO_DATA_RETURNED' END,
                  CASE WHEN g%%2=0 THEN 0 ELSE g END,
                  CASE WHEN g%%2=0 THEN NULL ELSE '2026-10-30T04:00Z'::timestamptz END
                FROM generate_series(1,5000)g''',(self.run,self.run))
            relation=conn.execute('SELECT oid,relowner,relacl,reloptions FROM pg_class WHERE oid=%s::regclass',
                (self.f.schema+'.backfill_tasks_v2',)).fetchone()
            configs=conn.execute('''SELECT oid,proname,proowner,proacl,proconfig,prosrc FROM pg_proc
                WHERE oid=ANY(%s::regprocedure[]) ORDER BY oid''',([
                    self.f.schema+'.rpc_dispatch(text,jsonb)',self.f.schema+'.backfill_dispatch_v2(text,jsonb)',
                    'public.'+self.f.endpoint+'(text,jsonb)'],)).fetchall()
            settings=conn.execute("SELECT current_setting('statement_timeout') statement_timeout,current_setting('lock_timeout') lock_timeout").fetchone()
        before=self.report()
        with self.f.admin() as conn:
            started=perf_counter();conn.execute(self.maintenance_sql);build_seconds=perf_counter()-started
            self.assertEqual(conn.execute('SELECT oid,relowner,relacl,reloptions FROM pg_class WHERE oid=%s::regclass',
                (self.f.schema+'.backfill_tasks_v2',)).fetchone(),relation)
            self.assertEqual(conn.execute('''SELECT oid,proname,proowner,proacl,proconfig,prosrc FROM pg_proc
                WHERE oid=ANY(%s::regprocedure[]) ORDER BY oid''',([
                    self.f.schema+'.rpc_dispatch(text,jsonb)',self.f.schema+'.backfill_dispatch_v2(text,jsonb)',
                    'public.'+self.f.endpoint+'(text,jsonb)'],)).fetchall(),configs)
            self.assertEqual(conn.execute("SELECT current_setting('statement_timeout') statement_timeout,current_setting('lock_timeout') lock_timeout").fetchone(),settings)
            index=conn.execute('''SELECT i.indisunique,i.indisvalid,i.indisready,i.indnkeyatts,
                pg_get_indexdef(i.indexrelid) definition,pg_relation_size(i.indexrelid) bytes
                FROM pg_index i WHERE indexrelid=%s::regclass''',(self.f.schema+'.'+current.INDEX,)).fetchone()
            self.assertFalse(index['indisunique']);self.assertTrue(index['indisvalid']);self.assertTrue(index['indisready'])
            self.assertEqual(index['indnkeyatts'],7)
            self.assertIn('(run_id, family, kind, provider, status, records_committed, last_progress_at)',index['definition'])
        self.assertEqual(current.normalized(before),current.normalized(self.report()))
        with self.assertRaises(self.f.psycopg.Error),self.f.admin() as conn:conn.execute(self.maintenance_sql)
        PERFORMANCE['successful_build']={'tasks':5000,'seconds':build_seconds,'index_bytes':index['bytes'],
            'index_valid_ready_nonunique':True,'same_seven_keys':True,'complete_status_values_equal':True,
            'table_oid_owner_acl_options_unchanged':True,'runtime_functions_and_timeouts_unchanged':True,
            'session_settings_restored_after_commit':True,'existing_name_replay_rejected':True}

    def test_lock_deadline_stays_three_seconds_with_atomic_no_index_result(self):
        self.task()
        started=perf_counter()
        with self.f.admin() as holder:
            holder.execute(f'LOCK TABLE {self.f.schema}.backfill_tasks_v2 IN ROW EXCLUSIVE MODE')
            with self.assertRaises(self.f.psycopg.errors.LockNotAvailable),self.f.admin() as builder:
                builder.execute(self.maintenance_sql)
        elapsed=perf_counter()-started
        self.assertTrue(2.5<elapsed<5.5,elapsed)
        with self.f.admin() as conn:
            self.assertIsNone(conn.execute('SELECT to_regclass(%s) i',(self.f.schema+'.'+current.INDEX,)).fetchone()['i'])
        PERFORMANCE['blocked_build']={'seconds':elapsed,'sqlstate':'55P03','index_absent_after_rollback':True}

    def test_twenty_second_whole_do_timeout_rolls_back_a_completed_index(self):
        self.task()
        self.assertEqual(self.maintenance_sql.count('END $build$;'),1)
        # Add a deterministic local-only stall INSIDE the same DO, after the
        # exact ordinary CREATE INDEX. This proves the single statement budget
        # and rollback of already-performed DDL, without changing production SQL.
        delayed=self.maintenance_sql.replace('END $build$;',' PERFORM pg_sleep(21);\nEND $build$;')
        started=perf_counter()
        with self.assertRaises(self.f.psycopg.errors.QueryCanceled),self.f.admin() as builder:
            builder.execute(delayed)
        elapsed=perf_counter()-started
        self.assertTrue(19.5<elapsed<23,elapsed)
        with self.f.admin() as conn:
            self.assertIsNone(conn.execute('SELECT to_regclass(%s) i',(self.f.schema+'.'+current.INDEX,)).fetchone()['i'])
            self.assertEqual(conn.execute('SELECT pg_get_functiondef(%s::regprocedure) d',
                (self.f.schema+'.rpc_dispatch(text,jsonb)',)).fetchone()['d'],self.outer_rpc)
        PERFORMANCE['whole_do_timeout']={'seconds':elapsed,'sqlstate':'57014','delay_inside_same_do_after_index':True,
            'index_absent_after_rollback':True,'outer_rpc_definition_unchanged':True}


if __name__=='__main__':unittest.main()
