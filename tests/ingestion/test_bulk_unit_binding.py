"""Network-free source-to-unit-set candidate checks; no admission or SQL writes."""
from __future__ import annotations
from dataclasses import replace
import unittest

from astra_ingestion.bulk_expected import (
    DenominatorEvidence, ExpectedUnitPlan, FamilyExpectedUnits,
)
from astra_ingestion.bulk_manifest_admission import FamilySourcePin
from astra_ingestion.bulk_scope import (
    CAPTURE_KEY, RETAINED_RECEIPT_SHA256, ScopeError, canonical, sha256_text,
)
from astra_ingestion.bulk_unit_binding import (
    build_reviewed_unit_candidate, pg_jsonb_reviewed_unit_sha256,
)


class ReviewedUnitCandidateTests(unittest.TestCase):
    def setUp(self):
        self.family = "REF01"
        self.keys = ("REF01:a", "REF01:b")
        self.contract = "c" * 64
        self.manifest = "d" * 64
        self.definition = DenominatorEvidence(
            self.family, self.contract, "explicit", "1"*64,
            sha256_text(canonical(list(self.keys))), self.keys,
            "full original effective dated listing episodes")
        self.plan = ExpectedUnitPlan(
            CAPTURE_KEY, RETAINED_RECEIPT_SHA256,
            (FamilyExpectedUnits(
                self.family, "READY_FOR_STAGING", 2, self.manifest,
                "fixture only", "explicit"),),
            {self.family: self.definition}, (), ())
        self.rows = [self.row(k) for k in self.keys]
        self.pin = FamilySourcePin(
            self.family, self.contract, self.manifest, "9"*64,
            sha256_text(canonical([
                [r[f] for f in (
                    "unit_key","source_sha256","provenance_sha256",
                    "identity_sha256","point_in_time_sha256")]
                for r in self.rows
            ])))

    @staticmethod
    def row(key):
        return {
            "unit_key": key,
            "source_sha256": sha256_text("source:" + key),
            "provenance_sha256": sha256_text("provenance:" + key),
            "identity_sha256": sha256_text("identity:" + key),
            "point_in_time_sha256": sha256_text("PIT:" + key),
        }

    def reader(self, rows=None):
        rows = self.rows if rows is None else rows
        def read_page(family, after, limit):
            self.assertEqual(family,self.family)
            eligible = [r for r in rows if after is None or r["unit_key"] > after]
            batch = eligible[:limit]
            return {"rows":batch,"has_more":len(eligible)>len(batch)}
        return read_page

    def make(self,*,pin=None,read=None,plan=None,limit=1):
        return build_reviewed_unit_candidate(
            plan or self.plan, self.family, pin or self.pin,
            read or self.reader(), page_limit=limit)

    def test_complete_source_metadata_has_nonadmitting_sql_set_digest(self):
        candidate=self.make()
        self.assertEqual(candidate.family,"REF01")
        self.assertEqual(candidate.unit_count,2)
        self.assertEqual(candidate.source_observation_sha256,self.pin.source_receipt_sha256)
        self.assertEqual(candidate.exact_unit_set_sha256,
                         pg_jsonb_reviewed_unit_sha256(candidate.rows))
        self.assertEqual(tuple(r[0] for r in candidate.rows),self.keys)
        self.assertFalse(candidate.worker_admission_authorized)

    def test_source_drift_and_wrong_contract_are_rejected(self):
        altered=[dict(r) for r in self.rows]
        altered[1]["source_sha256"]="a"*64
        with self.assertRaisesRegex(ScopeError,"receipt"):
            self.make(read=self.reader(altered))
        with self.assertRaisesRegex(ScopeError,"contract"):
            self.make(pin=replace(self.pin,contract_sha256="2"*64))
        with self.assertRaisesRegex(ScopeError,"snapshot"):
            self.make(pin=replace(self.pin,expected_manifest_sha256="8"*64))

    def test_missing_extra_and_malformed_pit_fail_closed(self):
        with self.assertRaisesRegex(ScopeError,"expected population"):
            self.make(read=self.reader(self.rows[:1]))
        with self.assertRaisesRegex(ScopeError,"expected population"):
            self.make(read=self.reader(self.rows+[self.row("REF01:z")]))
        corrupted=[dict(r) for r in self.rows]
        corrupted[1]["point_in_time_sha256"]="unverified"
        with self.assertRaisesRegex(ScopeError,"unpinned"):
            self.make(read=self.reader(corrupted))
        with self.assertRaisesRegex(ScopeError,"bounded family/source plan"):
            self.make(limit=0)

    def test_nonascii_and_malformed_order_cannot_silently_change_jsonb_digest(self):
        good=tuple(tuple(self.rows[i][f] for f in (
            "unit_key","source_sha256","provenance_sha256",
            "identity_sha256","point_in_time_sha256")) for i in range(2))
        with self.assertRaisesRegex(ScopeError,"unordered"):
            pg_jsonb_reviewed_unit_sha256(good[::-1])
        with self.assertRaisesRegex(ScopeError,"noncanonical"):
            pg_jsonb_reviewed_unit_sha256((("REF01:🌍",)+good[0][1:],))
        with self.assertRaisesRegex(ScopeError,"witness"):
            pg_jsonb_reviewed_unit_sha256((("REF01:a","not-a-digest"),))


if __name__=="__main__":
    unittest.main()
