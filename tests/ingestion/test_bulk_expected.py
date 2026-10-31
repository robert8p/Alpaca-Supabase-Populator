"""No provider or database access: synthetic readiness/expected-unit gate tests."""
from __future__ import annotations
from dataclasses import replace
import unittest
from unittest.mock import patch

from astra_ingestion import bulk_scope as b
from astra_ingestion import bulk_expected as e


class ExpectedUnitTests(unittest.TestCase):
    def setUp(self):
        self.co = tuple(f"company-{i:04d}" for i in range(1, 3001))
        self.sessions = tuple(f"2026-08-{i:02d}" for i in range(1, 22)) + tuple(f"2026-09-{i:02d}" for i in range(1, 22))
        self.cap = b.RetainedManifest(b.CAPTURE_KEY, b.RETAINED_RECEIPT_SHA256, 4136,
            self.co, self.sessions, 16380, tuple(f"d06-{i}" for i in range(1065)),
            (("REF01",), tuple(f for f in b.FAMILIES if f != "REF01")))
        self.rows = []
        self.hashes = {}
        for f in b.FAMILIES:
            basis = "session" if f in b.SHARED_FAMILIES else "company"
            body = b.canonical({"dependencies": [] if f=="REF01" else ["REF01"],
                                "expected_unit_basis": basis})
            h = b.sha256_text(body)
            self.rows.append({"family_id": f, "contract_text": body, "contract_sha256": h})
            self.hashes[f] = h
        self.pinned_set = b.sha256_text("\n".join(f+":"+self.hashes[f] for f in sorted(self.hashes)))

    def defn(self, f, basis="company"):
        keys = [f"company:{x}" for x in self.co] if basis == "company" else [f"session:{x}" for x in self.sessions]
        return e.DenominatorEvidence(f, self.hashes[f], basis, "a"*64,
                                     b.sha256_text(b.canonical(keys)))

    def planner(self, ev):
        with patch.object(b, "CONTRACT_SET_SHA256", self.pinned_set):
            return e.plan_expected_units(self.cap, self.rows, ev)

    def test_missing_does_not_fake_denominator_or_qualify_all(self):
        result = self.planner({})
        self.assertEqual(len(result.families), 24)
        self.assertTrue(all(x.status == "UNKNOWN_DENOMINATOR" and x.count is None for x in result.families))
        with self.assertRaisesRegex(b.ScopeError, "cannot be paged"):
            result.page("P01")

    def test_company_candidates_paged_without_claiming_data_acceptance(self):
        result = self.planner({"P01": self.defn("P01")})
        family = result.family("P01")
        self.assertEqual(family.count, 3000)
        self.assertEqual(family.status, "READY_FOR_STAGING")
        self.assertIn("admission remain open", family.reason)
        with self.assertRaises(TypeError):
            result.source_bindings["P01"] = self.defn("P01")
        first, next_idx = result.page("P01", limit=128)
        self.assertEqual(len(first), 128)
        self.assertEqual(next_idx, 128)
        last, next_idx = result.page("P01", after_index=2990, limit=128)
        self.assertEqual(len(last), 10)
        self.assertIsNone(next_idx)
        self.assertEqual(first[0], "company:company-0001")

    def test_shared_family_never_multiplied_by_3000(self):
        with self.assertRaisesRegex(b.ScopeError, "shared family"):
            self.planner({"CTX06": self.defn("CTX06", "company")})
        result = self.planner({"CTX06": self.defn("CTX06", "session")})
        self.assertEqual(result.family("CTX06").count, 42)
        self.assertEqual(result.page("CTX06", after_index=41), (("session:2026-09-21",), None))

    def test_no_implicit_contract_basis_or_substitute(self):
        # Old/unknown contract fields are never silently interpreted as company.
        self.rows[1]["contract_text"] = b.canonical({"dependencies": ["REF01"]})
        self.rows[1]["contract_sha256"] = b.sha256_text(self.rows[1]["contract_text"])
        self.hashes["P01"] = self.rows[1]["contract_sha256"]
        self.pinned_set = b.sha256_text("\n".join(f+":"+self.hashes[f] for f in sorted(self.hashes)))
        result = self.planner({"P01": self.defn("P01")})
        self.assertEqual(result.family("P01").status, "UNKNOWN_DENOMINATOR")

    def test_identity_contract_and_key_hash_fail_closed(self):
        good = self.defn("P01")
        for bad in [replace(good, contract_sha256="d"*64),
                    replace(good, unit_keys_sha256="e"*64),
                    replace(good, eligibility_sha256=""),
                    replace(good, explicit_unit_keys=("rogue",))]:
            with self.subTest(bad=bad), self.assertRaises(b.ScopeError):
                self.planner({"P01": bad})
        with self.assertRaises(b.ScopeError):
            self.planner({"D06": self.defn("P01")})

    def test_explicit_keys_are_bounded_sorted_and_fenced_to_source(self):
        f = "P01"
        self.rows[1]["contract_text"] = b.canonical({"dependencies":["REF01"], "expected_unit_basis":"explicit"})
        self.rows[1]["contract_sha256"] = b.sha256_text(self.rows[1]["contract_text"])
        self.hashes[f] = self.rows[1]["contract_sha256"]
        self.pinned_set = b.sha256_text("\n".join(k+":"+self.hashes[k] for k in sorted(self.hashes)))
        ev = e.DenominatorEvidence(f,self.hashes[f],"explicit","f"*64,
                b.sha256_text(b.canonical(["event:one","event:two"])),("event:one","event:two"))
        result = self.planner({f:ev})
        self.assertEqual(result.page(f), (("event:one","event:two"),None))
        with self.assertRaises(b.ScopeError):
            self.planner({f:replace(ev, explicit_unit_keys=("event:two","event:one"))})

    def test_original_24_contract_shape_requires_literal_bound_explicit_population(self):
        # Real retained contracts use descriptive 'expected_unit' and do not
        # provide a blanket company/session enumeration basis. A complete,
        # externally pinned key list is the only safe staging alternative.
        f = "P01"
        literal = "eligible security-session-minute and required bar field"
        self.rows[1]["contract_text"] = b.canonical({
            "dependencies": ["REF01"], "expected_unit": literal,
        })
        self.rows[1]["contract_sha256"] = b.sha256_text(self.rows[1]["contract_text"])
        self.hashes[f] = self.rows[1]["contract_sha256"]
        self.pinned_set = b.sha256_text("\n".join(k+":"+self.hashes[k] for k in sorted(self.hashes)))
        self.assertEqual(self.planner({f: self.defn(f)}).family(f).status,
                         "UNKNOWN_DENOMINATOR")
        keys = ("security:synthetic/session:2026-08-03/minute:09:30/field:close",
                "security:synthetic/session:2026-08-03/minute:09:31/field:close")
        ev = e.DenominatorEvidence(
            f, self.hashes[f], "explicit", "f"*64,
            b.sha256_text(b.canonical(keys)), keys, literal,
        )
        planned = self.planner({f: ev})
        self.assertEqual(planned.family(f).status, "READY_FOR_STAGING")
        self.assertEqual(planned.page(f), (keys, None))
        with self.assertRaisesRegex(b.ScopeError, "original expected-unit literal"):
            self.planner({f: replace(ev, original_expected_unit="unrelated unit")})
        self.assertEqual(
            self.planner({f: replace(ev, original_expected_unit=None)}).family(f).status,
            "UNKNOWN_DENOMINATOR",
        )
        self.assertEqual(planned.family("REF01").status, "UNKNOWN_DENOMINATOR")

    def test_page_boundary_and_retained_capture_invariants(self):
        p = self.planner({"P01":self.defn("P01")})
        for invalid in (0, 257, True):
            with self.assertRaises(b.ScopeError): p.page("P01",limit=invalid)
        for invalid in (-1, 3001, True):
            with self.assertRaises(b.ScopeError): p.page("P01",after_index=invalid)
        with self.assertRaises(b.ScopeError): p.page("D06")
        with self.assertRaises(b.ScopeError):
            e.plan_expected_units(replace(self.cap,checked_source_rows=4135), [], {})

if __name__ == "__main__": unittest.main()