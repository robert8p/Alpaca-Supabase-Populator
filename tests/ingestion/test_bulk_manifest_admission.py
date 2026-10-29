"""Network-free, full-population manifest preflight tests; no job admission."""
from __future__ import annotations

from dataclasses import replace
import unittest
from unittest.mock import patch

from astra_ingestion import bulk_scope as b, bulk_expected as e
from astra_ingestion import bulk_manifest_admission as a


class ManifestAdmissionTests(unittest.TestCase):
    def setUp(self):
        self.company = tuple(f"company-{i:04d}" for i in range(1, 3001))
        self.sessions = tuple(f"2026-08-{i:02d}" for i in range(1, 22)) + tuple(
            f"2026-09-{i:02d}" for i in range(1, 22))
        self.capture = b.RetainedManifest(
            b.CAPTURE_KEY, b.RETAINED_RECEIPT_SHA256, 4136, self.company,
            self.sessions, 16380, tuple(f"preserved-{i}" for i in range(1065)),
            (("REF01",), tuple(f for f in b.FAMILIES if f != "REF01")),
        )
        self.contract_rows, self.keys, self.denominators = [], {}, {}
        for family in b.FAMILIES:
            literal = f"full independently evidenced original unit for {family}"
            body = b.canonical({
                "dependencies": [] if family == "REF01" else ["REF01"],
                "expected_unit": literal,
            })
            contract = b.sha256_text(body)
            self.contract_rows.append({
                "family_id": family, "contract_text": body, "contract_sha256": contract,
            })
            self.keys[family] = (f"{family}-unit-1",)
            self.denominators[family] = self.definition(family)
        self.contract_set = b.sha256_text("\n".join(
            row["family_id"] + ":" + row["contract_sha256"]
            for row in sorted(self.contract_rows, key=lambda x: x["family_id"])
        ))

    def definition(self, family):
        body = next(r for r in self.contract_rows if r["family_id"] == family)
        return e.DenominatorEvidence(
            family, body["contract_sha256"], "explicit",
            b.sha256_text("eligible:" + family),
            b.sha256_text(b.canonical(list(self.keys[family]))),
            self.keys[family], f"full independently evidenced original unit for {family}",
        )

    def planner(self):
        with patch.object(b, "CONTRACT_SET_SHA256", self.contract_set):
            return e.plan_expected_units(self.capture, self.contract_rows, self.denominators)

    def row(self, key):
        return {
            "unit_key": key,
            "source_sha256": b.sha256_text("source:" + key),
            "provenance_sha256": b.sha256_text("provenance:" + key),
            "identity_sha256": b.sha256_text("identity:" + key),
            "point_in_time_sha256": b.sha256_text("PIT:" + key),
        }

    def pins(self, plan, *, observed=None):
        result = {}
        for f in b.FAMILIES:
            rows = [self.row(k) for k in (observed or self.keys)[f]]
            receipt = b.sha256_text(b.canonical([
                [r[field] for field in a._FIELDS] for r in rows
            ]))
            result[f] = a.FamilySourcePin(
                f, self.denominators[f].contract_sha256,
                plan.family(f).manifest_sha256,
                b.sha256_text("snapshot:" + f), receipt,
            )
        return result

    def reader(self, observed=None):
        observed = observed or self.keys

        def read_page(family, after, limit):
            keys = observed[family]
            eligible = [k for k in keys if after is None or k > after]
            page = eligible[:limit]
            return {"rows": [self.row(k) for k in page],
                    "has_more": len(eligible) > len(page)}
        return read_page

    def review(self, plan=None, pins=None, reader=None, **kwargs):
        plan = self.planner() if plan is None else plan
        pins = self.pins(plan) if pins is None else pins
        reader = self.reader() if reader is None else reader
        with patch.object(b, "CONTRACT_SET_SHA256", self.contract_set):
            return a.compile_manifest_preflight(
                self.capture, plan, self.contract_rows, pins, reader, **kwargs)

    def test_all_24_structural_reconciliation_still_cannot_admit_jobs(self):
        result = self.review()
        self.assertEqual(len(result.family_results), 24)
        self.assertEqual(result.status, "INDEPENDENT_REVIEW_REQUIRED")
        self.assertIsNotNone(result.review_fingerprint_sha256)
        self.assertFalse(result.worker_admission_authorized)
        self.assertTrue(all(x.status == "STRUCTURALLY_RECONCILED_REVIEW_REQUIRED"
                            and x.observed_count == 1 and x.missing_count == 0
                            and x.extra_count == 0 for x in result.family_results))
        with self.assertRaises(b.ScopeError):
            self.review(pins=dict(self.pins(self.planner()), D06="not-a-family"))

    def test_missing_denominator_is_never_an_empty_or_accepted_family(self):
        del self.denominators["REF01"]
        p = self.planner()
        called = []
        def reader(f, after, limit):
            called.append(f)
            return self.reader()(f, after, limit)
        pins = self.pins(p)
        result = self.review(plan=p, pins=pins, reader=reader)
        self.assertEqual(result.status, "BLOCKED_INCOMPLETE_FAMILY_EVIDENCE")
        self.assertEqual(result.family_results[0].status, "BLOCKED_EXPECTED_POPULATION")
        self.assertNotIn("REF01", called)
        self.assertIsNone(result.review_fingerprint_sha256)

    def test_missing_proof_and_missing_data_are_distinct(self):
        plan = self.planner()
        pins = self.pins(plan)
        del pins["P01"]
        result = self.review(plan=plan, pins=pins)
        self.assertEqual(result.family_results[1].status, "BLOCKED_MISSING_SOURCE_PIN")
        observed = dict(self.keys, P01=())
        pins = self.pins(plan, observed=observed)
        gap = self.review(plan=plan, pins=pins, reader=self.reader(observed))
        self.assertEqual(gap.family_results[1].status, "BLOCKED_SOURCE_GAPS")
        self.assertEqual(gap.family_results[1].missing_count, 1)
        self.assertEqual(gap.family_results[1].observed_count, 0)

    def test_extra_units_and_mutated_receipts_fail_closed(self):
        p = self.planner()
        observed = dict(self.keys, P01=("P01-unit-1", "P01-unit-extra"))
        pins = self.pins(p, observed=observed)
        gap = self.review(plan=p, pins=pins, reader=self.reader(observed))
        self.assertEqual(gap.family_results[1].extra_count, 1)
        with self.assertRaisesRegex(b.ScopeError, "receipt"):
            self.review(plan=p, pins=self.pins(p), reader=self.reader(observed))

    def test_invalid_contract_snapshot_and_forged_plan_rejected(self):
        p = self.planner()
        pins = self.pins(p)
        pins["P01"] = replace(pins["P01"], contract_sha256="0"*64)
        with self.assertRaisesRegex(b.ScopeError, "source proof"):
            self.review(plan=p, pins=pins)
        fake = replace(p, families=tuple(replace(x, count=999)
                           if x.family == "P01" else x for x in p.families))
        with self.assertRaisesRegex(b.ScopeError, "planner"):
            self.review(plan=fake)

    def test_keyset_pagination_and_metadata_enforcement(self):
        self.keys["P01"] = ("P01-unit-1", "P01-unit-2", "P01-unit-3")
        self.denominators["P01"] = self.definition("P01")
        p = self.planner()
        result = self.review(plan=p, pins=self.pins(p), page_limit=1)
        self.assertEqual(result.family_results[1].observed_count, 3)
        for limit in (0, 257, True):
            with self.assertRaises(b.ScopeError):
                self.review(plan=p, pins=self.pins(p), page_limit=limit)
        def broken(f, after, limit):
            reply = self.reader()(f, after, limit)
            if f == "P01" and reply["rows"]:
                reply["rows"][0]["point_in_time_sha256"] = "missing"
            return reply
        with self.assertRaisesRegex(b.ScopeError, "evidence hash"):
            self.review(plan=p, pins=self.pins(p), reader=broken)


if __name__ == "__main__":
    unittest.main()
