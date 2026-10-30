"""Real disposable-PG qualification for the narrowly aligned static-plan boundary.

Provider acquisition is not simulated as successful data: the positive fixture
contains synthetic static workflow definitions only. It exercises the actual
planner, coverage checker, representative-map logic, seal and install guards.
"""
from copy import deepcopy
from hashlib import sha256
import json
import os
from pathlib import Path
import re
import unittest

import test_backfill_planner_v2 as planner
import test_rpc_defer_lock_abort_retry_v77 as current

ROOT = Path(__file__).resolve().parents[2]
ARCHIVE = 'review/recovery-v78/planner-seal/candidate_archive_v78.json'
FORWARD = 'sql/astra_backfill_seal_dynamic_exclusions_v78.sql'
RESTORE = 'sql/astra_backfill_seal_dynamic_exclusions_restore_v78.sql'
OWNER = 'root-replacement-20261030T042603Z'
RUN = 'fixed3000-20250901-20260731-v1-20261030'
RESULT = {'production_calls': 0, 'provider_calls': 0, 'http_used': False,
          'fixture_semantics': 'Synthetic static workflow definitions; no provider acquisition or coverage completion claim', 'cases': {}}


def archive():
    value = json.loads((ROOT / ARCHIVE).read_text())
    for row in value['functions']:
        assert sha256(row['original_definition'].encode()).hexdigest() == row['source_sha256']
        assert sha256(row['candidate_definition'].encode()).hexdigest() == row['candidate_source_sha256']
    return value


class SourceBindingTests(unittest.TestCase):
    def test_exact_two_helper_delta_and_file_integrity(self):
        value = archive()
        self.assertEqual(len(value['functions']), 2)
        self.assertEqual(sum(r['predicate_replacements'] for r in value['functions']), 3)
        for row in value['functions']:
            self.assertEqual(row['candidate_definition'].replace(value['new_predicate'], value['old_predicate']), row['original_definition'])
        for name, proof in value['files'].items():
            raw = (ROOT / name).read_bytes()
            self.assertEqual(sha256(raw).hexdigest(), proof['sha256'])
            self.assertEqual(len(raw), proof['bytes'])


