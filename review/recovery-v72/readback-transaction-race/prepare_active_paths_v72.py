"""Publish the exact prepared SQL and portable eight-case ingestion test module locally."""
from hashlib import sha256
import ast
import json
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
source = (HERE / 'qualify_readback_transaction_race_v72.py').read_text()
start = source.index('HERE = Path(__file__).resolve().parent')
end = source.index('BASELINE = ', start)
portable = source[:start] + '''ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / 'review/recovery-v72/readback-transaction-race'
import test_backfill_claim_capability_filter_v2 as base

''' + source[end:]
portable = portable.replace("FORWARD = (HERE / 'forward_readback_transaction_race_v72.sql').read_text()",
    "FORWARD = (ROOT / 'sql/astra_backfill_readback_transaction_race_v2.sql').read_text()")
portable = portable.replace('class PostgreSQLTests(base.CapabilityFilterPostgreSQLTests):\n', '''class PostgreSQLTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if not os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'):
            if os.environ.get('GITHUB_WORKFLOW') == 'ASTRA ingestion qualification':
                raise RuntimeError('ASTRA_INGESTION_POSTGRES_TEST_URL is required by ASTRA ingestion qualification; refusing an ingestion-gate skip')
            raise unittest.SkipTest('Disposable PostgreSQL is exercised by the dedicated ASTRA ingestion qualification gate')
        base.CapabilityFilterPostgreSQLTests.setUpClass.__func__(cls)

    rewrite = classmethod(base.CapabilityFilterPostgreSQLTests.rewrite.__func__)
    full_query = staticmethod(base.CapabilityFilterPostgreSQLTests.full_query)
    task = base.CapabilityFilterPostgreSQLTests.task
    call = base.CapabilityFilterPostgreSQLTests.call
    claim = base.CapabilityFilterPostgreSQLTests.claim
    page = base.CapabilityFilterPostgreSQLTests.page
    fence = staticmethod(base.CapabilityFilterPostgreSQLTests.fence)
    snapshot = base.CapabilityFilterPostgreSQLTests.snapshot

''')
portable = portable.replace('        super().setUp()\n', '        base.CapabilityFilterPostgreSQLTests.setUp(self)\n', 1)
portable = portable.replace("        cases = [\n", '''        drift_source = self.recheck.replace('BEGIN\\n', 'BEGIN\\n -- synthetic pre-snapshot source drift\\n', 1)
        drift_forward = self.forward.replace(
            ' SELECT jsonb_agg(to_jsonb(p) ORDER BY p.oid) INTO v_other_before',
            ' EXECUTE $drift$' + drift_source + '$drift$;\\n SELECT jsonb_agg(to_jsonb(p) ORDER BY p.oid) INTO v_other_before', 1)
        cases = [
            ('pre_snapshot_verifier_drift_rolls_back', drift_forward, None),
''', 1)
portable = portable.replace("        self.assertEqual(digest(BASELINE), MANIFEST['baseline_sha256'])",
    "        self.assertEqual(digest(FORWARD), MANIFEST['artifacts']['forward_readback_transaction_race_v72.sql']['sha256'])\n"
    "        self.assertEqual(digest(BASELINE), MANIFEST['baseline_sha256'])", 1)
portable = portable[:portable.index("if __name__ == '__main__':")] + "if __name__ == '__main__':\n    unittest.main()\n"
portable = portable.replace('Real local PostgreSQL transaction-race regression; never production.',
    'Required ingestion-CI regression for the real readback transaction race.')
portable = portable.replace('import sys\n', '')
assert '/tmp/' not in portable and '55432' not in portable and 'EXPECTED_LOCAL_URL' not in portable
assert 'skipUnless' not in portable and 'skipTest' not in portable
assert "os.environ.get('GITHUB_WORKFLOW') == 'ASTRA ingestion qualification'" in portable
ast.parse(portable)
original_tree = ast.parse(source)
portable_tree = ast.parse(portable)
def tests(tree):
    return {node.name + '.' + fn.name: ast.dump(fn, include_attributes=False)
            for node in tree.body if isinstance(node, ast.ClassDef)
            for fn in node.body if isinstance(fn, ast.FunctionDef) and fn.name.startswith('test_')}
original_tests, active_tests = tests(original_tree), tests(portable_tree)
assert original_tests.keys() == active_tests.keys() and len(active_tests) == 8
assert all(active_tests[name] == body for name, body in original_tests.items()
           if name not in ('SourceTests.test_exact_single_predicate_and_unchanged_verifier',
                           'PostgreSQLTests.test_forward_guards_and_atomic_postwrite_rollback'))
paths = {
    'tests/ingestion/test_backfill_readback_transaction_race_v2.py': portable,
    'sql/astra_backfill_readback_transaction_race_v2.sql': (HERE / 'forward_readback_transaction_race_v72.sql').read_text(),
}
for name, text in paths.items():
    path = ROOT / name
    if path.exists():
        initial = json.loads((HERE / 'active_paths_initial_v72.json').read_text())
        current = json.loads((HERE / 'active_paths_v72.json').read_text())
        allowed = {sha256(text.encode()).hexdigest(), initial['active_paths'][name]['sha256'], current['active_paths'][name]['sha256']}
        assert sha256(path.read_bytes()).hexdigest() in allowed, 'Refusing unexpected active-path drift'
    path.write_text(text)
manifest = {
    'schema': 'astra.readback-transaction-race-active-paths/1',
    'active_paths': {name: {'sha256': sha256(text.encode()).hexdigest(), 'bytes': len(text.encode())}
                     for name, text in paths.items()},
    'discovery_command': "python -m unittest discover -s tests/ingestion -p 'test_backfill_readback_transaction_race_v2.py' -v",
    'test_names': sorted(active_tests),
    'six_database_test_bodies_equal_to_qualified_frozen_harness': True,
    'guard_test_added_case': 'Verifier changes after precheck but before snapshot; final source pin rejects and rolls back both function replacements.',
    'source_test_extra_assertion': 'The active SQL path must have the exact prepared forward hash.',
    'fixture_setup': 'Same existing capability fixture methods, composed into unittest.TestCase without inheriting unrelated tests or an import-time skip flag.',
    'database_admission': 'Existing ASTRA_INGESTION_POSTGRES_TEST_URL convention; missing DSN is an error in ASTRA ingestion qualification and an explicitly named dedicated-gate skip in other workflows.',
    'frozen_harness_sha256': sha256(source.encode()).hexdigest(),
    'frozen_qualification_sha256': sha256((HERE / 'qualification_v72.json').read_bytes()).hexdigest(),
    'active_discovery_execution': 'PENDING_COMBINED_STAGED_QUALIFICATION',
    'production_calls': 0,
}
(HERE / 'active_paths_v72.json').write_text(json.dumps(manifest, indent=2) + '\n')
print(json.dumps(manifest, indent=2))
