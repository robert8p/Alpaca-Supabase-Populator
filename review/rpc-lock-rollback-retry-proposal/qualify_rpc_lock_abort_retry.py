"""Run active tests and retain their exact opened local dependency closure."""
import argparse
from contextlib import redirect_stderr, redirect_stdout
from hashlib import sha256
import io
import json
from pathlib import Path
import sys
from time import perf_counter
import unittest


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    root = args.root.resolve()
    opened = set()
    def audit(event, values):
        if event == "open" and values and isinstance(values[0], str):
            path = Path(values[0]).resolve()
            if path.is_relative_to(root) and path.suffix in {".py", ".sql", ".json"}:
                opened.add(path)
    sys.addaudithook(audit)
    sys.path[:0] = [str(root), str(root / "tests/ingestion")]
    names = ["test_rpc_lock_abort_retry", "test_rpc_lock_abort_retry_postgres",
             "test_rpc_store", "test_rpc_failure_observability_v71"]
    suite = unittest.defaultTestLoader.loadTestsFromNames(names)
    stream, captured_out, captured_err = io.StringIO(), io.StringIO(), io.StringIO()
    started = perf_counter()
    with redirect_stdout(captured_out), redirect_stderr(captured_err):
        result = unittest.TextTestRunner(stream=stream, verbosity=2).run(suite)
    for module in list(sys.modules.values()):
        filename = getattr(module, "__file__", None)
        if isinstance(filename, str):
            path = Path(filename).resolve()
            if path.is_relative_to(root) and path.suffix == ".py":
                opened.add(path)
    dependencies = [{"path": str(path.relative_to(root)), "sha256": sha256(path.read_bytes()).hexdigest(),
                     "bytes": path.stat().st_size} for path in sorted(opened) if path.exists()]
    receipt = {
        "schema": "astra.rpc-confirmed-lock-abort-retry-qualification/1",
        "status": "PASS" if result.wasSuccessful() and not result.skipped else "FAIL_OR_SKIPPED",
        "tests": result.testsRun, "failures": len(result.failures), "errors": len(result.errors),
        "skips": len(result.skipped), "seconds": round(perf_counter() - started, 3),
        "modules": names, "test_log": stream.getvalue(), "stdout": captured_out.getvalue(),
        "stderr": captured_err.getvalue(), "opened_or_imported_dependencies": dependencies,
        "postgresql_evidence": getattr(sys.modules.get("test_rpc_lock_abort_retry_postgres"), "RESULT", {"status": "NOT_IMPORTED"}),
        "production_calls": 0, "provider_calls": 0,
        "deployment_hold": "INDEPENDENT_REVIEW_AND_EXACT_PUBLISHED_HEAD_CI_REQUIRED",
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({key: receipt[key] for key in ("status", "tests", "failures", "errors", "skips", "seconds")}))
    print(stream.getvalue() if not result.wasSuccessful() else "All named active tests passed.")
    return 0 if result.wasSuccessful() and not result.skipped else 1


if __name__ == "__main__":
    raise SystemExit(main())
