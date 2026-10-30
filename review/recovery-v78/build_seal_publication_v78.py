"""Build an additive, content-addressed v78 release over the reconciled v77 tree."""
from __future__ import annotations
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BASE_COMMIT = '08bea176e39174f8c39f62caebae79d5cb50cdcf'
BASE_TREE = '564347923f62753c8303c7448455310528ff6b72'
MANIFEST = 'evidence/replacement-planner-seal-publication-manifest-v78.json'
spec = importlib.util.spec_from_file_location('git_objects', ROOT / 'review/recovery-v76/build_independent_claim_publication_v76.py')
go = importlib.util.module_from_spec(spec)
spec.loader.exec_module(go)

def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--selection', required=True)
    args = ap.parse_args()
    selection = json.loads((ROOT / args.selection).read_text())
    assert selection['base_commit'] == BASE_COMMIT
    assert selection['local_qualification_passed'] is True
    assert selection['independent_review_passed'] is True
    base = json.loads((ROOT / 'review/recovery-v78/base_tree_entries_v78.json').read_text())
    assert base['sha'] == BASE_TREE and not base.get('truncated')
    leaves = {item['path']: item for item in base['tree'] if item['type'] != 'tree'}
    assert len(leaves) == 1125 and go.root_sha(leaves)[0] == BASE_TREE
    held_path = Path('/tmp/replacement-checkpoint-publication-packet-v75.json')
    held_raw = held_path.read_bytes()
    assert digest(held_raw) == '8806ef636f5be4220562b0ee52d64426f620461d8ad99adef5f9edd1f9724da3'
    held_paths = {item['path'] for item in json.loads(held_raw)['tree_entries']}
    selected = selection['files']
    paths = [item['path'] for item in selected]
    assert len(paths) == len(set(paths)) and MANIFEST not in paths and args.selection not in paths
    assert not (set(paths) | {MANIFEST, args.selection}) & held_paths
    assert all(path not in leaves for path in paths + [MANIFEST, args.selection])
    assert all(not path.startswith(('astra_ingestion/', '.github/', 'docs/')) for path in paths)
    assert all(not (path.startswith('review/') and Path(path).name.startswith('test_') and path.endswith('.py')) for path in paths)
    entries = []
    artifacts = []
    for item in sorted(selected, key=lambda item: item['path']):
        path = item['path']
        data = (ROOT / path).read_bytes()
        assert digest(data) == item['sha256'] and len(data) == item['bytes'], path
        blob = go.object_sha('blob', data)
        entries.append({'path': path, 'mode': '100644', 'type': 'blob', 'content': data.decode('utf-8')})
        artifacts.append(dict(item, git_blob_sha1=blob, mode='100644'))
    selection_raw = (ROOT / args.selection).read_bytes()
    entries.append({'path': args.selection, 'mode': '100644', 'type': 'blob', 'content': selection_raw.decode('utf-8')})
    artifacts.append({'path': args.selection, 'bytes': len(selection_raw), 'sha256': digest(selection_raw), 'git_blob_sha1': go.object_sha('blob', selection_raw), 'mode': '100644'})
    manifest = {
        'schema': 'astra.planner-seal-additive-publication-manifest/1',
        'base_commit': BASE_COMMIT, 'base_tree': BASE_TREE,
        'existing_blobs_preserved': len(leaves), 'existing_replacements': [],
        'selected_files_excluding_manifest': artifacts,
        'selection': args.selection, 'selection_sha256': digest((ROOT / args.selection).read_bytes()),
        'scope': 'Align exactly three static-plan predicates in two existing SQL helpers with the installed explicit dynamic exclusions. Preserve all plan count, hash, calendar, coverage, representative-map, ownership and security checks.',
        'security_diff': selection['security_diff'],
        'local_qualification': selection['local_qualification'],
        'independent_review': selection['independent_review'],
        'held_v75': {'state': 'RECOVERY_HOST_REJECTED_NO_RETRY_HOLD', 'packet_sha256': digest(held_raw), 'expected_tree': 'e56dc140deeb00eb2a0aae4e7d572519d773ccd0', 'overlapping_selected_paths': [], 'remaining_object_retry_budget': 0, 'remaining_readback_budget': 0},
        'activation_gate': 'Exact published-commit CI with explicit new-test collection; current owner, finite lease, stop/fence, fixed cohort and source/OID/full metadata readback; reserve one guarded migration and reconcile uncertain outcomes before retry; independently verify installed sources and ordinary-worker planner/acquisition results.',
        'worker_deployment': 'Existing08bea deployment remains unchanged. This SQL-only release does not trigger, restart or redeploy the worker.',
        'reporting_policy': 'DOT_CONSOLIDATED_CHECKPOINTS_ONLY',
        'mission_complete': False,
    }
    manifest_raw = (json.dumps(manifest, indent=2, ensure_ascii=False) + '\n').encode()
    (ROOT / MANIFEST).write_bytes(manifest_raw)
    entries.append({'path': MANIFEST, 'mode': '100644', 'type': 'blob', 'content': manifest_raw.decode()})
    proposed = dict(leaves)
    for entry in entries:
        path = entry['path']
        proposed[path] = {'path': path, 'mode': entry['mode'], 'type': 'blob', 'sha': go.object_sha('blob', entry['content'].encode())}
    assert all(proposed[path]['sha'] == item['sha'] for path, item in leaves.items())
    tree, trees = go.root_sha(proposed)
    packet = {'schema': 'astra.planner-seal-additive-publication-packet/1', 'repository_full_name': 'robert8p/Alpaca-Supabase-Populator', 'branch': 'feat/astra-ingestion-service', 'base_commit': BASE_COMMIT, 'base_tree': BASE_TREE, 'expected_result_tree': tree, 'existing_blobs_preserved': len(leaves), 'result_blob_count': len(proposed), 'manifest_sha256': digest(manifest_raw), 'tree_entries': entries}
    raw = (json.dumps(packet, indent=2, ensure_ascii=False) + '\n').encode()
    packet_path = ROOT / 'review/recovery-v78/planner_seal_publication_packet_v78.json'
    packet_path.write_bytes(raw)
    proof = {'schema': 'astra.planner-seal-publication-local-proof/1', 'base_commit': BASE_COMMIT, 'base_tree': BASE_TREE, 'expected_result_tree': tree, 'entry_count': len(entries), 'existing_blobs_preserved': len(leaves), 'changed_existing_paths': [], 'result_blob_count': len(proposed), 'packet_path': packet_path.relative_to(ROOT).as_posix(), 'packet_sha256': digest(raw), 'packet_bytes': len(raw), 'manifest_sha256': digest(manifest_raw), 'tree_objects': trees, 'expected_leaves': sorted([dict(item, path=path) for path, item in proposed.items()], key=lambda item: item['path'])}
    (ROOT / 'review/recovery-v78/planner_seal_publication_local_proof_v78.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps({key: value for key, value in proof.items() if key not in ('tree_objects', 'expected_leaves')}))

if __name__ == '__main__':
    main()
