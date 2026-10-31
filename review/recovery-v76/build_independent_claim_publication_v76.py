"""Build an explicit additive claim-repair publication; never include held v75 work."""
from __future__ import annotations
import argparse
import hashlib
import json
from pathlib import Path

BASE_COMMIT = 'e694009d75f3fd91c69976befa0e12838e64efec'
BASE_TREE = '3599d2822a30b658666ab219e8eeca728f3917df'
MANIFEST = 'evidence/replacement-independent-claim-publication-manifest-v76.json'

def object_sha(kind: str, data: bytes) -> str:
    return hashlib.sha1(kind.encode() + b' ' + str(len(data)).encode() + b'\0' + data).hexdigest()

def root_sha(leaves: dict) -> tuple[str, dict]:
    dirs: dict[str, dict] = {'': {}}
    for path, item in leaves.items():
        parts = path.split('/')
        for n in range(1, len(parts)):
            dirs.setdefault('/'.join(parts[:n]), {})
        parent, name = path.rsplit('/', 1) if '/' in path else ('', path)
        dirs[parent][name] = {'mode': item['mode'], 'sha': item['sha'], 'type': item['type']}
    hashes = {}
    for directory in sorted(dirs, key=lambda x: (x.count('/') + bool(x), x), reverse=True):
        children = dirs[directory]
        raw = b''.join((format(int(v['mode'], 8), 'o') + ' ' + name).encode() + b'\0' + bytes.fromhex(v['sha'])
                       for name, v in sorted(children.items(), key=lambda kv: (kv[0] + ('/' if kv[1]['type'] == 'tree' else '')).encode()))
        hashes[directory] = object_sha('tree', raw)
        if directory:
            parent, name = directory.rsplit('/', 1) if '/' in directory else ('', directory)
            dirs[parent][name] = {'mode': '040000', 'type': 'tree', 'sha': hashes[directory]}
    return hashes[''], hashes

def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument('--paths', required=True)
    ap.add_argument('--base-tree-file', default='/tmp/replacement-combined-reliability-tree-v74.json')
    ap.add_argument('--packet-out', default='/tmp/replacement-independent-claim-publication-packet-v76.json')
    args = ap.parse_args()
    repo = Path(__file__).resolve().parents[2]
    base = json.loads(Path(args.base_tree_file).read_text())
    assert base['sha'] == BASE_TREE and not base.get('truncated'), 'Base tree differs or is incomplete'
    leaves = {x['path']: x for x in base['tree'] if x['type'] != 'tree'}
    assert len(leaves) == 1063 and root_sha(leaves)[0] == BASE_TREE, 'Full base reconstruction differs'
    paths = json.loads(Path(args.paths).read_text())
    assert isinstance(paths, list) and len(paths) == len(set(paths)) and MANIFEST not in paths
    held = json.loads(Path('/tmp/replacement-checkpoint-publication-packet-v75.json').read_text())
    held_paths = {x['path'] for x in held['tree_entries']}
    assert not set(paths) & held_paths, 'Independent repair includes a held checkpoint payload'
    assert all(p not in leaves for p in paths + [MANIFEST]), 'Independent release must preserve all existing blobs'
    assert all(not p.startswith('docs/') and not p.startswith('astra_ingestion/') for p in paths)
    assert all(not (p.startswith('review/') and Path(p).name.startswith('test_') and p.endswith('.py')) for p in paths)
    selected, entries = [], []
    for path in sorted(paths):
        data = (repo / path).read_bytes()
        content = data.decode('utf-8')
        selected.append({'path': path, 'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                         'git_blob_sha1': object_sha('blob', data), 'mode': '100644'})
        entries.append({'path': path, 'mode': '100644', 'type': 'blob', 'content': content})
    manifest = {'schema': 'astra.independent-claim-publication-manifest/1', 'base_commit': BASE_COMMIT,
                'base_tree': BASE_TREE, 'existing_blobs_preserved': len(leaves), 'existing_replacements': [],
                'selected_files_excluding_manifest': selected,
                'scope': 'Independent query-only claim cursor repair, tests and evidence; no held v75 checkpoint or identity rollout',
                'held_checkpoint_preserved': {'packet_sha256': '8806ef636f5be4220562b0ee52d64426f620461d8ad99adef5f9edd1f9724da3',
                                             'expected_tree': 'e56dc140deeb00eb2a0aae4e7d572519d773ccd0',
                                             'state': 'HOST_REJECTED_NO_RETRY_HOLD'},
                'later_checkpoint_rule': 'Reconcile against the then-current head and retain this independent repair; never advance the branch to the held historical tree over a newer repair.',
                'activation_gate': 'Exact new-source CI, current ownership/source reconciliation and one guarded SQL migration with independent readback; no Render rollout or manual restart.'}
    data = (json.dumps(manifest, indent=2, ensure_ascii=False) + '\n').encode()
    (repo / MANIFEST).write_bytes(data)
    entries.append({'path': MANIFEST, 'mode': '100644', 'type': 'blob', 'content': data.decode()})
    proposed = dict(leaves)
    for entry in entries:
        proposed[entry['path']] = {'path': entry['path'], 'mode': entry['mode'], 'type': 'blob',
                                  'sha': object_sha('blob', entry['content'].encode())}
    expected, trees = root_sha(proposed)
    packet = {'schema': 'astra.independent-claim-publication-packet/1', 'repository_full_name': 'robert8p/Alpaca-Supabase-Populator',
              'branch': 'feat/astra-ingestion-service', 'base_commit': BASE_COMMIT, 'base_tree': BASE_TREE,
              'expected_result_tree': expected, 'existing_blobs_preserved': len(leaves), 'result_blob_count': len(proposed),
              'manifest_sha256': hashlib.sha256(data).hexdigest(), 'manifest_git_blob_sha1': object_sha('blob', data),
              'tree_entries': entries}
    packet_bytes = (json.dumps(packet, indent=2, ensure_ascii=False) + '\n').encode()
    Path(args.packet_out).write_bytes(packet_bytes)
    proof = {'base_commit': BASE_COMMIT, 'base_tree': BASE_TREE, 'expected_result_tree': expected,
             'entry_count': len(entries), 'retained_blobs': len(leaves), 'result_blobs': len(proposed),
             'packet_sha256': hashlib.sha256(packet_bytes).hexdigest(), 'packet_bytes': len(packet_bytes),
             'manifest_sha256': packet['manifest_sha256'], 'tree_objects': trees,
             'expected_leaves': sorted([dict(v, path=k) for k, v in proposed.items()], key=lambda x: x['path'])}
    (repo / 'review/recovery-v76/independent_claim_publication_local_proof_v76.json').write_text(json.dumps(proof, indent=2) + '\n')
    print(json.dumps({k: v for k, v in proof.items() if k not in ('tree_objects', 'expected_leaves')}))

if __name__ == '__main__':
    main()
