"""Create an explicit, hash-bound local publication packet; never publish it."""
from datetime import datetime, timezone
from hashlib import sha1, sha256
import gzip
import io
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / 'review/recovery-v71'
BASE_COMMIT = '3ee4db2a79c081ffb65ef0d7ec2a04228d69fb1d'
BASE_TREE = 'a7d7ba1a50018eb6c05f716625f48f3562c3d338'
REVIEWED = {
    'sql/astra_backfill_claim_capability_filter_v2.sql':'25427b992aebe5c81ae6c4b9e4cb44b560c8201b044476ea1ea937a933fed10c',
    'tests/ingestion/test_backfill_claim_capability_filter_v2.py':'9d8f00fdabb87b1cbd62ed1e1b5c38e7e60a5a16e26f9c9a3cf6417587f58fd1',
    'evidence/replacement-claim-capability-filter-qualification-v71.json':'4c05ecd655308790394f429bf5b357a867409dcd2c72d5c55f3cc538ff40b50b',
    'evidence/replacement-claim-capability-filter-independent-review-v71.json':'7f94069b27e617a7731856ec2cf08ab3ff52314a9cc0720744e9b2556e92084f',
}
PATHS = [
    *REVIEWED,
    'review/recovery-v71/live_functions_1155.json',
    'review/recovery-v71/claim_n01_readonly_custom_v71.sql',
    'review/recovery-v71/live_n01_custom_result.json',
    'review/recovery-v71/claim_n01_capability_candidate_readonly_v71.sql',
    'review/recovery-v71/live_n01_capability_candidate_result.json',
    'review/recovery-v71/claim_n01_capability_generic_readonly_v71.sql',
    'review/recovery-v71/live_n01_capability_generic_result.json',
    'review/recovery-v71/claim_capability_benchmark_v71.py',
    'review/recovery-v71/claim_capability_benchmark_result_v71.json',
    'review/recovery-v71/claim_capability_qualification_initial_result_v71.json',
    'review/recovery-v71/claim_capability_qualification_guard_fixture_failure_v71.json',
    'review/recovery-v71/claim_capability_qualification_guard_rerun_v71.json',
    'review/recovery-v71/claim_capability_independent_qualification_v71.json',
    'review/recovery-v71/audit_capability_publication_dependencies_v71.py',
    'review/recovery-v71/stage_capability_publication_v71.py',
    'review/recovery-v71/build_capability_publication_packet_v71.py',
    'review/recovery-v71/claim_capability_publication_dependencies_v71.json',
    'review/recovery-v71/claim_capability_staged_source_v71.json',
    'review/recovery-v71/claim_capability_staged_publication_dependencies_v71.json',
    'evidence/replacement-claim-capability-filter-publication-readiness-v71.json',
    'evidence/replacement-3ee4-release-gates-v71.json',
    'evidence/replacement-preactivation-reconciliation-v71.json',
    'evidence/replacement-approved-relay-worker-deployment-v71.json',
]


def ref(path, data):
    return {'path':path, 'bytes':len(data), 'sha256':sha256(data).hexdigest(),
            'git_blob_sha1':sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()}


