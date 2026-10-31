"""Actual PostgreSQL equivalence and scale checks for the inherited family report."""
from hashlib import sha256
import json
import os
from pathlib import Path
import unittest

import test_backfill_feature_reuse_v2 as cache
import test_backfill_nonminute_coverage_v2 as coverage
import test_backfill_retained_s02_v2 as s02
import test_backfill_runtime_v2 as runtime

ROOT = Path(__file__).resolve().parents[2]
PERFORMANCE_EVIDENCE = {}
REPORT_COLUMNS = ('family,planned_units,terminal_units,committed_records,verified_pages,archived_pages,'
                  'referenced_qualifying_records,referenced_usable_records,operational_error_units,'
                  'blocked_units,work_completion')


@unittest.skipUnless(os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'), 'Explicit disposable PostgreSQL required')
class FamilyReportPerformanceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        s02.RetainedS02Tests.setUpClass.__func__(cls)
        f = cls.fixture('runTest')
        with f.admin() as conn:
            for filename in ('astra_backfill_shared_records_v2.sql', 'astra_backfill_contract_registry_v2.sql'):
                conn.execute(cls.rewrite((ROOT / 'sql' / filename).read_text()))
            base = conn.execute('SELECT pg_get_viewdef(%s::regclass,true) d',
                (f.schema + '.backfill_family_receipt_status_v2',)).fetchone()['d']
            outer = conn.execute('SELECT pg_get_viewdef(%s::regclass,true) d',
                (f.schema + '.backfill_family_status_v2',)).fetchone()['d']
            replacements = {f.schema + '.backfill_family_receipt_status_v2':f.schema + '.performance_original_receipt_v2'}
            conn.execute(f'CREATE VIEW {f.schema}.performance_original_receipt_v2 WITH(security_invoker=true) AS ' + base)
            for suffix in ('selected_tasks', 'effective_pages', 'family_counts', 'variants', 'field_coverage'):
                original = f.schema + '.backfill_nonminute_' + suffix + '_v2'
                saved = f.schema + '.performance_original_' + suffix + '_v2'
                definition = conn.execute('SELECT pg_get_viewdef(%s::regclass,true) d', (original,)).fetchone()['d']
                for current, prior in replacements.items():
                    definition = definition.replace(current, prior)
                conn.execute(f'CREATE VIEW {saved} WITH(security_invoker=true) AS ' + definition)
                replacements[original] = saved
            saved_outer = outer
            for current, prior in replacements.items():
                saved_outer = saved_outer.replace(current, prior)
            conn.execute(f'CREATE VIEW {f.schema}.performance_original_family_v2 WITH(security_invoker=true) AS ' +
                saved_outer)
            cls.metadata_before = conn.execute('''SELECT oid,relowner,relacl,reloptions FROM pg_class
                WHERE oid=ANY(%s::regclass[]) ORDER BY oid''', ([f.schema + '.' + name for name in
                ('backfill_family_receipt_status_v2', 'backfill_nonminute_effective_pages_v2', 'backfill_family_status_v2')],)).fetchall()
            cls.outer_before = outer
            cls.migration = cls.rewrite((ROOT / 'sql/astra_backfill_family_report_performance_v2.sql').read_text())
            conn.execute(cls.migration)

    rewrite = classmethod(s02.RetainedS02Tests.rewrite.__func__)
    task = runtime.BackfillRuntimeTests.task
    call = runtime.BackfillRuntimeTests.call
    claim = runtime.BackfillRuntimeTests.claim
    fence = staticmethod(runtime.BackfillRuntimeTests.fence)
    owned = cache.CompactFeatureReuseTests.owned
    commit_source = cache.CompactFeatureReuseTests.commit_source
    setup_derived = cache.CompactFeatureReuseTests.setup_derived
    source_page = s02.RetainedS02Tests.source_page
    record = staticmethod(s02.RetainedS02Tests.record)
    seed = s02.RetainedS02Tests.seed
    prove = s02.RetainedS02Tests.prove
    task_for = coverage.NonminuteCoverageTests.task_for
    commit_rows = coverage.NonminuteCoverageTests.commit_rows
    verify = coverage.NonminuteCoverageTests.verify
    daily = staticmethod(coverage.NonminuteCoverageTests.daily)

    def setUp(self):
        cache.CompactFeatureReuseTests.setUp(self)
        with self.f.admin() as conn:
            for table in ('s02_record_fixture', 's02_page_fixture', 's02_document_fixture'):
                conn.execute(f'DELETE FROM {self.f.schema}.{table}')

    def reports(self, view='backfill_family_status_v2'):
        with self.f.admin() as conn:
            return conn.execute(f'SELECT to_jsonb(v) report FROM {self.f.schema}.{view} v WHERE run_id=%s ORDER BY family',
                (self.run,)).fetchall()

    def equivalent(self):
        current = self.reports()
        self.assertEqual(current, self.reports('performance_original_family_v2'))
        self.assertEqual(len(current), 16)
        return {r['report']['family']: r['report'] for r in current}

    def test_every_task_state_minute_alias_and_retry_deadline_preserve_full_report(self):
        states = ['PENDING', 'RUNNING', 'RETRY_WAIT', 'INGESTED', 'NO_DATA_RETURNED', 'NOT_APPLICABLE',
                  'PROVIDER_LIMITATION', 'IDENTITY_OR_QUALITY_UNRESOLVED', 'OPERATIONAL_ERROR',
                  'BLOCKED_EXTERNAL', 'SUPERSEDED_BY_SCOPE_CHANGE']
        cases = [('P01', 'alpaca_stock_bars', 'Alpaca', '1Min'),
                 ('P01', 'alpaca_stock_bars', 'Alpaca', '1Day'),
                 ('P01', 'derive_intraday', 'DERIVED', '1Min'),
                 ('P02', 'alpaca_stock_bars', 'Alpaca', '1Min'),
                 ('D02', 'derive_daily', 'DERIVED', '1Day'),
                 ('N01', 'massive_news', 'Massive', '1Day')]
        with self.f.admin() as conn:
            for i, (family, kind, provider, timeframe) in enumerate(cases):
                for j, status in enumerate(states):
                    conn.execute(f'''INSERT INTO {self.f.schema}.backfill_tasks_v2
                        (id,run_id,family,provider,kind,scope,status,owner,lease_until,next_retry_at)
                        VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                        (f'{self.run}-state-{i}-{j}', self.run, family, provider, kind,
                         json.dumps({'symbols':['AAPL'], 'member_ids':['member-1'], 'timeframe':timeframe}),
                         status, 'fixture-worker' if status == 'RUNNING' else None,
                         '2027-01-01T00:00Z' if status == 'RUNNING' else None, '2026-10-30T10:30Z'))
        report = self.equivalent()
        self.assertEqual(report['P01']['planned_units'], 33)
        self.assertEqual(report['P02']['planned_units'], 22)
        self.assertEqual(report['P02']['terminal_units'], 10)
        self.assertEqual(report['P02']['operational_error_units'], 2)
        self.assertEqual(report['P02']['work_completion'], 'PARTIAL_OPERATIONAL_FAILURE')

    def test_actual_retained_minute_feature_and_s02_readbacks_preserve_counts_and_wrappers(self):
        _, claim = self.setup_derived(prefer_cache=True)
        result = self.call('backfill_feature_reuse_commit', {'claim':self.fence(claim)})
        self.call('backfill_verify', {'claim':self.fence(claim), 'page_no':0, 'include_raw':False})
        self.assertEqual(result['record_count'], 1)
        self.source_page(1, [self.record(), self.record('T2')])
        self.assertEqual(self.seed(), 1)
        self.prove()
        report = self.equivalent()
        self.assertEqual(report['D01']['committed_records'], 390)
        # This retained-source fixture has two qualifying input bars and a
        # complete 390-slot derived clock grid; those counts remain distinct.
        self.assertEqual(report['D01']['referenced_qualifying_records'], 2)
        self.assertEqual(report['S02']['committed_records'], 2)
        self.assertEqual(report['S02']['nonminute_coverage']['referenced_source_observations'], 2)
        self.assertFalse(report['S02']['nonminute_coverage']['full_replacement_query_satisfied'])

    def test_view_identity_permissions_outer_definition_and_one_time_guard_are_unchanged(self):
        with self.f.admin() as conn:
            metadata = conn.execute('''SELECT oid,relowner,relacl,reloptions FROM pg_class
                WHERE oid=ANY(%s::regclass[]) ORDER BY oid''', ([self.f.schema + '.' + name for name in
                ('backfill_family_receipt_status_v2', 'backfill_nonminute_effective_pages_v2', 'backfill_family_status_v2')],)).fetchall()
            self.assertEqual(metadata, self.metadata_before)
            current = conn.execute('SELECT pg_get_viewdef(%s::regclass,true) d',
                (self.f.schema + '.backfill_family_status_v2',)).fetchone()['d']
            self.assertEqual(current, self.outer_before)
            for role in (self.f.gateway, self.f.outsider):
                self.assertFalse(conn.execute("SELECT has_table_privilege(%s,%s,'SELECT') allowed",
                    (role, self.f.schema + '.backfill_family_receipt_status_v2')).fetchone()['allowed'])
        with self.assertRaises(self.f.psycopg.Error), self.f.admin() as conn:
            conn.execute(self.migration)
        self.equivalent()

    def test_partial_and_completed_derived_revisions_keep_identical_selection(self):
        original = self.task_for()
        self.commit_rows(original, [self.daily(), self.daily('2025-09-03')])
        revision = self.task_for(identity_refresh_of=original['id'])
        self.commit_rows(revision, [self.daily(close=200)], next_cursor='derived-continuation')
        report = self.equivalent()['D02']['nonminute_coverage']
        self.assertEqual(report['selected_derived_records'], 2)
        self.assertEqual(report['superseded_or_incomplete_revision_records'], 1)
        continuing = self.claim(['derive_daily'])
        self.assertEqual(continuing['id'], revision['id'])
        self.commit_rows(continuing, [self.daily('2025-09-03', 200)])
        self.assertEqual(self.equivalent()['D02']['nonminute_coverage']['superseded_or_incomplete_revision_records'], 2)
        with self.f.admin() as conn:
            selected = conn.execute(f'''SELECT task_id FROM {self.f.schema}.backfill_nonminute_selected_tasks_v2
                WHERE run_id=%s AND family='D02' ''', (self.run,)).fetchall()
            self.assertEqual([r['task_id'] for r in selected], [revision['id']])

    def test_mixed_pointer_and_derived_pages_preserve_existing_role_group_join_semantics(self):
        original = self.task_for()
        self.commit_rows(original, [self.daily()], next_cursor='pointer-fixture-next')
        continuing = self.claim(['derive_daily'])
        self.assertEqual(continuing['id'], original['id'])
        self.commit_rows(continuing, [{'record_type':'RETAINED_REFERENCE_SOURCE_POINTER',
                                      'symbol':'AAPL', 'market_date':'2025-09-03'}])
        self.equivalent()
        with self.f.admin() as conn:
            rows = conn.execute(f'''SELECT page_no,root_task_id,identity_material_current,identity_invalidated,
                invalidation_reason,selected_output FROM {self.f.schema}.backfill_nonminute_effective_pages_v2
                WHERE task_id=%s ORDER BY page_no''', (original['id'],)).fetchall()
            old = conn.execute(f'''SELECT page_no,root_task_id,identity_material_current,identity_invalidated,
                invalidation_reason,selected_output FROM {self.f.schema}.performance_original_effective_pages_v2
                WHERE task_id=%s ORDER BY page_no''', (original['id'],)).fetchall()
            self.assertEqual(rows, old)
            self.assertEqual(len(rows), 4)
            self.assertTrue(all(r['root_task_id'] == original['id'] for r in rows))

    def test_report_scale_does_not_materialize_all_planned_tasks_for_page_counts(self):
        scale = int(os.environ.get('ASTRA_REPORT_PERFORMANCE_SCALE', '20000'))
        self.assertTrue(10000 <= scale <= 500000)
        with self.f.admin() as conn:
            # Real guarded task insertion; the read-only workload is deliberately
            # mostly pending, as it is in the observed live execution plan.
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_tasks_v2(id,run_id,family,provider,kind,scope)
                SELECT %s||'-scale-'||g,%s,
                    CASE WHEN g%%20=0 THEN 'P01' WHEN g%%10=0 THEN 'N01' ELSE 'D01' END,
                    CASE WHEN g%%20=0 THEN 'Alpaca' WHEN g%%10=0 THEN 'Massive' ELSE 'DERIVED' END,
                    CASE WHEN g%%20=0 THEN 'alpaca_stock_bars' WHEN g%%10=0 THEN 'massive_news' ELSE 'derive_intraday' END,
                    jsonb_build_object('symbols',jsonb_build_array(CASE WHEN (g-1)%%3000=0 THEN 'AAPL' ELSE 'T'||(1+(g-1)%%3000) END),
                      'member_ids',jsonb_build_array('member-'||(1+(g-1)%%3000)),
                      'timeframe','1Min','fixture_padding',repeat(md5(g::text),25))
                FROM generate_series(1,%s) g''', (self.run, self.run, scale))
            # Representative arrival shape: 1,500 immutable pages, of which
            # 300 feed non-minute coverage. Real readback and projection
            # functions process these source-independent derived fixtures.
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_tasks_v2
                (id,run_id,family,provider,kind,scope,status,generation,page_no,records_committed)
                SELECT %s||'-arrival-'||g,%s,CASE WHEN g%%5=0 THEN 'D02' ELSE 'D01' END,'DERIVED',
                    CASE WHEN g%%5=0 THEN 'derive_daily' ELSE 'derive_intraday' END,
                    '{{"symbols":["AAPL"],"member_ids":["member-1"]}}','INGESTED',1,1,1
                FROM generate_series(1,1500) g''', (self.run, self.run))
            raw = json.dumps({'rows':[{'symbol':'AAPL', 'member_id':'member-1', 'market_date':'2025-09-02',
                                      'values':{'raw_close':100, 'raw_volume':10}, 'null_reasons':{}}]})
            conn.execute(f'''INSERT INTO {self.f.schema}.backfill_pages_v2
                (task_id,page_no,run_id,generation,run_fence,provider,request,http_status,fetched_at,raw_body,
                 body_sha256,records_sha256,record_count,source_bytes,adapter_version)
                SELECT id,0,run_id,1,1,'DERIVED',jsonb_build_object('provider','DERIVED','kind',kind),200,
                    '2026-10-30T08:00Z',%s,%s,%s,1,%s,'synthetic-report-arrival'
                FROM {self.f.schema}.backfill_tasks_v2 WHERE run_id=%s AND id LIKE %s''',
                (raw, sha256(raw.encode()).hexdigest(), '0'*64, len(raw.encode()), self.run, self.run+'-arrival-%%'))
            conn.commit()
            conn.execute(f'''SELECT {self.f.schema}.backfill_recheck_page_v2(task_id,page_no)
                FROM {self.f.schema}.backfill_pages_v2 WHERE run_id=%s''', (self.run,)).fetchall()
            for table in ('backfill_tasks_v2', 'backfill_pages_v2', 'backfill_readbacks_v2', 'backfill_family_catalogue_v2'):
                conn.execute(f'ANALYZE {self.f.schema}.{table}')
            old_query = f'SELECT {REPORT_COLUMNS} FROM {self.f.schema}.performance_original_family_v2 WHERE run_id=%s ORDER BY family'
            new_query = f'SELECT {REPORT_COLUMNS} FROM {self.f.schema}.backfill_family_status_v2 WHERE run_id=%s ORDER BY family'
            self.assertEqual(conn.execute(old_query, (self.run,)).fetchall(), conn.execute(new_query, (self.run,)).fetchall())
            plans = {}
            for label, query in [('original', old_query), ('candidate', new_query)]:
                plans[label] = conn.execute('EXPLAIN(ANALYZE,BUFFERS,FORMAT JSON) ' + query, (self.run,)).fetchone()['QUERY PLAN'][0]
            def nodes(plan):
                yield plan
                for child in plan.get('Plans', []):
                    yield from nodes(child)
            self.assertTrue(any(n.get('CTE Name') == 'mapped_tasks' for n in nodes(plans['original']['Plan'])))
            self.assertFalse(any(n.get('CTE Name') == 'mapped_tasks' for n in nodes(plans['candidate']['Plan'])))
            # Three coverage branches may each rank once, but never once per
            # page. Other session/S02 window functions are also bounded here.
            self.assertTrue(all(n.get('Actual Loops', 0) <= 1 for n in nodes(plans['candidate']['Plan'])
                                if n.get('Node Type') == 'WindowAgg'))
            PERFORMANCE_EVIDENCE.update(scale=scale, arrived_pages=1500, nonminute_pages=300,
                fixture='actual_stage3_shared_registry_schema_with_3000_member_guarded_tasks_and_real_readback_projections',
                jit=conn.execute('SHOW jit').fetchone()['jit'], plans=plans,
                original_ms=plans['original']['Execution Time'], candidate_ms=plans['candidate']['Execution Time'],
                original_cost=plans['original']['Plan']['Total Cost'], candidate_cost=plans['candidate']['Plan']['Total Cost'])
            self.assertLess(plans['candidate']['Execution Time'], 8000)
        self.equivalent()


if __name__ == '__main__':
    unittest.main()
