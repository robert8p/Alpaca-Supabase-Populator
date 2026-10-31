"""Full fixed-cohort bounded planner against an explicit disposable PostgreSQL."""
import json
import os
from pathlib import Path
from time import perf_counter
import unittest
import uuid

import test_backfill_delivery_v2 as delivery

ROOT = Path(__file__).resolve().parents[2]
COHORT = json.loads((ROOT / 'evidence/replacement-cohort-v1.json').read_text())
CALENDAR = json.loads((ROOT / 'evidence/replacement-calendar-v1.json').read_text())
KINDS = ['alpaca_reference','alpaca_stock_bars','alpaca_news','alpaca_actions','alpaca_option_contracts',
         'alpaca_option_bars','massive_reference','massive_news','massive_dividends','massive_splits',
         'massive_short_volume','massive_short_interest','retained_reuse','derive_daily','derive_intraday','derive_breadth']


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'), 'Explicit disposable PostgreSQL required')
class BackfillPlannerTests(unittest.TestCase):
    cleanup_monitor = classmethod(delivery.BackfillDeliveryTests.cleanup_monitor.__func__)

    @classmethod
    def setUpClass(cls):
        delivery.BackfillDeliveryTests.setUpClass.__func__(cls)
        f=cls.fixture('runTest')
        with f.admin() as conn:
            conn.execute(f'CREATE TABLE {f.schema}.planner_reference_fixture(instrument_key integer PRIMARY KEY,symbol text,alpaca_asset_id uuid)')
            conn.execute(f'CREATE INDEX ON {f.schema}.planner_reference_fixture(symbol)')
            conn.execute(f"INSERT INTO {f.schema}.planner_reference_fixture VALUES(41,'NVDA','00000000-0000-0000-0000-000000000041')")
            sql=(ROOT/'sql/astra_backfill_planner_v2.sql').read_text()
            for old,new in [('reference.alpaca_fixed_window_instruments_v1',f.schema+'.planner_reference_fixture'),
                            ('astra_ingestion_v1',f.schema),('astra_ingestion_rpc_owner_v1',f.owner)]:
                sql=sql.replace(old,new)
            conn.execute(sql)

    def setUp(self):
        self.f=self.fixture('runTest');self.f.setUp()
        self.run='planner-test-'+uuid.uuid4().hex
        scope={'calendar':CALENDAR,'daily_support_start':'2025-06-05','intraday_support_start':'2025-08-04'}
        with self.f.admin() as conn:
            conn.execute(f"UPDATE {self.f.schema}.backfill_runs_v2 SET status='PAUSED',fence=fence+1 WHERE status='ACTIVE'")
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_runs_v2
                (id,instruction_sha256,cohort_sha256,cohort_manifest_sha256,cohort_ref,scope)
                VALUES(%s,%s,%s,%s,%s,%s)''',(self.run,'1'*64,COHORT['cohort_sha256'],
                COHORT['company_manifest_sha256'],COHORT['source'],json.dumps(scope)))
            with conn.cursor() as cur:
                cur.executemany(f'''INSERT INTO {self.f.schema}.backfill_members_v2
                    (run_id,member_id,selection_order,anchor_ticker,anchor) VALUES(%s,%s,%s,%s,%s)''',
                    [(self.run,m['member_id'],m['selection_order'],m['symbol'],json.dumps(m)) for m in COHORT['members']])

    def plan(self,limit=1,kinds=None):
        return self.f.ok('backfill_plan_next',{'run_id':self.run,'member_limit':limit,
                                             'supported_kinds':KINDS if kinds is None else kinds},actor='worker')

    def tasks(self):
        with self.f.admin() as conn:
            return conn.execute(f'SELECT * FROM {self.f.schema}.backfill_tasks_v2 WHERE run_id=%s ORDER BY id',(self.run,)).fetchall()

    def test_one_member_complete_static_workflows_and_actual_support_calendar(self):
        started=perf_counter();result=self.plan();elapsed=perf_counter()-started
        self.assertLess(elapsed,10)
        self.assertFalse(result['plan_complete'])
        self.assertEqual(result['planned_members'],1)
        self.assertEqual(result['next_selection_order'],2)
        rows=self.tasks()
        self.assertEqual(len(rows),319)
        self.assertEqual(result['inserted_tasks'],319)
        minutes=[r for r in rows if r['family']=='P01']
        self.assertEqual(len(minutes),12)
        self.assertTrue(all(r['kind']=='retained_reuse' for r in minutes))
        self.assertTrue(all(r['scope']['shared_families']==['P01','P02'] for r in minutes))
        self.assertTrue(all(r['scope']['alpaca_asset_id']=='00000000-0000-0000-0000-000000000041' for r in minutes))
        self.assertEqual(min(r['scope']['target_start'] for r in minutes),'2025-08-04')
        d01=[r for r in rows if r['family']=='D01']
        target_dates=[e['date'] for e in CALENDAR['sessions'] if '2025-09-01'<=e['date']<='2026-07-31']
        self.assertEqual(sorted(r['scope']['target_start'] for r in d01),target_dates)
        for row in d01:
            self.assertEqual(row['scope']['target_start'],row['scope']['target_end'])
            self.assertEqual(len(row['scope']['calendar']),1)
            self.assertEqual(len(row['dependencies']),1)
            self.assertIn(row['dependencies'][0],[r['id'] for r in minutes])
        early=next(r for r in d01 if r['scope']['target_start']=='2025-11-28')
        self.assertEqual(early['scope']['calendar'][0]['close'],'13:00')
        daily=[r for r in rows if r['kind']=='derive_daily']
        self.assertEqual(len(daily),44)
        for row in daily:
            support=[e for e in row['scope']['calendar'] if e['date']<row['scope']['target_start']]
            self.assertEqual(len(support),60)
            self.assertEqual(len(row['dependencies']),2)
        sources=[r for r in rows if r['kind']=='alpaca_stock_bars']
        self.assertEqual({r['scope']['adjustment'] for r in sources},{'raw','split'})
        self.assertTrue(all(r['scope']['input_start']=='2025-06-05' for r in sources))
        news=[r for r in rows if r['kind']=='massive_news']
        self.assertEqual(len(news),11)
        september=next(r for r in news if r['scope']['target_start']=='2025-09-01')
        self.assertEqual(september['scope']['start'],'2025-09-01T04:00:00Z')
        self.assertEqual(september['scope']['end'],'2025-10-01T03:59:59.999999Z')
        self.assertTrue(all(r['scope']['include_weekends_holidays'] for r in news))
        self.assertFalse(any(r['kind']=='alpaca_news' for r in rows))
        for kind in ['massive_dividends','massive_splits']:
            row=next(r for r in rows if r['kind']==kind)
            self.assertEqual(row['scope']['archive_date_filter'],'UNBOUNDED_PROVIDER_EVENT_HISTORY')
        options=[r for r in rows if r['kind']=='alpaca_option_contracts']
        self.assertEqual({r['scope']['status'] for r in options},{'active','inactive'})
        self.assertTrue(all(r['scope']['expiration_end']=='2099-12-31' for r in options))
        with self.f.admin() as conn:
            metadata=conn.execute(f'SELECT metadata FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s',(self.run,)).fetchone()['metadata']
            count=conn.execute(f'SELECT count(*) n FROM {self.f.schema}.backfill_plan_units_v2 WHERE run_id=%s',(self.run,)).fetchone()['n']
        self.assertEqual(count,319)
        self.assertEqual(len(metadata['workflow_plan']['families']),16)
        self.assertEqual(metadata['workflow_plan']['REF03']['mode'],'CONTINUOUS_AUDIT')
        self.assertFalse(metadata.get('planning_complete',False))

    def test_resume_advances_member_and_conditionally_admits_alpaca_news(self):
        first=self.plan()
        old_ids={r['id'] for r in self.tasks()}
        second=self.plan(kinds=[k for k in KINDS if not k.startswith('massive_')])
        self.assertEqual(second['planned_members'],2)
        self.assertEqual(second['inserted_tasks'],330)
        rows=self.tasks()
        self.assertEqual(len(rows),649)
        self.assertTrue(old_ids.issubset({r['id'] for r in rows}))
        member2=COHORT['members'][1]['member_id']
        second_rows=[r for r in rows if r['scope'].get('member_ids')==[member2]]
        self.assertEqual(len(second_rows),330)
        self.assertTrue(all(r['kind']=='alpaca_stock_bars' for r in second_rows if r['family']=='P01'))
        self.assertEqual(len([r for r in second_rows if r['kind']=='massive_news']),11)
        fallbacks=[r for r in second_rows if r['kind']=='alpaca_news']
        self.assertEqual(len(fallbacks),11)
        self.assertTrue(all(r['scope']['does_not_complete_primary_archive'] for r in fallbacks))
        self.assertTrue(all(r['scope']['alternative_reason']=='MASSIVE_WORKER_CONFIGURATION_UNAVAILABLE' for r in fallbacks))

    def test_member_limit_is_clamped_and_api_role_cannot_plan(self):
        with self.assertRaises(self.f.psycopg.Error) as denied:
            self.f.rpc('backfill_plan_next',{'run_id':self.run},actor='api')
        self.assertEqual(denied.exception.sqlstate,'PT403')
        result=self.plan(limit=100)
        self.assertEqual(result['members_admitted_this_call'],5)
        self.assertEqual(result['planned_members'],5)
        self.assertEqual(result['inserted_tasks'],319*5)
        with self.f.admin() as conn:
            acl=conn.execute('SELECT has_function_privilege(%s,%s,\'EXECUTE\') allowed',
                (self.f.gateway,self.f.schema+'.backfill_plan_next_v2(jsonb)')).fetchone()['allowed']
        self.assertFalse(acl)

    def test_conflicting_deterministic_task_rolls_back_cursor_and_new_admission(self):
        member=COHORT['members'][0]
        with self.f.admin() as conn:
            key=conn.execute(f'SELECT {self.f.schema}.backfill_plan_task_id_v2(%s,%s) id',
                             (self.run,member['member_id']+':daily-source:raw')).fetchone()['id']
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_tasks_v2
                (id,run_id,family,provider,kind,scope) VALUES(%s,%s,'REF01','Alpaca','alpaca_reference',%s)''',
                (key,self.run,json.dumps({'member_ids':[member['member_id']],'symbols':[member['symbol']]})))
        result=self.f.rpc('backfill_plan_next',{'run_id':self.run,'member_limit':1,'supported_kinds':KINDS},actor='worker')
        self.assertFalse(result['ok'])
        self.assertEqual(len(self.tasks()),1)
        with self.f.admin() as conn:
            metadata=conn.execute(f'SELECT metadata FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s',(self.run,)).fetchone()['metadata']
        self.assertNotIn('planner_next_selection_order',metadata)

    def test_breadth_uses_all_frozen_representatives_and_partial_plan_cannot_seal(self):
        self.plan()
        # Deliberately corrupt only this disposable fixture's planning cursor:
        # the independent full member/date seal must reject incomplete work.
        with self.f.admin() as conn:
            conn.execute(f'''UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=metadata||%s::jsonb WHERE id=%s''',
                         (json.dumps({'planner_phase':'BREADTH','planner_next_selection_order':3001,
                                      'planner_next_breadth_index':0}),self.run))
        result=self.plan()
        self.assertEqual(result['breadth_sessions'],1)
        breadth=next(r for r in self.tasks() if r['family']=='CTX06')
        representatives=breadth['scope']['representative_security']
        self.assertEqual(set(representatives),{m['member_id'] for m in COHORT['members']})
        self.assertTrue(all(representatives[m['member_id']]=={'symbol':m['symbol'],'eligible':None} for m in COHORT['members']))
        self.assertEqual(breadth['dependencies'],[])
        self.assertEqual(breadth['scope']['source_month'],'2025-09-01')
        self.assertEqual(breadth['scope']['target_start'],'2025-09-02')
        with self.f.admin() as conn:
            conn.execute(f'''UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=metadata||%s::jsonb WHERE id=%s''',
                         (json.dumps({'planner_next_breadth_index':229}),self.run))
        self.assertEqual(self.plan()['phase'],'SEAL')
        result=self.plan()
        self.assertEqual(result['state'],'INCOMPLETE_MEMBER_DATE_WORKFLOWS')
        self.assertFalse(result['plan_complete'])
        with self.f.admin() as conn:
            row=conn.execute(f'''SELECT metadata->>'planning_complete' complete,
                (SELECT count(*) FROM {self.f.schema}.backfill_plan_manifests_v2 WHERE run_id=%s) seals
                FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s''',(self.run,self.run)).fetchone()
        self.assertIsNone(row['complete'])
        self.assertEqual(row['seals'],0)


if __name__=='__main__':
    unittest.main()
