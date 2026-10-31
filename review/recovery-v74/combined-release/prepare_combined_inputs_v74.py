"""Merge two frozen explicit scopes; never glob changing review directories."""
from pathlib import Path
from hashlib import sha256
import argparse
import importlib.util
import json

ROOT = Path(__file__).resolve().parents[3]
HERE = "review/recovery-v74/combined-release"
spec = importlib.util.spec_from_file_location("combined_packet", ROOT / HERE / "build_combined_publication_v74.py")
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)
SHARED = HERE + "/shared_artifact_selection_v74.json"
SHARED_PIN = "2800495cc1db5c4dd332f92c9dd39e80fb1f24e015b852d20848c9e86d15b28a"
RETRY = "review/rpc-lock-rollback-retry-proposal/frozen_publication_scope.json"
RETRY_PIN = "03ef5f5ed25a91a59e8224bbb1fb9a75f9103437e7b671cb56fa16b2ec1e8b55"
SHARED_REVIEW = "review/recovery-v74/shared-field-cache/independent_shared_field_release_review_v74.json"
BASE = "a3e48a080c70c802a2fbb1a1bb5db29b0d7aee62"
TREE = "71db22123ba2db26d1135916cb91081b03bab2cb"
CONTINUITY = (
    "evidence/replacement-published-checkpoint-v74.json",
    "review/recovery-v74/checkpoint_metadata_attempt1_v74.json",
    "review/recovery-v74/live_progress_1643_v74.json",
)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--retry-review", required=True)
    ap.add_argument("--retry-review-sha256", required=True)
    ap.add_argument("--root-decision", required=True)
    ap.add_argument("--root-decision-sha256", required=True)
    args = ap.parse_args()
    shared = json.loads(builder.pinned(SHARED, SHARED_PIN))
    retry = json.loads(builder.pinned(RETRY, RETRY_PIN))
    if not (retry.get("frozen") is True and retry.get("no_writes_in_flight") is True
            and retry.get("base_commit") == builder.QUALIFIED_BASE
            and retry.get("publication_target_base_commit") == BASE
            and retry.get("runtime_replacements") == [builder.RUNTIME]):
        raise ValueError("The explicit retry scope is not frozen for this base")
    pins = dict(shared["selected_artifact_pins"])
    for item in retry["files"]:
        path, pin = item["path"], item["sha256"]
        if path in pins and pins[path] != pin:
            raise ValueError("Frozen component scopes conflict")
        pins[path] = pin
    audit = builder.document(builder.QUALIFICATION)
    for item in audit["actual_reads_and_imports"]:
        if item["state"] == "EXACT_EXISTING_BLOB":
            continue
        if item["path"] in pins and pins[item["path"]] != item["sha256"]:
            raise ValueError("Actual active/dependency bytes differ from the selected scope")
        pins[item["path"]] = item["sha256"]
    pins.update({SHARED: SHARED_PIN, RETRY: RETRY_PIN,
                 args.retry_review: args.retry_review_sha256,
                 args.root_decision: args.root_decision_sha256})
    for path in CONTINUITY:
        pins[path] = sha256(builder.read(path)).hexdigest()
    for path in (HERE + "/build_combined_publication_v74.py", HERE + "/prepare_combined_inputs_v74.py"):
        pins[path] = sha256(builder.read(path)).hexdigest()
    for path, pin in pins.items():
        builder.pinned(path, pin)
    old_path = Path("/tmp/replacement-combined-qualification-base-tree-v74.json")
    current_path = Path("/tmp/replacement-checkpoint-tree-v74.json")
    old_input = {"path": str(old_path), "sha256": sha256(old_path.read_bytes()).hexdigest(), "tree": builder.QUALIFIED_TREE}
    new_input = {"path": str(current_path), "sha256": sha256(current_path.read_bytes()).hexdigest(), "tree": TREE}
    old = builder.tree(str(old_path), old_input)
    new = builder.tree(str(current_path), new_input)
    changed = [p for p in sorted(set(old) | set(new)) if old.get(p) != new.get(p)]
    result = {
        "schema": "astra.combined-reliability-publication-inputs/1",
        "base_commit": BASE, "base_tree": TREE,
        "qualified_tree_input": old_input, "publication_tree_input": new_input,
        "selected_artifact_pins": dict(sorted(pins.items())),
        "independent_review_paths": [SHARED_REVIEW, args.retry_review],
        "root_conditional_deployment_decision": {
            "path": args.root_decision, "sha256": args.root_decision_sha256,
            "is_not_a_claim_of_activation": True,
        },
        "expected_reporting_base_changes": changed,
        "scope": "Seven exact active paths plus frozen explicit component evidence and actual-read fixture closure; no canonical document change.",
        "root_is_sole_publisher_installer_and_deployer": True,
        "no_production_call_or_mutation_performed": True,
    }
    out = builder.safe_path(HERE + "/combined_publication_inputs_v74.json")
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"path": out.relative_to(ROOT).as_posix(), "sha256": sha256(out.read_bytes()).hexdigest(),
                      "selected_files": len(pins), "base_changes": len(changed)}))


if __name__ == "__main__":
    main()
