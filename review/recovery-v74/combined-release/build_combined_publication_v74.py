"""Build one explicit combined release after a documentation/evidence-only head.

This local builder never calls GitHub, a production database, or a deployment API.
It preserves the original qualification base and proves its dependencies remain
unchanged instead of rewriting old qualification or independent-review receipts.
"""
from datetime import datetime, timezone
from hashlib import sha1, sha256
from pathlib import Path, PurePosixPath
import argparse
import gzip
import io
import json
import re
import tarfile

ROOT = Path(__file__).resolve().parents[3]
HERE = "review/recovery-v74/combined-release"
QUALIFICATION = HERE + "/combined_active_dependency_qualification_v74.json"
QUALIFIED_BASE = "a3bc0520e624054b278e46682b04cebb33e9b677"
QUALIFIED_TREE = "52d5ed1305aff8246599b689176d8732f2dadb2f"
RUNTIME = "astra_ingestion/rpc_store.py"
ACTIVE = {
    RUNTIME: "1deb7051d4311b22c09d7245a36d751dd10c843192207aaefc0a2d4cf1291403",
    "tests/ingestion/test_rpc_lock_abort_retry.py": "f0f2bc191b60c4fe737af763fe57c1b939edf2d2ffed7fcaee7df4f726976468",
    "tests/ingestion/test_rpc_lock_abort_retry_postgres.py": "ad9ded264e3f18cae54417a8a6cf5765b22a01e04d7af876034735bb38404570",
    "tests/ingestion/test_backfill_shared_field_cache_v74.py": "6ed056ec347cfe6f43706a5e06f2f7ab013e179a70711f4bb3ab20e0cd65dac8",
    "tests/ingestion/test_backfill_shared_field_cache_installation_v74.py": "f4856947f23dae88df8e5d1ce7de72363a1034fa6ea1c9052a8f8c5100caaef0",
    "sql/astra_backfill_shared_field_cache_v74.sql": "b11210b980ad7afb4f821b184d2682d1d3123406da6cf47ece4bb9855803777b",
    "sql/astra_backfill_shared_field_cache_restore_v74.sql": "4fa9d60877b25355445f0d3b8b630d87630f1e2bb00a5896a1bb83fcd4fef376",
}
MANIFEST = "evidence/replacement-combined-reliability-publication-manifest-v74.json"
REBASE = HERE + "/combined_dependency_rebase_v74.json"
HASH = re.compile(r"[a-f0-9]{64}\Z")
GIT_HASH = re.compile(r"[a-f0-9]{40}\Z")


def safe_path(value, root=ROOT):
    if type(value) is not str or not re.fullmatch(r"[A-Za-z0-9_./-]+", value):
        raise ValueError("Noncanonical repository path")
    p = PurePosixPath(value)
    if p.is_absolute() or str(p) != value or any(x in ("", ".", "..") for x in value.split("/")):
        raise ValueError("Noncanonical repository path")
    q = root
    for part in p.parts:
        q = q / part
        if q.is_symlink():
            raise ValueError("Symlink input is forbidden")
    if not q.resolve().is_relative_to(root.resolve()):
        raise ValueError("Input escaped repository")
    return q


def read(path):
    return safe_path(path).read_bytes()


def document(path):
    return json.loads(read(path))


def git_blob(data):
    return sha1(b"blob " + str(len(data)).encode() + b"\0" + data).hexdigest()


def record(path, data):
    return {"path": path, "bytes": len(data), "sha256": sha256(data).hexdigest(), "git_blob_sha1": git_blob(data)}


def pinned(path, pin):
    if type(pin) is not str or HASH.fullmatch(pin) is None:
        raise ValueError("Invalid SHA256 pin")
    data = read(path)
    if sha256(data).hexdigest() != pin:
        raise ValueError("Frozen input drift: " + path)
    return data