def main():
    audit = json.loads((HERE / 'claim_capability_staged_publication_dependencies_v71.json').read_text())
    if not (audit['passed'] and audit['tests'] == 9 and audit['skipped'] == 0
            and audit['all_active_tests_executed'] and not audit['different_paths']):
        raise ValueError('Exact-base staged qualification is not complete')
    for path, expected in REVIEWED.items():
        if sha256((ROOT / path).read_bytes()).hexdigest() != expected:
            raise ValueError('Reviewed artifact drift: ' + path)
    raw_tree = json.loads(Path('/tmp/replacement-3ee4-tree.json').read_text())
    if raw_tree['sha'] != BASE_TREE or raw_tree['truncated']:
        raise ValueError('Unexpected or truncated base tree')
    tree = {x['path']:x for x in raw_tree['tree'] if x.get('type') == 'blob'}
    data = {path:(ROOT / path).read_bytes() for path in sorted(set(PATHS))}
    payloads = []
    for path, content in data.items():
        item = ref(path, content)
        prior = tree.get(path)
        item['base_state'] = 'ABSENT' if prior is None else 'IDENTICAL' if prior['sha'] == item['git_blob_sha1'] else 'DIFFERENT'
        if item['base_state'] == 'DIFFERENT':
            raise ValueError('Unexpected replacement of an existing base file: ' + path)
        payloads.append(item)
    manifest_path = 'evidence/replacement-claim-capability-filter-publication-manifest-v71.json'
    manifest = {'schema':'astra.claim-capability.publication-manifest/1',
        'created_at':datetime.now(timezone.utc).isoformat(),
        'repository':'robert8p/Alpaca-Supabase-Populator', 'base_commit':BASE_COMMIT, 'base_tree':BASE_TREE,
        'state':'PREPARED_LOCAL_NOT_PUBLISHED', 'scope':'Performance-only two-predicate SQL forward, active qualification and retained evidence.',
        'reviewed_inner_before':'136871b8ca305ae69c661541d9c2684e71b1d5e6fe84a6ec9b8b594b1da56d02',
        'reviewed_inner_after':'28ae5f1a0b7662b4463d8709d68c1402265dc20fd5cd11fb408ac12522c5de44',
        'unchanged_outer_auth':'a9a72d498ca12ec1828721f605d14eb357d7728dc3b0d9d24aab3a636afa2520',
        'runtime_python_or_worker_changes':False, 'security_logic_or_frozen_relay_changes':False,
        'existing_fixture_overwrites':False,
        'historical_fixture_dependencies_absent_from_base':[],
        'exact_base_staged_tests':{'passed':9, 'skipped':0, 'failures':0, 'errors':0,
            'receipt':'review/recovery-v71/claim_capability_staged_publication_dependencies_v71.json'},
        'payload_count_excluding_manifest':len(payloads), 'payload_bytes':sum(x['bytes'] for x in payloads),
        'files':payloads,
        'application_is_separate':'Root must reconcile ownership, source and uncertain writes before applying the guarded SQL. Publishing test fixtures never authorizes replaying historical migrations.'}
    manifest_data = (json.dumps(manifest, indent=2) + '\n').encode()
    (ROOT / manifest_path).write_bytes(manifest_data)
    data[manifest_path] = manifest_data
    packet = {'schema':'astra.claim-capability.publication-packet/1',
        'base_commit':BASE_COMMIT, 'base_tree':BASE_TREE, 'manifest':ref(manifest_path, manifest_data),
        'expected_head_must_be_reconciled_before_mutation':True,
        'tree_entries':[{'path':path, 'mode':'100644', 'type':'blob', 'content':content.decode('utf-8')}
                        for path, content in sorted(data.items())]}
    packet_path = Path('/tmp/replacement-claim-capability-publication-packet-v71.json')
    packet_path.write_text(json.dumps(packet, ensure_ascii=False) + '\n')
    paths_path = Path('/tmp/replacement-claim-capability-publication-files-v71.txt')
    paths_path.write_text('\n'.join(sorted(data)) + '\n')
    archive_path = Path('/tmp/replacement-claim-capability-publication-packet-v71.tar.gz')
    with archive_path.open('wb') as output, gzip.GzipFile(fileobj=output, mode='wb', mtime=0) as compressed, tarfile.open(fileobj=compressed, mode='w') as archive:
        for path, content in sorted(data.items()):
            info = tarfile.TarInfo(path)
            info.size = len(content)
            info.mode = 0o644
            info.mtime = 0
            archive.addfile(info, io.BytesIO(content))
    print(json.dumps({'manifest':ref(manifest_path, manifest_data), 'file_count':len(data),
        'packet':ref(str(packet_path), packet_path.read_bytes()),
        'archive':ref(str(archive_path), archive_path.read_bytes()), 'file_list':str(paths_path)}))


if __name__ == '__main__':
    main()
