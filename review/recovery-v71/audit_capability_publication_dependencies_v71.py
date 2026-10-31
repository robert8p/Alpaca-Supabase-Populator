"""Local-only runtime/import fixture audit for the capability repair publication.

The explicit disposable PostgreSQL environment variable is required. This runs
one real forward/preservation case to observe setup-time ROOT/read_text inputs.
No production connection, GitHub call, publication or credential loading occurs.
"""
import ast
from hashlib import sha1, sha256
import json
import os
from pathlib import Path
import sys
from time import perf_counter
import unittest

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
sys.path[:0] = [str(ROOT / 'tests/ingestion'), str(ROOT)]
opened = set()


def audit(event, args):
    if event != 'open' or not args or not isinstance(args[0], (str, bytes)):
        return
    try:
        path = Path(os.fsdecode(args[0])).resolve()
        relative = path.relative_to(ROOT)
    except (ValueError, OSError):
        return
    if '__pycache__' not in relative.parts and path.is_file():
        opened.add(relative.as_posix())


def file_ref(path):
    data = (ROOT / path).read_bytes()
    return {'path':path, 'bytes':len(data), 'sha256':sha256(data).hexdigest(),
            'git_blob_sha1':sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()}


def main():
    if not os.environ.get('ASTRA_INGESTION_POSTGRES_TEST_URL'):
        raise SystemExit('An explicit disposable PostgreSQL fixture is required')
    sys.addaudithook(audit)
    import test_backfill_claim_capability_filter_v2 as test
    started = perf_counter()
    all_tests = '--all-tests' in sys.argv[1:]
    suite = unittest.defaultTestLoader.loadTestsFromModule(test) if all_tests else unittest.TestSuite([
        test.CapabilityFilterPostgreSQLTests('test_forward_preserves_all_other_source_metadata_auth_status_and_data')])
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    elapsed = perf_counter() - started
    modules = set()
    for module in tuple(sys.modules.values()):
        filename = getattr(module, '__file__', None)
        if not filename:
            continue
        try:
            relative = Path(filename).resolve().relative_to(ROOT)
        except ValueError:
            continue
        if relative.suffix == '.py':
            modules.add(relative.as_posix())
    # Audit all read_text/read_bytes call sites, including unused sibling tests
    # imported by the fixture inheritance chain. Runtime reads identify the
    # actual executed fixture closure; static sites retain the broader inventory.
    static_sites = []
    for path in sorted(modules):
        source = (ROOT / path).read_text()
        for node in ast.walk(ast.parse(source, filename=path)):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and node.func.attr in ('read_text', 'read_bytes'):
                static_sites.append({'path':path, 'line':node.lineno, 'expression':ast.get_source_segment(source, node)})
    needed = modules | {p for p in opened if not p.startswith('review/recovery-v71/')}
    needed.add('sql/astra_backfill_claim_capability_filter_v2.sql')
    raw_tree = json.loads(Path('/tmp/replacement-3ee4-tree.json').read_text())
    entries = raw_tree['tree'] if isinstance(raw_tree, dict) else raw_tree
    tree = {x['path']:x for x in entries if x.get('type') == 'blob'}
    files = []
    for path in sorted(needed):
        record = file_ref(path)
        prior = tree.get(path)
        record['base_state'] = 'ABSENT' if prior is None else 'IDENTICAL' if prior['sha'] == record['git_blob_sha1'] else 'DIFFERENT'
        record['base_git_blob_sha1'] = prior.get('sha') if prior else None
        files.append(record)
    record = {'schema':'astra.claim-capability.publication-dependency-audit/1',
        'base_commit':'3ee4db2a79c081ffb65ef0d7ec2a04228d69fb1d',
        'base_tree':'a7d7ba1a50018eb6c05f716625f48f3562c3d338',
        'base_tree_truncated':False, 'base_tree_entries':len(entries),
        'passed':result.wasSuccessful(), 'tests':result.testsRun, 'skipped':len(result.skipped),
        'failures':len(result.failures), 'errors':len(result.errors), 'all_active_tests_executed':all_tests,
        'elapsed_seconds':elapsed, 'imported_project_modules':sorted(modules),
        'observed_project_reads':sorted(opened), 'static_read_call_sites':static_sites,
        'files':files, 'absent_paths':[x['path'] for x in files if x['base_state']=='ABSENT'],
        'different_paths':[x['path'] for x in files if x['base_state']=='DIFFERENT'],
        'limits':['All active tests executed.' if all_tests else 'One actual forward/preservation case executed to trace the complete shared setup fixture.',
                  'Static read-site inventory includes sibling tests not selected by this qualification; their extra reads are not automatically required by the active test.']}
    if all_tests:
        record['qualification'] = json.loads(json.dumps(test.EVIDENCE))
        plans = record['qualification'].get('backlog', {}).pop('plans', {})
        record['qualification'].setdefault('backlog', {})['timings_ms'] = {
            branch:{mode:{label:plan['Execution Time'] for label,plan in labels.items()}
                    for mode,labels in modes.items()} for branch,modes in plans.items()}
    output = HERE / ('claim_capability_staged_publication_dependencies_v71.json' if all_tests else 'claim_capability_publication_dependencies_v71.json')
    output.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps({'passed':record['passed'], 'files':len(files),
        'absent':record['absent_paths'], 'different':record['different_paths'],
        'output':str(output), 'sha256':sha256(output.read_bytes()).hexdigest()}))
    return 0 if result.wasSuccessful() else 1


if __name__ == '__main__':
    raise SystemExit(main())
