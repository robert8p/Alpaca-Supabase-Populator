"""Stage only the new qualification's audited dependency closure at exact 3ee4.

Existing remote blobs must be supplied read-only by the root controller. This
script has no network or publication capability and cannot alter the runtime.
"""
from hashlib import sha1, sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE = Path('/tmp/replacement-3ee4-baseline')
STAGE = Path('/tmp/replacement-claim-capability-staged-v71')
AUDIT = ROOT / 'review/recovery-v71/claim_capability_publication_dependencies_v71.json'


def blob(data):
    return sha1(b'blob ' + str(len(data)).encode() + b'\0' + data).hexdigest()


def main():
    audit = json.loads(AUDIT.read_text())
    files = []
    for entry in audit['files']:
        path = Path(entry['path'])
        if path.is_absolute() or '..' in path.parts:
            raise ValueError('Unsafe dependency path')
        source = BASE / path if entry['base_state'] == 'DIFFERENT' else ROOT / path
        data = source.read_bytes()
        expected = entry['base_git_blob_sha1'] if entry['base_state'] != 'ABSENT' else None
        if expected is not None and blob(data) != expected:
            raise ValueError('Exact base blob mismatch: ' + path.as_posix())
        if expected is None and path.as_posix() not in {
            'sql/astra_backfill_claim_capability_filter_v2.sql',
            'tests/ingestion/test_backfill_claim_capability_filter_v2.py',
            'review/recovery-v71/audit_capability_publication_dependencies_v71.py',
        }:
            raise ValueError('Unexpected new dependency: ' + path.as_posix())
        target = STAGE / path
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(data)
        files.append({'path':path.as_posix(), 'source':'ROOT_RETAINED_BASE_BLOB' if entry['base_state']=='DIFFERENT' else entry['base_state'],
            'git_blob_sha1':blob(data), 'sha256':sha256(data).hexdigest(), 'bytes':len(data)})
    result = {'schema':'astra.claim-capability.staged-source/1',
        'base_commit':audit['base_commit'], 'base_tree':audit['base_tree'],
        'existing_dependencies_all_exact_base':True, 'dependency_count':len(files),
        'files':files, 'stage':str(STAGE), 'remote_mutations':False,
        'test_command':'ASTRA_INGESTION_POSTGRES_TEST_URL=<explicit-disposable-loopback-fixture> python3 review/recovery-v71/audit_capability_publication_dependencies_v71.py --all-tests'}
    output = ROOT / 'review/recovery-v71/claim_capability_staged_source_v71.json'
    output.write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps({'stage':str(STAGE), 'dependency_count':len(files),
        'source_manifest':str(output), 'sha256':sha256(output.read_bytes()).hexdigest()}))


if __name__ == '__main__':
    main()
