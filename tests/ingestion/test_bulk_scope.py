from __future__ import annotations
import copy
from dataclasses import replace
from datetime import datetime, timezone
import json
import unittest
from unittest.mock import patch

from astra_ingestion import bulk_scope as b


class BulkScopeTests(unittest.TestCase):
    def rows(self):
        rows = []
        for family in b.FAMILIES:
            text = json.dumps({"dependencies": [] if family == "REF01" else ["REF01"], "unit_type": family})
            rows.append({"family_id": family, "contract_text": text,
                         "contract_sha256": b.sha256_text(text)})
        return rows

    def pin(self, rows):
        value = b.sha256_text("\n".join(r["family_id"] + ":" + r["contract_sha256"]
                                      for r in sorted(rows, key=lambda r: r["family_id"])))
        return patch.object(b, "CONTRACT_SET_SHA256", value)

    def test_all_24_exact_text_and_dependency_waves(self):
        rows = self.rows()
        with self.pin(rows):
            contracts = b.read_contracts(rows)
        waves = b.dependency_waves(contracts)
        self.assertEqual(waves[0], ("REF01",))
        self.assertEqual(sum(map(len, waves)), 24)

    def test_missing_duplicate_extra_and_d06_rejected(self):
        for kind in ("missing", "duplicate", "extra", "d06"):
            rows = self.rows()
            if kind == "missing": rows.pop()
            if kind == "extra": rows.append(copy.deepcopy(rows[0]))
            if kind == "duplicate": rows[-1] = copy.deepcopy(rows[0])
            if kind == "d06": rows[-1]["family_id"] = "D06"
            with self.subTest(kind=kind), self.assertRaises(b.ScopeError):
                b.read_contracts(rows)

    def test_changed_bytes_even_equivalent_json_are_not_original_receipt(self):
        rows = self.rows()
        with self.pin(rows):
            rows[0]["contract_text"] += " "
            with self.assertRaisesRegex(b.ScopeError, "original contract bytes"):
                b.read_contracts(rows)

    def test_rehashed_changed_contract_does_not_bypass_original_set_pin(self):
        rows = self.rows()
        with self.pin(rows):
            rows[0]["contract_text"] += " "
            rows[0]["contract_sha256"] = b.sha256_text(rows[0]["contract_text"])
            with self.assertRaisesRegex(b.ScopeError, "set changed"):
                b.read_contracts(rows)

    def test_duplicate_json_keys_and_invalid_dependency_fail(self):
        for text in ('{"dependencies":[],"dependencies":[]}', '{"dependencies":["UNKNOWN"]}',
                     '{"dependencies":["REF01","REF01"]}', '{"dependencies":[5]}',
                     '{"dependencies":[],"x":NaN}', '[]'):
            rows = self.rows()
            rows[0].update(contract_text=text, contract_sha256=b.sha256_text(text))
            with self.pin(rows), self.subTest(text=text), self.assertRaises(b.ScopeError):
                b.read_contracts(rows)

    def test_cycles_fail_instead_of_waiting_forever(self):
        contracts = {f: {"dependencies": []} for f in b.FAMILIES}
        contracts["P01"]["dependencies"] = ["D01"]
        contracts["D01"]["dependencies"] = ["P01"]
        with self.assertRaisesRegex(b.ScopeError, "cyclic"):
            b.dependency_waves(contracts)

    def proposal(self, **changes):
        values = dict(manifest_sha256="a"*64, family="P01", unit_key="company:1/session:2026-08-03",
                      mode="retained_source_reuse", source_receipt_sha256="b"*64,
                      original_deadline="2026-10-29T10:00:00Z", max_requests=0, max_records=390)
        values.update(changes)
        return b.BoundedPartition(**values)

    def test_stable_key_includes_scope_source_deadline_and_bounds(self):
        p = self.proposal()
        self.assertEqual(p.idempotency_key, self.proposal().idempotency_key)
        for changes in (dict(manifest_sha256="c"*64), dict(source_receipt_sha256="c"*64),
                        dict(max_records=391), dict(original_deadline="2026-10-29T10:01:00Z")):
            self.assertNotEqual(p.idempotency_key, self.proposal(**changes).idempotency_key)

    def test_no_negative_boolean_unbounded_or_paid_accounting(self):
        for changes in (dict(max_records=-1), dict(max_requests=True), dict(max_records=0),
                        dict(max_records=1_000_001), dict(incremental_cost_microusd=1),
                        dict(max_requests=1), dict(family="D06"), dict(mode="other"),
                        dict(manifest_sha256=""), dict(unit_key=""), dict(max_requests=201)):
            with self.subTest(changes=changes), self.assertRaises(b.ScopeError):
                self.proposal(**changes)

    def test_provider_accounting_separate_from_reuse(self):
        p = self.proposal(mode="provider_acquisition", max_requests=2)
        self.assertEqual(p.max_requests, 2)
        with self.assertRaises(b.ScopeError):
            self.proposal(mode="provider_acquisition", max_requests=0)

    def test_original_deadline_not_reset_at_retry(self):
        p = self.proposal()
        p.require_current(datetime(2026,10,29,9,59,tzinfo=timezone.utc))
        with self.assertRaisesRegex(b.ScopeError, "expired"):
            p.require_current(datetime(2026,10,29,10,0,tzinfo=timezone.utc))
        with self.assertRaises(b.ScopeError):
            p.require_current(datetime(2026,10,29,9,59))
        # No programme expiry: jobs remain subject to their own finite original deadline.
        future = self.proposal(original_deadline="2027-01-15T03:15:00Z")
        future.require_current(datetime(2027, 1, 15, 3, 14, tzinfo=timezone.utc))
        with self.assertRaisesRegex(b.ScopeError, "expired"):
            future.require_current(datetime(2027, 1, 15, 3, 15, tzinfo=timezone.utc))
        with self.assertRaisesRegex(b.ScopeError, "deadline must specify UTC"):
            self.proposal(original_deadline="2027-01-15T03:15:00")
        self.assertNotEqual(p.idempotency_key, future.idempotency_key)

    def test_unknown_absent_unavailable_and_zero_not_certified(self):
        self.assertEqual(b.coverage_state(None, 100), "UNKNOWN_DENOMINATOR")
        self.assertEqual(b.coverage_state(100, 99), "INCOMPLETE")
        self.assertEqual(b.coverage_state(100, 99, 1), "INCOMPLETE_UNAVAILABLE")
        self.assertEqual(b.coverage_state(100, 100), "COUNT_RECONCILED_NOT_CERTIFIED")
        self.assertEqual(b.coverage_state(0, 0), "COUNT_RECONCILED_NOT_CERTIFIED")
        with self.assertRaises(b.ScopeError): b.coverage_state(1, 2)
        with self.assertRaises(b.ScopeError): b.coverage_state(True, 0)

    def test_shared_market_data_not_multiplied_by_company_count(self):
        self.assertTrue({"CTX06", "CTX07", "CTX14"} <= b.SHARED_FAMILIES)
        self.assertNotIn("P01", b.SHARED_FAMILIES)
        self.assertEqual(len(b.FAMILIES), 24)
        self.assertNotIn("D06", b.FAMILIES)

if __name__ == "__main__": unittest.main()
