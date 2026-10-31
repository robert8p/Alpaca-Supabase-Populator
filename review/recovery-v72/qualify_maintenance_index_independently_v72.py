from datetime import datetime, timezone
from hashlib import sha256
import importlib
import io
import json
import os
from pathlib import Path
import sys
from time import monotonic
import unittest

ROOT = Path('/workspace/scratch/a1eb25e9f187/replacement-run')
STAGE = Path('/tmp/replacement-maintenance-index-staged-v72')
DSN = 'postgresql://postgres@127.0.0.1:55432/astra_ingestion_qualification'
if os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL') != DSN:
    raise RuntimeError('This review runner accepts only the explicit disposable loopback database')

PINS = {
    'sql/astra_backfill_breadth_pending_hash_index_v2.sql': '8ff7824557d19d6981e036acc9228d148b460de50c38ec33017b7f628037fad9',
    'sql/astra_backfill_minute_pending_hash_index_v2.sql': '1355b571ffd60602bee67e525dc687535b31e5c7c69ea3ac058551fc0c591203',
    'tests/ingestion/test_backfill_maintenance_task_indexes_v2.py': '50108ef354e9d3c36b76e6f3b55f31306067f2c20ee4a749b4c5eded931a2145',
}
for path, expected in PINS.items():
    for directory in (ROOT, STAGE):
        assert sha256((directory / path).read_bytes()).hexdigest() == expected, path

sys.path[:0] = [str(STAGE / 'tests/ingestion'), str(STAGE)]
module = importlib.import_module('test_backfill_maintenance_task_indexes_v2')
assert Path(module.__file__).resolve() == STAGE / 'tests/ingestion/test_backfill_maintenance_task_indexes_v2.py'
suite = unittest.defaultTestLoader.loadTestsFromTestCase(module.MaintenanceTaskIndexTests)
assert suite.countTestCases() == 9
log = io.StringIO()
started = datetime.now(timezone.utc).isoformat()
clock = monotonic()
result = unittest.TextTestRunner(stream=log, verbosity=2).run(suite)
elapsed = monotonic() - clock
receipt = {
    'schema': 'astra.maintenance-index-independent-execution/1',
    'reviewer': '/root/relay_v3_review',
    'started_at_utc': started,
    'finished_at_utc': datetime.now(timezone.utc).isoformat(),
    'passed': result.wasSuccessful() and result.testsRun == 9 and not result.skipped,
    'tests': result.testsRun,
    'errors': len(result.errors),
    'failures': len(result.failures),
    'skipped': len(result.skipped),
    'elapsed_seconds': elapsed,
    'production_calls': 0,
    'disposable_loopback_database_only': True,
    'staged_base_commit': '536bb850cf5c5653b4865e63db3f20f50a6769a1',
    'verified_input_sha256': PINS,
    'runner_sha256': sha256(Path(__file__).read_bytes()).hexdigest(),
    'qualification': module.EVIDENCE,
    'test_log': log.getvalue(),
}
out = ROOT / 'review/recovery-v72/maintenance_index_independent_test_result_v72.json'
out.write_text(json.dumps(receipt, indent=2, sort_keys=True) + '\n')
print(json.dumps({k: receipt[k] for k in ('passed', 'tests', 'errors', 'failures', 'skipped', 'elapsed_seconds')}))
print('receipt_sha256=' + sha256(out.read_bytes()).hexdigest())
if not receipt['passed']:
    print(log.getvalue())
    raise SystemExit(1)