class SealPostgreSQLTests(unittest.TestCase):
    rewrite = classmethod(current.DeferPostgreSQLTests.rewrite.__func__)
    full_query = staticmethod(current.DeferPostgreSQLTests.full_query)

    @classmethod
    def setUpClass(cls):
        current.DeferPostgreSQLTests.setUpClass.__func__(cls)
        cls.candidate = archive()
        f = cls.fixture('runTest')
        with f.admin() as conn:
            RESULT['postgresql_version'] = conn.execute('SHOW server_version').fetchone()['server_version']

    @classmethod
    def adapt_definition(cls, text):
        f = cls.fixture('runTest')
        text = cls.rewrite(text).replace('public.astra_ingestion_rpc_v1', 'public.' + f.endpoint)
        return re.sub(r'\banon\b', f.gateway, text)

    def normalized(self, text):
        for before, after in self.production_normalization.items():
            text = text.replace(before, after)
        return text

    def setUp(self):
        planner.BackfillPlannerTests.setUp(self)
        self.install_metadata = {
            'implementation_owner': OWNER, 'implementation_lease_until': '2099-01-01T00:00:00Z',
            'implementation_reporting_policy': {'mode': 'DOT_CONSOLIDATED_CHECKPOINTS_ONLY'},
            'planner_phase': 'SEAL', 'planning_complete': False,
            'planner_next_selection_order': 3001, 'planner_next_breadth_index': 230,
            'planner_expected_static_count': 0, 'planner_preexisting_static_count': 0,
            'planner_version': 'fixed3000-plan-v2.1'}
        with self.f.admin() as conn:
            for row in self.candidate['functions']:
                conn.execute(self.adapt_definition(row['original_definition']))
            conn.execute(f'UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=%s WHERE id=%s',
                         (json.dumps(self.install_metadata), self.run))
        self.forward, self.restore = self.bound_migrations()

    def function_rows(self):
        with self.f.admin() as conn:
            rows = []
            for pin in self.candidate['protected_function_pins']:
                signature = self.adapt_definition(pin['signature'])
                row = conn.execute("SELECT oid::text oid,pg_get_functiondef(oid) definition,to_jsonb(p)-'prosrc' metadata,encode(sha256(convert_to((to_jsonb(p)-'prosrc')::text,'UTF8')),'hex') metadata_sha256 FROM pg_proc p WHERE oid=%s::regprocedure", (signature,)).fetchone()
                rows.append({'signature': pin['signature'], **dict(row)})
            return rows

    def bound_migrations(self):
        actual = {r['signature']: r for r in self.function_rows()}
        before, after = [], []
        changed = {r['signature']: r for r in self.candidate['functions']}
        observed = {}
        for pin in self.candidate['protected_function_pins']:
            row = actual[pin['signature']]
            observed[pin['signature']] = sha256(self.normalized(row['definition']).encode()).hexdigest()
            self.assertEqual(observed[pin['signature']], pin['source_sha256'], pin['signature'])
            local = {'signature': self.adapt_definition(pin['signature']), 'oid': row['oid'],
                     'source_sha256': sha256(row['definition'].encode()).hexdigest(),
                     'metadata_sha256': row['metadata_sha256']}
            before.append(local)
            revised = dict(local)
            if pin['signature'] in changed:
                revised['source_sha256'] = sha256(self.adapt_definition(changed[pin['signature']]['candidate_definition']).encode()).hexdigest()
            after.append(revised)
        RESULT['normalized_guard_dependency_sources'] = observed
        def prepare(path, b, a):
            sql = self.adapt_definition((ROOT / path).read_text()).replace(RUN, self.run)
            def literal(value):
                return "'" + json.dumps(value,separators=(',',':')).replace("'", "''") + "'::jsonb;"
            sql = re.sub(r"before_pins jsonb:='[^']*'::jsonb;", lambda _: 'before_pins jsonb:=' + literal(b), sql, count=1)
            sql = re.sub(r"after_pins jsonb:='[^']*'::jsonb;", lambda _: 'after_pins jsonb:=' + literal(a), sql, count=1)
            self.assertIn('count(*)=13', sql)
            return sql
        return prepare(FORWARD, before, after), prepare(RESTORE, after, before)

    def execute_migration(self, sql):
        with self.f.admin() as conn:
            conn.execute(sql)

    def metadata(self):
        with self.f.admin() as conn:
            return conn.execute(f'SELECT metadata FROM {self.f.schema}.backfill_runs_v2 WHERE id=%s', (self.run,)).fetchone()['metadata']

    def set_metadata(self, metadata):
        with self.f.admin() as conn:
            conn.execute(f'UPDATE {self.f.schema}.backfill_runs_v2 SET metadata=%s WHERE id=%s', (json.dumps(metadata),self.run))

    def rows(self):
        with self.f.admin() as conn:
            return {table: conn.execute(f'SELECT to_jsonb(t) r FROM {self.f.schema}.{table} t WHERE '+('id=%s' if table=='backfill_runs_v2' else 'run_id=%s')+' ORDER BY to_jsonb(t)::text',(self.run,)).fetchall()
                    for table in ('backfill_runs_v2','backfill_tasks_v2','backfill_members_v2','backfill_plan_units_v2','backfill_plan_coverage_v2','backfill_plan_manifests_v2','backfill_pages_v2','backfill_readbacks_v2','backfill_audit_v2')}

    def dynamic_identity(self):
        scope={'symbols':[planner.COHORT['members'][0]['symbol']], 'member_ids':[], 'shared_cohort_reference':True,
               'cohort_sha256':planner.COHORT['cohort_sha256'],'plan_static':False,'target_start':'2025-09-01','target_end':'2026-07-31','market_timezone':'America/New_York'}
        with self.f.admin() as conn:
            conn.execute(f"INSERT INTO {self.f.schema}.backfill_tasks_v2(id,run_id,family,provider,kind,scope,attempts,requests_reserved,records_committed) VALUES(%s,%s,'REF01','REUSE','retained_identity',%s,3,2,7)",(self.run+':dynamic',self.run,json.dumps(scope)))

    def plan(self):
        return self.f.ok('backfill_plan_next',{'run_id':self.run,'member_limit':1,'supported_kinds':planner.KINDS},actor='worker')

    def manifest_arguments(self):
        with self.f.admin() as conn:
            rows=conn.execute(f'SELECT task_id,definition_sha256 FROM {self.f.schema}.backfill_plan_units_v2 WHERE run_id=%s ORDER BY task_id COLLATE "C"',(self.run,)).fetchall()
        digest=sha256('\n'.join(r['task_id']+':'+r['definition_sha256'] for r in rows).encode()).hexdigest()
        workflow={'version':'synthetic-complete-static-plan-v78','target_start':'2025-09-01','target_end':'2026-07-31','market_timezone':'America/New_York','representative_policy':'Every exact frozen member retains its explicit anchor and unknown eligibility','session_dates':[x['date'] for x in planner.CALENDAR['sessions'] if '2025-09-01'<=x['date']<='2026-07-31']}
        return len(rows),digest,workflow

    def seal_direct(self, count=None, digest=None):
        n,h,workflow=self.manifest_arguments()
        with self.f.admin() as conn:
            return conn.execute(f'SELECT {self.f.schema}.backfill_seal_plan_v2(%s,%s,%s,%s) result',(self.run,n if count is None else count,h if digest is None else digest,json.dumps(workflow))).fetchone()['result']

    def seed_complete_static_workflows(self, invalid_map=False):
        members=planner.COHORT['members']; ids=[m['member_id'] for m in members]
        representative={m['member_id']:{'symbol':m['symbol'],'eligible':None} for m in members}
        if invalid_map: representative.pop(ids[-1])
        with self.f.admin() as conn:
            for family in ('REF01','P01','D01','D02','D03','D04','D05','N01','N02','N03','S01','S02','CTX02','CTX06'):
                scope={'symbols':[members[0]['symbol']],'member_ids':ids,'target_start':'2025-09-01','target_end':'2026-07-31','market_timezone':'America/New_York'}
                if family=='CTX06':scope['representative_security']=representative
                conn.execute(f'INSERT INTO {self.f.schema}.backfill_tasks_v2(id,run_id,family,provider,kind,scope) VALUES(%s,%s,%s,\'Alpaca\',%s,%s)',(self.run+':static:'+family,self.run,family,'alpaca_stock_bars' if family=='P01' else 'alpaca_reference',json.dumps(scope)))
        count,_,_=self.manifest_arguments()
        metadata=self.metadata();metadata['planner_expected_static_count']=count;self.set_metadata(metadata)
        return count

    def test_forward_inverse_preserve_metadata_accounting_and_refuse_replays(self):
        self.dynamic_identity(); before=self.rows(); functions=self.function_rows()
        self.execute_migration(self.forward)
        self.assertEqual(self.rows(),before)
        after=self.function_rows()
        self.assertEqual([(r['oid'],r['metadata']) for r in functions],[(r['oid'],r['metadata']) for r in after])
        self.assertEqual(sum(a['definition']!=b['definition'] for a,b in zip(functions,after)),2)
        with self.assertRaises(self.f.psycopg.Error):self.execute_migration(self.forward)
        self.assertEqual(self.rows(),before)
        self.execute_migration(self.restore)
        self.assertEqual(self.function_rows(),functions);self.assertEqual(self.rows(),before)
        with self.assertRaises(self.f.psycopg.Error):self.execute_migration(self.restore)
        RESULT['cases']['forward_inverse']={'two_sources_only':True,'oids_full_metadata_business_rows_unchanged':True,'forward_and_inverse_replay_refused':True}

    def test_installation_authority_and_phase_guards_fail_closed(self):
        variants={'owner':{'implementation_owner':'other-owner'},'null_lease':{'implementation_lease_until':None},'infinite_lease':{'implementation_lease_until':'infinity'},'expired_lease':{'implementation_lease_until':'2000-01-01T00:00:00Z'},'wrong_phase':{'planner_phase':'MEMBERS'},'already_sealed':{'planning_complete':True},'cursor':{'planner_next_selection_order':3000},'missing_reporting':{'implementation_reporting_policy':{}}}
        original=self.metadata();functions=self.function_rows()
        for name,change in variants.items():
            with self.subTest(name=name):
                self.set_metadata({**original,**change});before=self.rows()
                with self.assertRaises(self.f.psycopg.Error):self.execute_migration(self.forward)
                self.assertEqual(self.function_rows(),functions);self.assertEqual(self.rows(),before)
        self.set_metadata(original)
        before=self.rows()
        with self.assertRaisesRegex(self.f.psycopg.Error,'current finite existing controller'):
            with self.f.admin() as conn:
                conn.execute(f'UPDATE {self.f.schema}.backfill_runs_v2 SET fence=fence+1 WHERE id=%s',(self.run,))
                conn.execute(self.forward)
        self.assertEqual(self.rows(),before);self.assertEqual(self.function_rows(),functions)
        RESULT['cases']['installation_authority']={'rejected_variants':list(variants)+['fence'],'no_mutation':True}

    def test_postinstall_pin_failure_rolls_back_all_replacements_and_rows(self):
        before=self.rows();functions=self.function_rows()
        def corrupt_after(match):
            expected=json.loads(match.group(1));expected[0]['source_sha256']='0'*64
            return "after_pins jsonb:='"+json.dumps(expected,separators=(',',':'))+"'::jsonb;"
        broken,n=re.subn(r"after_pins jsonb:='([^']*)'::jsonb;",corrupt_after,self.forward,count=1)
        self.assertEqual(n,1)
        with self.assertRaisesRegex(self.f.psycopg.Error,'post-replacement source/OID/full metadata differs'):
            self.execute_migration(broken)
        self.assertEqual(self.rows(),before);self.assertEqual(self.function_rows(),functions)
        RESULT['cases']['postguard_rollback']={'real_ddl_reached':True,'forced_postcondition_failure':True,'all_thirteen_definitions_metadata_and_rows_rolled_back':True}


    def test_partial_missing_function_and_metadata_drift_roll_back(self):
        signature=self.f.schema+'.backfill_plan_snapshot_v2(text,integer)'
        original=self.function_rows()
        with self.f.admin() as conn:conn.execute(f'ALTER FUNCTION {signature} RENAME TO backfill_plan_snapshot_hidden_v78')
        try:
            with self.assertRaises(self.f.psycopg.Error):self.execute_migration(self.forward)
        finally:
            with self.f.admin() as conn:conn.execute(f'ALTER FUNCTION {self.f.schema}.backfill_plan_snapshot_hidden_v78(text,integer) RENAME TO backfill_plan_snapshot_v2')
        self.assertEqual(self.function_rows(),original)
        cost=next(r['metadata']['procost'] for r in original if r['signature'].endswith('backfill_plan_snapshot_v2(text,integer)'))
        with self.f.admin() as conn:conn.execute(f'ALTER FUNCTION {signature} COST {cost+1}')
        try:
            with self.assertRaises(self.f.psycopg.Error):self.execute_migration(self.forward)
        finally:
            with self.f.admin() as conn:conn.execute(f'ALTER FUNCTION {signature} COST {cost}')
        self.assertEqual(self.function_rows(),original)
        RESULT['cases']['partial_missing_and_metadata_drift']={'partial_missing_signature_rejected':True,'metadata_drift_rejected':True,'originals_restored':True}

    def test_initial_planning_snapshot_can_advance_after_dynamic_row(self):
        self.dynamic_identity()
        initial={k:v for k,v in self.install_metadata.items() if not k.startswith('planner_') and k!='planning_complete'}
        self.set_metadata(initial)
        old=self.plan();self.assertEqual(old['state'],'SNAPSHOTTING_EXISTING_TASKS')
        self.assertEqual(old['snapshot'],{'snapshotted':0,'more':True})
        self.set_metadata(self.install_metadata);self.execute_migration(self.forward);self.set_metadata(initial)
        repaired=self.plan();self.assertEqual(repaired['state'],'PLAN_ADVANCED');self.assertEqual(repaired['planned_members'],1)
        self.assertFalse(repaired['plan_complete']);self.assertGreater(repaired['inserted_tasks'],0)
        RESULT['cases']['initial_snapshot']={'before':old,'after':repaired,'ordinary_planner_invoked':True}

    def test_seal_reaches_actual_missing_coverage_and_never_forces_completion(self):
        self.dynamic_identity();old=self.plan();self.assertEqual(old['state'],'SNAPSHOTTING_EXISTING_TASKS')
        self.execute_migration(self.forward);before=self.rows()
        repaired=self.plan();self.assertEqual(repaired['state'],'INCOMPLETE_MEMBER_DATE_WORKFLOWS');self.assertFalse(repaired['plan_complete'])
        self.assertTrue(repaired['evidence']['missing_member_date_workflows']);self.assertEqual(self.rows(),before)
        RESULT['cases']['missing_coverage']={'old':old,'repaired_state':repaired['state'],'missing_evidence_nonempty':True,'business_rows_unchanged':True}

    def test_actual_complete_static_workflow_seals_once_and_preserves_dynamic_rows(self):
        self.dynamic_identity();self.execute_migration(self.forward);count=self.seed_complete_static_workflows()
        before=self.rows();sealed=self.plan();self.assertEqual(sealed['state'],'FULL_PLAN_SEALED');self.assertTrue(sealed['plan_complete'])
        after=self.rows();self.assertEqual(after['backfill_tasks_v2'],before['backfill_tasks_v2']);self.assertEqual(after['backfill_members_v2'],before['backfill_members_v2'])
        self.assertEqual(after['backfill_plan_units_v2'],before['backfill_plan_units_v2']);self.assertEqual(len(after['backfill_plan_manifests_v2']),1)
        self.assertEqual(after['backfill_plan_manifests_v2'][0]['r']['expected_task_count'],count)
        repeat=self.plan();self.assertTrue(repeat['plan_complete']);self.assertEqual(self.rows(),after)
        self.execute_migration(self.restore);self.assertEqual(self.rows(),after)
        RESULT['cases']['full_seal']={'inverse_preserves_committed_manifest':True,'synthetic_static_workflows':count,'real_coverage_checker_and_representative_map':True,'one_manifest':True,'repeat_no_effect':True,'dynamic_rows_and_existing_plan_unchanged':True}

    def test_count_hash_and_representative_integrity_still_reject(self):
        self.execute_migration(self.forward);count=self.seed_complete_static_workflows()
        for name,n,h in [('count',count+1,None),('hash',None,'0'*64)]:
            with self.subTest(name=name):
                before=self.rows()
                with self.assertRaises(self.f.psycopg.Error):self.seal_direct(n,h)
                self.assertEqual(self.rows(),before)
        metadata=self.metadata();metadata['planner_expected_static_count']=count+1;self.set_metadata(metadata);before=self.rows()
        outcome=self.f.rpc('backfill_plan_next',{'run_id':self.run,'member_limit':1,'supported_kinds':planner.KINDS},actor='worker')
        self.assertFalse(outcome['ok']);self.assertEqual(self.rows(),before)
        RESULT['cases']['count_hash']={'count_rejected':True,'hash_rejected':True,'planner_expected_count_rejected':True,'no_business_mutation':True}

    def test_invalid_breadth_representative_map_remains_unsealable(self):
        self.execute_migration(self.forward);self.seed_complete_static_workflows(invalid_map=True);before=self.rows()
        with self.assertRaises(self.f.psycopg.Error):self.seal_direct()
        self.assertEqual(self.rows(),before)
        RESULT['cases']['invalid_representative_map']={'real_map_validation_rejected':True,'no_mutation':True}
