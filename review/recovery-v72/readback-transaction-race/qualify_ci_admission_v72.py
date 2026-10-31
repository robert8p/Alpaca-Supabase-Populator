"""Qualify the two CI admission contexts without opening any database connection."""
from hashlib import sha256
import importlib.util
import json
import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
ACTIVE = ROOT / 'tests/ingestion/test_backfill_readback_transaction_race_v2.py'
STAGED = Path('/tmp/replacement-claim-capability-staged-v71')
sys.path[:0] = [str(STAGED / 'tests/ingestion'), str(STAGED)]
spec = importlib.util.spec_from_file_location('readback_race_admission_subject', ACTIVE)
subject = importlib.util.module_from_spec(spec)
spec.loader.exec_module(subject)
RESULT = {'schema': 'astra.readback-race-ci-admission-qualification/1', 'database_connections': 0,
          'production_calls': 0, 'test_sha256': sha256(ACTIVE.read_bytes()).hexdigest()}


class AdmissionTests(unittest.TestCase):
    def admission(self, context, expected_exception=None):
        delegated = []

        def fixture_setup(cls):
            delegated.append(cls.__name__)

        with patch.dict(os.environ, context, clear=True), patch.object(
                subject.base.CapabilityFilterPostgreSQLTests, 'setUpClass', classmethod(fixture_setup)):
            if expected_exception:
                with self.assertRaises(expected_exception) as caught:
                    subject.PostgreSQLTests.setUpClass()
                self.assertIn('ASTRA ingestion qualification', str(caught.exception))
                self.assertEqual(delegated, [])
            else:
                subject.PostgreSQLTests.setUpClass()
                self.assertEqual(delegated, ['PostgreSQLTests'])

    def test_dedicated_ingestion_without_dsn_errors(self):
        self.admission({'GITHUB_WORKFLOW': 'ASTRA ingestion qualification'}, RuntimeError)
        RESULT['missing_dsn_dedicated_workflow'] = 'ERROR; no fixture or database called'

    def test_general_release_without_dsn_explicitly_skips(self):
        self.admission({'GITHUB_WORKFLOW': 'General release gate'}, unittest.SkipTest)
        RESULT['missing_dsn_other_workflow'] = 'EXPLICIT_SKIP naming the dedicated ingestion gate'

    def test_unset_workflow_without_dsn_explicitly_skips(self):
        self.admission({}, unittest.SkipTest)
        RESULT['missing_dsn_unset_workflow'] = 'EXPLICIT_SKIP naming the dedicated ingestion gate'

    def test_dedicated_ingestion_with_dsn_delegates_and_discovers_eight_cases(self):
        self.admission({'GITHUB_WORKFLOW': 'ASTRA ingestion qualification',
                        'ASTRA_INGESTION_POSTGRES_TEST_URL': 'postgresql://synthetic-fixture/qualification'})
        self.assertEqual(unittest.defaultTestLoader.loadTestsFromModule(subject).countTestCases(), 8)
        self.assertFalse(getattr(subject.PostgreSQLTests, '__unittest_skip__', False))
        RESULT['configured_dedicated_workflow'] = 'EXISTING_FIXTURE_DELEGATION; eight discoverable cases; no inherited skip'


if __name__ == '__main__':
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(AdmissionTests))
    passed = result.wasSuccessful() and not result.skipped
    RESULT.update(passed=passed, tests=result.testsRun, errors=len(result.errors), failures=len(result.failures),
                  skipped=len(result.skipped), runner_sha256=sha256(Path(__file__).read_bytes()).hexdigest(),
                  limitation='Mocked admission only; actual eight-case database discovery is qualified separately.')
    path = HERE / 'ci_admission_qualification_v72.json'
    path.write_text(json.dumps(RESULT, indent=2) + '\n')
    print(json.dumps({'passed': passed, 'receipt': str(path), 'sha256': sha256(path.read_bytes()).hexdigest()}))
    raise SystemExit(0 if passed else 1)
