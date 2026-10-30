"""Verify every actual qualification dependency against the immutable base tree."""
from hashlib import sha1, sha256
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
STAGE = Path("/tmp/replacement-maintenance-index-staged-v72")
TREE = Path("/tmp/replacement-phase-observation-tree-v73.json")
QUALIFICATION = HERE / "qualification_final.json"


def sha(path):
    return sha256(path.read_bytes()).hexdigest()


def main():
    tree = json.loads(TREE.read_text())
    assert not tree["truncated"]
    base = {row["path"]: row["sha"] for row in tree["tree"] if row["type"] == "blob"}
    qualification = json.loads(QUALIFICATION.read_text())
    assert qualification["status"] == "PASS" and qualification["skips"] == 0
    intended_runtime_changes = {"astra_ingestion/rpc_store.py"}
    intended_additions = {
        "tests/ingestion/test_rpc_lock_abort_retry.py",
        "tests/ingestion/test_rpc_lock_abort_retry_postgres.py",
        "review/recovery-v74/retry_closure_root_definitions_v74.json",
        "review/recovery-v74/retry_closure_callees_and_catalog_v74.json",
    }
    rows, unexpected, changes, additions = [], [], [], []
    for row in qualification["opened_or_imported_dependencies"]:
        path = STAGE / row["path"]
        raw = path.read_bytes()
        assert sha256(raw).hexdigest() == row["sha256"], row["path"]
        blob = sha1(b"blob " + str(len(raw)).encode() + b"\0" + raw).hexdigest()
        expected = base.get(row["path"])
        if expected is None:
            additions.append(row["path"])
            if row["path"] not in intended_additions:
                unexpected.append(row["path"])
            state = "INTENDED_ADDITION"
        elif blob != expected:
            changes.append(row["path"])
            if row["path"] not in intended_runtime_changes:
                unexpected.append(row["path"])
            state = "INTENDED_RUNTIME_REPLACEMENT"
        else:
            state = "EXACT_EXISTING_PUBLISHED_BLOB"
        if row["path"] in intended_runtime_changes | intended_additions:
            assert (ROOT / row["path"]).read_bytes() == raw, row["path"]
        rows.append({**row, "actual_git_blob": blob, "base_git_blob": expected, "state": state})
    assert set(changes) == intended_runtime_changes
    assert set(additions) == intended_additions
    assert not unexpected, unexpected
    publication = ROOT / "evidence/replacement-published-checkpoint-v73.json"
    output = {
        "schema": "astra.confirmed-lock-abort-dependency-audit/1",
        "status": "PASS", "actual_dependency_count": len(rows),
        "base_tree": tree["sha"], "base_commit": "3fddb6cf196e289e79eb9bfaef45d56965b64eca",
        "current_published_checkpoint": "a3bc0520e624054b278e46682b04cebb33e9b677",
        "checkpoint_preservation_evidence": {"path": str(publication.relative_to(ROOT)), "sha256": sha(publication),
            "claim": "a3bc changed only two canonical documents and added27 evidence files; active code and dependencies remained byte-identical"},
        "qualification": {"path": str(QUALIFICATION.relative_to(ROOT)), "sha256": sha(QUALIFICATION)},
        "runtime_replacements": changes, "new_actual_read_dependencies": additions,
        "unexpected_existing_blob_changes": unexpected, "dependencies": rows,
        "workspace_caution": "The main workspace retains older foundation files. Publication must replace only the explicitly named runtime file and add the new files; use the immutable remote base for existing dependencies.",
        "production_calls": 0, "publication_or_deployment": "NOT_PERFORMED",
    }
    destination = HERE / "dependency_audit.json"
    destination.write_text(json.dumps(output, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": output["status"], "actual_dependencies": len(rows),
        "runtime_replacements": changes, "additions": additions, "sha256": sha(destination)}, indent=2))


if __name__ == "__main__":
    main()
