from __future__ import annotations
import copy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
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


    def evidence_fixture(self):
        """Synthetic complete capture, never production data or a coverage claim."""
        rows = []

        def add(kind, key, value):
            body = value if isinstance(value, str) else json.dumps(value, sort_keys=True)
            rows.append({"kind": kind, "evidence_key": key,
                         "source_text": body, "source_sha256": b.sha256_text(body)})

        add("scope", "scope:one", {})
        add("cohort", "cohort:one", {})
        add("membership", "membership:one", {})
        for key in ("23872", "24407"):
            add("acceptance_event", key, {})
        for rank in range(1, 3001):
            add("company", f"synthetic-company-{rank:04d}",
                {"company_id": f"synthetic-company-{rank:04d}",
                 "selection_order": rank, "membership_accepted": True,
                 "exact_global_rank_certified": False,
                 "financial_capitalization_qualified": False,
                 "full_period_instrument_coverage_accepted": False})
        for contract in self.rows():
            add("contract", contract["family_id"], contract["contract_text"])
        day = datetime(2026, 8, 3, tzinfo=timezone.utc)
        end = datetime(2026, 9, 30, tzinfo=timezone.utc)
        while day <= end:
            date = day.date().isoformat()
            if day.weekday() < 5 and date != "2026-09-07":
                add("calendar", date, {"session_date": date,
                                       "regular_scheduled_minutes": 390})
            day += timedelta(days=1)
        for number in range(1, 1066):
            key = f"synthetic-preserved-{number:04d}"
            add("preservation", key, {"relation_name": key})
        return sorted(rows, key=lambda r: (r["kind"], r["evidence_key"]))

    @staticmethod
    def reader_from_rows(rows):
        def reader(after, limit):
            rest = [r for r in rows if after is None
                    or (r["kind"], r["evidence_key"]) > after]
            return {"rows": rest[:limit], "has_more": len(rest) > limit}
        return reader

    @staticmethod
    def fixture_receipt():
        return {"capture_key": b.CAPTURE_KEY,
                "evidence_sha256": b.RETAINED_RECEIPT_SHA256,
                "evidence_rows": 4136, "state": "CAPTURED_NOT_ADMITTED",
                "provider_requests": 0, "incremental_cost_microusd": 0}

    def test_complete_keyset_retained_reader(self):
        rows = self.evidence_fixture()
        self.assertEqual(len(rows), 4136)
        with self.pin(self.rows()):
            result = b.read_retained_capture(self.fixture_receipt(),
                                             self.reader_from_rows(rows),
                                             page_limit=128)
        self.assertEqual(result.checked_source_rows, 4136)
        self.assertEqual(len(result.company_ids_by_rank), 3000)
        self.assertEqual(result.company_ids_by_rank[0], "synthetic-company-0001")
        self.assertEqual(len(result.sessions), 42)
        self.assertEqual(result.scheduled_minutes, 16380)
        self.assertEqual(len(result.preserved_d06_relations), 1065)
        self.assertEqual(sum(map(len, result.family_dependency_waves)), 24)
        self.assertFalse(result.aggregate_receipt_independently_verified)
        self.assertFalse(result.research_dataset_coverage_certified)

    def test_retained_reader_rejects_missing_tampered_duplicate_and_short_pages(self):
        rows = self.evidence_fixture()
        cases = {}
        cases["missing"] = rows[:-1]
        changed = copy.deepcopy(rows)
        changed[0]["source_text"] += " "
        cases["changed_bytes"] = changed
        out_of_order = list(rows)
        out_of_order[0], out_of_order[1] = out_of_order[1], out_of_order[0]
        def bad_order(after, limit):
            if after is None:
                return {"rows": out_of_order[:limit], "has_more": True}
            return self.reader_from_rows(out_of_order)(after, limit)
        def duplicate_page(after, limit):
            if after is None:
                return {"rows": rows[:limit-1] + [rows[limit-2]], "has_more": True}
            return self.reader_from_rows(rows)(after, limit)
        with self.pin(self.rows()):
            with self.assertRaisesRegex(b.ScopeError, "duplicate or out-of-order"):
                b.read_retained_capture(self.fixture_receipt(), duplicate_page)
            for case, evidence in cases.items():
                with self.subTest(case=case), self.assertRaises(b.ScopeError):
                    b.read_retained_capture(self.fixture_receipt(),
                                            self.reader_from_rows(evidence))
            with self.assertRaisesRegex(b.ScopeError, "out-of-order"):
                b.read_retained_capture(self.fixture_receipt(), bad_order)
            with self.assertRaisesRegex(b.ScopeError, "incomplete"):
                b.read_retained_capture(self.fixture_receipt(),
                    lambda after, limit: {"rows": rows[:20], "has_more": False})

    def test_retained_reader_rejects_false_receipt_and_qualification_drift(self):
        rows = self.evidence_fixture()
        bad_receipt = self.fixture_receipt()
        bad_receipt["incremental_cost_microusd"] = 1
        with self.assertRaisesRegex(b.ScopeError, "receipt"):
            b.read_retained_capture(bad_receipt, self.reader_from_rows(rows))
        changed = copy.deepcopy(rows)
        index = next(i for i,r in enumerate(changed) if r["kind"] == "company")
        obj = json.loads(changed[index]["source_text"])
        obj["exact_global_rank_certified"] = True
        changed[index]["source_text"] = json.dumps(obj, sort_keys=True)
        changed[index]["source_sha256"] = b.sha256_text(changed[index]["source_text"])
        with self.pin(self.rows()), self.assertRaisesRegex(b.ScopeError, "qualification"):
            b.read_retained_capture(self.fixture_receipt(), self.reader_from_rows(changed))
        with self.assertRaisesRegex(b.ScopeError, "page limit"):
            b.read_retained_capture(self.fixture_receipt(), self.reader_from_rows(rows),
                                    page_limit=0)
        with self.assertRaisesRegex(b.ScopeError, "has_more"):
            b.read_retained_capture(self.fixture_receipt(),
                                    lambda after, limit: {"rows": [], "has_more": "unknown"})

if __name__ == "__main__": unittest.main()
