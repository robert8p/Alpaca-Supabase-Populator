"""Independently execute the frozen v73 suite against disposable loopback PG only."""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import importlib
import json
import os
from pathlib import Path
import sys
from time import perf_counter
import unittest

ROOT = Path(__file__).resolve().parents[2]
EXPECTED_TARGET = "postgresql://postgres@127.0.0.1:55432/astra_ingestion_qualification"
PINS = {
    "review/recovery-v73/baseline_maintain_installed_v73.sql":
        "6c880114a645c8a9167d5260c4aeabf58a10617c4244cf0340be1d6cf4bf0ce7",
    "review/recovery-v73/candidate_maintain_phase_observation_v73.sql":
        "12e05b1fa5a6e59f1f626a33aaec4e30248d0cfc858917be171fd812b41c229d",
    "review/recovery-v73/maintenance_phase_observation_derivation_v73.json":
        "09d0d67217b0dcb2c129608cf72db5432f7142072c3699932c7bb88ab740a0f1",
    "tests/ingestion/test_backfill_maintenance_phase_observation_v73.py":
        "1744faa5fedb092991c2229dffc31de8c45a6e19c3ad614bf4d1c654f6df89fe",
}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--qualification-root", type=Path, default=ROOT)
    args = parser.parse_args()
    qualification_root = args.qualification_root.resolve()
    if os.environ.get("ASTRA_INGESTION_POSTGRES_TEST_URL") != EXPECTED_TARGET:
        raise SystemExit("Only the established disposable loopback PostgreSQL target is allowed")
    if os.environ.get("GITHUB_WORKFLOW") != "ASTRA ingestion qualification":
        raise SystemExit("The dedicated qualification admission context must be explicit")
    for relative, expected in PINS.items():
        for source in (ROOT, qualification_root):
            if sha256((source / relative).read_bytes()).hexdigest() != expected:
                raise SystemExit(f"Frozen qualification input differs: {relative}")
    sys.path[:0] = [str(qualification_root / "tests/ingestion"), str(qualification_root)]
    target = importlib.import_module("test_backfill_maintenance_phase_observation_v73")
    suite = unittest.defaultTestLoader.loadTestsFromModule(target)
    started = perf_counter()
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    elapsed = perf_counter() - started
    passed = result.wasSuccessful() and not result.skipped and result.testsRun == 17
    receipt = {
        "schema": "astra.maintenance-phase-observation-independent-test-result/1",
        "reviewer": "/root/relay_v3_review",
        "recorded_at": datetime.now(timezone.utc).isoformat(),
        "passed": passed,
        "tests": result.testsRun,
        "errors": len(result.errors),
        "failures": len(result.failures),
        "skipped": len(result.skipped),
        "elapsed_seconds": elapsed,
        "production_calls": 0,
        "remote_mutations": 0,
        "target": "established disposable loopback PostgreSQL fixture",
        "qualification_root": str(qualification_root),
        "workflow_context": "ASTRA ingestion qualification",
        "input_pins": PINS,
        "runner_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "fixture_evidence": target.RESULT,
        "errors_detail": [{"test": str(test), "trace": trace} for test, trace in result.errors],
        "failures_detail": [{"test": str(test), "trace": trace} for test, trace in result.failures],
    }
    output = ROOT / "review/recovery-v73/maintenance_phase_observation_independent_test_result_v73.json"
    with output.open("x") as handle:
        handle.write(json.dumps(receipt, indent=2, default=str) + "\n")
    print(json.dumps({"path": str(output.relative_to(ROOT)),
        "sha256": sha256(output.read_bytes()).hexdigest(), "passed": passed,
        "tests": result.testsRun, "errors": len(result.errors), "failures": len(result.failures),
        "skipped": len(result.skipped), "seconds": elapsed}))
    raise SystemExit(0 if passed else 1)


if __name__ == "__main__":
    main()