def tree(path, expected):
    # Tree inputs live in /tmp but are themselves explicitly byte-pinned by the
    # selected inputs. Reject a symlink before opening that local input as well.
    p = Path(path)
    if not p.is_absolute() or p.parent != Path("/tmp") or p.is_symlink():
        raise ValueError("Tree snapshot must be a regular direct /tmp file")
    raw = p.read_bytes()
    if sha256(raw).hexdigest() != expected["sha256"]:
        raise ValueError("Frozen tree input drift")
    result = json.loads(raw)
    if result.get("sha") != expected["tree"] or result.get("truncated") is not False:
        raise ValueError("Exact full tree is required")
    rows = result["tree"]
    seen = set()
    for item in rows:
        safe_path(item["path"])
        if item["path"] in seen:
            raise ValueError("Duplicate Git tree path")
        seen.add(item["path"])
    return {x["path"]: x for x in rows if x["type"] == "blob"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", required=True)
    args = parser.parse_args()
    inputs = document(args.inputs)
    if inputs.get("schema") != "astra.combined-reliability-publication-inputs/1":
        raise ValueError("Unknown frozen inputs schema")
    base, base_tree = inputs["base_commit"], inputs["base_tree"]
    if GIT_HASH.fullmatch(base) is None or GIT_HASH.fullmatch(base_tree) is None:
        raise ValueError("Invalid publication base")
    old = tree(inputs["qualified_tree_input"]["path"], inputs["qualified_tree_input"])
    current = tree(inputs["publication_tree_input"]["path"], inputs["publication_tree_input"])
    if inputs["qualified_tree_input"]["tree"] != QUALIFIED_TREE or inputs["publication_tree_input"]["tree"] != base_tree:
        raise ValueError("Tree input does not bind the declared base")
    pins = inputs["selected_artifact_pins"]
    for path, pin in pins.items():
        pinned(path, pin)
    decision = inputs.get("root_conditional_deployment_decision", {})
    if not (decision.get("path") in pins
            and pins[decision["path"]] == decision.get("sha256")
            and decision.get("is_not_a_claim_of_activation") is True):
        raise ValueError("Root's conditional decision must be explicitly selected and hash-bound")
    if any(pins.get(path) != pin for path, pin in ACTIVE.items()):
        raise ValueError("Exact seven active paths must be selected")
    if args.inputs in pins or MANIFEST in pins or REBASE in pins:
        raise ValueError("Generated outputs cannot be self-pinned inputs")
    if QUALIFICATION not in pins:
        raise ValueError("Actual read/import qualification must be hash-bound")
    audit = document(QUALIFICATION)
    if not (audit.get("passed") is True and audit.get("base_commit") == QUALIFIED_BASE
            and audit.get("base_tree") == QUALIFIED_TREE and audit.get("tests") == 56
            and audit.get("errors") == audit.get("failures") == audit.get("skipped") == 0
            and audit.get("active_paths") == ACTIVE
            and not audit.get("unexpected_existing_blob_differences")):
        raise ValueError("Final combined qualification is incomplete or for other bytes")
    observed = audit["actual_reads_and_imports"]
    if len(observed) != audit["actual_dependency_count"] or len({x["path"] for x in observed}) != len(observed):
        raise ValueError("Dependency inventory is inconsistent")

    # Preserve the original independent reviews. The explicit tree comparison
    # below is the only basis for carrying their exact-byte findings forward.
    reviewed = {}
    for path in inputs["independent_review_paths"]:
        if path not in pins:
            raise ValueError("Independent review is not hash-bound")
        review = document(path)
        if review.get("passed") is not True or review.get("base_commit") != QUALIFIED_BASE:
            raise ValueError("Independent review must explicitly bind the qualified base")
        if review.get("base_tree", QUALIFIED_TREE) != QUALIFIED_TREE:
            raise ValueError("Independent review tree conflicts with its qualified base")
        for source, pin in review.get("reviewed_artifact_pins", {}).items():
            if source not in pins or pins[source] != pin:
                raise ValueError("Independent source binding is missing or differs: " + source)
            pinned(source, pin)
            if source in reviewed and reviewed[source] != pin:
                raise ValueError("Independent review bindings conflict")
            reviewed[source] = pin
    if any(reviewed.get(path) != pin for path, pin in ACTIVE.items()):
        raise ValueError("Independent reviews do not cover the seven exact active paths")

    changed_base = []
    for path in sorted(set(old) | set(current)):
        before, after = old.get(path), current.get(path)
        if before == after:
            continue
        if after is None:
            raise ValueError("A reporting-only rebase cannot delete a base blob")
        if not path.startswith(("docs/", "evidence/", "review/")):
            raise ValueError("Rebase changed an executable or other unadmitted blob: " + path)
        changed_base.append({"path": path, "before": before, "after": after})
    if [x["path"] for x in changed_base] != inputs["expected_reporting_base_changes"]:
        raise ValueError("The actual reporting-only tree changes differ from the selected list")

    dependency_proof = []
    required_new = []
    for item in observed:
        path = item["path"]
        safe_path(path)
        before = old.get(path)
        after = current.get(path)
        baseline_blob = item["base_git_blob_sha1"]
        if (before or {}).get("sha") != baseline_blob:
            raise ValueError("Qualification does not match its immutable base: " + path)
        if baseline_blob is not None:
            if after is None or after["sha"] != baseline_blob or after != before:
                raise ValueError("A qualified existing dependency changed on rebase: " + path)
            if path != RUNTIME and item["git_blob_sha1"] != baseline_blob:
                raise ValueError("An unreviewed existing dependency changed in qualification")
        else:
            if after is not None and after["sha"] != item["git_blob_sha1"]:
                raise ValueError("A newly observed fixture conflicts with the publication base")
            if pins.get(path) != item["sha256"]:
                raise ValueError("A new actual fixture dependency is not selected and pinned: " + path)
            if after is None:
                required_new.append(path)
        dependency_proof.append({**item, "publication_base_git_blob_sha1": (after or {}).get("sha"),
                                 "unchanged_or_exact_addition_on_publication_base": True})

    paths = set(pins) | {args.inputs}
    payload = {}
    refs = []
    for path in sorted(paths):
        if path.startswith(("docs/", ".github/")):
            raise ValueError("Canonical document/workflow edits are outside this release")
        if path.startswith(("astra_ingestion/", "sql/", "tests/")) and path not in ACTIVE:
            raise ValueError("Unexpected executable path in combined release: " + path)
        if path not in ACTIVE and not path.startswith(("evidence/", "review/")):
            raise ValueError("Unexpected artifact namespace")
        data = read(path)
        item = record(path, data)
        prior = current.get(path)
        item["base_git_blob_sha1"] = (prior or {}).get("sha")
        item["base_state"] = "ABSENT" if prior is None else "IDENTICAL" if prior["sha"] == item["git_blob_sha1"] else "DIFFERENT"
        if prior is not None and (prior.get("mode") != "100644" or prior.get("type") != "blob"):
            raise ValueError("Unexpected selected base file mode")
        if item["base_state"] == "DIFFERENT" and path != RUNTIME:
            raise ValueError("Only rpc_store.py may replace an existing blob: " + path)
        if path == RUNTIME and item["base_state"] != "DIFFERENT":
            raise ValueError("The intended replacement is already present or lacks its baseline; reconcile before rebuilding")
        refs.append(item)
        if item["base_state"] != "IDENTICAL":
            payload[path] = data
    if any(path not in payload and path not in current for path in required_new):
        raise ValueError("Actual-read fixture publication closure is incomplete")

    rebase = {
        "schema": "astra.combined-reliability-dependency-rebase/1", "passed": True,
        "qualified_base_commit": QUALIFIED_BASE, "qualified_base_tree": QUALIFIED_TREE,
        "publication_base_commit": base, "publication_base_tree": base_tree,
        "original_qualification": record(QUALIFICATION, read(QUALIFICATION)),
        "original_review_receipts": [record(p, read(p)) for p in inputs["independent_review_paths"]],
        "documentation_and_evidence_base_changes": changed_base,
        "existing_runtime_sql_test_workflow_blobs_unchanged": True,
        "dependency_count": len(dependency_proof), "dependencies": dependency_proof,
        "no_old_receipt_rewritten_or_redated": True, "additional_test_run_claimed": False,
        "no_production_call_or_publication_performed": True,
    }
    rebase_bytes = (json.dumps(rebase, indent=2) + "\n").encode()
    if REBASE in current:
        raise ValueError("The generated rebase receipt already exists; reconcile before rebuilding")
    safe_path(REBASE).write_bytes(rebase_bytes)
    payload[REBASE] = rebase_bytes
    manifest = {
        "schema": "astra.combined-reliability-publication-manifest/1",
        "state": "PREPARED_LOCAL_NOT_PUBLISHED_NOT_ACTIVATED",
        "created_at": datetime.now(timezone.utc).isoformat(),
        "repository": "robert8p/Alpaca-Supabase-Populator",
        "base_commit": base, "base_tree": base_tree,
        "qualification_base_commit": QUALIFIED_BASE, "qualification_base_tree": QUALIFIED_TREE,
        "scope": "One strictly classified rolled-back 55P03 RPC retry replacement; additive guarded shared-field refresh optimization and exact restore; focused tests and closed evidence.",
        "intended_existing_replacements": [RUNTIME],
        "active_additions": sorted(set(ACTIVE) - {RUNTIME}), "active_artifact_pins": ACTIVE,
        "all_other_existing_blobs_retained": True,
        "existing_base_blob_count": len(current),
        "resulting_blob_count": len(current) + sum(p not in current for p in payload) + 1,
        "canonical_documents_and_reporting_only_changes_preserved": True,
        "runtime_replacement_is_only_rpc_store": True,
        "other_worker_module_changes": False,
        "authentication_grant_credential_provider_schedule_changes": False,
        "strict_rpc_transport_change_is_separately_reviewed": True,
        "actual_read_import_dependency_count": len(observed),
        "new_actual_read_dependencies": sorted(required_new),
        "local_qualification": {"tests": 56, "errors": 0, "failures": 0, "skips": 0,
                                "receipt": record(QUALIFICATION, read(QUALIFICATION))},
        "dependency_rebase": record(REBASE, rebase_bytes),
        "independent_reviews": [record(p, read(p)) for p in inputs["independent_review_paths"]],
        "root_conditional_deployment_decision": record(decision["path"], read(decision["path"])),
        "required_before_activation": [
            "Root reconciles the exact published head, existing controller/successor, owner/fence/cohort/lease and any uncertain write.",
            "All actual exact-head CI gates pass; the dedicated PostgreSQL suite executes every new case with zero skips.",
            "Shared SQL is applied once only after its exact source/metadata/catalog guards pass, followed by independent readback.",
            "The six retry operations require fresh current source and complete transactional-boundary reconciliation, including any selected shared helper replacement, before selecting the exact worker deployment.",
            "Root alone selects deployment and reads back the exact runtime commit; real subsequent pages/readbacks and errors determine recovery.",
        ],
        "limitations": [
            "The shared optimization reduces demonstrated repeated buffer work but increases temporary I/O; separate live snapshots do not establish a controlled latency ratio or whole-cron recovery.",
            "The exact source-only restore preserves data and status; it does not roll back previously acquired data.",
            "Earlier failed fixture/qualification attempts remain retained as evidence and are not reported as passes.",
            "Unselected historical pure-read preparation is not authority to replay helpers or repeat already completed probes.",
        ],
        "production_calls_by_builder": 0, "remote_mutations_by_builder": 0,
        "selected_artifacts": refs,
        "payload_files_excluding_manifest": [record(p, d) for p, d in sorted(payload.items())],
    }
    if MANIFEST in current:
        raise ValueError("The generated release manifest already exists; reconcile before rebuilding")
    manifest_bytes = (json.dumps(manifest, indent=2) + "\n").encode()
    safe_path(MANIFEST).write_bytes(manifest_bytes)
    payload[MANIFEST] = manifest_bytes
    packet = {
        "schema": "astra.combined-reliability-publication-packet/1", "base_commit": base, "base_tree": base_tree,
        "expected_head_must_be_reconciled_before_mutation": True,
        "manifest": record(MANIFEST, manifest_bytes),
        "tree_entries": [{"path": p, "mode": "100644", "type": "blob", "content": d.decode("utf-8")}
                         for p, d in sorted(payload.items())],
    }
    out = Path("/tmp/replacement-combined-reliability-publication-packet-v74.json")
    out.write_text(json.dumps(packet, ensure_ascii=False) + "\n")
    listing = Path("/tmp/replacement-combined-reliability-publication-files-v74.txt")
    listing.write_text("\n".join(sorted(payload)) + "\n")
    archive = Path("/tmp/replacement-combined-reliability-publication-packet-v74.tar.gz")
    with archive.open("wb") as stream, gzip.GzipFile(fileobj=stream, mode="wb", mtime=0) as zipped, tarfile.open(fileobj=zipped, mode="w") as tar:
        for path, data in sorted(payload.items()):
            info = tarfile.TarInfo(path)
            info.size, info.mode, info.mtime = len(data), 0o644, 0
            tar.addfile(info, io.BytesIO(data))
    print(json.dumps({"files": len(payload), "existing_replacements": [RUNTIME],
                      "new_files": sum(p not in current for p in payload),
                      "manifest": record(MANIFEST, manifest_bytes),
                      "packet": record(str(out), out.read_bytes()),
                      "archive": record(str(archive), archive.read_bytes()),
                      "file_list": str(listing), "actual_dependencies": len(observed)}))


if __name__ == "__main__":
    main()
