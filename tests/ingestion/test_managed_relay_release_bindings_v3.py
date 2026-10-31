"""Active-release integrity checks for the immutable, separately approved relay.

Historical pre-installation tests keep their original inputs and receipts. These
checks bind the promoted release to those artifacts without pretending that the
active worker is still the pre-installation baseline.
"""
from hashlib import sha256
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[2]
PHASE_TESTS = {
    "tests/ingestion/test_backfill_massive_relay_integration_review_v2.py",
    "tests/ingestion/test_backfill_massive_relay_postgres_v2.py",
}
BASELINE = "review/massive-relay-v3/activation/baseline_backfill_worker_v2.py"


class ManagedRelayReleaseBindingsTests(unittest.TestCase):
    def assert_pin(self, path, pin):
        data = (ROOT / path).read_bytes()
        self.assertEqual(len(data), pin["bytes"], path)
        self.assertEqual(sha256(data).hexdigest(), pin["sha256"], path)

    def test_all_frozen_v3_review_payloads_and_scope_remain_exact(self):
        manifest = json.loads((ROOT / "evidence/replacement-managed-relay-review-manifest-v3.json").read_text())
        self.assertEqual(len(manifest["files"]), 15)
        for pin in manifest["files"]:
            with self.subTest(path=pin["path"]):
                self.assert_pin(pin["path"], pin)
        scope = json.loads((ROOT / "evidence/replacement-managed-relay-review-scope-v3.json").read_text())
        digest = sha256(json.dumps(scope, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode()).hexdigest()
        self.assertEqual(digest, manifest["scope_sha256"])
        self.assertEqual(scope["review_id"], manifest["review_id"])

    def test_all_original_v2_payloads_remain_available_with_explicit_test_phase_mapping(self):
        manifest = json.loads((ROOT / "evidence/replacement-managed-relay-review-manifest-v2.json").read_text())
        self.assertEqual(len(manifest["files"]), 19)
        mapped = set()
        for pin in manifest["files"]:
            path = pin["path"]
            if path in PHASE_TESTS:
                self.assertTrue((ROOT / path).is_file())
                mapped.add(path)
                path = "review/massive-relay-v2/candidates/" + path
            with self.subTest(path=path):
                self.assert_pin(path, pin)
        self.assertEqual(mapped, PHASE_TESTS)

    def test_promoted_runtime_matches_approved_proposal_and_archived_baseline(self):
        manifest = json.loads((ROOT / "evidence/replacement-managed-relay-review-manifest-v3.json").read_text())
        for pin in manifest["unchanged_runtime_inputs"]:
            path = BASELINE if pin["role"] == "existing_worker_base" else pin["path"]
            with self.subTest(path=path):
                self.assert_pin(path, pin)
        self.assertEqual(
            (ROOT / "astra_ingestion/backfill_worker_v2.py").read_bytes(),
            (ROOT / "review/massive-relay-v2/backfill_worker_v2.py.proposed").read_bytes(),
        )


if __name__ == "__main__":
    unittest.main()
